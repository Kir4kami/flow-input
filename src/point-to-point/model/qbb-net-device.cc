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
#include <chrono>
#include "ns3/qbb-net-device.h"
#include "ns3/log.h"
#include "ns3/boolean.h"
#include "ns3/uinteger.h"
#include "ns3/double.h"
#include "ns3/data-rate.h"
#include "output-directory.h"
#include "switch-timing-tag.h"
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
#include "flow-acc.h"


#include <iostream>
#include <cmath>
#include <sstream>
#include <iomanip>
#include <vector>
#include <set>
#include <fstream>
#include "ns3/mixed-granularity.h"
#include "qbb-net-device.h"

#define ENABLE_JUMP_TRANSITION  // 启用跃迁功能

bool allSteadyStateReached=false;
bool flag_steady =true;// 刚刚/第一次进入稳态
bool flag_read_SwitchStats = false;

bool flag_ENABLE_JUMP_TRANSITION=false;//启动跃迁
bool flag_ENABLE_SWITCH_QUEUE_LOGGING = false; // 启用交换机队列记录
extern bool flag_ENABLE_QBB_DEVICE_RATE_CALC; // 启用QbbNetDevice接收端流速率计算
bool flag_ENABLE_ROUND_ROBIN_DEBUG = true; // 启用轮询调度调试日志（sender_round_robin_debug.csv），主要测试PFC

// 全局静态变量：控制接收端速率CSV文件的打开模式（第一次覆盖，之后追加）
static bool g_isFirstOpenReceiverRateCsv = true;

// 交换机/网侧时间统计（每个数据包）
static bool g_switchNetLogOpened = false;
static bool g_switchNetSummaryScheduled = false;
static uint64_t g_switchTimeSumNs = 0;
static uint64_t g_netTimeSumNs = 0;
static uint64_t g_switchNetPacketCount = 0;
static uint64_t g_switchWallTimeSumNs = 0;
static uint64_t g_netWallTimeSumNs = 0;

namespace {
uint64_t GetWallClockNs() {
	return std::chrono::duration_cast<std::chrono::nanoseconds>(
	           std::chrono::steady_clock::now().time_since_epoch())
	    .count();
}
} // namespace

static void WriteSwitchNetTimeSummary() {
	if (g_switchNetPacketCount == 0) {
		return;
	}
	std::ofstream summaryFile;
	std::string summaryPath = ns3::GetOutputDirectory() + "/packet_switch_net_time_report.txt";
	summaryFile.open(summaryPath.c_str(), std::ios::out);
	if (!summaryFile.is_open()) {
		return;
	}
	double avgSwitch = static_cast<double>(g_switchTimeSumNs) / g_switchNetPacketCount;
	double avgNet = static_cast<double>(g_netTimeSumNs) / g_switchNetPacketCount;
	double avgTotal = avgSwitch + avgNet;
	double avgWallSwitch = static_cast<double>(g_switchWallTimeSumNs) / g_switchNetPacketCount;
	double avgWallNet = static_cast<double>(g_netWallTimeSumNs) / g_switchNetPacketCount;
	double avgWallTotal = avgWallSwitch + avgWallNet;
	double switchRatio = avgTotal > 0 ? (avgSwitch / avgTotal) * 100.0 : 0.0;
	double netRatio = avgTotal > 0 ? (avgNet / avgTotal) * 100.0 : 0.0;
	double switchWallRatio = avgWallTotal > 0 ? (avgWallSwitch / avgWallTotal) * 100.0 : 0.0;
	double netWallRatio = avgWallTotal > 0 ? (avgWallNet / avgWallTotal) * 100.0 : 0.0;
	summaryFile << "交换机/网侧时间统计报告" << std::endl;
	summaryFile << "======================" << std::endl;
	summaryFile << "统计包数量: " << g_switchNetPacketCount << std::endl;
	summaryFile << "平均交换机时间(ns): " << avgSwitch << std::endl;
	summaryFile << "平均网侧时间(ns): " << avgNet << std::endl;
	summaryFile << "平均总时间(ns): " << avgTotal << std::endl;
	summaryFile << "交换机时间占比(%): " << switchRatio << std::endl;
	summaryFile << "网侧时间占比(%): " << netRatio << std::endl;
	summaryFile << std::endl;
	summaryFile << "平均交换机挂钟时间(ns): " << avgWallSwitch << std::endl;
	summaryFile << "平均网侧挂钟时间(ns): " << avgWallNet << std::endl;
	summaryFile << "平均总挂钟时间(ns): " << avgWallTotal << std::endl;
	summaryFile << "交换机挂钟时间占比(%): " << switchWallRatio << std::endl;
	summaryFile << "网侧挂钟时间占比(%): " << netWallRatio << std::endl;
	summaryFile.close();
}

NS_LOG_COMPONENT_DEFINE("QbbNetDevice");

namespace ns3 {

namespace {

std::string
BuildFlowIdFromQp(const Ptr<RdmaQueuePair>& qp)
{
	std::ostringstream oss;
	uint32_t srcIp = qp->sip.Get();
	uint32_t dstIp = qp->dip.Get();
	uint32_t srcId = ((srcIp >> 8) & 0xffff);
	uint32_t dstId = ((dstIp >> 8) & 0xffff);
	uint16_t srcPort = qp->sport;
	uint16_t dstPort = qp->dport;
	oss << srcId << "-" << dstId << "-" << srcPort << "-" << dstPort;
	return oss.str();
}

} // anonymous namespace

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
		
