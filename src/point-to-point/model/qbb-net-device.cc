/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
* Copyright (c) 2006 Georgia Tech Research Corporation, INRIA
*
* This program is free software; you can redistribute it and/or modify
* it under the terms of the GNU General Public License version 2 as
* published by the Free Software Foundation;
*
* This program is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
* GNU General Public License for more details.
*
* You should have received a copy of the GNU General Public License
* along with this program; if not, write to the Free Software
* Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
*
* Author: Yuliang Li <yuliangli@g.harvard.com>
* Modified (by Vamsi Addanki) to also serve TCP/IP traffic.
*/

#define __STDC_LIMIT_MACROS 1
#include <stdint.h>
#include <stdio.h>
#include <unistd.h>
#include <fcntl.h>
#include "ns3/qbb-net-device.h"
#include "ns3/log.h"
#include "ns3/boolean.h"
#include "ns3/uinteger.h"
#include "ns3/double.h"
#include "ns3/data-rate.h"
#include "ns3/object-vector.h"
#include "ns3/pause-header.h"
#include "ns3/drop-tail-queue.h"
#include "ns3/assert.h"
#include "ns3/ipv4.h"
#include "ns3/ipv4-header.h"
#include "ns3/simulator.h"
#include "ns3/point-to-point-channel.h"
#include "ns3/qbb-channel.h"
#include "ns3/random-variable.h"
#include "ns3/qbb-header.h"
#include "ns3/error-model.h"
#include "ns3/cn-header.h"
#include "ns3/ppp-header.h"
#include "ns3/udp-header.h"
#include "ns3/tcp-header.h"
#include "ns3/seq-ts-header.h"
#include "ns3/pointer.h"
#include "ns3/custom-header.h"
#include "ns3/rdma-tag.h"
#include "ns3/interface-tag.h"
#include "ns3/unsched-tag.h"
#include "ns3/node-list.h"
#include "ns3/switch-node.h"


#include <iostream>
#include <limits>
#include <cmath>
#include <iomanip>
#include <fstream>
#include <deque>
#include <set>
#include "ns3/rdma-driver.h"
#include "ns3/mixed-granularity.h"
#include "qbb-net-device.h"
// Mixed granularity is selected per process through the environment.

bool allSteadyStateReached=false;
bool flag_steady =true;// 刚刚/第一次进入稳态
bool flag_read_SwitchStats = true;
int steady_state_count = 0;  // 稳态次数计数器

bool flag_ENABLE_JUMP_TRANSITION = ns3::IsMixedGranularityEnabled();

NS_LOG_COMPONENT_DEFINE("QbbNetDevice");

