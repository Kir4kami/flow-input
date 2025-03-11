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
#include "flow-acc.h"

#include <iostream>

NS_LOG_COMPONENT_DEFINE("QbbNetDevice");

namespace ns3 {

uint32_t RdmaEgressQueue::ack_q_idx = 3;
uint32_t RdmaEgressQueue::tcpip_q_idx = 1;

//计算接收端口流量速率的变量
uint64_t MONITOR_PERIOD =10000; // 监测周期(ns)
bool isFirstOpen = true;
std::map<std::string, FlowStat> flowStats; //flowid,size字节数,存储流的统计信息
uint64_t steadyStateStartTime = 0;  // 记录稳态进入时间
bool inSteadyState = false;         // 标识系统是否处于稳态
double flowMinTime = 1.79769e+308;	//整个系统最小流完成时间


// RdmaEgressQueue
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

Ptr<Packet> RdmaEgressQueue::DequeueQindex(int qIndex) {

	NS_ASSERT_MSG(qIndex != -2, "qIndex -2 appeared in DequeueQindex. This is not intended. Aborting!");
	if (qIndex == -1) { // high prio
		Ptr<Packet> p = m_ackQ->Dequeue();
		m_qlast = -1;
		m_traceRdmaDequeue(p, 0);
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

int RdmaEgressQueue::GetLastQueue() {
	return m_qlast;
}

uint32_t RdmaEgressQueue::GetNBytes(uint32_t qIndex) {
	NS_ASSERT_MSG(qIndex < m_qpGrp->GetN(), "RdmaEgressQueue::GetNBytes: qIndex >= m_qpGrp->GetN()");
	return m_qpGrp->Get(qIndex)->GetBytesLeft();
}

uint32_t RdmaEgressQueue::GetFlowCount(void) {
	return m_qpGrp->GetN();
}

Ptr<RdmaQueuePair> RdmaEgressQueue::GetQp(uint32_t i) {
	return m_qpGrp->Get(i);
}

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
	Time txCompleteTime = txTime + m_tInterframeGap;

	NS_LOG_LOGIC("Schedule TransmitCompleteEvent in " << txCompleteTime.GetSeconds() << "sec");
	Simulator::Schedule(txCompleteTime, &QbbNetDevice::TransmitComplete, this);

	bool result = m_channel->TransmitStart(p, this, txTime);
	if (result == false)
	{
		m_phyTxDropTrace(p);
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
	DequeueAndTransmit();//
}

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
				numTxBytes += p->GetSize();
				totalBytesSent += p->GetSize();
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
			m_rdmaPktSent(lastQp, p, m_tInterframeGap);
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
				std::ofstream flowstatsFile;
				// 根据是否是第一次打开文件来选择文件打开模式
        		std::ios_base::openmode mode = isFirstOpen ? std::ios::out : std::ios::app;

				flowstatsFile.open("flow_stats.txt", mode);
				
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
	return;
}

//生成flowid和获取数据包大小
void QbbNetDevice::GenerateFlowId(Ptr<Packet> cp,CustomHeader& header,std::ofstream& flowstatsFile)
{
	uint8_t protocol = header.l3Prot; // 获取协议号
    uint32_t srcIp = header.sip; // 获取源IP地址
    uint32_t dstIp = header.dip; // 获取目标IP地址
	//将IP转换成ID
	uint32_t srcId = ((srcIp >> 8) & 0xffff);
	uint32_t dstId = ((dstIp >> 8) & 0xffff);
    uint16_t srcPort = 0; // 源端口号
    uint16_t dstPort = 0; // 目标端口号
	//获取数据包大小
	uint16_t packetSize = 0;
	// 根据协议类型处理传输层头部
    if (protocol == 0x11) // UDP协议号为17
    {
        srcPort = header.udp.sport; // 获取源端口号
        dstPort = header.udp.dport; // 获取目标端口号
		packetSize = cp->GetSize();
		//packetSize = header.udp.payload_size;
		//packetSize = header.m_payloadSize;
    }
    else
    {
        NS_LOG_INFO("不支持的协议: " << static_cast<uint32_t>(protocol)); // 记录不支持的协议
        return ; // 返回默认值表示不支持的协议
    }
    /*Ipv4Header ipv4Header; // IPv4头部对象
    Ptr<Packet> payload = packet->Copy(); // 复制数据包以避免修改原始数据包
    payload->RemoveHeader(ipv4Header); // 移除IPv4头部

    uint8_t protocol = ipv4Header.GetProtocol(); // 获取协议号
    uint32_t srcIp = ipv4Header.GetSource().Get(); // 获取源IP地址
    uint32_t dstIp = ipv4Header.GetDestination().Get(); // 获取目标IP地址
    uint16_t srcPort = 0; // 源端口号
    uint16_t dstPort = 0; // 目标端口号

    // 根据协议类型处理传输层头部
    if (protocol == 0x12) // UDP协议号为17
    {
        UdpHeader udpHeader;
        payload->RemoveHeader(udpHeader); // 移除UDP头部
        srcPort = udpHeader.GetSourcePort(); // 获取源端口号
        dstPort = udpHeader.GetDestinationPort(); // 获取目标端口号
    }
    else if (protocol == 0x06) // TCP协议号为6
    {
        TcpHeader tcpHeader;
        payload->RemoveHeader(tcpHeader); // 移除TCP头部
        srcPort = tcpHeader.GetSourcePort(); // 获取源端口号
        dstPort = tcpHeader.GetDestinationPort(); // 获取目标端口号
    }
    else
    {
        NS_LOG_INFO("不支持的协议: " << static_cast<uint32_t>(protocol)); // 记录不支持的协议
        return ; // 返回默认值表示不支持的协议
    }*/

    // 将所有信息组合成一个字符串
    std::ostringstream oss;
    oss << srcId << "-" << dstId << "-" << srcPort << "-" << dstPort;

    // 使用哈希函数将组合后的字符串转换为唯一整数ID
    /*std::hash<std::string> hasher;
    uint32_t flowid = static_cast<uint32_t>(hasher(oss.str()));*/
	std::string flowid = oss.str();
    
	//计算速率
	onPacketReceived(flowid, packetSize,flowstatsFile);
}

void QbbNetDevice::onPacketReceived(std::string flowid, uint16_t packetSize,std::ofstream& flowstatsFile) {
    uint64_t currentTime = Simulator::Now().GetNanoSeconds();
    
    // 检查该流是否存在
    auto it = flowStats.find(flowid);
    
    if (it == flowStats.end()){
        // 流不存在，创建新流
        FlowStat newStat = { packetSize, currentTime };
        flowStats[flowid] = newStat;
    }
	calculateRate(flowid,packetSize,flowstatsFile);
}

// 计算速率并输出
void QbbNetDevice::calculateRate(std::string flowid, uint16_t packetSize,std::ofstream& flowstatsFile) {
    uint64_t currentTime =  Simulator::Now().GetNanoSeconds();
    //判断系统稳态的变量
	bool allSteadyStateReached = true;

    // 遍历所有流，找出与flowid对应的流，计算速率
    for (auto& entry : flowStats) {
        string flow_id = entry.first;
        FlowStat& stat = entry.second;

        // 判断是否超过监测周期
		if (currentTime - stat.timestamp >= MONITOR_PERIOD) {
			if(stat.ifnewpacket){	//在这个周期内是否有这个流的新数据包进入
				// 计算速率（单位：字节/纳秒）
				double rate = static_cast<double>(stat.byteCount)*8 / MONITOR_PERIOD;  // 
				cout << "Flow ID: " << flow_id << " - Rate: " << rate << " Gbps" << " currentTime: " << currentTime << endl;
				flowstatsFile << "Flow ID: " << flow_id << " - Rate: " << rate << " Gbps" << " currentTime: " << currentTime << std::endl;
				stat.ifnewpacket =false;
				if(stat.rate.size() >= stat.size){
					stat.rate.erase(stat.rate.begin());
					// 获取最小值和最大值
					auto result = std::minmax_element(stat.rate.begin(), stat.rate.end());
					auto minIt = result.first;
					auto maxIt = result.second;
					if(std::fabs(*maxIt - *minIt)  <= 2.22045e-16 ){
						stat.steadyStateReached = true;//流进入稳态
						//cout<<"进入稳态"<<endl;
						
					}else {
						stat.steadyStateReached = false;  // 如果速率波动超过阈值，重置稳态状态
						allSteadyStateReached = false;   // 任何一个流未进入稳态，系统不再稳态
					}
					
				}
				stat.rate.push_back(rate);
				// 清空流的统计信息
				stat.byteCount = 0;
				stat.timestamp = currentTime;
				//stat.byteCount +=packetSize;
			}
			/*// 计算速率（单位：字节/纳秒）
			double rate = static_cast<double>(stat.byteCount)*8 / MONITOR_PERIOD;  // 
			cout << "Flow ID: " << flow_id << " - Rate: " << rate << " Gbps" << " currentTime: " << currentTime << endl;
			flowstatsFile << "Flow ID: " << flow_id << " - Rate: " << rate << " Gbps" << " currentTime: " << currentTime << std::endl;
			stat.ifnewpacket =false;
			if(stat.rate.size() >= stat.size){
				stat.rate.erase(stat.rate.begin());
				// 获取最小值和最大值
				auto result = std::minmax_element(stat.rate.begin(), stat.rate.end());
				auto minIt = result.first;
				auto maxIt = result.second;
				if(std::fabs(*maxIt - *minIt)  <= 2.22045e-16 ){
					stat.steadyStateReached = true;//流进入稳态
					//cout<<"进入稳态"<<endl;
					
				}else {
					stat.steadyStateReached = false;  // 如果速率波动超过阈值，重置稳态状态
					allSteadyStateReached = false;   // 任何一个流未进入稳态，系统不再稳态
				}
				
			}
			stat.rate.push_back(rate);
			// 清空流的统计信息
			stat.byteCount = 0;
			stat.timestamp = currentTime;
			//stat.byteCount +=packetSize;*/
		}
		if(flow_id == flowid){		
			stat.ifnewpacket	= true;
			stat.byteCount +=packetSize;
		}
		/*if(flow_id == flowid){//（应该还得加一个变量，判断在这个周期内，这个流有没有新数据包进入,有进入再更新）

			// 判断是否超过监测周期
			if (currentTime - stat.timestamp >= MONITOR_PERIOD) {
				// 计算速率（单位：字节/纳秒）
				double rate = static_cast<double>(stat.byteCount)*8 / MONITOR_PERIOD;  // 
				cout << "Flow ID: " << flow_id << " - Rate: " << rate << " Gbps" << " currentTime: " << currentTime << endl;
				flowstatsFile << "Flow ID: " << flow_id << " - Rate: " << rate << " Gbps" << " currentTime: " << currentTime << std::endl;
				if(stat.rate.size() >= stat.size){
					stat.rate.erase(stat.rate.begin());
					// 获取最小值和最大值
					auto result = std::minmax_element(stat.rate.begin(), stat.rate.end());
					auto minIt = result.first;
					auto maxIt = result.second;
					if(std::fabs(*maxIt - *minIt)  <= 2.22045e-16 ){
						stat.steadyStateReached = true;//流进入稳态
						//cout<<"进入稳态"<<endl;
						
					}else {
						stat.steadyStateReached = false;  // 如果速率波动超过阈值，重置稳态状态
						allSteadyStateReached = false;   // 任何一个流未进入稳态，系统不再稳态
					}
					
				}
				stat.rate.push_back(rate);

				// 清空流的统计信息
				stat.byteCount = 0;
				stat.timestamp = currentTime;

				//stat.byteCount +=packetSize;
			}
			
			stat.byteCount +=packetSize;

    	}*/
	}

	for (auto& entry_SteadyState : flowStats) {				
		if (!entry_SteadyState.second.steadyStateReached) {
			allSteadyStateReached = false;
			break;  // 一旦发现一个流未进入稳态，直接跳出循环
		}
	}
	// 判断系统是否刚刚进入稳态
    if (allSteadyStateReached && !inSteadyState) {
        steadyStateStartTime = currentTime;
        inSteadyState = true;
        cout << "System entered steady state at time: " << steadyStateStartTime << " ns" << endl;
		//计算剩余流量大小除以已测量的速度均值，获取最小流完成时间
		//如果在这里进行，就只计算了接收端这一个节点的，所以我们要在外部计算所有节点的流完成时间
		calculateMintime();
		cout << "最小流完成时间: " << flowMinTime <<endl;
		
    }

    // 判断系统是否退出稳态
    if (!allSteadyStateReached && inSteadyState) {
        uint64_t steadyStateExitTime = currentTime;
        uint64_t duration = steadyStateExitTime - steadyStateStartTime;
        cout << "System exited steady state at time: " << steadyStateExitTime << " ns" << endl;
        cout << "Steady state duration: " << duration / 1e9 << " s" << endl;
        flowstatsFile << "System exited steady state at time: " << steadyStateExitTime << " ns, duration: " << duration / 1e9 << " s" << std::endl;
        inSteadyState = false;
    }
	/*for (auto& entry_SteadyState : flowStats) {				
		if (!entry_SteadyState.second.steadyStateReached) {
			allSteadyStateReached = false;
			break;  // 一旦发现一个流未进入稳态，直接跳出循环
			}
		}
	if (allSteadyStateReached) {
		cout << "All flows have reached steady state." << endl;
		// 在这里可以执行进一步操作，比如标记系统进入稳态
		// 例如，触发一些事件或改变状态等
	}*/
}

//计算剩余流量大小除以已测量的速度均值，获取最小时间
void QbbNetDevice::calculateMintime(){
	uint32_t qIndex;
	uint32_t fcount = m_rdmaEQ->m_qpGrp->GetN();
		for (qIndex = 1; qIndex <= fcount; qIndex++) {
			uint32_t idx = qIndex ;
			Ptr<RdmaQueuePair> qp = m_rdmaEQ->m_qpGrp->Get(idx);//qp里面也有很多条流

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
				double sum = std::accumulate(iter->second.rate.begin(), iter->second.rate.end(), 0.0); // 计算总和
    			double avg = sum / iter->second.rate.size();
				double time = static_cast<double>(qp->GetBytesLeft())*8 / avg;
				if(time < flowMinTime)
					flowMinTime =time;
			}
		}

}

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

void QbbNetDevice::UpdateNextAvail(Time t) {
	if (!m_nextSend.IsExpired() && t < Time(m_nextSend.GetTs())) {
		Simulator::Cancel(m_nextSend);
		Time delta = t < Simulator::Now() ? Time(0) : t - Simulator::Now();
		m_nextSend = Simulator::Schedule(delta, &QbbNetDevice::DequeueAndTransmit, this);
	}
}
} 
// namespace ns3