		// 记录m_rrlast的更新
		if (flag_ENABLE_ROUND_ROBIN_DEBUG) {
			uint64_t currentTime = Simulator::Now().GetNanoSeconds();
			static std::ofstream rrlastFile;
			static bool rrlastFileOpened = false;
			if (!rrlastFileOpened) {
				std::string rrlastPath = GetOutputDirectory() + "/sender_round_robin_debug.csv";
				rrlastFile.open(rrlastPath.c_str(), std::ios::out);
				rrlastFile << "Time(ns),NodeType,NodeID,FlowID,PacketSize(Bytes)" << std::endl;
				rrlastFileOpened = true;
			}
			
			Ptr<RdmaQueuePair> qp = m_qpGrp->Get(qIndex);
			std::ostringstream flowIdStream;
			flowIdStream << ((qp->sip.Get() >> 8) & 0xffff) << "-" << ((qp->dip.Get() >> 8) & 0xffff);
			std::string flowId = flowIdStream.str();
			
			// 获取节点类型和ID
			std::string nodeType = "Unknown";
			uint32_t nodeId = 0;
			if (qb_dev) {
				Ptr<Node> node = qb_dev->GetNode();
				if (node) {
					nodeId = node->GetId();
					nodeType = (node->GetNodeType() == 0) ? "Node" : "Switch";
				}
			}
			
			uint32_t packetSize = p->GetSize();
			rrlastFile << currentTime << "," << nodeType << "," << nodeId << "," << flowId << "," << packetSize << std::endl;
		}
		
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


//在RDMA 出队过程中选择下一个队列索引(qIndex)
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
			if (qIndex == -1) { // high prio 直接出队并发送，不涉及流控或下次可用时间更新
				p = m_rdmaEQ->DequeueQindex(qIndex);
				m_traceDequeue(p, 0);
				TransmitStart(p);
				numTxBytes += p->GetSize(); //当前发送窗口的数据�?
				totalBytesSent += p->GetSize(); //总发送量
				return;
			}
			else if (qIndex == -2) { //使用 Round Robin 方式从普通队列中取包（可能用于 TCP/IP 流量）
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
			Ptr<RdmaQueuePair> lastQp = m_rdmaEQ->GetQp(qIndex);//获取队列对
			p = m_rdmaEQ->DequeueQindex(qIndex);//出队并发送数据包
			// if (p==NULL)
			// std::cout << "p is null" << std::endl;

			// transmit
			m_traceQpDequeue(p, lastQp);//记录数据包出队事件
			TransmitStart(p);//发送数据包

			// update for the next avail time
			m_rdmaPktSent(lastQp, p, m_tInterframeGap);//通知 QP 该数据包已发送，并设置下次可用时�? (m_tInterframeGap)
			/*if (lastQp->IsFinished() || lastQp->GetBytesLeft() == 0) {
				RemoveFlowStat(BuildFlowIdFromQp(lastQp));
			}*/
			totalBytesSent += p->GetSize();
		} else { // no packet to send
			NS_LOG_INFO("PAUSE prohibits send at node " << m_node->GetId());
			Time t = Simulator::GetMaximumSimulationTime();
			for (uint32_t i = 0; i < m_rdmaEQ->GetFlowCount(); i++) {
				Ptr<RdmaQueuePair> qp = m_rdmaEQ->GetQp(i);
				if (qp->GetBytesLeft() == 0)
					continue;
				t = Min(qp->m_nextAvail, t);// 找出所有未完成 QP 中最早的 m_nextAvail
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
			
			// 记录发送的流ID（简化日志）
			if (flag_ENABLE_ROUND_ROBIN_DEBUG && qIndex != 0) {
				uint64_t currentTime = Simulator::Now().GetNanoSeconds();
				// 从数据包中提取流ID
				Ptr<Packet> cp = p->Copy();
				CustomHeader ch(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
				ch.getInt = 1;
				cp->PeekHeader(ch);
				
				std::string flowid = "";
				if (ch.l3Prot == 0x11) { // UDP
					Ptr<SwitchNode> switchNode = DynamicCast<SwitchNode>(m_node);
					if (switchNode) {
						flowid = switchNode->GenerateFlowIdFromPacket(cp, ch);
					}
				}
				
				// 协议类型转换
				std::string protocolStr = "";
				uint8_t protocol = ch.l3Prot;
				if (protocol == 0x06) protocolStr = "TCP";
				else if (protocol == 0x11) protocolStr = "UDP";
				else if (protocol == 0xFC) protocolStr = "ACK";
				else if (protocol == 0xFD) protocolStr = "NACK";
				else if (protocol == 0xFE) protocolStr = "PFC";
				else if (protocol == 0xFF) protocolStr = "QCN";
				else {
					std::ostringstream oss;
					oss << "0x" << std::hex << std::setfill('0') << std::setw(2) << static_cast<uint32_t>(protocol);
					protocolStr = oss.str();
				}
				
				static std::ofstream switchEgressDebugFile;
				static bool switchEgressDebugFileOpened = false;
				if (!switchEgressDebugFileOpened) {
					std::string switchEgressPath = GetOutputDirectory() + "/switch_egress_round_robin_debug.csv";
					switchEgressDebugFile.open(switchEgressPath.c_str(), std::ios::out);
					switchEgressDebugFile << "Time(ns),SwitchID,Port,Queue,Protocol,FlowID" << std::endl;
					switchEgressDebugFileOpened = true;
				}
				switchEgressDebugFile << currentTime << "," << m_node->GetId() << "," << m_ifIndex << "," << qIndex << "," << protocolStr << "," << flowid << std::endl;
			}
			
			if (qIndex == 0) { //this is a pause or cnp, send it immediately! 直接通知交换机数据包出队，不涉及流控或下次可用时间更新
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
			// 记录没有找到可发送的数据包（结果已在DoDequeueRR中记录）
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
		/*for(int k=0;k<pCnt;++k){
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
		}*/
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
		uint64_t currentTime = Simulator::Now().GetNanoSeconds();
		
		// 记录PFC接收事件
		static bool pfcLogFileOpened = false;
		std::ofstream pfcLogFile;
		std::ios_base::openmode mode = pfcLogFileOpened ? std::ios::app : std::ios::out;
		std::string pfcEventsPath = GetOutputDirectory() + "/pfc_events.csv";
		pfcLogFile.open(pfcEventsPath.c_str(), mode);
		if (pfcLogFile.is_open()) {
			if (!pfcLogFileOpened) {
				pfcLogFile << "Time(ns),Event,NodeType,NodeID,Port/DeviceIndex,Queue,Action" << std::endl;
				pfcLogFileOpened = true;
			}
			
			// 区分节点和交换机
			std::string nodeType = (m_node->GetNodeType() == 0) ? "Node" : "Switch";
			
			if (ch.pfc.time > 0) {
				m_tracePfc(1);
				m_paused[qIndex] = true;
				pfcLogFile << currentTime << ",PFC_PAUSE_RECEIVED," << nodeType << "," << m_node->GetId() << "," << m_ifIndex << "," << qIndex << ",Pause" << std::endl;
			} else {
				m_tracePfc(0);
				Resume(qIndex);
				pfcLogFile << currentTime << ",PFC_RESUME_RECEIVED," << nodeType << "," << m_node->GetId() << "," << m_ifIndex << "," << qIndex << ",Resume" << std::endl;
			}
			pfcLogFile.close();
		}
	} else { // non-PFC packets (data, ACK, NACK, CNP...)
		// 记录每个数据包在交换机与网侧的时间
		SwitchTimingTag timingTag;
		if (packet->PeekPacketTag(timingTag)) {
			uint64_t nowNs = Simulator::Now().GetNanoSeconds();
			uint64_t ingressNs = timingTag.GetIngressTimeNs();
			uint64_t egressNs = timingTag.GetEgressTimeNs();

			uint64_t nowWallNs = GetWallClockNs();
			uint64_t ingressWallNs = timingTag.GetIngressWallTimeNs();
			uint64_t egressWallNs = timingTag.GetEgressWallTimeNs();

			if (ingressNs > 0 && egressNs >= ingressNs && nowNs >= egressNs) {
				uint64_t switchTimeNs = egressNs - ingressNs;
				uint64_t netTimeNs = nowNs - egressNs;
				uint64_t totalTimeNs = nowNs - ingressNs;

				uint64_t switchWallTimeNs = 0;
				uint64_t netWallTimeNs = 0;
				uint64_t totalWallTimeNs = 0;
				if (ingressWallNs > 0 && egressWallNs >= ingressWallNs && nowWallNs >= egressWallNs) {
					switchWallTimeNs = egressWallNs - ingressWallNs;
					netWallTimeNs = nowWallNs - egressWallNs;
					totalWallTimeNs = nowWallNs - ingressWallNs;
				}

				std::ofstream logFile;
				std::ios_base::openmode mode = g_switchNetLogOpened ? std::ios::app : std::ios::out;
				std::string logPath = GetOutputDirectory() + "/packet_switch_net_time.csv";
				logFile.open(logPath.c_str(), mode);
				if (logFile.is_open()) {
					if (!g_switchNetLogOpened) {
						logFile << "TimeNs,WallTimeNs,PacketUid,SwitchId,InDev,OutDev,QIndex,PacketSize,"
						        << "SwitchTimeNs,NetTimeNs,TotalTimeNs,SwitchWallTimeNs,NetWallTimeNs,TotalWallTimeNs,"
						        << "NodeType,NodeId,Protocol" << std::endl;
						g_switchNetLogOpened = true;
					}
					logFile << nowNs << "," << nowWallNs << "," << packet->GetUid() << "," << timingTag.GetSwitchId() << ","
					        << timingTag.GetInDev() << "," << timingTag.GetOutDev() << "," << timingTag.GetQIndex() << ","
					        << packet->GetSize() << "," << switchTimeNs << "," << netTimeNs << "," << totalTimeNs << ","
					        << switchWallTimeNs << "," << netWallTimeNs << "," << totalWallTimeNs << ","
					        << m_node->GetNodeType() << "," << m_node->GetId() << "," << static_cast<uint32_t>(ch.l3Prot)
					        << std::endl;
					logFile.close();
				}

				g_switchTimeSumNs += switchTimeNs;
				g_netTimeSumNs += netTimeNs;
				g_switchNetPacketCount += 1;
				if (switchWallTimeNs > 0 || netWallTimeNs > 0) {
					g_switchWallTimeSumNs += switchWallTimeNs;
					g_netWallTimeSumNs += netWallTimeNs;
				}

				if (!g_switchNetSummaryScheduled) {
					Simulator::ScheduleDestroy(MakeEvent(&WriteSwitchNetTimeSummary));
					g_switchNetSummaryScheduled = true;
				}
			}
		}

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
				std::ofstream flowstatsFile;
				// 根据是否是第一次打开文件来选择文件打开模式
        		std::ios_base::openmode mode = isFirstOpen ? std::ios::out : std::ios::app;
				std::string flowStatsPath = GetOutputDirectory() + "/flow_stats.txt";
				flowstatsFile.open(flowStatsPath.c_str(), mode);
				
				if (!flowstatsFile.is_open()) {
        			throw std::runtime_error("Unable to open file for writing flow statistics.");
    			}

				GenerateFlowId(cp,ch,flowstatsFile);
				
				// 如果是第一次打开，设置标志为false，后续追加
            	isFirstOpen = false;
				flowstatsFile.close();
				}
				ret = m_rdmaReceiveCb(packet, ch);
			}
			// TODO we may based on the ret do something
		}
	}
	if(allSteadyStateReached && flag_ENABLE_JUMP_TRANSITION){
		if(flag_read_SwitchStats){
			loadFlowSwitchStats("flow_SwitchStats.txt");
			flag_read_SwitchStats =false;
			
		}
		
		Simulator::ScheduleNow( &ns3::QbbNetDevice::exitSteadyState, this);

		allSteadyStateReached=false;
		transition_cnt++;//增加状态转换计数器
		flag_steady=true;
	}
	if(allSteadyStateReached == false&&flag_steady==false && !flag_ENABLE_JUMP_TRANSITION){
		// 方案1：流完成后重置相关流的稳态状态（不开启跃迁时）
		resetRemainingFlowsSteadyState();
		
		for (NodeList::Iterator it = NodeList::Begin(); it != NodeList::End(); ++it)
		{
			Ptr<Node> node = *it;

			if(node->GetNodeType()==1){//交换机
					node->SwitchStatsCount(0);
			}
		}
		int stageIndex = static_cast<int>(multiSwitchStats.size());
		SwitchStatsPair oneRun;
		oneRun.normalStats = SwitchStats;
		oneRun.exitStats = exit_SwitchStats;
		multiSwitchStats.push_back(oneRun);
		LogSwitchStatsDiff(oneRun.normalStats, oneRun.exitStats, stageIndex);

		allSteadyStateReached=false;
			cout<<"System exit"<<endl;
			flag_steady=true;

		std::ofstream flowstatsFile;
		// 根据是否是第一次打开文件来选择文件打开模式
		std::ios_base::openmode mode = isFirstOpen ? std::ios::out : std::ios::app;
		std::string flowStatsPath = GetOutputDirectory() + "/flow_stats.txt";
		flowstatsFile.open(flowStatsPath.c_str(), mode);	
		if (!flowstatsFile.is_open()) {
			throw std::runtime_error("Unable to open file for writing flow statistics.");
		}
		// 如果是第一次打开，设置标志为false，后续追加
		isFirstOpen = false;
		
		// 记录仿真结束时的交换机状态
		if (flag_ENABLE_SWITCH_QUEUE_LOGGING) {
			uint64_t currentTime = Simulator::Now().GetNanoSeconds();
			LogAllSwitchQueueInfo(flowstatsFile, currentTime, "Simulation End");
		}
		
		flowstatsFile << "System exit"<<endl;
		flowstatsFile.close();

		SwitchStats.clear();
		exit_SwitchStats.clear();
	}
	return;
}