namespace ns3 {

namespace {
using WideUInt = unsigned __int128;
const size_t steadyWindowSamples = 10;

struct JumpFlow {
    Ptr<RdmaQueuePair> qp;
    std::string id;
    uint64_t sourceNext = 0;
    uint64_t remaining = 0;
    uint64_t inFlight = 0;
    uint64_t reserve = 0;
    uint64_t skipLimit = 0;
    uint64_t horizonNs = 0;
    uint64_t payloadNumerator = 0;
    uint64_t elapsedDenominator = 0;
    uint64_t packetPeriodNs = 0;
    uint64_t skipBytes = 0;
    uint32_t mtu = 0;
    uint32_t wireBytes = 0;
};

struct JumpPlan {
    std::vector<JumpFlow> flows;
    uint64_t durationNs = 0;
    uint64_t originalHorizonNs = 0;
    uint64_t commonPacketTickNs = 0;
    bool packetTimeAligned = false;
    std::string alignmentFallback;
    bool ready = false;
    bool blocked = false;
};

JumpPlan jumpPlan;
int pendingJumpToken = 0;
std::set<std::string> reportedJumpGuards;
uint32_t largestObservedFrame = 0;
using BufferKey = std::pair<uint32_t, uint32_t>;
using BufferSnapshot = std::map<BufferKey, uint64_t>;
std::deque<BufferSnapshot> bufferHistory;
uint64_t lastBufferSampleNs = 0;
bool bufferSampleInitialized = false;
bool bufferStationaryCacheValid = false;
bool bufferStationaryCacheResult = false;

WideUInt GreatestCommonDivisor(WideUInt a, WideUInt b) {
    while (b) { const WideUInt remainder = a % b; a = b; b = remainder; }
    return a;
}

std::string WideIntegerString(WideUInt value) {
    if (!value) return "0";
    std::string result;
    while (value) { result.push_back('0' + static_cast<unsigned>(value % 10)); value /= 10; }
    std::reverse(result.begin(), result.end());
    return result;
}

std::ofstream& FlowStatisticsFile() {
    static std::ofstream output(GetSimulationOutputPath("flow_stats.txt"),
                                isFirstOpen ? std::ios::out : std::ios::app);
    if (!output) throw std::runtime_error("Unable to write flow statistics");
    isFirstOpen = false;
    return output;
}

flow_acc::SamplingPolicy SamplingPolicy() {
    return flow_acc::SamplingPolicy(MONITOR_PERIOD, steadyWindowSamples, 1);
}

void JumpGuard(const std::string& reason, const std::string& flow = "") {
    jumpPlan.blocked = true;
    const std::string key = reason + ":" + flow;
    if (!reportedJumpGuards.insert(key).second) return;
    std::ofstream output(GetSimulationOutputPath("jump_events.jsonl"), std::ios::app);
    output << "{\"event\":\"jump_deferred\",\"time_ns\":" << Simulator::Now().GetNanoSeconds()
           << ",\"reason\":\"" << reason << "\",\"flow\":\"" << flow << "\"}" << std::endl;
    if (!output) throw std::runtime_error("Unable to write jump guard telemetry");
}

void SampleBuffers(uint64_t now) {
    if (bufferSampleInitialized && now >= lastBufferSampleNs && now - lastBufferSampleNs < MONITOR_PERIOD)
        return;
    BufferSnapshot snapshot;
    for (auto it = NodeList::Begin(); it != NodeList::End(); ++it) {
        Ptr<SwitchNode> sw = DynamicCast<SwitchNode>(*it);
        if (!sw) continue;
        snapshot[{sw->GetId(), std::numeric_limits<uint32_t>::max()}] = sw->m_mmu->totalUsed;
        for (uint32_t index = 0; index < sw->GetNDevices(); ++index) {
            auto device = DynamicCast<QbbNetDevice>(sw->GetDevice(index));
            if (device && device->GetQueue())
                snapshot[{sw->GetId(), index}] = device->GetQueue()->GetNBytesTotal();
        }
    }
    bufferHistory.push_back(std::move(snapshot));
    if (bufferHistory.size() > steadyWindowSamples + 1) bufferHistory.pop_front();
    lastBufferSampleNs = now;
    bufferSampleInitialized = true;
    bufferStationaryCacheValid = false;
}

bool BuffersAreStationary() {
    if (bufferStationaryCacheValid) {
        if (!bufferStationaryCacheResult) jumpPlan.blocked = true;
        return bufferStationaryCacheResult;
    }
    bufferStationaryCacheValid = true;
    bufferStationaryCacheResult = false;
    if (bufferHistory.size() < steadyWindowSamples + 1 || !largestObservedFrame) {
        JumpGuard("buffer_history_warming");
        return false;
    }
    // One real frame is the discrete queue-observation uncertainty. A growing
    // or draining queue is not a stationary network, even at a constant rate.
    for (const auto& resource : bufferHistory.front()) {
        uint64_t low = resource.second, high = resource.second;
        for (const auto& snapshot : bufferHistory) {
            const auto found = snapshot.find(resource.first);
            if (found == snapshot.end()) { JumpGuard("buffer_layout_changed"); return false; }
            low = std::min(low, found->second); high = std::max(high, found->second);
        }
        if (high - low > largestObservedFrame) {
            JumpGuard("buffer_growing_or_draining");
            return false;
        }
    }
    bufferStationaryCacheResult = true;
    return true;
}

std::string FlowId(Ptr<RdmaQueuePair> qp) {
    return std::to_string((qp->sip.Get() >> 8) & 0xffff) + "-"
        + std::to_string((qp->dip.Get() >> 8) & 0xffff) + "-"
        + std::to_string(qp->sport) + "-" + std::to_string(qp->dport);
}
}

uint32_t RdmaEgressQueue::ack_q_idx = 3;
uint32_t RdmaEgressQueue::tcpip_q_idx = 1;

//计算接收端口流量速率的变�?

//int number_test = 0;//做一个计数实验，看判断多少次最小流完成时间

// RdmaEgressQueue
//使用 TypeId 机制来查�? RdmaEgressQueue 的类型信�?
//监听 RdmaEgressQueue 中数据包的入�? (Enqueue) 和出�? (Dequeue) �?
TypeId RdmaEgressQueue::GetTypeId (void)
{
	static TypeId tid = TypeId ("ns3::RdmaEgressQueue")
	                    .SetParent<Object> ()
	                    .AddTraceSource ("RdmaEnqueue", "Enqueue a packet in the RdmaEgressQueue.",
	                                     MakeTraceSourceAccessor (&RdmaEgressQueue::m_traceRdmaEnqueue), "ns3::Packet::TracedCallback")
	                    .AddTraceSource ("RdmaDequeue", "Dequeue a packet in the RdmaEgressQueue.",
	                                     MakeTraceSourceAccessor (&RdmaEgressQueue::m_traceRdmaDequeue), "ns3::Packet::TracedCallback")
	                    ;
	return tid;
}

RdmaEgressQueue::RdmaEgressQueue() {
	m_rrlast = 0;
	m_qlast = 0;
	m_ackQ = CreateObject<DropTailQueue<Packet>>();
	m_ackQ->SetAttribute("MaxSize", QueueSizeValue (QueueSize (BYTES, 0xffffffff))); // queue limit is on a higher level, not here
}

// RDMA 出队
Ptr<Packet> RdmaEgressQueue::DequeueQindex(int qIndex) {

	NS_ASSERT_MSG(qIndex != -2, "qIndex -2 appeared in DequeueQindex. This is not intended. Aborting!");
	if (qIndex == -1) { // high prio
		Ptr<Packet> p = m_ackQ->Dequeue();
		m_qlast = -1;
		m_traceRdmaDequeue(p, 0);//出队
		UnSchedTag tag;
		bool found = p->PeekPacketTag(tag);
		uint32_t unsched = tag.GetValue();
		return p;
	}
	if (qIndex >= 0) { // qp
		Ptr<Packet> p = m_rdmaGetNxtPkt(m_qpGrp->Get(qIndex));
		m_rrlast = qIndex;
		m_qlast = qIndex;
		m_traceRdmaDequeue(p, m_qpGrp->Get(qIndex)->m_pg);
		UnSchedTag tag;
		bool found = p->PeekPacketTag(tag);
		uint32_t unsched = tag.GetValue();
		return p;
	}
	return 0;
}


//�? RDMA 出队过程中选择下一个队列索�? (qIndex)
int RdmaEgressQueue::GetNextQindex(bool paused[]) {
	bool found = false;
	uint32_t qIndex;
	if (!paused[ack_q_idx] && m_ackQ->GetNPackets() > 0)
		return -1;

	// no pkt in highest priority queue, do rr for each qp
	int res = -1024;

	for (uint32_t dorr = 0; dorr < 2; dorr++) {
		hostDequeueIndex++;
		if (hostDequeueIndex % 2) {
			uint32_t fcount = m_qpGrp->GetN();
			uint32_t min_finish_id = 0xffffffff;
			for (qIndex = 1; qIndex <= fcount; qIndex++) {
				uint32_t idx = (qIndex + m_rrlast) % fcount;
				Ptr<RdmaQueuePair> qp = m_qpGrp->Get(idx);
				if (!paused[qp->m_pg] && qp->GetBytesLeft() > 0 && !qp->IsWinBound()) {
					if (m_qpGrp->Get(idx)->m_nextAvail.GetTimeStep() > Simulator::Now().GetTimeStep()) //not available now
						continue;
					res = idx;
					break;
				} else if (qp->IsFinished()) {
					min_finish_id = idx < min_finish_id ? idx : min_finish_id;
				}
			}

			// clear the finished qp
			if (min_finish_id < 0xffffffff) {
				int nxt = min_finish_id;
				auto &qps = m_qpGrp->m_qps;
				for (int i = min_finish_id + 1; i < fcount; i++) if (!qps[i]->IsFinished()) {
						if (i == res) // update res to the idx after removing finished qp
							res = nxt;
						qps[nxt] = qps[i];
						nxt++;
					}
				qps.resize(nxt);
			}

			if (res != -1024) {
				return res;
			}
		}
		else {
			if (qb_dev->GetQueue()->GetNBytes(tcpip_q_idx)) {
				res = -2;
				return res;
			}
		}
	}

	return res;
}

//获取最近使用的队列
int RdmaEgressQueue::GetLastQueue() {
	return m_qlast;
}

//获取指定队列的剩余字节数
uint32_t RdmaEgressQueue::GetNBytes(uint32_t qIndex) {
	NS_ASSERT_MSG(qIndex < m_qpGrp->GetN(), "RdmaEgressQueue::GetNBytes: qIndex >= m_qpGrp->GetN()");
	return m_qpGrp->Get(qIndex)->GetBytesLeft();
}

//获取 RDMA 流的数量
uint32_t RdmaEgressQueue::GetFlowCount(void) {
	return m_qpGrp->GetN();
}

//获取特定�? QP
Ptr<RdmaQueuePair> RdmaEgressQueue::GetQp(uint32_t i) {
	return m_qpGrp->Get(i);
}

//恢复指定队列的状态（超时重传或队列复位）
void RdmaEgressQueue::RecoverQueue(uint32_t i) {
	NS_ASSERT_MSG(i < m_qpGrp->GetN(), "RdmaEgressQueue::RecoverQueue: qIndex >= m_qpGrp->GetN()");
	m_qpGrp->Get(i)->snd_nxt = m_qpGrp->Get(i)->snd_una;
}

void RdmaEgressQueue::EnqueueHighPrioQ(Ptr<Packet> p) {
	m_traceRdmaEnqueue(p, 0);
	m_ackQ->Enqueue(p);
}

void RdmaEgressQueue::CleanHighPrio(TracedCallback<Ptr<const Packet>, uint32_t> dropCb) {
	while (m_ackQ->GetNPackets() > 0) {
		Ptr<Packet> p = m_ackQ->Dequeue();
		dropCb(p, 0);
	}
}

/******************
 * QbbNetDevice
 *****************/
NS_OBJECT_ENSURE_REGISTERED(QbbNetDevice);

TypeId
QbbNetDevice::GetTypeId(void)
{
	static TypeId tid = TypeId("ns3::QbbNetDevice")
	                    .SetParent<PointToPointNetDevice>()
	                    .AddConstructor<QbbNetDevice>()
	                    .AddAttribute("QbbEnabled",
	                                  "Enable the generation of PAUSE packet.",
	                                  BooleanValue(true),
	                                  MakeBooleanAccessor(&QbbNetDevice::m_qbbEnabled),
	                                  MakeBooleanChecker())
	                    .AddAttribute("QcnEnabled",
	                                  "Enable the generation of PAUSE packet.",
	                                  BooleanValue(false),
	                                  MakeBooleanAccessor(&QbbNetDevice::m_qcnEnabled),
	                                  MakeBooleanChecker())
	                    .AddAttribute("PauseTime",
	                                  "Number of microseconds to pause upon congestion",
	                                  UintegerValue(5),
	                                  MakeUintegerAccessor(&QbbNetDevice::m_pausetime),
	                                  MakeUintegerChecker<uint32_t>())
	                    .AddAttribute ("TxBeQueue",
	                                   "A queue to use as the transmit queue in the device.",
	                                   PointerValue (),
	                                   MakePointerAccessor (&QbbNetDevice::m_queue),
	                                   MakePointerChecker<Queue<Packet>>())
	                    .AddAttribute ("RdmaEgressQueue",
	                                   "A queue to use as the transmit queue in the device.",
	                                   PointerValue (),
	                                   MakePointerAccessor (&QbbNetDevice::m_rdmaEQ),
	                                   MakePointerChecker<Object> ())
	                    .AddTraceSource ("QbbEnqueue", "Enqueue a packet in the QbbNetDevice.",
	                                     MakeTraceSourceAccessor (&QbbNetDevice::m_traceEnqueue), "ns3::Packet::TracedCallback")
	                    .AddTraceSource ("QbbDequeue", "Dequeue a packet in the QbbNetDevice.",
	                                     MakeTraceSourceAccessor (&QbbNetDevice::m_traceDequeue), "ns3::Packet::TracedCallback")
	                    .AddTraceSource ("QbbDrop", "Drop a packet in the QbbNetDevice.",
	                                     MakeTraceSourceAccessor (&QbbNetDevice::m_traceDrop), "ns3::Packet::TracedCallback")
	                    .AddTraceSource ("RdmaQpDequeue", "A qp dequeue a packet.",
	                                     MakeTraceSourceAccessor (&QbbNetDevice::m_traceQpDequeue), "ns3::Packet::TracedCallback")
	                    .AddTraceSource ("QbbPfc", "get a PFC packet. 0: resume, 1: pause",
	                                     MakeTraceSourceAccessor (&QbbNetDevice::m_tracePfc), "ns3::Packet::TracedCallback")
	                    ;

	return tid;
}

QbbNetDevice::QbbNetDevice()
{
    // Keep the legacy artifact for launchers that copy it, without collecting
    // unused multi-megabyte switch matrices. Never truncate a mixed-mode input.
    if (!flag_ENABLE_JUMP_TRANSITION) {
        static bool compatibilityFileInitialized = false;
        if (!compatibilityFileInitialized) {
            std::ofstream calibration(GetSimulationOutputPath("flow_SwitchStats.txt"), std::ios::trunc);
            if (!calibration) throw std::runtime_error("Unable to create legacy calibration compatibility file");
            compatibilityFileInitialized = true;
            std::cout << "Legacy switch matrix calibration disabled: mixed transitions use "
                         "payload samples and lightweight buffer guards." << std::endl;
        }
    }

	NS_LOG_FUNCTION(this);
	m_ecn_source = new std::vector<ECNAccount>;
	m_rdmaEQ = CreateObject<RdmaEgressQueue>();
	m_rdmaEQ->qb_dev = this;

	for (uint32_t i = 0; i < qCnt; i++) {
		m_paused[i] = false;
		dummy_paused[i] = false;
		m_rdmaEQ->dummy_paused[i] = dummy_paused[i];
	}
	hostDequeueIndex = 0;
}

QbbNetDevice::~QbbNetDevice()
{
	NS_LOG_FUNCTION(this);
}

void
QbbNetDevice::DoDispose()
{
	NS_LOG_FUNCTION(this);

	PointToPointNetDevice::DoDispose();
}

//获取数据速率
DataRate QbbNetDevice::GetDataRate() {
	return m_bps;
}

bool
QbbNetDevice::TransmitStart(Ptr<Packet> p)
{
	NS_LOG_FUNCTION(this << p);
	NS_LOG_LOGIC("UID is " << p->GetUid() << ")");
	//
	// This function is called to start the process of transmitting a packet.
	// We need to tell the channel that we've started wiggling the wire and
	// schedule an event that will be executed when the transmission is complete.
	//
	NS_ASSERT_MSG(m_txMachineState == READY, "Must be READY to transmit");
	m_txMachineState = BUSY;
	m_currentPkt = p;
	m_phyTxBeginTrace(m_currentPkt);

	Time txTime = m_bps.CalculateBytesTxTime(p->GetSize());
	auto it = node_latency_fix.find(m_node->GetId());
	if(it!=node_latency_fix.end()){
		txTime+=it->second;
		node_latency_fix.erase(it);
	}
	Time txCompleteTime = txTime + m_tInterframeGap;

	NS_LOG_LOGIC("Schedule TransmitCompleteEvent in " << txCompleteTime.GetSeconds() << "sec");
	Simulator::Schedule(txCompleteTime, &QbbNetDevice::TransmitComplete, this);

	bool result = m_channel->TransmitStart(p, this, txTime);
	if (result == false)
	{
		m_phyTxDropTrace(p);//丢包
	}
	return result;
}

void
QbbNetDevice::TransmitComplete(void)
{
	NS_LOG_FUNCTION(this);
	NS_ASSERT_MSG(m_txMachineState == BUSY, "Must be BUSY if transmitting");
	m_txMachineState = READY;
	NS_ASSERT_MSG(m_currentPkt != 0, "QbbNetDevice::TransmitComplete(): m_currentPkt zero");
	m_phyTxEndTrace(m_currentPkt);
	m_currentPkt = 0;
	DequeueAndTransmit();//传输下一个数据包
}

//从队列中取出数据包并发送，确保设备可以持续传输数据
void
QbbNetDevice::DequeueAndTransmit(void)
{
	// std::cout << "dequeue " << std::endl;
	NS_LOG_FUNCTION(this);
	if (!m_linkUp) return; // if link is down, return
	if (m_txMachineState == BUSY) return;	// Quit if channel busy
	Ptr<Packet> p;
	if (m_node->GetNodeType() == 0) {
		int qIndex = m_rdmaEQ->GetNextQindex(m_paused);
		// std::cout << "qIndex " << qIndex << std::endl;
		if (qIndex != -1024) {
			if (qIndex == -1) { // high prio
				p = m_rdmaEQ->DequeueQindex(qIndex);
				m_traceDequeue(p, 0);
				TransmitStart(p);
				numTxBytes += p->GetSize(); //当前发送窗口的数据�?
				totalBytesSent += p->GetSize(); //总发送量
				return;
			}
			else if (qIndex == -2) {
				Ptr<Packet> p = m_queue->DequeueRR (m_paused);
				if (p == 0)
				{
					NS_LOG_LOGIC ("No pending packets in device queue after tx complete");
					return;
				}

				// //
				// // Got another packet off of the queue, so start the transmit process again.
				// //
				m_snifferTrace (p);
				m_promiscSnifferTrace (p);
				TransmitStart (p);
				totalBytesSent += p->GetSize();
				return;
			}
			// a qp dequeue a packet
			Ptr<RdmaQueuePair> lastQp = m_rdmaEQ->GetQp(qIndex);
			p = m_rdmaEQ->DequeueQindex(qIndex);
			// if (p==NULL)
			// std::cout << "p is null" << std::endl;

			// transmit
			m_traceQpDequeue(p, lastQp);
			TransmitStart(p);

			// update for the next avail time
			m_rdmaPktSent(lastQp, p, m_tInterframeGap);//通知 QP 该数据包已发送，并设置下次可用时�? (m_tInterframeGap)
			totalBytesSent += p->GetSize();
		} else { // no packet to send
			NS_LOG_INFO("PAUSE prohibits send at node " << m_node->GetId());
			Time t = Simulator::GetMaximumSimulationTime();
			for (uint32_t i = 0; i < m_rdmaEQ->GetFlowCount(); i++) {
				Ptr<RdmaQueuePair> qp = m_rdmaEQ->GetQp(i);
				if (qp->GetBytesLeft() == 0)
					continue;
				t = Min(qp->m_nextAvail, t);
			}
			if (m_nextSend.IsExpired() && t < Simulator::GetMaximumSimulationTime() && t > Simulator::Now()) {
				m_nextSend = Simulator::Schedule(t - Simulator::Now(), &QbbNetDevice::DequeueAndTransmit, this);
			}
		}
		return;
	}
	else {  //switch, doesn't care about qcn, just send
		p = m_queue->DequeueRR(m_paused);		//this is round-robin
		if (p != 0) {
			m_snifferTrace(p);
			m_promiscSnifferTrace(p);
			Ipv4Header h;
			Ptr<Packet> packet = p->Copy();
			uint16_t protocol = 0;
			ProcessHeader(packet, protocol);
			packet->RemoveHeader(h);
			InterfaceTag t;
			uint32_t qIndex = m_queue->GetLastQueue();
			if (qIndex == 0) { //this is a pause or cnp, send it immediately!
				m_node->SwitchNotifyDequeue(m_ifIndex, qIndex, p);
				p->RemovePacketTag(t);
			} else {
				m_node->SwitchNotifyDequeue(m_ifIndex, qIndex, p);
				p->RemovePacketTag(t);
			}
			m_traceDequeue(p, qIndex);
			TransmitStart(p);
			numTxBytes += p->GetSize();
			totalBytesSent += p->GetSize();
			return;
		} else { //No queue can deliver any packet
			NS_LOG_INFO("PAUSE prohibits send at node " << m_node->GetId());
			if (m_node->GetNodeType() == 0 && m_qcnEnabled) { //nothing to send, possibly due to qcn flow control, if so reschedule sending
				Time t = Simulator::GetMaximumSimulationTime();
				for (uint32_t i = 0; i < m_rdmaEQ->GetFlowCount(); i++) {
					Ptr<RdmaQueuePair> qp = m_rdmaEQ->GetQp(i);
					if (qp->GetBytesLeft() == 0)
						continue;
					t = Min(qp->m_nextAvail, t);
				}
				if (m_nextSend.IsExpired() && t < Simulator::GetMaximumSimulationTime() && t > Simulator::Now()) {
					m_nextSend = Simulator::Schedule(t - Simulator::Now(), &QbbNetDevice::DequeueAndTransmit, this);
				}
			}
		}
	}
	return;
}

//恢复在指定队�? qIndex 上暂停的传输
void
QbbNetDevice::Resume(unsigned qIndex)
{
	NS_LOG_FUNCTION(this << qIndex);
	NS_ASSERT_MSG(m_paused[qIndex], "Must be PAUSEd");
	m_paused[qIndex] = false;
	NS_LOG_INFO("Node " << m_node->GetId() << " dev " << m_ifIndex << " queue " << qIndex <<
	            " resumed at " << Simulator::Now().GetSeconds());
	DequeueAndTransmit();
}

void
QbbNetDevice::SetReceiveCallback (NetDevice::ReceiveCallback cb)
{
	m_rxCallback = cb;
}

//从包 p 中移�? PPP头�?
//提取 PPP 协议号，并使�? PppToEther() 将其转换为以太网协议�?
bool
QbbNetDevice::ProcessHeader (Ptr<Packet> p, uint16_t& param)
{
	NS_LOG_FUNCTION (this << p << param);
	PppHeader ppp;
	p->RemoveHeader (ppp);
	// std::cout << "p2p prot " << uint32_t(ppp.GetProtocol ()) << std::endl;
	param = PppToEther (ppp.GetProtocol ());
	return true;
}

uint16_t
QbbNetDevice::PppToEther (uint16_t proto)
{
	NS_LOG_FUNCTION_NOARGS();
	switch (proto)
	{
	case 0x0021: return 0x0800;   //IPv4
	case 0x0057: return 0x86DD;   //IPv6
	default:
		NS_ASSERT_MSG (false, "PPP Protocol number not defined!");
		std::cout << "PPP Protocol number not defined!" << std::endl;
	}
	return 0;
}

uint16_t
QbbNetDevice::EtherToPpp (uint16_t proto)
{
	NS_LOG_FUNCTION_NOARGS();
	switch (proto)
	{
	case 0x0800: return 0x0021;   //IPv4
	case 0x86DD: return 0x0057;   //IPv6
	default: NS_ASSERT_MSG (false, "PPP Protocol number not defined!");
	}
	return 0;
}




//打印swicthStats信息
void QbbNetDevice::PrintAllSwitchStats(std::map<uint32_t,SwitchStat>& stats,std::ofstream& flowstatsFile) {
    for (const auto& pair : stats) {
        uint32_t sw_id = pair.first;
        const SwitchStat& stat = pair.second;

		int flag=1;
		//for(int k=0;k<pCnt;++k){
			for (int i = 0; i < pCnt; ++i) {
				for (int j = 0; j < qCnt; ++j) {
					if(stat.egress_bytes[i][j]||stat.ingress_bytes[i][j]||stat.egressLpf_bytes[i][j]||stat.ingressLpf_bytes[i][j]//||stat.m_bytes[k][i][j]
					){
						// 写入文件而不是输出到终端
						if(flag!=0) {
							flowstatsFile << "===== Switch ID: " << sw_id << " =====\n";
							flag =0;
						}
						flowstatsFile 
						<< "Port " << i << ", Queue " << j << ": "
						//<<stat.m_bytes[k][i][j]<<", "
						<< "Egress Bytes = " << stat.egress_bytes[i][j] << ", "
						<< "Ingress Bytes = " << stat.ingress_bytes[i][j] << ", "
						<< "Egress LPF = " << stat.egressLpf_bytes[i][j] << ", "
						<< "Ingress LPF = " << stat.ingressLpf_bytes[i][j]<<", "
						<<"DequeueRateIngress = "<<stat.dequeueRateIngress[i][j]<<", "
						<<"Bandwidth = "<<stat.bandwidth[j]
						<< "\n";
					}
				}
        	}
		//}
		for(int k=0;k<pCnt;++k){
			for (int i = 0; i < pCnt; ++i) {
				for (int j = 0; j < qCnt; ++j) {
					if(stat.m_bytes[k][i][j]
					){
						// 写入文件而不是输出到终端
						if(flag!=0) {
							flowstatsFile << "===== Switch ID: " << sw_id << " =====\n";
							flag =0;
						}
						flowstatsFile 
						<< "iPort " << k << ", ePort " << i << ", Queue " << j << ": "
						<<stat.m_bytes[k][i][j]<<", "
						<< "\n";
					}
				}
        	}
		}
    }
}

bool QbbNetDevice::IsAllZero(const SwitchStat& stat) {
    if (stat.totalUsed != 0 ||
        stat.egressPoolUsed[0] != 0 ||
        stat.egressPoolUsed[1] != 0 ||
        stat.xoffTotalUsed != 0 ||
        stat.totalIngressReservedUsed != 0 ||
        stat.sharedPoolUsed != 0) {
        return false;
    }

    for (int i = 0; i < pCnt; ++i) {
        for (int j = 0; j < pCnt; ++j) {
            for (int k = 0; k < qCnt; ++k) {
                if (stat.m_bytes[i][j][k] != 0)
                    return false;
            }
        }
    }

    for (int i = 0; i < pCnt; ++i) {
        for (int j = 0; j < qCnt; ++j) {
            if (stat.ingressLpf_bytes[i][j] != 0 ||
                stat.egressLpf_bytes[i][j] != 0 ||
                stat.ingress_bytes[i][j] != 0 ||
                stat.egress_bytes[i][j] != 0) {
                return false;
            }
        }
    }

    return true;
}

void
QbbNetDevice::Receive(Ptr<Packet> packet)
{
// std::cout << "receive" << std::endl;
	NS_LOG_FUNCTION(this << packet);
	if (!m_linkUp) {
		m_traceDrop(packet, 0);
		return;
	}

	if (m_receiveErrorModel && m_receiveErrorModel->IsCorrupt(packet))
	{
		//
		// If we have an error model and it indicates that it is time to lose a
		// corrupted packet, don't forward this packet up, let it go.
		//
		m_phyRxDropTrace(packet);
		return;
	}

	m_macRxTrace(packet);

	CustomHeader ch(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
	ch.getInt = 1; // parse INT header
	packet->PeekHeader(ch);//查看但不移除数据包中的头部信息
	if (ch.l3Prot == 0xFE) { // PFC
		if (!m_qbbEnabled) return;
		unsigned qIndex = ch.pfc.qIndex;
		if (ch.pfc.time > 0) {
			m_tracePfc(1);
			m_paused[qIndex] = true;
		} else {
			m_tracePfc(0);
			Resume(qIndex);
		}
	} else { // non-PFC packets (data, ACK, NACK, CNP...)
		if (m_node->GetNodeType() > 0) { // switch
			packet->AddPacketTag(InterfaceTag(m_ifIndex));
			m_node->SwitchReceiveFromDevice(this, packet, ch);
		} else { // NIC
			int ret;
			Ptr<Packet> cp = packet->Copy();
			
			PppHeader ph; cp->RemoveHeader(ph);//（可以得到源、目的端口）
 			Ipv4Header ih;//(这里可以得到源、目的地址ipv4地址)
			cp->RemoveHeader(ih);
			if (ih.GetProtocol() == 0x06) {
				m_snifferTrace (packet);
				m_promiscSnifferTrace (packet);
				m_phyRxEndTrace (packet);
				Ptr<Packet> originalPacket = packet->Copy ();
				uint16_t prot = 0;
				ProcessHeader (packet, prot);//PPP（Point-to-Point Protocol）协议号转换为以太网协议号

				if (!m_promiscCallback.IsNull ())
				{
					m_macPromiscRxTrace (originalPacket);
					m_promiscCallback (this, packet, prot, GetRemote (), GetAddress (), NetDevice::PACKET_HOST);
				}
				m_macRxTrace (originalPacket);
				m_rxCallback (this, packet, prot, GetRemote ());
			}
			else {
				// send to RdmaHw
				if(((ch.dip >> 8) & 0xffff)==m_node->GetId()){//接收端才进行计算
                auto& flowstatsFile = FlowStatisticsFile();
                GenerateFlowId(packet, ch, flowstatsFile);
				}
				ret = m_rdmaReceiveCb(packet, ch);
			}
			// TODO we may based on the ret do something
		}
	}
    // Every flow uses one frozen payload-service model for both elapsed time
    // and sequence progress. The exit callback only closes this transition.
    if (allSteadyStateReached && flag_ENABLE_JUMP_TRANSITION && !pendingJumpToken) {
        calculateMintime();
        if (jumpPlan.ready) {
            const uint64_t duration = jumpPlan.durationNs;
            ApplyJumpPlan();
            transition_delay.push_back(duration);
            // Schedule under the old stage so the core moves this callback to
            // the end of the virtual interval along with the pending packets.
            Simulator::ScheduleNow(&QbbNetDevice::exitSteadyState, this);
            ++transition_cnt;
            pendingJumpToken = transition_cnt;
            next_trans_avail = Simulator::Now().GetNanoSeconds() + duration;
            allSteadyStateReached = false;
            flag_steady = true;
            std::cout << "Mixed transition " << transition_cnt << " at "
                      << Simulator::Now().GetNanoSeconds() << " ns, duration "
                      << duration << " ns" << std::endl;
            FILE* marker = fopen(GetSimulationOutputPath("bandwidth_markers.txt").c_str(), "a");
            if (marker) {
                fprintf(marker, "# TRANSITION %.9f\n", Simulator::Now().GetSeconds());
                fclose(marker);
            }
        }
    }
    if (!allSteadyStateReached && !flag_steady && flag_ENABLE_JUMP_TRANSITION) {
        RecordSteadyStateEvent("exit", Simulator::Now().GetNanoSeconds());
        flag_steady = true;
    }
    if (!allSteadyStateReached && !flag_steady && !flag_ENABLE_JUMP_TRANSITION) {
        RecordSteadyStateEvent("exit", Simulator::Now().GetNanoSeconds());
        flag_steady = true;
        auto& output = FlowStatisticsFile();
        output << "System exit" << std::endl;
        if (!output) throw std::runtime_error("Unable to write steady-state exit");
    }
	return;
}

//生成flowid和获取数据包大小
void QbbNetDevice::GenerateFlowId(Ptr<Packet> packet, CustomHeader& header,
                                std::ofstream& flowstatsFile) {
    if (header.l3Prot != 0x11) return;
    const uint32_t wireBytes = packet->GetSize();
    const uint32_t headerBytes = header.GetSerializedSize();
    if (wireBytes < headerBytes)
        throw std::runtime_error("RDMA frame is shorter than its parsed headers");
    const uint32_t payloadBytes = wireBytes - headerBytes;
    if (wireBytes > largestObservedFrame) {
        largestObservedFrame = wireBytes;
        bufferStationaryCacheValid = false;
    }
    const std::string id = std::to_string((header.sip >> 8) & 0xffff) + "-"
        + std::to_string((header.dip >> 8) & 0xffff) + "-"
        + std::to_string(header.udp.sport) + "-" + std::to_string(header.udp.dport);
    onPacketReceived(id, payloadBytes, wireBytes, flowstatsFile);
}

void QbbNetDevice::onPacketReceived(std::string flowid, uint32_t payloadBytes,
                                   uint32_t wireBytes, std::ofstream& flowstatsFile) {
    MarkFlowObserved(flowid);
    if (filter.find(flowid) != filter.end()) return;
    // ObservePacket owns the first byte count too: never pre-count a packet.
    if (flowStats.find(flowid) == flowStats.end()) flowStats.emplace(flowid, FlowStat{});
    calculateRate(flowid, payloadBytes, wireBytes, flowstatsFile);
}

void QbbNetDevice::calculateRate(std::string flowid, uint32_t payloadBytes,
                                uint32_t wireBytes, std::ofstream& flowstatsFile) {
    const uint64_t now = Simulator::Now().GetNanoSeconds();
    const auto policy = SamplingPolicy();
    auto current = flowStats.find(flowid);
    if (current == flowStats.end()) { allSteadyStateReached = false; return; }
    const auto observation = flow_acc::ObservePacket(current->second.sampling, now,
                                                      payloadBytes, wireBytes, policy);
    for (auto& entry : flowStats) {
        auto& stat = entry.second;
        bool historyChanged = observation.sampled || observation.history_reset;
        if (entry.first != flowid) {
            const size_t previousSize = stat.sampling.samples.size();
            const bool previousInvalid = stat.sampling.interval_invalidated;
            flow_acc::InvalidateIfStale(stat.sampling, now, policy);
            historyChanged = previousSize != stat.sampling.samples.size() ||
                             previousInvalid != stat.sampling.interval_invalidated;
        }
        stat.byteCount = stat.sampling.payload_bytes;
        stat.timestamp = stat.sampling.interval_start_ns;
        stat.steadyStateReached = flow_acc::IsFreshSteady(stat.sampling, now, policy);
        if (historyChanged) {
            stat.rate.clear();
            for (const auto& sample : stat.sampling.samples) stat.rate.push_back(sample.payload_gbps);
        }
    }
    SampleBuffers(now);
    if (observation.sampled) {
        const auto& sample = observation.sample;
        flowstatsFile << "Flow ID: " << flowid << " - Payload rate: " << sample.payload_gbps
                      << " Gbps currentTime: " << now << " elapsed_ns: " << sample.elapsed_ns
                      << " payload_bytes: " << sample.payload_bytes << " wire_bytes: "
                      << sample.wire_bytes << std::endl;
        static std::ofstream animation(GetSimulationOutputPath("bandwidth_animation_task.txt"));
        if (!animation) throw std::runtime_error("Unable to write payload bandwidth samples");
        animation << std::fixed << std::setprecision(9) << now / 1e9 << ' ' << flowid
                  << ' ' << std::setprecision(6) << sample.payload_gbps << std::endl;
    }
    allSteadyStateReached = !flowStats.empty() && !HasUnobservedFlows() && !pendingJumpToken;
    for (const auto& entry : flowStats)
        if (!entry.second.steadyStateReached) { allSteadyStateReached = false; break; }
    if (allSteadyStateReached && !BuffersAreStationary()) allSteadyStateReached = false;
    if (allSteadyStateReached && flag_steady) {
        flag_steady = false;
        ++steady_state_count;
        steadyStateStartTime = now;
        RecordSteadyStateEvent("enter", now);
        std::cout << "System entered steady state at time: " << now << " ns" << std::endl;
        flowstatsFile << "System entered steady state at time: " << now << " ns" << std::endl;
        FILE* marker = fopen(GetSimulationOutputPath("bandwidth_markers.txt").c_str(), "a");
        if (marker) {
            fprintf(marker, "# STEADY_STATE_ENTER %.9f\n", now / 1e9);
            fclose(marker);
        }
    }
}

void QbbNetDevice::UpdateSwitchStats(){
	if((transition_cnt-1)<multiSwitchStats.size()){
		const auto& exitStatsMap = multiSwitchStats[transition_cnt - 1].exitStats;
		for (const auto& [switchId, stat] : exitStatsMap) {

			for (NodeList::Iterator it = NodeList::Begin(); it != NodeList::End(); ++it)
			{
				Ptr<Node> node = *it;
				
				if(node->GetId()==switchId){//交换机
					node->SwitchStatsUpdate(transition_cnt-1,switchId);
				}
			}
		}

	}
}

void QbbNetDevice::TimeDelaySwitchStats() {
    // Historical snapshot deltas mix bytes, bps and ns, and are not a validated
    // buffer evolution model. Real queued packets remain in the event queue.
    JumpGuard("buffer_compensation_disabled_unvalidated_model");
}

// 新增：延迟后的逻辑
void QbbNetDevice::ContinueAfterDelay(double max_time) {
    std::cout<<"Waited time = " << max_time << " seconds. Continuing...";
}

void QbbNetDevice::exitSteadyState() {
    if (!pendingJumpToken || pendingJumpToken != transition_cnt)
        throw std::runtime_error("Mixed transition exit token does not match its frozen plan");
    RecordSteadyStateEvent("exit", Simulator::Now().GetNanoSeconds());
    std::ofstream output(GetSimulationOutputPath("jump_events.jsonl"), std::ios::app);
    output << "{\"event\":\"jump_complete\",\"transition_index\":" << pendingJumpToken
           << ",\"time_ns\":" << Simulator::Now().GetNanoSeconds() << "}" << std::endl;
    if (!output) throw std::runtime_error("Unable to write mixed transition completion");
    pendingJumpToken = 0;
    jumpPlan = JumpPlan();
    allSteadyStateReached = false;
    flag_steady = true;
}

void QbbNetDevice::calculateMintime() {
    if (!flag_ENABLE_JUMP_TRANSITION) return;
    jumpPlan = JumpPlan();
    flowMinTime = std::numeric_limits<double>::max();
    transMinTime = 0;
    if (pendingJumpToken) { JumpGuard("transition_exit_pending"); return; }
    if (transition_cnt == std::numeric_limits<int>::max()) { JumpGuard("transition_count_limit"); return; }
    if (HasPendingExternalReleases()) { JumpGuard("external_release_pending"); return; }
    if (HasUnobservedFlows()) { JumpGuard("first_packet_pending"); return; }
    if (!BuffersAreStationary()) return;
    for (auto it = NodeList::Begin(); it != NodeList::End(); ++it) {
        if ((*it)->GetNodeType() != 0) continue;
        for (uint32_t index = 0; index < (*it)->GetNDevices(); ++index) {
            auto device = DynamicCast<QbbNetDevice>((*it)->GetDevice(index));
            if (device && device->m_rdmaEQ) device->flowCompletiontime(device->m_rdmaEQ);
        }
    }
    if (jumpPlan.blocked) return;
    if (jumpPlan.flows.empty()) { JumpGuard("no_eligible_flows"); return; }
    uint64_t duration = std::numeric_limits<uint64_t>::max();
    for (const auto& flow : jumpPlan.flows) duration = std::min(duration, flow.horizonNs);
    if (duration < MONITOR_PERIOD) { JumpGuard("tail_boundary_too_close"); return; }
    jumpPlan.originalHorizonNs = duration;
    // A common integer-ns service grid removes systematic time credited to a
    // flow without a matching whole-packet advance (e.g. 335ns vs 167ns NICs).
    // Bound the LCM by the original safe horizon before multiplying: arbitrary
    // rational rates need not have a practical common grid, and may fall back
    // to the existing conservative whole-packet quantization instead.
    WideUInt commonTick = 1;
    for (const auto& flow : jumpPlan.flows) {
        const WideUInt packetDenominator = static_cast<WideUInt>(flow.mtu) * flow.elapsedDenominator;
        const WideUInt tick = packetDenominator / GreatestCommonDivisor(flow.payloadNumerator, packetDenominator);
        const WideUInt factor = tick / GreatestCommonDivisor(commonTick, tick);
        if (factor > duration || commonTick > static_cast<WideUInt>(duration) / factor) {
            jumpPlan.alignmentFallback = "common_packet_grid_exceeds_horizon";
            break;
        }
        commonTick *= factor;
    }
    if (jumpPlan.alignmentFallback.empty()) {
        const uint64_t tick = static_cast<uint64_t>(commonTick);
        const uint64_t aligned = duration / tick * tick;
        jumpPlan.commonPacketTickNs = tick;
        if (aligned >= MONITOR_PERIOD) {
            duration = aligned;
            jumpPlan.packetTimeAligned = true;
        } else {
            jumpPlan.alignmentFallback = "aligned_horizon_below_sampling_period";
        }
    }
    for (auto& flow : jumpPlan.flows) {
        const WideUInt payload = static_cast<WideUInt>(duration) * flow.payloadNumerator / flow.elapsedDenominator;
        const WideUInt packets = payload / flow.mtu;
        const WideUInt advance = packets * flow.mtu;
        if (advance > flow.skipLimit || advance > std::numeric_limits<uint64_t>::max()) {
            JumpGuard("invalid_progress_boundary", flow.id); return;
        }
        flow.skipBytes = static_cast<uint64_t>(advance);
        if (!flow.skipBytes) { JumpGuard("no_complete_packet_to_skip", flow.id); return; }
    }
    jumpPlan.durationNs = duration;
    jumpPlan.ready = true;
    flowMinTime = static_cast<double>(duration);
    transMinTime = static_cast<double>(duration);
}

void QbbNetDevice::flowCompletiontime(Ptr<RdmaEgressQueue> queue) {
    const uint64_t now = Simulator::Now().GetNanoSeconds();
    auto driver = m_node->GetObject<RdmaDriver>();
    if (!driver || !driver->m_rdma) { JumpGuard("missing_rdma_hardware"); return; }
    auto hardware = driver->m_rdma;
    for (uint32_t index = 0; index < queue->m_qpGrp->GetN(); ++index) {
        auto qp = queue->m_qpGrp->Get(index);
        if (qp->IsFinished()) continue;
        const std::string id = FlowId(qp);
        if (qp->GetWin() || qp->m_win) { JumpGuard("window_state_not_supported", id); continue; }
        if (hardware->m_cc_mode != 0) { JumpGuard("dynamic_cc_timestamps_not_supported", id); continue; }
        if (!m_linkUp || qp->m_pg >= qCnt || m_paused[qp->m_pg]) { JumpGuard("source_paused_or_down", id); continue; }
        if (qp->stopTime != Simulator::GetMaximumSimulationTime()) { JumpGuard("absolute_flow_deadline", id); continue; }
        if (qp->snd_nxt > qp->m_size || qp->snd_una > qp->snd_nxt ||
            qp->m_size > std::numeric_limits<uint32_t>::max()) { JumpGuard("unsupported_sequence_range", id); continue; }
        const uint64_t remaining = qp->GetBytesLeft();
        if (!remaining) { JumpGuard("flow_awaiting_final_ack", id); continue; }
        const auto stat = flowStats.find(id);
        if (stat == flowStats.end() || !flow_acc::IsFreshSteady(stat->second.sampling, now, SamplingPolicy())) {
            JumpGuard("flow_sample_not_fresh_steady", id); continue;
        }
        auto rate = flow_acc::GetPayloadRate(stat->second.sampling);
        const uint32_t mtu = hardware->m_mtu;
        const uint64_t header = static_cast<uint64_t>(PppHeader::GetStaticSize())
            + Ipv4Header().GetSerializedSize() + UdpHeader().GetSerializedSize() + SeqTsHeader().GetSerializedSize();
        const uint64_t frame = mtu + header;
        if (!rate.valid || !mtu || frame > std::numeric_limits<uint32_t>::max() / 8 || qp->lastPktSize != frame) {
            JumpGuard("unsupported_packet_layout", id); continue;
        }
        const DataRate pacing = hardware->m_rateBound ? qp->m_rate : qp->m_max_rate;
        if (!pacing.GetBitRate() || !m_bps.GetBitRate()) { JumpGuard("zero_sender_rate", id); continue; }
        const int64_t wireNs = m_bps.CalculateBytesTxTime(static_cast<uint32_t>(frame)).GetNanoSeconds();
        const int64_t pacingNs = pacing.CalculateBytesTxTime(static_cast<uint32_t>(frame)).GetNanoSeconds();
        const int64_t gapNs = m_tInterframeGap.GetNanoSeconds();
        if (wireNs <= 0 || pacingNs <= 0 || gapNs < 0 || std::max(wireNs, pacingNs) > std::numeric_limits<int64_t>::max() - gapNs) {
            JumpGuard("invalid_packet_service_time", id); continue;
        }
        const uint64_t period = static_cast<uint64_t>(std::max(wireNs, pacingNs) + gapNs);
        // A receive measurement cannot advance payload faster than a real full
        // frame can be serialized by this source NIC and its configured pacer.
        if (static_cast<WideUInt>(rate.payload_bytes) * period > static_cast<WideUInt>(mtu) * rate.elapsed_ns) {
            rate.payload_bytes = mtu; rate.elapsed_ns = period;
        }
        const WideUInt rttBytes = (static_cast<WideUInt>(rate.payload_bytes) * qp->m_baseRtt + rate.elapsed_ns - 1) / rate.elapsed_ns;
        const uint64_t flight = qp->snd_nxt - qp->snd_una;
        const WideUInt reserve = ((std::max<WideUInt>(flight, rttBytes) + mtu - 1) / mtu + 1) * mtu;
        if (reserve >= remaining) { JumpGuard("packet_and_flight_tail_boundary", id); continue; }
        const uint64_t retained = static_cast<uint64_t>(reserve);
        const uint64_t skipLimit = (remaining - retained) / mtu * mtu;
        if (!skipLimit) { JumpGuard("no_complete_packet_before_tail", id); continue; }
        WideUInt horizon = static_cast<WideUInt>(skipLimit) * rate.elapsed_ns / rate.payload_bytes;
        const int64_t nextAvailSigned = qp->m_nextAvail.GetNanoSeconds();
        if (nextAvailSigned < 0) { JumpGuard("invalid_pacer_timestamp", id); continue; }
        const uint64_t nextAvail = static_cast<uint64_t>(nextAvailSigned);
        const uint64_t absoluteLimit = static_cast<uint64_t>(std::numeric_limits<int64_t>::max());
        horizon = std::min<WideUInt>(horizon, absoluteLimit - std::max(now, nextAvail));
        JumpFlow candidate;
        candidate.qp = qp; candidate.id = id; candidate.sourceNext = qp->snd_nxt;
        candidate.remaining = remaining; candidate.inFlight = flight; candidate.reserve = retained;
        candidate.skipLimit = skipLimit; candidate.horizonNs = static_cast<uint64_t>(horizon);
        candidate.payloadNumerator = rate.payload_bytes; candidate.elapsedDenominator = rate.elapsed_ns;
        candidate.packetPeriodNs = period; candidate.mtu = mtu; candidate.wireBytes = static_cast<uint32_t>(frame);
        jumpPlan.flows.push_back(std::move(candidate));
    }
}

void QbbNetDevice::ApplyJumpPlan() {
    if (!jumpPlan.ready || pendingJumpToken || !jumpPlan.durationNs)
        throw std::runtime_error("Cannot apply an unfrozen mixed transition plan");
    const uint64_t now = Simulator::Now().GetNanoSeconds();
    std::ofstream output(GetSimulationOutputPath("jump_events.jsonl"), std::ios::app);
    output << "{\"event\":\"jump_plan\",\"transition_index\":" << transition_cnt + 1
           << ",\"start_ns\":" << now << ",\"duration_ns\":" << jumpPlan.durationNs
           << ",\"original_horizon_ns\":" << jumpPlan.originalHorizonNs
           << ",\"packet_time_aligned\":" << (jumpPlan.packetTimeAligned ? "true" : "false")
           << ",\"common_packet_tick_ns\":" << jumpPlan.commonPacketTickNs
           << ",\"alignment_fallback\":\"" << jumpPlan.alignmentFallback << '"'
           << ",\"resume_ns\":" << now + jumpPlan.durationNs
           << ",\"buffer_compensation\":\"disabled_unvalidated_model\",\"flows\":[";
    bool first = true;
    for (const auto& flow : jumpPlan.flows) {
        auto qp = flow.qp;
        if (qp->snd_nxt != flow.sourceNext || flow.skipBytes > qp->GetBytesLeft() ||
            qp->GetBytesLeft() - flow.skipBytes < flow.reserve)
            throw std::runtime_error("Flow changed after its mixed transition plan was frozen");
        if (!first) output << ',';
        first = false;
        const WideUInt remainder = static_cast<WideUInt>(jumpPlan.durationNs) * flow.payloadNumerator
                                 - static_cast<WideUInt>(flow.skipBytes) * flow.elapsedDenominator;
        output << "{\"flow\":\"" << flow.id << "\",\"remaining_bytes\":" << flow.remaining
               << ",\"in_flight_bytes\":" << flow.inFlight << ",\"reserved_tail_bytes\":" << flow.reserve
               << ",\"mtu\":" << flow.mtu << ",\"wire_bytes\":" << flow.wireBytes
               << ",\"packet_period_ns\":" << flow.packetPeriodNs
               << ",\"payload_rate_bytes\":" << flow.payloadNumerator
               << ",\"payload_rate_elapsed_ns\":" << flow.elapsedDenominator
               << ",\"horizon_ns\":" << flow.horizonNs << ",\"skip_bytes\":" << flow.skipBytes
               << ",\"time_remainder_numerator\":" << WideIntegerString(remainder)
               << ",\"time_remainder_denominator\":" << flow.payloadNumerator
               << ",\"conservative_time_remainder_ns\":"
               << static_cast<long double>(remainder) / flow.payloadNumerator << '}';
        qp->snd_nxt += flow.skipBytes;
        qp->m_ipid = static_cast<uint16_t>(qp->m_ipid + flow.skipBytes / flow.mtu);
        qp->m_nextAvail += NanoSeconds(jumpPlan.durationNs);
        for (auto& timestamp : qp->rates) timestamp.second += jumpPlan.durationNs;
        flowStats.erase(flow.id);
        RegisterUnobservedFlow(flow.id);
    }
    output << "]}" << std::endl;
    if (!output) throw std::runtime_error("Unable to write mixed transition plan");
    // These callbacks and buffers are simulated after the same queue-time shift.
    // Never invent additional delay from the old dimensionally-invalid model.
    node_latency_fix.clear();
    bufferHistory.clear();
    bufferSampleInitialized = false;
    bufferStationaryCacheValid = false;
    reportedJumpGuards.clear();
}

//获取当前 NetDevice 所连接的远端设备的地址
Address
QbbNetDevice::GetRemote (void) const
{
	NS_LOG_FUNCTION (this);
	NS_ASSERT (m_channel->GetNDevices () == 2);
	for (std::size_t i = 0; i < m_channel->GetNDevices (); ++i)
	{
		Ptr<NetDevice> tmp = m_channel->GetDevice (i);
		if (tmp != this)
		{
			return tmp->GetAddress ();
		}
	}
	NS_ASSERT (false);
	// quiet compiler.
	return Address ();
}

//发送数据包�? dest 地址，并使用 protocolNumber 指定协议类型
bool QbbNetDevice::Send(Ptr<Packet> packet, const Address &dest, uint16_t protocolNumber)
{
	NS_LOG_FUNCTION (this << packet << dest << protocolNumber);
	NS_LOG_LOGIC ("p=" << packet << ", dest=" << &dest);
	NS_LOG_LOGIC ("UID is " << packet->GetUid ());

	if (IsLinkUp () == false)
	{
		m_macTxDropTrace (packet);
		return false;
	}
	AddHeader (packet, protocolNumber);
	m_macTxTrace (packet);
	m_queue->Enqueue (packet, m_rdmaEQ->tcpip_q_idx);
	DequeueAndTransmit();
	return true;
}

bool QbbNetDevice::SwitchSend (uint32_t qIndex, Ptr<Packet> packet, CustomHeader &ch) {
	m_macTxTrace(packet);
	m_traceEnqueue(packet, qIndex);
	m_queue->Enqueue(packet, qIndex);
	DequeueAndTransmit();
	return true;
}

void QbbNetDevice::SendPfc(uint32_t qIndex, uint32_t type) {
	Ptr<Packet> p = Create<Packet>(0);
	PauseHeader pauseh((type == 0 ? m_pausetime : 0), m_queue->GetNBytes(qIndex), qIndex);
	p->AddHeader(pauseh);
	Ipv4Header ipv4h;  // Prepare IPv4 header
	ipv4h.SetProtocol(0xFE);
	ipv4h.SetSource(m_node->GetObject<Ipv4>()->GetAddress(m_ifIndex, 0).GetLocal());
	ipv4h.SetDestination(Ipv4Address("255.255.255.255"));
	ipv4h.SetPayloadSize(p->GetSize());
	ipv4h.SetTtl(1);
	ipv4h.SetIdentification(UniformVariable(0, 65536).GetValue());
	p->AddHeader(ipv4h);
	AddHeader(p, 0x800);
	CustomHeader ch(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
	p->PeekHeader(ch);
	m_tracePfc(type+2); // 2 indicates PFC PAUSE sent.3 indicates RESUME sent
	SwitchSend(0, p, ch);
}

bool
QbbNetDevice::Attach(Ptr<QbbChannel> ch)
{
	NS_LOG_FUNCTION(this << &ch);
	m_channel = ch;
	m_channel->Attach(this);
	NotifyLinkUp();
	return true;
}

Ptr<Channel>
QbbNetDevice::GetChannel(void) const
{
	return m_channel;
}

bool QbbNetDevice::IsQbb(void) const {
	return true;
}

void QbbNetDevice::NewQp(Ptr<RdmaQueuePair> qp) {
	qp->m_nextAvail = Simulator::Now();
	DequeueAndTransmit();
}
void QbbNetDevice::ReassignedQp(Ptr<RdmaQueuePair> qp) {
	DequeueAndTransmit();
}
void QbbNetDevice::TriggerTransmit(void) {
	DequeueAndTransmit();
}

void QbbNetDevice::SetQueue(Ptr<BEgressQueue> q) {
	NS_LOG_FUNCTION(this << q);
	m_queue = q;
}

Ptr<BEgressQueue> QbbNetDevice::GetQueue() {
	return m_queue;
}

Ptr<RdmaEgressQueue> QbbNetDevice::GetRdmaQueue() {
	return m_rdmaEQ;
}

void QbbNetDevice::RdmaEnqueueHighPrioQ(Ptr<Packet> p) {
	m_traceEnqueue(p, 0);
	m_rdmaEQ->EnqueueHighPrioQ(p);
}

//在网络设备停止工作或链路失效时进行清理工作。它的主要目标包括：
/*清除队列中的所有数据包（防止内存泄漏或残留数据）�?
通知相关模块（例如驱动程序、RDMA 硬件或交换机）链路已经断开�?
将设备状态设置为链路断开（m_linkUp = false）�?*/
void QbbNetDevice::TakeDown() {
	// TODO: delete packets in the queue, set link down
	if (m_node->GetNodeType() == 0) {
		// clean the high prio queue
		m_rdmaEQ->CleanHighPrio(m_traceDrop);
		// notify driver/RdmaHw that this link is down
		m_rdmaLinkDownCb(this);
	} else { // switch
		// clean the queue
		for (uint32_t i = 0; i < qCnt; i++)
			m_paused[i] = false;
		while (1) {
			Ptr<Packet> p = m_queue->DequeueRR(m_paused);
			if (p == 0)
				break;
			m_traceDrop(p, m_queue->GetLastQueue());
		}
		// TODO: Notify switch that this link is down
	}
	m_linkUp = false;
}

//更新设备的下一次可用发送时�?
void QbbNetDevice::UpdateNextAvail(Time t) {
	if (!m_nextSend.IsExpired() && t < Simulator::Now() + Simulator::GetDelayLeft(m_nextSend)) {
		Simulator::Cancel(m_nextSend);
		Time delta = t < Simulator::Now() ? Time(0) : t - Simulator::Now();
		m_nextSend = Simulator::Schedule(delta, &QbbNetDevice::DequeueAndTransmit, this);
	}
}
} 
// namespace ns3