//生成flowid和获取数据包大小
void QbbNetDevice::GenerateFlowId(Ptr<Packet> cp,CustomHeader& header,std::ofstream& flowstatsFile)
{
	uint8_t protocol = header.l3Prot; // 获取协议�?
    uint32_t srcIp = header.sip; // 获取源IP地址
    uint32_t dstIp = header.dip; // 获取目标IP地址
	//将IP转换成ID
	uint32_t srcId = ((srcIp >> 8) & 0xffff);
	uint32_t dstId = ((dstIp >> 8) & 0xffff);
    uint16_t srcPort = 0; // 源端口号
    uint16_t dstPort = 0; // 目标端口�?
	//获取数据包大�?
	uint16_t packetSize = 0;
	// 根据协议类型处理传输层头�?
    if (protocol == 0x11) // UDP协议号为17
    {
        srcPort = header.udp.sport; // 获取源端口号
        dstPort = header.udp.dport; // 获取目标端口�?
		packetSize = cp->GetSize();
		//packetSize = header.udp.payload_size;
		//packetSize = header.m_payloadSize;
    }
    else
    {
        NS_LOG_INFO("不支持的协议: " << static_cast<uint32_t>(protocol)); // 记录不支持的协议
        return ; // 返回默认值表示不支持的协�?
    }

    // 将所有信息组合成一个字符串
    std::ostringstream oss;
    oss << srcId << "-" << dstId << "-" << srcPort << "-" << dstPort;

    // 使用哈希函数将组合后的字符串转换为唯一整数ID
    /*std::hash<std::string> hasher;
    uint32_t flowid = static_cast<uint32_t>(hasher(oss.str()));*/
	std::string flowid = oss.str();
    
	/*if(flowid == "0-1-0-0"){
		cout << header.udp.seq<<endl;
		flowstatsFile <<header.udp.seq<<endl;
	}*/

	// 启动跃迁逻辑
	#ifdef ENABLE_JUMP_TRANSITION
    //计算速率
	onPacketReceived(flowid, packetSize,flowstatsFile); 
	#else
    // 可选：记录日志或保持静默
    // NS_LOG_DEBUG("Jump transition is disabled via macro.");
	#endif
	
}

void QbbNetDevice::onPacketReceived(std::string flowid, uint16_t packetSize,std::ofstream& flowstatsFile) {
    uint64_t currentTime = Simulator::Now().GetNanoSeconds();
    
    // 静态标志：记录是否已经记录过仿真开始时的交换机状态
    static bool simulationStartLogged = false;
    if (!simulationStartLogged && flag_ENABLE_SWITCH_QUEUE_LOGGING) {
        simulationStartLogged = true;
        LogAllSwitchQueueInfo(flowstatsFile, currentTime, "Simulation Start");
    }
    
    // 检查该流是否存在
    auto it = flowStats.find(flowid);
    auto filter_it =filter.find(flowid);
    if (it == flowStats.end()&&filter_it==filter.end()){
        // 流不存在，创建新流
        FlowStat newStat;
        newStat.byteCount = packetSize;
        newStat.timestamp = currentTime;
        newStat.ifnewpacket = true;
        newStat.steadyStateReached = false;
        newStat.steadyCooldown = 0;
        newStat.lastPacketTime = currentTime;
        newStat.lastPacketSize = packetSize;
        // 初始化固定时间窗口
        newStat.monitorWindowStartTime = currentTime;
        newStat.monitorWindowSize = 3015; // 默认3000纳秒（对应phase:3000）
        newStat.monitorWindowBytes = 0;
        newStat.monitorWindowPacketCount = 0;
        flowStats[flowid] = newStat;
    }
	
	// 如果启用速率计算，则计算速率
	if (flag_ENABLE_QBB_DEVICE_RATE_CALC) {
	calculateRate(flowid,packetSize,flowstatsFile);
	}
}

// 计算每条流速率并输出
void QbbNetDevice::calculateRate(std::string flowid, uint16_t packetSize,std::ofstream& flowstatsFile) {
    uint64_t currentTime =  Simulator::Now().GetNanoSeconds();

    //判断系统稳态的变量
	allSteadyStateReached = flowStats.size()>0;

    // 【修改】基于固定时间窗口的速率计算（替代滑动窗口）
    auto currentFlowIt = flowStats.find(flowid);
    if (currentFlowIt != flowStats.end()) {
        FlowStat& stat = currentFlowIt->second;
        
        // 如果是新流，初始化固定时间窗口
        if (stat.monitorWindowStartTime == 0) {
            stat.monitorWindowStartTime = currentTime;
            stat.monitorWindowSize = 3015; // 默认3000纳秒（对应phase:3000）
            stat.monitorWindowBytes = 0;
            stat.monitorWindowPacketCount = 0;
        }
        
        // 保存上一个数据包的时间，用于计算瞬时速率（在更新lastPacketTime之前）
        uint64_t prevPacketTime = stat.lastPacketTime;
        uint64_t prevPacketSize = stat.lastPacketSize;
        
        // 更新lastPacketTime（每次数据包到达时都更新）
        stat.lastPacketTime = currentTime;
        stat.lastPacketSize = packetSize;

        // 检查当前时间是否在监测时间窗口内
        uint64_t windowEndTime = stat.monitorWindowStartTime + stat.monitorWindowSize;
        bool inWindow = (currentTime >= stat.monitorWindowStartTime && currentTime < windowEndTime);
        
        double avgRate = 0.0;
        double instantRate = 0.0;
        
        if (inWindow) {
            // 在监测时间窗口内，累计字节数
            stat.monitorWindowBytes += packetSize;
            stat.monitorWindowPacketCount++;
            
            // 计算瞬时速率（基于当前数据包和上一个数据包的时间间隔）
            if (prevPacketTime > 0 && currentTime > prevPacketTime) {
                uint64_t interval = currentTime - prevPacketTime;
                if (interval > 0) {
                    instantRate = static_cast<double>(packetSize) * 8.0 / interval; // Gbps
                }
            }
        } else {
            // 监测时间窗口已结束，计算平均速率
            if (stat.monitorWindowBytes > 0 && stat.monitorWindowSize > 0) {
                // 计算固定时间窗口内的平均速率
                avgRate = static_cast<double>(stat.monitorWindowBytes) * 8.0 / stat.monitorWindowSize; // Gbps
            }
            
            // 计算瞬时速率（基于当前数据包和上一个数据包的时间间隔）
            if (prevPacketTime > 0 && currentTime > prevPacketTime) {
                uint64_t interval = currentTime - prevPacketTime;
                if (interval > 0) {
                    instantRate = static_cast<double>(packetSize) * 8.0 / interval; // Gbps
                }
            }
            
                    // 输出速率（如果计算出了有效速率）
                    if (avgRate > 0.0 || instantRate > 0.0) {
                        double maxReasonableRate = 100.0; // Gbps
                        if (avgRate <= maxReasonableRate && instantRate <= maxReasonableRate) {
                            // 输出速率
                            cout << "Flow ID: " << flowid << " - AvgRate: " << avgRate << " Gbps, InstantRate: " << instantRate 
                                 << " Gbps, WindowStart: " << stat.monitorWindowStartTime 
                                 << ", WindowEnd: " << windowEndTime << ", WindowBytes: " << stat.monitorWindowBytes
                                 << ", PacketCount: " << stat.monitorWindowPacketCount << ", currentTime: " << currentTime << endl;
                            flowstatsFile << "Flow ID: " << flowid << " - AvgRate: " << avgRate << " Gbps, InstantRate: " << instantRate 
                                          << " Gbps, WindowStart: " << stat.monitorWindowStartTime 
                                          << ", WindowEnd: " << windowEndTime << ", WindowBytes: " << stat.monitorWindowBytes
                                          << ", PacketCount: " << stat.monitorWindowPacketCount << ", currentTime: " << currentTime << std::endl;
                            
                            // 输出速率到CSV文件
                            LogReceiverRateToCsv(flowid, avgRate, instantRate, stat.monitorWindowStartTime, 
                                                 windowEndTime, stat.monitorWindowBytes, 
                                                 stat.monitorWindowPacketCount, currentTime);
                            
                            // 记录交换机队列信息（只记录与当前流相关的交换机）
                            if (flag_ENABLE_SWITCH_QUEUE_LOGGING) {
                                LogSwitchQueueInfo(flowstatsFile, currentTime, flowid);
                            }
                    
                    // 保存速率历史（用于稳态检测，使用平均速率）
                    stat.rate.push_back(avgRate);
				if(stat.rate.size() > static_cast<size_t>(stat.size)){
					stat.rate.erase(stat.rate.begin());
				}
                    
                    // 稳态检测逻辑
				bool immediateExit = false;
				if (stat.rate.size() >= 2) {
					double latestRate = stat.rate.back();
					double prevRate = *(stat.rate.end() - 2);
					double denomPair = std::max(std::max(latestRate, prevRate), kSteadyRateEpsilon);
					double relativeDiff = std::fabs(latestRate - prevRate) / denomPair;
					if (relativeDiff > kSteadyRelativeThreshold) {
						stat.steadyStateReached = false;
						stat.steadyCooldown = 0;
						allSteadyStateReached = false;
						immediateExit = true;
					}
				}
				if(!immediateExit && stat.rate.size() >= static_cast<size_t>(stat.size)){
					// 获取最小值和最大值
					auto result = std::minmax_element(stat.rate.begin(), stat.rate.end());
					double minRate = *result.first;
					double maxRate = *result.second;
                        double avgRateForSteady = std::accumulate(stat.rate.begin(), stat.rate.end(), 0.0) / static_cast<double>(stat.rate.size());
                        double denom = std::max(avgRateForSteady, kSteadyRateEpsilon);
					double relativeSpan = (maxRate - minRate) / denom;
					if(relativeSpan  <= kSteadyRelativeThreshold ){
						stat.steadyStateReached = true;//流进入稳态
						stat.steadyCooldown = kSteadyCooldownCycles;
					}else {
						if (stat.steadyCooldown > 0) {
							stat.steadyCooldown--;
						} else {
							stat.steadyStateReached = false;  // 如果速率波动超过阈值，重置稳态状态
							allSteadyStateReached = false;   // 任何一个流未进入稳态，系统不再稳态
						}
					}
                    }
                }
				}
				
            // 重置监测时间窗口，开始新的窗口（当前数据包计入新窗口）
            stat.monitorWindowStartTime = currentTime;
            stat.monitorWindowBytes = packetSize;
            stat.monitorWindowPacketCount = 1;
        }
    }  // 关闭 if (currentFlowIt != flowStats.end())

    // 更新 allSteadyStateReached（无论是否计算速率都需要执行）
	for (auto& entry_SteadyState : flowStats) {				
		if (!entry_SteadyState.second.steadyStateReached) {
			allSteadyStateReached = false;
			break;  // 一旦发现一个流未进入稳态，直接跳出循环
		}
	}
    // 修复：无条件检查 flow_fin_unack，确保系统不会在接收端还在接收数据包时进入稳态
    // 无论是否开启跃迁，都应该检查这个条件，因为这是网络状态的客观事实
    if(flow_fin_unack.size()!=0)
	 	allSteadyStateReached=false;
	// 判断系统是否刚刚进入稳态
    if (allSteadyStateReached&&flag_steady) {
		flag_steady=false;
        steadyStateStartTime = currentTime;
        cout << "System entered steady state at time: " << steadyStateStartTime << " ns" << endl;
		flowstatsFile << "System entered steady state at time: " << steadyStateStartTime << " ns" << endl;
		//计算剩余流量大小除以已测量的速度均值，获取最小流完成时间uu
		//如果在这里进行，就只计算了接收端这一个节点的，所以我们要在外部计算所有节点的流完成时间
		calculateMintime();
        // 修复：检查最小流完成时间是否有效
        if(flowMinTime < 1.79769e+308 && flowMinTime > 0.0 && std::isfinite(flowMinTime)){
		cout << "最小流完成时间: " <<std::fixed << std::setprecision(6)<< flowMinTime <<endl;
		flowstatsFile <<"最小流完成时间: " <<std::fixed << std::setprecision(6)<< flowMinTime <<endl;
		next_trans_avail=currentTime+flowMinTime;
		//flowstatsFile <<"判断最小流完成时间的次�?"<<number_test<<endl;
            // transition_delay 存储的是传输时间（基于配置速率），用于计算加速时跳过的字节数
            // transMinTime 是基于配置速率（qp->m_rate）计算的传输时间，单位为纳秒
		transition_delay.push_back(transMinTime);
        } else {
            // 如果没有找到有效的流完成时间，可能的原因：
            // 1. 所有发送端都已发送完所有数据（GetBytesLeft() == 0）
            // 2. 没有有效的速率历史（rate.size() == 0）
            // 注意：发送端完成 ≠ 接收端完成，接收端可能还在接收数据包
            cout << "最小流完成时间: 未找到有效值（可能所有发送端已发送完所有数据，或没有有效速率历史）" << endl;
            flowstatsFile <<"最小流完成时间: 未找到有效值（可能所有发送端已发送完所有数据，或没有有效速率历史）" << endl;
            // 设置一个默认的转换时间，避免后续计算错误
            next_trans_avail = currentTime + 1000000; // 默认1毫秒
            transition_delay.push_back(0);
        }
		flowMinTime = 1.79769e+308;
    }
	

    // 判断系统是否退出稳态
    
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

void QbbNetDevice::TimeDelaySwitchStats(){
	if((transition_cnt-1)<multiSwitchStats.size()){
		double max_time = 0;
		auto& exitStatsMap = multiSwitchStats[transition_cnt - 1].exitStats;
		for (const auto& [switchId, stat] : exitStatsMap) {
			auto& normalStatsMap = multiSwitchStats[transition_cnt - 1].normalStats;
			auto it_2 = normalStatsMap.find(switchId);
			if (it_2 != normalStatsMap.end()) {
				uint32_t secondKey = it_2->first;
				SwitchStat& secondValue = it_2->second;
				for (int i = 0; i < pCnt; ++i) {
					for (int j = 0; j < qCnt; ++j) {
						if(stat.ingress_bytes[i][j]>secondValue.ingress_bytes[i][j]){
							double time_temp = stat.ingress_bytes[i][j]-secondValue.ingress_bytes[i][j] / (stat.dequeueRateIngress[i][j] * stat.bandwidth[j] / 8);//bytes/s
							max_time=max(max_time,time_temp);
						}
					}
				}
			}
			
		}
		//
        Simulator::Schedule(NanoSeconds(max_time), &QbbNetDevice::ContinueAfterDelay, this,max_time);	
	}
}

// 新增：延迟后的逻辑
void QbbNetDevice::ContinueAfterDelay(double max_time) {
    std::cout<<"Waited time = " << max_time << " seconds. Continuing...";
}

void QbbNetDevice::exitSteadyState(){
	
	// 打开文件用于输出日志
	std::ofstream flowstatsFile;
	std::ios_base::openmode mode = isFirstOpen ? std::ios::out : std::ios::app;
	std::string flowStatsPath = GetOutputDirectory() + "/flow_stats.txt";
	flowstatsFile.open(flowStatsPath.c_str(), mode);
	if (!flowstatsFile.is_open()) {
		throw std::runtime_error("Unable to open file for writing flow statistics.");
	}
	if (isFirstOpen) {
		isFirstOpen = false;
	}
	
	// 方案1：流完成后重置相关流的稳态状态（开启跃迁时）
	resetRemainingFlowsSteadyState();
	
    //更新流完成状态
	for (NodeList::Iterator it = NodeList::Begin(); it != NodeList::End(); ++it)
    {
        Ptr<Node> node = *it;

        // 遍历�? Node 的所有NetDevice（设备）
        for (uint32_t i = 0; i < node->GetNDevices(); ++i)
        {
            Ptr<QbbNetDevice> qbbDev = DynamicCast<QbbNetDevice>(node->GetDevice(i));
            if (!qbbDev){
				continue;
			}
			else if(node->GetNodeType()!=0){
				auto iter = NodeStats.find(node->GetId());
				if(iter!=NodeStats.end()){
					DataRate queue_rate(iter->second.rate); //获取节点的队列速率
					queue_rate-= qbbDev->m_bps; //减去设备的带宽
					
					Time latency_fix=qbbDev->m_bps.CalculateBytesTxTime(transition_delay[transition_cnt]*queue_rate.GetBitRate()) ;
					node_latency_fix[node->GetId()]=latency_fix;
				}
				
			}else{
				// 获取该设备的 RDMA 事件队列
				Ptr<RdmaEgressQueue> rdmaEQ = qbbDev->m_rdmaEQ;
				if (!rdmaEQ) continue;
	
				uint32_t qIndex;
				uint32_t fcount = rdmaEQ->m_qpGrp->GetN();
				for (qIndex = 0; qIndex < fcount; qIndex++) {
					uint32_t idx = qIndex ;
					Ptr<RdmaQueuePair> qp = rdmaEQ->m_qpGrp->Get(idx);//qp里面也有很多条流
	
				//获取flowid
					uint32_t srcIp = qp->sip.Get(); // 获取源IP地址
					uint32_t dstIp = qp->dip.Get(); // 获取目标IP地址
				//将IP转换成ID
					uint32_t srcId = ((srcIp >> 8) & 0xffff);
					uint32_t dstId = ((dstIp >> 8) & 0xffff);
					uint16_t srcPort = qp->sport; // 源端口号
					uint16_t dstPort = qp->dport; // 目标端口�?
					std::ostringstream oss;
					oss << srcId << "-" << dstId << "-" << srcPort << "-" << dstPort;
					std::string flowid = oss.str();
	
					map<std::string, FlowStat>::iterator iter=flowStats.find(flowid);
					if(iter!=flowStats.end()){
						// 检查流是否已经完成
						if(qp->GetBytesLeft() > 0) {
							// 只有未完成的流才更新状态
							double sum = std::accumulate(iter->second.rate.begin(), iter->second.rate.end(), 0.0); // 计算总和
							double avg = sum / iter->second.rate.size();

							// 记录加速前的状态
							uint64_t bytesLeftBefore = qp->GetBytesLeft();
							uint64_t sndNxtBefore = qp->snd_nxt;
							
							// 加速：根据配置速率和传输时间，计算跳过的字节数
							// transition_delay[transition_cnt-1] 是基于配置速率（qp->m_rate）计算的传输时间（纳秒）
							// 得到稳态期间传输的字节数，累加到 snd_nxt（已发送的下一个字节序号），即更新所有流的状态（跃迁）
							// 公式：字节数 = (配置速率 bps / 8) * (传输时间 ns / 1e9) = 配置速率 bps * 传输时间 ns / 8e9
							double acceleratedBytes = qp->m_rate.GetBitRate()/8e9*transition_delay[transition_cnt-1];
							qp->snd_nxt += acceleratedBytes;
							
							// 修复：限制 snd_nxt 不超过 m_size，保持一致性
							/*if (qp->snd_nxt > qp->m_size) {
								qp->snd_nxt = qp->m_size;
							}
							
							// 修复：如果加速后 snd_nxt >= m_size 或 GetBytesLeft() <= 1000，手动添加 flow_fin_unack
							// 因为加速是直接修改 snd_nxt，跳过了 GetNxtPacket() 的调用，所以不会自动添加 flow_fin_unack
							// 需要手动添加，确保 flow_fin_unack 机制正常工作，防止在接收端还未收到所有数据包时进入稳态
							// 如果 GetBytesLeft() <= 1000，说明流已经接近完成（只剩最后一个包），在 flowCompletiontime() 中会被忽略（trans_time = 0）
							// 这种情况下也应该添加 flow_fin_unack，与 flowCompletiontime() 的逻辑保持一致
							if (qp->snd_nxt >= qp->m_size || qp->GetBytesLeft() <= 1005) {
								auto fin_unack_it = flow_fin_unack.find(flowid);
								if (fin_unack_it == flow_fin_unack.end()) {
									flow_fin_unack.insert(flowid);
									if (qp->snd_nxt >= qp->m_size) {
										cout << "Flow ID: " << flowid << " - 加速后发送完成，添加到 flow_fin_unack (snd_nxt=" 
											 << qp->snd_nxt << ", m_size=" << qp->m_size << ")" << endl;
										flowstatsFile << "Flow ID: " << flowid << " - 加速后发送完成，添加到 flow_fin_unack (snd_nxt=" 
													  << qp->snd_nxt << ", m_size=" << qp->m_size << ")" << std::endl;
									} else {
										cout << "Flow ID: " << flowid << " - 接近完成（GetBytesLeft() <= 1000），添加到 flow_fin_unack (snd_nxt=" 
											 << qp->snd_nxt << ", m_size=" << qp->m_size << ", bytesLeft=" << qp->GetBytesLeft() << ")" << endl;
										flowstatsFile << "Flow ID: " << flowid << " - 接近完成（GetBytesLeft() <= 1000），添加到 flow_fin_unack (snd_nxt=" 
													  << qp->snd_nxt << ", m_size=" << qp->m_size << ", bytesLeft=" << qp->GetBytesLeft() << ")" << std::endl;
									}
								}
							}*/
							
							// 输出加速信息
							cout << "Flow ID: " << flowid << " - 加速前: bytesLeft=" << bytesLeftBefore 
								 << ", snd_nxt=" << sndNxtBefore << ", 加速字节数=" << acceleratedBytes 
								 << ", 加速后: snd_nxt=" << qp->snd_nxt << ", bytesLeft=" << qp->GetBytesLeft() << endl;
							flowstatsFile << "Flow ID: " << flowid << " - 加速前: bytesLeft=" << bytesLeftBefore 
										  << ", snd_nxt=" << sndNxtBefore << ", 加速字节数=" << acceleratedBytes 
										  << ", 加速后: snd_nxt=" << qp->snd_nxt << ", bytesLeft=" << qp->GetBytesLeft() << std::endl;

							// 重置流统计
							iter->second.byteCount = 0;
							iter->second.timestamp = Simulator::Now().GetNanoSeconds();
							iter->second.rate.clear();  // 清空 rate 历史
							iter->second.steadyStateReached = false;
							iter->second.ifnewpacket = false;
							// 重置固定时间窗口相关字段
							uint64_t resetTime = Simulator::Now().GetNanoSeconds();
							iter->second.monitorWindowStartTime = resetTime;
							iter->second.monitorWindowSize = 3000; // 默认3000纳秒
							iter->second.monitorWindowBytes = 0;
							iter->second.monitorWindowPacketCount = 0;
							iter->second.lastPacketTime = resetTime;
							iter->second.lastPacketSize = 0;
						} else {
							// 流已完成，输出完成信息
							cout << "Flow ID: " << flowid << " - 流已完成 (GetBytesLeft() == 0)" << endl;
							flowstatsFile << "Flow ID: " << flowid << " - 流已完成 (GetBytesLeft() == 0)" << std::endl;
							// 流已完成，删除统计（流完成时会在 rdma-hw.cc 中删除，这里也可以提前删除）
							 flowStats.erase(flowid);
						}
						
						//删除流
						//flowStats.erase(flowid);
						
						/*if(qp->IsFinished()){
							filter.insert(flowid);
						}*/
							
					}
					
				}
			}

        }
    }
	allSteadyStateReached=false;
	
	// 输出退出稳态时的流状态统计
	uint32_t activeFlowCount = 0;
	uint32_t completedFlowCount = 0;
	for (NodeList::Iterator it = NodeList::Begin(); it != NodeList::End(); ++it)
	{
		Ptr<Node> node = *it;
		if (node->GetNodeType() != 0) continue;
		
		for (uint32_t i = 0; i < node->GetNDevices(); ++i)
		{
			Ptr<QbbNetDevice> qbbDev = DynamicCast<QbbNetDevice>(node->GetDevice(i));
			if (!qbbDev) continue;
			
			Ptr<RdmaEgressQueue> rdmaEQ = qbbDev->m_rdmaEQ;
			if (!rdmaEQ) continue;
			
			uint32_t fcount = rdmaEQ->m_qpGrp->GetN();
			for (uint32_t qIndex = 0; qIndex < fcount; qIndex++) {
				Ptr<RdmaQueuePair> qp = rdmaEQ->m_qpGrp->Get(qIndex);
				if (qp->GetBytesLeft() > 0) {
					activeFlowCount++;
				} else {
					completedFlowCount++;
				}
			}
		}
	}
	cout << "退出稳态 - 活跃流数量: " << activeFlowCount << ", 已完成流数量: " << completedFlowCount << endl;
	flowstatsFile << "退出稳态 - 活跃流数量: " << activeFlowCount << ", 已完成流数量: " << completedFlowCount << std::endl;
	
	for (NodeList::Iterator itSwitch = NodeList::Begin(); itSwitch != NodeList::End(); ++itSwitch)
	{
		Ptr<Node> node = *itSwitch;
		if (node->GetNodeType() == 1) {
			node->SwitchStatsCount(0);
		}
	}
	if (transition_cnt > 0) {
		LogSwitchStatsDiff(SwitchStats, exit_SwitchStats, transition_cnt - 1);
	} else {
		LogSwitchStatsDiff(SwitchStats, exit_SwitchStats, transition_cnt);
	}
		cout<<"System exit"<<endl;

	// 清理 flow_fin_unack，避免阻止进入稳态
	//flow_fin_unack.clear();

	//补偿
	//UpdateSwitchStats();

	//时延
	//TimeDelaySwitchStats();

	// 记录仿真结束时的交换机状态
	if (flag_ENABLE_SWITCH_QUEUE_LOGGING) {
		uint64_t currentTime = Simulator::Now().GetNanoSeconds();
		LogAllSwitchQueueInfo(flowstatsFile, currentTime, "Simulation End");
    }
	
	flowstatsFile<<"System exit"<<endl;
	flowstatsFile.close();
	
		/*for (NodeList::Iterator it = NodeList::Begin(); it != NodeList::End(); ++it)
		{
			Ptr<Node> node = *it;

			if(node->GetNodeType()==1){//交换机
					node->SwitchStatsCount(0);
			}
		}
		flowstatsFile<<"SwitchStats"<<endl;
		PrintAllSwitchStats(SwitchStats,flowstatsFile);
		SwitchStats.clear();
		flowstatsFile<<"exit_SwitchStats"<<endl;
		PrintAllSwitchStats(exit_SwitchStats,flowstatsFile);
		exit_SwitchStats.clear();
		flowstatsFile.close();	*/

}

// 方案1：流完成后重置相关流的稳态状态
// 检测是否有流完成，如果有，重置所有剩余流的稳态状态
void QbbNetDevice::resetRemainingFlowsSteadyState(){
	// 先遍历一遍，检查是否有流完成
	bool hasFlowCompleted = false;
	for (NodeList::Iterator it = NodeList::Begin(); it != NodeList::End(); ++it)
	{
		Ptr<Node> node = *it;
		if (node->GetNodeType() != 0) continue; // 只检查主机节点

		for (uint32_t i = 0; i < node->GetNDevices(); ++i)
		{
			Ptr<QbbNetDevice> qbbDev = DynamicCast<QbbNetDevice>(node->GetDevice(i));
			if (!qbbDev) continue;

			Ptr<RdmaEgressQueue> rdmaEQ = qbbDev->m_rdmaEQ;
			if (!rdmaEQ) continue;

			uint32_t fcount = rdmaEQ->m_qpGrp->GetN();
			for (uint32_t qIndex = 0; qIndex < fcount; qIndex++) {
				Ptr<RdmaQueuePair> qp = rdmaEQ->m_qpGrp->Get(qIndex);
				
				uint32_t srcIp = qp->sip.Get();
				uint32_t dstIp = qp->dip.Get();
				uint32_t srcId = ((srcIp >> 8) & 0xffff);
				uint32_t dstId = ((dstIp >> 8) & 0xffff);
				uint16_t srcPort = qp->sport;
				uint16_t dstPort = qp->dport;
				std::ostringstream oss;
				oss << srcId << "-" << dstId << "-" << srcPort << "-" << dstPort;
				std::string flowid = oss.str();

				map<std::string, FlowStat>::iterator iter = flowStats.find(flowid);
				if (iter != flowStats.end() && qp->GetBytesLeft() == 0) {
					hasFlowCompleted = true;
					break;
				}
			}
			if (hasFlowCompleted) break;
		}
		if (hasFlowCompleted) break;
	}
	
	// 如果有流完成，重置所有剩余流的稳态状态
	if (hasFlowCompleted) {
		for (NodeList::Iterator it = NodeList::Begin(); it != NodeList::End(); ++it)
		{
			Ptr<Node> node = *it;
			if (node->GetNodeType() != 0) continue; // 只检查主机节点

			for (uint32_t i = 0; i < node->GetNDevices(); ++i)
			{
				Ptr<QbbNetDevice> qbbDev = DynamicCast<QbbNetDevice>(node->GetDevice(i));
				if (!qbbDev) continue;

				Ptr<RdmaEgressQueue> rdmaEQ = qbbDev->m_rdmaEQ;
				if (!rdmaEQ) continue;

				uint32_t fcount = rdmaEQ->m_qpGrp->GetN();
				for (uint32_t qIndex = 0; qIndex < fcount; qIndex++) {
					Ptr<RdmaQueuePair> qp = rdmaEQ->m_qpGrp->Get(qIndex);
					
					uint32_t srcIp = qp->sip.Get();
					uint32_t dstIp = qp->dip.Get();
					uint32_t srcId = ((srcIp >> 8) & 0xffff);
					uint32_t dstId = ((dstIp >> 8) & 0xffff);
					uint16_t srcPort = qp->sport;
					uint16_t dstPort = qp->dport;
					std::ostringstream oss;
					oss << srcId << "-" << dstId << "-" << srcPort << "-" << dstPort;
					std::string flowid = oss.str();

					map<std::string, FlowStat>::iterator iter = flowStats.find(flowid);
					if (iter != flowStats.end() && qp->GetBytesLeft() > 0) {
						// 重置剩余流的稳态状态，强制重新积累速率历史
						iter->second.rate.clear();  // 清空速率历史
						iter->second.steadyStateReached = false;  // 重置稳态标志
						iter->second.steadyCooldown = 0;  // 重置冷却周期
						// 重置固定时间窗口相关字段
						uint64_t resetTime = Simulator::Now().GetNanoSeconds();
						iter->second.monitorWindowStartTime = resetTime;
						iter->second.monitorWindowSize = 3000; // 默认3000纳秒
						iter->second.monitorWindowBytes = 0;
						iter->second.monitorWindowPacketCount = 0;
						iter->second.lastPacketTime = resetTime;
						iter->second.lastPacketSize = 0;
					}
				}
			}
		}
	}
}

//1.新流进入能否，心流进入会不会影响我们的稳态 
//2.监视交换机上每条队列的延迟更新
// o---0---o
//200   100 
// 100gbps
//	
//3.tr 数据包级别的事件观测 混合粒度 fin包
// 
//



//计算剩余流量大小除以已测量的速度均值，获取最小时间
//每一个设备qbbnetdevice都对应一个m_rdmaEQ，也就是要计算所有设备找出最小流完成时间
void QbbNetDevice::calculateMintime(){
	// 修复：重置最小流完成时间为初始值，确保每次计算都从初始值开始
	flowMinTime = 1.79769e+308;
	transMinTime = 0;
	
	// 遍历所有Node（网络节点）
    for (NodeList::Iterator it = NodeList::Begin(); it != NodeList::End(); ++it)
    {
        Ptr<Node> node = *it;

		if(node->GetNodeType()==1){//交换机
				node->SwitchStatsCount(1);
		}

        // 遍历�? Node 的所有 NetDevice（设备）
        for (uint32_t i = 0; i < node->GetNDevices(); ++i)
        {
            Ptr<QbbNetDevice> qbbDev = DynamicCast<QbbNetDevice>(node->GetDevice(i));


            if (!qbbDev|| node->GetNodeType()!=0) continue; // 如果不是 QbbNetDevice或者主机端，则跳过

			if (node->GetNodeType()==1){
				int i=1;
			}

            // 获取该设备的 RDMA 事件队列
            Ptr<RdmaEgressQueue> rdmaEQ = qbbDev->m_rdmaEQ;
            if (!rdmaEQ) continue;

            // 遍历 RDMA 事件队列中的所有流，计算最小流完成时间
            flowCompletiontime(rdmaEQ);
        }
    }
}


void QbbNetDevice::flowCompletiontime(Ptr<RdmaEgressQueue> rdmaEQ){
	uint32_t qIndex;
	uint32_t fcount = rdmaEQ->m_qpGrp->GetN();
		for (qIndex = 0; qIndex < fcount; qIndex++) {
			uint32_t idx = qIndex ;
			Ptr<RdmaQueuePair> qp = rdmaEQ->m_qpGrp->Get(idx);//qp里面也有很多条流

			//获取flowid
			uint32_t srcIp = qp->sip.Get(); // 获取源IP地址
			uint32_t dstIp = qp->dip.Get(); // 获取目标IP地址
			//将IP转换成ID
			uint32_t srcId = ((srcIp >> 8) & 0xffff);
			uint32_t dstId = ((dstIp >> 8) & 0xffff);
			uint16_t srcPort = qp->sport; // 源端口号
			uint16_t dstPort = qp->dport; // 目标端口号
			std::ostringstream oss;
    		oss << srcId << "-" << dstId << "-" << srcPort << "-" << dstPort;
			std::string flowid = oss.str();

			map<std::string, FlowStat>::iterator iter=flowStats.find(flowid);
			if(iter!=flowStats.end()){
				// 修复：添加边界检查，避免除零和空速率历史
				// GetBytesLeft() == 0 表示发送端已发送完所有数据，但接收端可能还在接收数据包
				if(iter->second.rate.size() == 0 || qp->GetBytesLeft() == 0){
					continue; // 跳过没有速率历史或发送端已发送完所有数据的流
				}
				
				//流的实际速率（FlowStat::rate）是通过测量接收到的数据包（byteCount）计算的，单位为 Gbps
				//m_rate 是配置速率，反映 RDMA 队列对的分配带宽，通常是稳定的、协议定义的值，适合用于更新发送进度
				double sum = std::accumulate(iter->second.rate.begin(), iter->second.rate.end(), 0.0); // 计算总和
    			double avg = sum / iter->second.rate.size();
				
				// 修复：检查平均速率是否有效（大于0）
				if(avg <= 0.0){
					continue; // 跳过无效的平均速率
				}
				
				double trans_time=0;
				if(qp->GetBytesLeft()>1000) //至少还有一个包在发送端
				//确保流还有足够的剩余数据需要传输，避免将接近完成的流（可能只剩控制包，如 FIN）计入主要传输时间
					trans_time = static_cast<double>(qp->GetBytesLeft()-1000) / qp->m_rate.GetBitRate()*1e9*8;//bps
				double time=static_cast<double>(qp->GetBytesLeft())*8 / avg;
				
				// 修复：检查计算结果是否有效（非NaN、非无穷大、大于0）
				if(std::isfinite(time) && time > 0.0 && time < flowMinTime){
					flowMinTime =time;
					transMinTime=trans_time;
				}
					
			}
		}

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
	if (!m_nextSend.IsExpired() && t < Time(m_nextSend.GetTs())) {
		Simulator::Cancel(m_nextSend);
		Time delta = t < Simulator::Now() ? Time(0) : t - Simulator::Now();
		m_nextSend = Simulator::Schedule(delta, &QbbNetDevice::DequeueAndTransmit, this);
	}
}

// 记录交换机队列信息（只记录与指定流相关的交换机）
void QbbNetDevice::LogSwitchQueueInfo(std::ofstream& flowstatsFile, uint64_t currentTime, const std::string& flowid) {
	// 从flowid中提取源和目的节点ID
	// flowid格式: "srcId-dstId-srcPort-dstPort"
	std::istringstream iss(flowid);
	std::string token;
	std::vector<std::string> tokens;
	while (std::getline(iss, token, '-')) {
		tokens.push_back(token);
	}
	
	if (tokens.size() < 2) {
		return; // flowid格式不正确
	}
	
	uint32_t srcId = std::stoul(tokens[0]);
	uint32_t dstId = std::stoul(tokens[1]);
	
	// 找到源和目的节点
	Ptr<Node> srcNode = nullptr;
	Ptr<Node> dstNode = nullptr;
	for (NodeList::Iterator it = NodeList::Begin(); it != NodeList::End(); ++it) {
		Ptr<Node> node = *it;
		if (node->GetId() == srcId && node->GetNodeType() == 0) {
			srcNode = node;
		}
		if (node->GetId() == dstId && node->GetNodeType() == 0) {
			dstNode = node;
		}
	}
	
	if (!srcNode || !dstNode) {
		return; // 找不到源或目的节点
	}
	
	// 遍历所有交换机节点，检查是否有与当前流相关的队列数据
	for (NodeList::Iterator it = NodeList::Begin(); it != NodeList::End(); ++it) {
		Ptr<Node> node = *it;
		if (node->GetNodeType() != 1) continue; // 只检查交换机节点（类型1）
		
		Ptr<SwitchNode> switchNode = DynamicCast<SwitchNode>(node);
		if (!switchNode || !switchNode->m_mmu) continue;
		
		uint32_t switchId = node->GetId();
		
		// 检查交换机上是否有与当前流相关的队列数据
		// 记录所有有数据的端口和队列（包括入口端口和出口端口）
		std::set<std::pair<uint32_t, uint32_t>> relevantQueues; // <port, queue>，使用set避免重复
		
		// 遍历所有端口和队列，查找与流相关的队列
		for (uint32_t port = 0; port < switchNode->m_mmu->pCnt; ++port) {
			for (uint32_t queue = 0; queue < switchNode->m_mmu->qCnt; ++queue) {
				uint64_t ingressBytes = switchNode->m_mmu->ingress_bytes[port][queue];
				uint64_t egressBytes = switchNode->m_mmu->egress_bytes[port][queue];
				uint64_t ingressLpf = switchNode->m_mmu->ingressLpf_bytes[port][queue];
				uint64_t egressLpf = switchNode->m_mmu->egressLpf_bytes[port][queue];
				
				// 如果该端口队列有任何数据（入口或出口），就认为可能与流相关
				if (ingressBytes > 0 || egressBytes > 0 || ingressLpf > 0 || egressLpf > 0) {
					// 进一步检查：检查m_bytes是否有数据，确保这个端口确实在处理数据包
					bool hasData = false;
					// 检查作为入口端口：m_bytes[port][outPort][queue]
					for (uint32_t outPort = 0; outPort < switchNode->m_mmu->pCnt; ++outPort) {
						if (switchNode->m_bytes[port][outPort][queue] > 0) {
							hasData = true;
							break;
						}
					}
					// 检查作为出口端口：m_bytes[inPort][port][queue]
					if (!hasData) {
						for (uint32_t inPort = 0; inPort < switchNode->m_mmu->pCnt; ++inPort) {
							if (switchNode->m_bytes[inPort][port][queue] > 0) {
								hasData = true;
								break;
							}
						}
					}
					
					// 如果有数据，添加到相关队列集合
					if (hasData) {
						relevantQueues.insert({port, queue});
					}
				}
			}
		}
		
		// 如果有相关队列，记录交换机信息
		if (!relevantQueues.empty()) {
			flowstatsFile << "  [Switch " << switchId << " @ " << currentTime << " ns] ";
			
			bool hasQueueInfo = false;
			for (const auto& q : relevantQueues) {
				uint32_t port = q.first;
				uint32_t queue = q.second;
				
				uint64_t ingressBytes = switchNode->m_mmu->ingress_bytes[port][queue];
				uint64_t egressBytes = switchNode->m_mmu->egress_bytes[port][queue];
				uint64_t ingressLpf = switchNode->m_mmu->ingressLpf_bytes[port][queue];
				uint64_t egressLpf = switchNode->m_mmu->egressLpf_bytes[port][queue];
				
				if (ingressBytes > 0 || egressBytes > 0 || ingressLpf > 0 || egressLpf > 0) {
					if (!hasQueueInfo) {
						flowstatsFile << "Queues: ";
						hasQueueInfo = true;
					}
					flowstatsFile << "P" << port << "Q" << queue 
								  << "(Ing:" << ingressBytes << ",Egr:" << egressBytes 
								  << ",IngLpf:" << ingressLpf << ",EgrLpf:" << egressLpf << ") ";
				}
			}
			
			if (!hasQueueInfo) {
				flowstatsFile << "No queue backlog";
			}
			flowstatsFile << std::endl;
		}
	}
}

// 记录所有交换机的队列信息（用于仿真开始和结束时）
void QbbNetDevice::LogAllSwitchQueueInfo(std::ofstream& flowstatsFile, uint64_t currentTime, const std::string& label) {
	flowstatsFile << "=== " << label << " - All Switch Queue Status @ " << currentTime << " ns ===" << std::endl;
	
	// 遍历所有交换机节点
	for (NodeList::Iterator it = NodeList::Begin(); it != NodeList::End(); ++it) {
		Ptr<Node> node = *it;
		if (node->GetNodeType() != 1) continue; // 只检查交换机节点（类型1）
		
		Ptr<SwitchNode> switchNode = DynamicCast<SwitchNode>(node);
		if (!switchNode || !switchNode->m_mmu) continue;
		
		uint32_t switchId = node->GetId();
		
		// 记录所有有数据的端口和队列
		std::set<std::pair<uint32_t, uint32_t>> relevantQueues; // <port, queue>
		
		// 遍历所有端口和队列
		for (uint32_t port = 0; port < switchNode->m_mmu->pCnt; ++port) {
			for (uint32_t queue = 0; queue < switchNode->m_mmu->qCnt; ++queue) {
				uint64_t ingressBytes = switchNode->m_mmu->ingress_bytes[port][queue];
				uint64_t egressBytes = switchNode->m_mmu->egress_bytes[port][queue];
				uint64_t ingressLpf = switchNode->m_mmu->ingressLpf_bytes[port][queue];
				uint64_t egressLpf = switchNode->m_mmu->egressLpf_bytes[port][queue];
				
				// 如果该端口队列有任何数据，就记录
				if (ingressBytes > 0 || egressBytes > 0 || ingressLpf > 0 || egressLpf > 0) {
					relevantQueues.insert({port, queue});
				}
			}
		}
		
		// 如果有相关队列，记录交换机信息
		if (!relevantQueues.empty()) {
			flowstatsFile << "  [Switch " << switchId << "] ";
			
			bool hasQueueInfo = false;
			for (const auto& q : relevantQueues) {
				uint32_t port = q.first;
				uint32_t queue = q.second;
				
				uint64_t ingressBytes = switchNode->m_mmu->ingress_bytes[port][queue];
				uint64_t egressBytes = switchNode->m_mmu->egress_bytes[port][queue];
				uint64_t ingressLpf = switchNode->m_mmu->ingressLpf_bytes[port][queue];
				uint64_t egressLpf = switchNode->m_mmu->egressLpf_bytes[port][queue];
				
				if (ingressBytes > 0 || egressBytes > 0 || ingressLpf > 0 || egressLpf > 0) {
					if (!hasQueueInfo) {
						flowstatsFile << "Queues: ";
						hasQueueInfo = true;
					}
					flowstatsFile << "P" << port << "Q" << queue 
								  << "(Ing:" << ingressBytes << ",Egr:" << egressBytes 
								  << ",IngLpf:" << ingressLpf << ",EgrLpf:" << egressLpf << ") ";
				}
			}
			
			if (!hasQueueInfo) {
				flowstatsFile << "No queue backlog";
			}
			flowstatsFile << std::endl;
		}
	}
	
	flowstatsFile << "=== End of " << label << " ===" << std::endl;
}

// 设置是否启用交换机队列记录
void QbbNetDevice::SetEnableSwitchQueueLogging(bool enable) {
	flag_ENABLE_SWITCH_QUEUE_LOGGING = enable;
}

// 获取是否启用交换机队列记录
bool QbbNetDevice::GetEnableSwitchQueueLogging() {
	return flag_ENABLE_SWITCH_QUEUE_LOGGING;
}

// 设置是否启用轮询调度调试日志
void QbbNetDevice::SetEnableRoundRobinDebug(bool enable) {
	flag_ENABLE_ROUND_ROBIN_DEBUG = enable;
}

// 获取是否启用轮询调度调试日志
bool QbbNetDevice::GetEnableRoundRobinDebug() {
	return flag_ENABLE_ROUND_ROBIN_DEBUG;
}

// 输出接收端速率到CSV文件
void QbbNetDevice::LogReceiverRateToCsv(const std::string& flowid, double avgRate, double instantRate, 
                                         uint64_t windowStart, uint64_t windowEnd, uint64_t windowBytes, 
                                         uint64_t packetCount, uint64_t currentTime) {
	if (!flag_ENABLE_QBB_DEVICE_RATE_CALC) {
		return;
	}
	
	std::ofstream csvFile;
	std::ios_base::openmode mode = g_isFirstOpenReceiverRateCsv ? std::ios::out : std::ios::app;
	std::string receiverRatePath = GetOutputDirectory() + "/flow_stats_receiver_rate.csv";
	csvFile.open(receiverRatePath.c_str(), mode);
	if (csvFile.is_open()) {
		// 如果是第一次打开，写入CSV头部
		if (g_isFirstOpenReceiverRateCsv) {
			csvFile << "NodeID,FlowID,AvgRate(Gbps),InstantRate(Gbps),WindowStart(ns),WindowEnd(ns),WindowBytes,PacketCount,Time(ns)" << std::endl;
			g_isFirstOpenReceiverRateCsv = false;
		}
		
		// 获取节点ID
		uint32_t nodeId = m_node ? m_node->GetId() : 0;
		
		csvFile << nodeId << ","
		        << flowid << ","
		        << avgRate << ","
		        << instantRate << ","
		        << windowStart << ","
		        << windowEnd << ","
		        << windowBytes << ","
		        << packetCount << ","
		        << currentTime << std::endl;
		csvFile.close();
	}
}
} 
// namespace ns3
