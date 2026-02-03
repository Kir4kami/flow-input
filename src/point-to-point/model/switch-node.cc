#include "ns3/ipv4.h"
#include "ns3/packet.h"
#include "ns3/ipv4-header.h"
#include "ns3/pause-header.h"
#include "ns3/interface-tag.h"
#include "ns3/boolean.h"
#include "ns3/uinteger.h"
#include "ns3/double.h"
#include "switch-node.h"
#include "qbb-net-device.h"
#include "ppp-header.h"
#include "ns3/int-header.h"
#include "ns3/simulator.h"
#include "output-directory.h"
#include "switch-timing-tag.h"
#include <cmath>
#include "ns3/tcp-header.h"
#include "ns3/udp-header.h"
#include "ns3/custom-priority-tag.h"
#include "ns3/feedback-tag.h"
#include "ns3/unsched-tag.h"
#include <iostream>
#include <chrono>
#include <fstream>
#include <sstream>
#include <iomanip>
#include <cmath>
#include <algorithm>
#include <map>

// 前向声明外部变量（在命名空间外）
extern bool flag_ENABLE_SWITCH_PORT_RATE_CALC;//计算交换机端口速率
extern bool flag_ENABLE_SWITCH_PORT_RATE_LOG;//记录交换机端口速率
extern bool flag_ENABLE_SWITCH_PORT_QUEUE_BYTES_LOG;//记录交换机端口数据量
extern bool flag_ENABLE_ROUND_ROBIN_DEBUG;//记录交换机内部数据包转发日志

namespace {
uint64_t GetWallClockNs() {
	return std::chrono::duration_cast<std::chrono::nanoseconds>(
	           std::chrono::steady_clock::now().time_since_epoch())
	    .count();
}
} // namespace

// 全局静态变量：控制 flow_stats_switch.txt 文件的打开模式（第一次覆盖，之后追加）
static bool g_isFirstOpenSwitchStats = true;
// 全局静态变量：控制 CSV 文件的打开模式（第一次覆盖，之后追加）
static bool g_isFirstOpenRateCsv = true;
static bool g_isFirstOpenQueueBytesCsv = true;
// 全局静态变量：控制PFC事件日志文件的打开模式
static bool g_isFirstOpenPfcLog = true;
// 全局静态变量：控制PFC详细统计日志文件的打开模式
static bool g_isFirstOpenPfcDetailedLog = true;
// 记录PFC暂停时间，用于计算暂停持续时间
static std::map<std::pair<uint32_t, uint32_t>, uint64_t> g_pfcPauseTime;

// 在命名空间外包含 flow-acc.h，避免命名空间污染
#include "flow-acc.h"

namespace ns3 {

TypeId SwitchNode::GetTypeId (void)
{
	static TypeId tid = TypeId ("ns3::SwitchNode")
	                    .SetParent<Node> ()
	                    .AddConstructor<SwitchNode> ()
	                    .AddAttribute("EcnEnabled",
	                                  "Enable ECN marking.",
	                                  BooleanValue(false),
	                                  MakeBooleanAccessor(&SwitchNode::m_ecnEnabled),
	                                  MakeBooleanChecker())
	                    .AddAttribute("CcMode",
	                                  "CC mode.",
	                                  UintegerValue(0),
	                                  MakeUintegerAccessor(&SwitchNode::m_ccMode),
	                                  MakeUintegerChecker<uint32_t>())
	                    .AddAttribute("AckHighPrio",
	                                  "Set high priority for ACK/NACK or not",
	                                  UintegerValue(0),
	                                  MakeUintegerAccessor(&SwitchNode::m_ackHighPrio),
	                                  MakeUintegerChecker<uint32_t>())
	                    .AddAttribute("MaxRtt",
	                                  "Max Rtt of the network",
	                                  UintegerValue(9000),
	                                  MakeUintegerAccessor(&SwitchNode::m_maxRtt),
	                                  MakeUintegerChecker<uint32_t>())
	                    .AddAttribute("PowerEnabled",
	                                  "Inserts Rxbytes instead of Txbytes in INT header",
	                                  BooleanValue(false),
	                                  MakeBooleanAccessor(&SwitchNode::PowerEnabled),
	                                  MakeBooleanChecker())

	                    ;
	return tid;
}

SwitchNode::SwitchNode() {
	m_ecmpSeed = m_id;
	m_node_type = 1;
	m_mmu = CreateObject<SwitchMmu>();
	for (uint32_t i = 0; i < pCnt; i++)
		for (uint32_t j = 0; j < pCnt; j++)
			for (uint32_t k = 0; k < qCnt; k++)
				m_bytes[i][j][k] = 0;
	for (uint32_t i = 0; i < pCnt; i++)
		m_txBytes[i] = 0;
	for (uint32_t i = 0; i < pCnt; i++)
		m_lastPktSize[i] = m_lastPktTs[i] = 0;
	for (uint32_t i = 0; i < pCnt; i++)
		m_u[i] = 0;
}

//ECMP 路由与出端口选择
int SwitchNode::GetOutDev(Ptr<const Packet> p, CustomHeader &ch) {
	// look up entries
	Ptr<Packet> cp = p->Copy();

	PppHeader ph; cp->RemoveHeader(ph);
	Ipv4Header ih; cp->RemoveHeader(ih);
	auto entry = m_rtTable.find(ih.GetDestination().Get());

	// no matching entry
	if (entry == m_rtTable.end())
		return -1;

	// entry found
	auto &nexthops = entry->second;

	// pick one next hop based on hash
	union {
		uint8_t u8[4 + 4 + 2 + 2];
		uint32_t u32[3];
	} buf;
	buf.u32[0] = ih.GetSource().Get();
	buf.u32[1] = ih.GetDestination().Get();
	if (ih.GetProtocol() == 0x6) {
		TcpHeader th; cp->PeekHeader(th);
		buf.u32[2] = th.GetSourcePort() | ((uint32_t)th.GetDestinationPort() << 16);
	}
	else if (ch.l3Prot == 0x11) {
		buf.u32[2] = ch.udp.sport | ((uint32_t)ch.udp.dport << 16);
	}
	else if (ch.l3Prot == 0xFC || ch.l3Prot == 0xFD)
		buf.u32[2] = ch.ack.sport | ((uint32_t)ch.ack.dport << 16);

	uint32_t idx = EcmpHash(buf.u8, 12, m_ecmpSeed) % nexthops.size();
	// if (nexthops.size()>1){ std::cout << "selected " << idx << std::endl; }
	return nexthops[idx];
}

void SwitchNode::CheckAndSendPfc(uint32_t inDev, uint32_t qIndex) {
	Ptr<QbbNetDevice> device = DynamicCast<QbbNetDevice>(m_devices[inDev]);
	if (m_mmu->CheckShouldPause(inDev, qIndex)) {
		device->SendPfc(qIndex, 0);
		// std::cout << "sending PFC" << std::endl;
		m_mmu->SetPause(inDev, qIndex);
		
		// 记录PFC暂停事件
		uint64_t currentTime = Simulator::Now().GetNanoSeconds();
		std::ofstream pfcLogFile;
		std::ios_base::openmode mode = g_isFirstOpenPfcLog ? std::ios::out : std::ios::app;
		std::string pfcEventsPath = GetOutputDirectory() + "/pfc_events.csv";
		pfcLogFile.open(pfcEventsPath.c_str(), mode);
		if (pfcLogFile.is_open()) {
			if (g_isFirstOpenPfcLog) {
				pfcLogFile << "Time(ns),Event,NodeType,NodeID,Port/DeviceIndex,Queue,Action" << std::endl;
				g_isFirstOpenPfcLog = false;
			}
			pfcLogFile << currentTime << ",PFC_PAUSE_SENT,Switch," << m_id << "," << inDev << "," << qIndex << ",Pause" << std::endl;
			pfcLogFile.close();
		}
		
		// 记录详细的PFC统计信息
		LogPfcDetailedStats(inDev, qIndex, true);
	}
}
void SwitchNode::CheckAndSendResume(uint32_t inDev, uint32_t qIndex) {
	Ptr<QbbNetDevice> device = DynamicCast<QbbNetDevice>(m_devices[inDev]);
	if (m_mmu->CheckShouldResume(inDev, qIndex)) {
		device->SendPfc(qIndex, 1);
		m_mmu->SetResume(inDev, qIndex);
		
		// 记录PFC恢复事件
		uint64_t currentTime = Simulator::Now().GetNanoSeconds();
		std::ofstream pfcLogFile;
		std::ios_base::openmode mode = g_isFirstOpenPfcLog ? std::ios::out : std::ios::app;
		std::string pfcEventsPath = GetOutputDirectory() + "/pfc_events.csv";
		pfcLogFile.open(pfcEventsPath.c_str(), mode);
		if (pfcLogFile.is_open()) {
			if (g_isFirstOpenPfcLog) {
				pfcLogFile << "Time(ns),Event,NodeType,NodeID,Port/DeviceIndex,Queue,Action" << std::endl;
				g_isFirstOpenPfcLog = false;
			}
			pfcLogFile << currentTime << ",PFC_RESUME_SENT,Switch," << m_id << "," << inDev << "," << qIndex << ",Resume" << std::endl;
			pfcLogFile.close();
		}
		
		// 记录详细的PFC统计信息
		LogPfcDetailedStats(inDev, qIndex, false);
	}
}

//交换机转发数据包
void SwitchNode::SendToDev(Ptr<Packet>p, CustomHeader &ch) {
	int idx = GetOutDev(p, ch);//选出出端口
	if (idx >= 0) {
		NS_ASSERT_MSG(m_devices[idx]->IsLinkUp(), "The routing table look up should return link that is up");

		// determine the qIndex
		uint32_t qIndex=0;
		MyPriorityTag priotag;
		// IMPORTANT: MyPriorityTag should only be attached by lossy traffic. This tag indicates the qIndex but also indicates that it is "lossy". Never attach MyPriorityTag on lossless traffic.
		bool found = p->PeekPacketTag(priotag);

		// UnSchedTag is used by ABM. End-hosts explicitly tag packets of the first BDP so that ABM then prioritizes these packets in the buffer allocation.
		uint32_t unsched = 0;
		UnSchedTag tag;
		bool foundunSched = p->PeekPacketTag (tag);
		if (foundunSched) {
			unsched = tag.GetValue();
		}

		if (ch.l3Prot == 0xFF || ch.l3Prot == 0xFE || (m_ackHighPrio && (ch.l3Prot == 0xFD || ch.l3Prot == 0xFC))) { //QCN or PFC or NACK, go highest priority
			qIndex = 0;
		}
		else if (found) {
			qIndex = priotag.GetPriority();
			// std::cout << "using queue " << qIndex << std::endl;
		}
		else {
			qIndex = (ch.l3Prot == 0x06 ? 1 : ch.udp.pg); // For TCP/IP if the stack did not attach MyPriorityTag, put to queue 1.
		}

		// admission control
		InterfaceTag t;
		p->PeekPacketTag(t);
		uint32_t inDev = t.GetPortId();

		// 更新交换机转发相关标签信息（出端口/队列）
		SwitchTimingTag timingTag;
		p->RemovePacketTag(timingTag);
		timingTag.SetSwitchId(m_id);
		timingTag.SetInDev(inDev);
		timingTag.SetOutDev(idx);
		timingTag.SetQIndex(qIndex);
		p->AddPacketTag(timingTag);
		if (qIndex != 0) { //not highest priority
			// IMPORTANT: MyPriorityTag should only be attached by lossy traffic. This tag indicates the qIndex but also indicates that it is "lossy". Never attach MyPriorityTag on lossless traffic.
			if (m_mmu->CheckIngressAdmission(inDev, qIndex, p->GetSize(), found,unsched) && m_mmu->CheckEgressAdmission(idx, qIndex, p->GetSize(), found,unsched)) {			// Admission control
				m_mmu->UpdateIngressAdmission(inDev, qIndex, p->GetSize(), found, unsched);
				m_mmu->UpdateEgressAdmission(idx, qIndex, p->GetSize(), found);
			} else {
				return; // Drop
			}
			CheckAndSendPfc(inDev, qIndex);
		}
		m_bytes[inDev][idx][qIndex] += p->GetSize();//记录入队字节数
		
		// 提取流ID（用于日志记录和速率计算）
		std::string flowid = "";
		if (qIndex != 0 && ch.l3Prot == 0x11) {
			flowid = GenerateFlowIdFromPacket(p, ch);
		}
		
		// 在入端口统计更新后计算入端口速率（如果启用）
		if (flag_ENABLE_SWITCH_PORT_RATE_CALC && qIndex != 0 && ch.l3Prot == 0x11) {
			if (!flowid.empty()) {
				// 计算入端口速率（数据包进入入端口队列时）
				CalculateFlowRateAtPort(inDev, flowid, p->GetSize(), true, qIndex);
			}
		}
		
		// 输出与流相关的交换机端口数据量（该流经过的入端口和出端口）
		if (flag_ENABLE_SWITCH_PORT_QUEUE_BYTES_LOG && qIndex != 0 && ch.l3Prot == 0x11 && !flowid.empty()) {
			uint64_t currentTime = Simulator::Now().GetNanoSeconds();
			LogFlowRelatedPortsQueueBytes(flowid, inDev, idx, qIndex, currentTime);
		}
		
		// 记录入端口数据包进入日志（格式类似于switch_egress_round_robin_debug.csv）
		if (flag_ENABLE_ROUND_ROBIN_DEBUG && qIndex != 0) {
			uint64_t currentTime = Simulator::Now().GetNanoSeconds();
			
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
			
			static std::ofstream switchIngressDebugFile;
			static bool switchIngressDebugFileOpened = false;
			if (!switchIngressDebugFileOpened) {
				std::string switchIngressPath = GetOutputDirectory() + "/switch_ingress_round_robin_debug.csv";
				switchIngressDebugFile.open(switchIngressPath.c_str(), std::ios::out);
				switchIngressDebugFile << "Time(ns),SwitchID,Port,Queue,Protocol,FlowID" << std::endl;
				switchIngressDebugFileOpened = true;
			}
			switchIngressDebugFile << currentTime << "," << m_id << "," << inDev << "," << qIndex << "," << protocolStr << "," << flowid << std::endl;
		}
		
		m_devices[idx]->SwitchSend(qIndex, p, ch);//实际转发数据到目标端口的目标队列
		//记录 egress（出端口）接收了多少数据
		DynamicCast<QbbNetDevice>(m_devices[idx])->totalBytesRcvd += p->GetSize(); // Attention: this is the egress port's total received packets. Not the ingress port.
	} else
		std::cout << "outdev not found! Dropped. This should not happen. Debugging required!" << std::endl;
	return; // Drop
}

uint32_t SwitchNode::EcmpHash(const uint8_t* key, size_t len, uint32_t seed) {
	uint32_t h = seed;
	if (len > 3) {
		const uint32_t* key_x4 = (const uint32_t*) key;
		size_t i = len >> 2;
		do {
			uint32_t k = *key_x4++;
			k *= 0xcc9e2d51;
			k = (k << 15) | (k >> 17);
			k *= 0x1b873593;
			h ^= k;
			h = (h << 13) | (h >> 19);
			h += (h << 2) + 0xe6546b64;
		} while (--i);
		key = (const uint8_t*) key_x4;
	}
	if (len & 3) {
		size_t i = len & 3;
		uint32_t k = 0;
		key = &key[i - 1];
		do {
			k <<= 8;
			k |= *key--;
		} while (--i);
		k *= 0xcc9e2d51;
		k = (k << 15) | (k >> 17);
		k *= 0x1b873593;
		h ^= k;
	}
	h ^= len;
	h ^= h >> 16;
	h *= 0x85ebca6b;
	h ^= h >> 13;
	h *= 0xc2b2ae35;
	h ^= h >> 16;
	return h;
}

//设置 ECMP 哈希的种子值
void SwitchNode::SetEcmpSeed(uint32_t seed) {
	m_ecmpSeed = seed;
}

//向路由表添加目的 IP 和输出接口的映射
void SwitchNode::AddTableEntry(Ipv4Address &dstAddr, uint32_t intf_idx) {
	uint32_t dip = dstAddr.Get();
	m_rtTable[dip].push_back(intf_idx);
}

void SwitchNode::ClearTable() {
	m_rtTable.clear();
}

// This function can only be called in switch mode
//从设备接收数据包并调用 SendToDev 进行转发
bool SwitchNode::SwitchReceiveFromDevice(Ptr<NetDevice> device, Ptr<Packet> packet, CustomHeader &ch) {
	// 数据包从外部网络进入交换机的入口点
	// 获取入端口（数据包已经添加了InterfaceTag，标记了入端口）
	InterfaceTag t;
	packet->PeekPacketTag(t);
	uint32_t inDev = t.GetPortId();

	// 记录进入交换机的时间戳（用于统计交换机时间和网侧时间）
	SwitchTimingTag timingTag;
	packet->RemovePacketTag(timingTag);
	timingTag.SetIngressTimeNs(Simulator::Now().GetNanoSeconds());
	timingTag.SetIngressWallTimeNs(GetWallClockNs());
	timingTag.SetSwitchId(m_id);
	timingTag.SetInDev(inDev);
	packet->AddPacketTag(timingTag);
	
	// 确定qIndex（与SendToDev中的逻辑相同）
	uint32_t qIndex = 0;
	MyPriorityTag priotag;
	bool found = packet->PeekPacketTag(priotag);
	
	if (ch.l3Prot == 0xFF || ch.l3Prot == 0xFE || (m_ackHighPrio && (ch.l3Prot == 0xFD || ch.l3Prot == 0xFC))) {
		qIndex = 0;
	}
	else if (found) {
		qIndex = priotag.GetPriority();
	}
	else {
		qIndex = (ch.l3Prot == 0x06 ? 1 : ch.udp.pg);
	}
	
	// 提取流ID（用于日志记录和速率计算）
	std::string flowid = "";
	if (qIndex != 0 && ch.l3Prot == 0x11) {
		flowid = GenerateFlowIdFromPacket(packet, ch);
	}
	
	// 转发数据包到出端口（入端口统计计算在SendToDev中进行）
	SendToDev(packet, ch);
	return true;
}

void SwitchNode::SwitchNotifyDequeue(uint32_t ifIndex, uint32_t qIndex, Ptr<Packet> p) {
	InterfaceTag t;
	p->PeekPacketTag(t);//该包是从哪个入端口进入交换机的

	// 记录离开交换机的时间戳（用于统计交换机时间和网侧时间）
	uint64_t currentTime = Simulator::Now().GetNanoSeconds();
	SwitchTimingTag timingTag;
	p->RemovePacketTag(timingTag);
	timingTag.SetEgressTimeNs(currentTime);
	timingTag.SetEgressWallTimeNs(GetWallClockNs());
	timingTag.SetOutDev(ifIndex);
	timingTag.SetQIndex(qIndex);
	p->AddPacketTag(timingTag);

	MyPriorityTag priotag;
	bool found = p->PeekPacketTag(priotag);//是否为带 MyPriorityTag 的 lossy 流量

	// 提取协议类型和流ID（用于日志记录）
	uint8_t protocol = 0;
	std::string flowid = "";
	uint8_t* buf = p->GetBuffer();
	if (buf) {
		protocol = buf[PppHeader::GetStaticSize() + 9]; // IP头部的协议字段
		if (qIndex != 0 && protocol == 0x11) {
			// 使用数据包的副本提取 CustomHeader，避免修改原始数据包
			Ptr<Packet> cp = p->Copy();
			CustomHeader ch(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
			ch.getInt = 0; // 不需要解析 INT header
			cp->PeekHeader(ch);
			flowid = GenerateFlowIdFromPacket(cp, ch);
		}
	}
	
	if (qIndex != 0) {
		uint32_t inDev = t.GetPortId();
		m_mmu->RemoveFromIngressAdmission(inDev, qIndex, p->GetSize(), found);
		m_mmu->RemoveFromEgressAdmission(ifIndex, qIndex, p->GetSize(), found);
		m_bytes[inDev][ifIndex][qIndex] -= p->GetSize();
		
		// 在数据包从出端口队列出队时计算出端口速率
		// 这是数据包真正离开交换机的时刻，能正确反映出端口的实际转发速率
		// 如果出端口队列积压，数据包会在队列中等待，出队速率会低于入队速率
		if (flag_ENABLE_SWITCH_PORT_RATE_CALC && qIndex != 0) {
			if (protocol == 0x11 && !flowid.empty()) { // UDP协议
				// 计算出端口速率（数据包从出端口队列出队时）
				// 此时数据包真正离开交换机，能反映出端口的实际转发速率
				CalculateFlowRateAtPort(ifIndex, flowid, p->GetSize(), false, qIndex);
			}
		}

		// 输出与流相关的交换机端口数据量（该流经过的入端口和出端口）
		if (flag_ENABLE_SWITCH_PORT_QUEUE_BYTES_LOG && qIndex != 0 && protocol == 0x11 && !flowid.empty()) {
			uint64_t currentTime = Simulator::Now().GetNanoSeconds();
			LogFlowRelatedPortsQueueBytes(flowid, inDev, ifIndex, qIndex, currentTime);
		}
		
		if (m_ecnEnabled) {
			bool egressCongested = m_mmu->ShouldSendCN(ifIndex, qIndex);
			if (egressCongested) {
				PppHeader ppp;
				Ipv4Header h;
				p->RemoveHeader(ppp);
				p->RemoveHeader(h);
				h.SetEcn((Ipv4Header::EcnType)0x03);
				p->AddHeader(h);
				p->AddHeader(ppp);
			}
		}
		//CheckAndSendPfc(inDev, qIndex);
		CheckAndSendResume(inDev, qIndex);
	}
	else {
		// qIndex=0的数据包出队时不会被统计到totalEgressBytes
	}
	if (1) {
		uint8_t* buf = p->GetBuffer();
		if (buf[PppHeader::GetStaticSize() + 9] == 0x11) { // udp packet
			IntHeader *ih = (IntHeader*)&buf[PppHeader::GetStaticSize() + 20 + 8 + 6]; // ppp, ip, udp, SeqTs, INT
			Ptr<QbbNetDevice> dev = DynamicCast<QbbNetDevice>(m_devices[ifIndex]);
			if (m_ccMode == 3) { // HPCC or PowerTCP-INT
				if (!PowerEnabled)
					ih->PushHop(Simulator::Now().GetTimeStep(), m_txBytes[ifIndex], dev->GetQueue()->GetNBytesTotal(), dev->GetDataRate().GetBitRate());
				else
					ih->PushHop(Simulator::Now().GetTimeStep(), dev->GetQueue()->GetNBytesRxTotal(), dev->GetQueue()->GetNBytesTotal(), dev->GetDataRate().GetBitRate());
				// ih->PushHop(Simulator::Now().GetTimeStep(), m_txBytes[ifIndex], dev->GetQueue()->GetNBytesTotal(), dev->GetDataRate().GetBitRate());
			} else if (m_ccMode == 10) { // HPCC-PINT
				uint64_t t = Simulator::Now().GetTimeStep();
				uint64_t dt = t - m_lastPktTs[ifIndex];
				if (dt > m_maxRtt)
					dt = m_maxRtt;
				uint64_t B = dev->GetDataRate().GetBitRate() / 8; //Bps
				uint64_t qlen = dev->GetQueue()->GetNBytesTotal();
				double newU;

				/**************************
				 * approximate calc
				 *************************/
				int b = 20, m = 16, l = 20; // see log2apprx's paremeters
				int sft = logres_shift(b, l);
				double fct = 1 << sft; // (multiplication factor corresponding to sft)
				double log_T = log2(m_maxRtt) * fct; // log2(T)*fct
				double log_B = log2(B) * fct; // log2(B)*fct
				double log_1e9 = log2(1e9) * fct; // log2(1e9)*fct
				double qterm = 0;
				double byteTerm = 0;
				double uTerm = 0;
				if ((qlen >> 8) > 0) {
					int log_dt = log2apprx(dt, b, m, l); // ~log2(dt)*fct
					int log_qlen = log2apprx(qlen >> 8, b, m, l); // ~log2(qlen / 256)*fct
					qterm = pow(2, (
					                log_dt + log_qlen + log_1e9 - log_B - 2 * log_T
					            ) / fct
					           ) * 256;
					// 2^((log2(dt)*fct+log2(qlen/256)*fct+log2(1e9)*fct-log2(B)*fct-2*log2(T)*fct)/fct)*256 ~= dt*qlen*1e9/(B*T^2)
				}
				if (m_lastPktSize[ifIndex] > 0) {
					int byte = m_lastPktSize[ifIndex];
					int log_byte = log2apprx(byte, b, m, l);
					byteTerm = pow(2, (
					                   log_byte + log_1e9 - log_B - log_T
					               ) / fct
					              );
					// 2^((log2(byte)*fct+log2(1e9)*fct-log2(B)*fct-log2(T)*fct)/fct) ~= byte*1e9 / (B*T)
				}
				if (m_maxRtt > dt && m_u[ifIndex] > 0) {
					int log_T_dt = log2apprx(m_maxRtt - dt, b, m, l); // ~log2(T-dt)*fct
					int log_u = log2apprx(int(round(m_u[ifIndex] * 8192)), b, m, l); // ~log2(u*512)*fct
					uTerm = pow(2, (
					                log_T_dt + log_u - log_T
					            ) / fct
					           ) / 8192;
					// 2^((log2(T-dt)*fct+log2(u*512)*fct-log2(T)*fct)/fct)/512 = (T-dt)*u/T
				}
				newU = qterm + byteTerm + uTerm;

#if 0
				/**************************
				 * accurate calc
				 *************************/
				double weight_ewma = double(dt) / m_maxRtt;
				double u;
				if (m_lastPktSize[ifIndex] == 0)
					u = 0;
				else {
					double txRate = m_lastPktSize[ifIndex] / double(dt); // B/ns
					u = (qlen / m_maxRtt + txRate) * 1e9 / B;
				}
				newU = m_u[ifIndex] * (1 - weight_ewma) + u * weight_ewma;
				printf(" %lf\n", newU);
#endif

				/************************
				 * update PINT header
				 ***********************/
				uint16_t power = Pint::encode_u(newU);
				if (power > ih->GetPower())
					ih->SetPower(power);

				m_u[ifIndex] = newU;
			}
		}
		else {
			FeedbackTag Int;
			bool found;
			found = p->PeekPacketTag(Int);
			if (found) {
				Ptr<QbbNetDevice> dev = DynamicCast<QbbNetDevice>(m_devices[ifIndex]);
				Int.setTelemetryQlenDeq(Int.getHopCount(), dev->GetQueue()->GetNBytesTotal()); // queue length at dequeue
				Int.setTelemetryTsDeq(Int.getHopCount(), Simulator::Now().GetNanoSeconds()); // timestamp at dequeue
				Int.setTelemetryBw(Int.getHopCount(), dev->GetDataRate().GetBitRate());
				Int.setTelemetryTxBytes(Int.getHopCount(), m_txBytes[ifIndex]);
				Int.incrementHopCount(); // Incrementing hop count at Dequeue. Don't do this at enqueue.
				p->ReplacePacketTag(Int); // replacing the tag with new values
				// std::cout << "found " << Int.getHopCount() << std::endl;
			}
		}
	}
	m_txBytes[ifIndex] += p->GetSize();
	m_lastPktSize[ifIndex] = p->GetSize();
	m_lastPktTs[ifIndex] = Simulator::Now().GetTimeStep();
}


//补偿
void SwitchNode::SwitchStatsUpdate(int flag, uint32_t switchid){
	auto& exitStatsMap = multiSwitchStats[flag].exitStats;
	auto it_1 = exitStatsMap.find(switchid);
	uint32_t firstKey,secondKey;
	SwitchStat firstValue,secondValue;
	if (it_1 != exitStatsMap.end()) {
		firstKey = it_1->first;
		firstValue = it_1->second;
	}

	auto& normalStatsMap = multiSwitchStats[flag].normalStats;
	auto it_2 = normalStatsMap.find(switchid);
	if (it_2 != normalStatsMap.end()) {
		secondKey = it_2->first;
		secondValue = it_2->second;
	}

	for(int k=0;k<m_mmu->pCnt;k++){	
		for (int i = 0; i < m_mmu->pCnt; ++i) {
			for (int j = 0; j < m_mmu->qCnt; ++j) {
				if(firstValue.ingress_bytes[i][j]||firstValue.ingressLpf_bytes[i][j]||firstValue.egress_bytes[i][j]||firstValue.egressLpf_bytes[i][j]
				||firstValue.m_bytes[k][i][j]||secondValue.ingress_bytes[i][j]||secondValue.ingressLpf_bytes[i][j]||secondValue.egress_bytes[i][j]||secondValue.egressLpf_bytes[i][j]
				||secondValue.m_bytes[k][i][j]){
					m_mmu->ingress_bytes[i][j] = firstValue.ingress_bytes[i][j];
					m_mmu->ingressLpf_bytes[i][j]=firstValue.ingressLpf_bytes[i][j];
					m_mmu->egress_bytes[i][j]=firstValue.egress_bytes[i][j];
					m_mmu->egressLpf_bytes[i][j]=firstValue.egressLpf_bytes[i][j];
					m_bytes[k][i][j]=firstValue.m_bytes[k][i][j];
				}
				/*if(firstValue.ingress_bytes[i][j]){
					m_mmu->ingress_bytes[i][j] = firstValue.ingress_bytes[i][j];
				}
				if(firstValue.ingressLpf_bytes[i][j]){
					m_mmu->ingressLpf_bytes[i][j]=firstValue.ingressLpf_bytes[i][j];
				}*/
			}
		}
	}
}

//时延
void SwitchNode::SwitchTimeDelay(int flag){

}

//统计交换机上的数据
void SwitchNode::SwitchStatsCount(int flag){
	uint32_t sw_id = m_id;
	if(flag==1){
		auto it = SwitchStats.find(sw_id);
		if (it == SwitchStats.end()){
			SwitchStat newswstat;
			for(int k=0;k<m_mmu->pCnt;k++){
					for(int i=0;i<m_mmu->pCnt;i++){
						for(int j=0;j<m_mmu->qCnt;j++){
							newswstat.m_bytes[k][i][j]=m_bytes[k][i][j];
							newswstat.egress_bytes[i][j]=m_mmu->egress_bytes[i][j];//入口队列当前占用的字节数
							newswstat.ingress_bytes[i][j]=m_mmu->ingress_bytes[i][j];//出口队列当前占用的字节数
							newswstat.egressLpf_bytes[i][j]=m_mmu->egressLpf_bytes[i][j];//入口队列的低通滤波（LPF）占用字节数
							newswstat.ingressLpf_bytes[i][j]=m_mmu->ingressLpf_bytes[i][j];//出口队列的低通滤波占用字节数
							newswstat.bandwidth[j]=m_mmu->bandwidth[j];
							newswstat.dequeueRateIngress[i][j]=m_mmu->dequeueRateIngress[i][j];
						}
				}
				/*newswstat.totalUsed = mmu->totalUsed;
                newswstat.egressPoolUsed[0] = mmu->egressPoolUsed[0];
                newswstat.egressPoolUsed[1] = mmu->egressPoolUsed[1];
                //mmu->totalUsed - mmu->xoffTotalUsed;
                newswstat.xoffTotalUsed =mmu->xoffTotalUsed;
                newswstat.sharedPoolUsed = mmu->sharedPoolUsed;*/
			}
			if(!IsAllZero(newswstat)){
					SwitchStats[sw_id]=newswstat;
			}
		}
	}
	else{
		auto it = exit_SwitchStats.find(sw_id);
		if (it == exit_SwitchStats.end()){
			SwitchStat newswstat;
			for(int k=0;k<m_mmu->pCnt;k++){
					for(int i=0;i<m_mmu->pCnt;i++){
						for(int j=0;j<m_mmu->qCnt;j++){
							newswstat.m_bytes[k][i][j]=m_bytes[k][i][j];
							newswstat.egress_bytes[i][j]=m_mmu->egress_bytes[i][j];//出口队列当前占用的字节数
							newswstat.ingress_bytes[i][j]=m_mmu->ingress_bytes[i][j];//入口队列当前占用的字节数
							newswstat.egressLpf_bytes[i][j]=m_mmu->egressLpf_bytes[i][j];//出口队列的低通滤波（LPF）占用字节数
							newswstat.ingressLpf_bytes[i][j]=m_mmu->ingressLpf_bytes[i][j];//入口队列的低通滤波占用字节数
							newswstat.bandwidth[j]=m_mmu->bandwidth[j];
							newswstat.dequeueRateIngress[i][j]=m_mmu->dequeueRateIngress[i][j];
						}
				}
			}
			if(!IsAllZero(newswstat)){
				exit_SwitchStats[sw_id]=newswstat;
			}
		}
	}
}


//定期监控交换节点（SwitchNode）上流量的发送速率（比特/时间）
void
SwitchNode::BandWidthMonitor(Ptr<Packet> packet, CustomHeader& ch)
{
	uint64_t currentTime = Simulator::Now().GetNanoSeconds();
    uint16_t packetSize = packet->GetSize();
    // 检查该流是否存在
    auto it = NodeStats.find(m_id);
    
    if (it == NodeStats.end()){
        // 流不存在，创建新在
        NodeStat newStat = { packetSize, currentTime,0 };
        NodeStats[m_id] = newStat;
    }else{
		if(currentTime-it->second.timestamp>= MONITOR_PERIOD){
			double rate = static_cast<double>(it->second.byteCount)*8 / MONITOR_PERIOD;  // 
			it->second.byteCount=packetSize;
			it->second.timestamp=currentTime;
		}else{
			it->second.byteCount+=packetSize;
		}
	}
}



int SwitchNode::logres_shift(int b, int l) {
	static int data[] = {0, 0, 1, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 4, 4, 4, 4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5};
	return l - data[b];
}

int SwitchNode::log2apprx(int x, int b, int m, int l) {
	int x0 = x;
	int msb = int(log2(x)) + 1;
	if (msb > m) {
		x = (x >> (msb - m) << (msb - m));
#if 0
		x += + (1 << (msb - m - 1));
#else
		int mask = (1 << (msb - m)) - 1;
		if ((x0 & mask) > (rand() & mask))
			x += 1 << (msb - m);
#endif
	}
	return int(log2(x) * (1 << logres_shift(b, l)));
}

// 从数据包提取流ID
std::string SwitchNode::GenerateFlowIdFromPacket(Ptr<Packet> packet, CustomHeader &ch) {
	uint8_t protocol = ch.l3Prot;
	uint32_t srcIp = ch.sip;
	uint32_t dstIp = ch.dip;
	
	// 将IP转换成ID
	uint32_t srcId = ((srcIp >> 8) & 0xffff);
	uint32_t dstId = ((dstIp >> 8) & 0xffff);
	uint16_t srcPort = 0;
	uint16_t dstPort = 0;
	
	// 根据协议类型处理传输层头部
	if (protocol == 0x11) { // UDP协议号为17
		srcPort = ch.udp.sport;
		dstPort = ch.udp.dport;
	} else {
		return ""; // 不支持的协议
	}
	
	// 组合成流ID字符串
	std::ostringstream oss;
	oss << srcId << "-" << dstId << "-" << srcPort << "-" << dstPort;
	return oss.str();
}

// 在交换机端口计算流速率
void SwitchNode::CalculateFlowRateAtPort(uint32_t port, const std::string& flowid, uint16_t packetSize, bool isIngress, uint32_t qIndex) {
	uint64_t currentTime = Simulator::Now().GetNanoSeconds();
	
	// 获取或创建该交换机的该端口的流统计信息
	// 使用交换机ID作为第一层键，确保不同交换机的数据完全隔离
	uint32_t switchId = m_id;
	auto& portStats = m_switchPortFlowStats[switchId][port];
	auto& stat = portStats[flowid];
	
	// 如果是新流，初始化统计信息
	if (stat.monitorWindowStartTime == 0) {
		stat.byteCount = packetSize;
		stat.timestamp = currentTime;
		stat.ifnewpacket = true;
		stat.steadyStateReached = false;
		stat.steadyCooldown = 0;
		stat.lastPacketTime = currentTime;
		stat.lastPacketSize = packetSize;
		stat.size = 10; // 速率历史队列大小
		stat.totalIngressBytes = 0;
		stat.totalEgressBytes = 0;
		// 初始化固定时间窗口
		stat.monitorWindowStartTime = currentTime;
		stat.monitorWindowSize = 1005; // 默认3000纳秒（对应phase:3000）
		stat.monitorWindowBytes = 0;
		stat.monitorWindowPacketCount = 0;
	}
	
	// 注意：TotalIngressBytes和TotalEgressBytes现在是端口级别的统计，不在这里更新
	// 端口级别的统计在switch-mmu.cc中的UpdateIngressAdmission和RemoveFromEgressAdmission中更新
	
	// 保存上一个数据包的时间，用于计算瞬时速率（在更新lastPacketTime之前）
	uint64_t prevPacketTime = stat.lastPacketTime;
	uint64_t prevPacketSize = stat.lastPacketSize;
	
	// 更新lastPacketTime（每次数据包到达时都更新，确保记录的是上一个数据包的时间）
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
				// 输出速率（可选，可以通过标志位控制）
				if (flag_ENABLE_SWITCH_PORT_RATE_LOG) {
					std::ofstream flowstatsFile;
					std::ios_base::openmode mode = g_isFirstOpenSwitchStats ? std::ios::out : std::ios::app;
					std::string flowStatsSwitchPath = GetOutputDirectory() + "/flow_stats_switch.txt";
					flowstatsFile.open(flowStatsSwitchPath.c_str(), mode);
					if (flowstatsFile.is_open()) {
						std::string portType = isIngress ? "Ingress" : "Egress";
						flowstatsFile << "Switch " << m_id << " Port " << port << " (" << portType << ") Flow " << flowid 
						              << " - AvgRate: " << avgRate << " Gbps, InstantRate: " << instantRate 
						              << " Gbps, Queue: " << qIndex << ", WindowStart: " << stat.monitorWindowStartTime 
						              << ", WindowEnd: " << windowEndTime << ", WindowBytes: " << stat.monitorWindowBytes
						              << ", PacketCount: " << stat.monitorWindowPacketCount << ", currentTime: " << currentTime << std::endl;
						flowstatsFile.close();
						g_isFirstOpenSwitchStats = false;
					}
					// 输出到CSV文件
					LogRateToCsv(port, qIndex, isIngress, flowid, avgRate, instantRate, 
					            stat.monitorWindowStartTime, windowEndTime, stat.monitorWindowBytes, 
					            stat.monitorWindowPacketCount, currentTime);
				}
				
				// 保存速率历史（用于稳态检测，使用平均速率）
				stat.rate.push_back(avgRate);
				if (stat.rate.size() > static_cast<size_t>(stat.size)) {
					stat.rate.erase(stat.rate.begin());
				}
			}
		}
		
		// 重置监测时间窗口，开始新的窗口（当前数据包计入新窗口）
		stat.monitorWindowStartTime = currentTime;
		stat.monitorWindowBytes = packetSize;
		stat.monitorWindowPacketCount = 1;
	}
	
	// 稳态检测逻辑（仅在窗口结束时进行）
	if (!inWindow && avgRate > 0.0) {
		// 稳态检测逻辑
		if (stat.rate.size() >= 2) {
			double latestRate = stat.rate.back();
			double prevRate = *(stat.rate.end() - 2);
			double denomPair = std::max(std::max(latestRate, prevRate), kSteadyRateEpsilon);
			double relativeDiff = std::fabs(latestRate - prevRate) / denomPair;
			
			if (relativeDiff > kSteadyRelativeThreshold) {
				// 速率变化超过阈值，退出稳态
				if (stat.steadyStateReached) {
					// 打印退出稳态信息（如果启用速率日志）
					if (flag_ENABLE_SWITCH_PORT_RATE_LOG) {
						std::ofstream flowstatsFile;
						std::ios_base::openmode mode = g_isFirstOpenSwitchStats ? std::ios::out : std::ios::app;
						std::string flowStatsSwitchPath = GetOutputDirectory() + "/flow_stats_switch.txt";
						flowstatsFile.open(flowStatsSwitchPath.c_str(), mode);
						if (flowstatsFile.is_open()) {
							std::string portType = isIngress ? "Ingress" : "Egress";
							flowstatsFile << "[STEADY STATE EXIT] Switch " << m_id << " Port " << port 
							              << " (" << portType << ") Flow " << flowid 
							              << " - Previous Rate: " << prevRate << " Gbps, Latest Rate: " << latestRate 
							              << " Gbps, Relative Diff: " << (relativeDiff * 100.0) << "%, Queue: " << qIndex 
							              << ", currentTime: " << currentTime << std::endl;
							flowstatsFile.close();
							g_isFirstOpenSwitchStats = false;
						}
						// 输出到CSV文件（使用最新速率作为平均速率，计算瞬时速率）
						double instantRate = latestRate; // 如果没有足够信息，使用最新速率
						if (stat.lastPacketTime > 0 && currentTime > stat.lastPacketTime && stat.lastPacketSize > 0) {
							uint64_t interval = currentTime - stat.lastPacketTime;
							if (interval > 0) {
								instantRate = static_cast<double>(stat.lastPacketSize) * 8.0 / interval;
							}
						}
						// 获取窗口信息（使用当前窗口的信息）
						uint64_t windowEndTime = stat.monitorWindowStartTime + stat.monitorWindowSize;
						LogRateToCsv(port, qIndex, isIngress, flowid, latestRate, instantRate, 
						            stat.monitorWindowStartTime, windowEndTime, stat.monitorWindowBytes, 
						            stat.monitorWindowPacketCount, currentTime);
					}
					
					// 单独输出端口数据量（如果启用）
					/*if (flag_ENABLE_SWITCH_PORT_QUEUE_BYTES_LOG) {
						LogPortQueueBytes(port, qIndex, isIngress, currentTime, flowid);
						// 输出到CSV文件
						LogPortQueueBytesToCsv(port, qIndex, isIngress, flowid, currentTime);
					}*/
				}
				stat.steadyStateReached = false;
				stat.steadyCooldown = 0;
			} else {
				// 速率稳定，检查是否可以进入稳态
				if (!stat.steadyStateReached && stat.rate.size() >= static_cast<size_t>(stat.size)) {
					// 检查最近的所有速率是否都稳定
					bool allStable = true;
					for (size_t i = 1; i < stat.rate.size(); ++i) {
						double r1 = stat.rate[i];
						double r2 = stat.rate[i-1];
						double denom = std::max(std::max(r1, r2), kSteadyRateEpsilon);
						if (std::fabs(r1 - r2) / denom > kSteadyRelativeThreshold) {
							allStable = false;
							break;
						}
					}
					if (allStable) {
						stat.steadyStateReached = true;
						// 打印进入稳态信息（如果启用速率日志）
						if (flag_ENABLE_SWITCH_PORT_RATE_LOG) {
							std::ofstream flowstatsFile;
							std::ios_base::openmode mode = g_isFirstOpenSwitchStats ? std::ios::out : std::ios::app;
							std::string flowStatsSwitchPath = GetOutputDirectory() + "/flow_stats_switch.txt";
							flowstatsFile.open(flowStatsSwitchPath.c_str(), mode);
							if (flowstatsFile.is_open()) {
								std::string portType = isIngress ? "Ingress" : "Egress";
								double avgRate = 0.0;
								for (const auto& r : stat.rate) {
									avgRate += r;
								}
								avgRate /= stat.rate.size();
								flowstatsFile << "[STEADY STATE ENTER] Switch " << m_id << " Port " << port 
								              << " (" << portType << ") Flow " << flowid 
								              << " - Average Rate: " << avgRate << " Gbps, Rate Samples: " << stat.rate.size() 
								              << ", Queue: " << qIndex << ", currentTime: " << currentTime << std::endl;
								flowstatsFile.close();
								g_isFirstOpenSwitchStats = false;
							}
							// 输出到CSV文件（使用平均速率）
							double avgRate = 0.0;
							for (const auto& r : stat.rate) {
								avgRate += r;
							}
							avgRate /= stat.rate.size();
							// 计算瞬时速率（基于最后一个数据包）
							double instantRate = avgRate; // 如果没有足够信息，使用平均速率
							if (stat.lastPacketTime > 0 && currentTime > stat.lastPacketTime && stat.lastPacketSize > 0) {
								uint64_t interval = currentTime - stat.lastPacketTime;
								if (interval > 0) {
									instantRate = static_cast<double>(stat.lastPacketSize) * 8.0 / interval;
								}
							}
							// 获取窗口信息（使用当前窗口的信息）
							uint64_t windowEndTime = stat.monitorWindowStartTime + stat.monitorWindowSize;
							LogRateToCsv(port, qIndex, isIngress, flowid, avgRate, instantRate, 
							            stat.monitorWindowStartTime, windowEndTime, stat.monitorWindowBytes, 
							            stat.monitorWindowPacketCount, currentTime);
						}
						
						// 单独输出端口数据量（如果启用）
						/*if (flag_ENABLE_SWITCH_PORT_QUEUE_BYTES_LOG) {
							LogPortQueueBytes(port, qIndex, isIngress, currentTime, flowid);
							// 输出到CSV文件
							LogPortQueueBytesToCsv(port, qIndex, isIngress, flowid, currentTime);
						}*/
					}
				}
			}
		}
	}
}

// 获取端口数据量
void SwitchNode::GetPortQueueBytes(uint32_t port, uint32_t qIndex, uint64_t& ingressBytes, uint64_t& egressBytes, uint64_t& ingressLpfBytes, uint64_t& egressLpfBytes) {
	ingressBytes = 0;
	egressBytes = 0;
	ingressLpfBytes = 0;
	egressLpfBytes = 0;
	
	if (m_mmu && qIndex < qCnt && port < pCnt) {
		ingressBytes = m_mmu->ingress_bytes[port][qIndex];
		egressBytes = m_mmu->egress_bytes[port][qIndex];
		ingressLpfBytes = m_mmu->ingressLpf_bytes[port][qIndex];
		egressLpfBytes = m_mmu->egressLpf_bytes[port][qIndex];
	}
}

// 获取端口累积统计（进入和离开的总字节数）- 端口级别，不区分流
void SwitchNode::GetPortTotalBytes(uint32_t port, uint32_t qIndex, uint64_t& totalIngressBytes, uint64_t& totalEgressBytes) {
	totalIngressBytes = 0;
	totalEgressBytes = 0;
	
	// 从端口级别的统计中获取累计字节数（不区分流）
	if (m_mmu && qIndex < qCnt && port < pCnt) {
		totalIngressBytes = m_mmu->totalIngressBytes[port][qIndex];
		totalEgressBytes = m_mmu->totalEgressBytes[port][qIndex];
	}
}

// 输出端口数据量
void SwitchNode::LogPortQueueBytes(uint32_t port, uint32_t qIndex, bool isIngress, uint64_t currentTime, const std::string& flowid) {
	if (!m_mmu || qIndex >= qCnt || port >= pCnt) {
		return;
	}
	
	uint64_t ingressBytes = 0;
	uint64_t egressBytes = 0;
	uint64_t ingressLpfBytes = 0;
	uint64_t egressLpfBytes = 0;
	uint64_t totalIngressBytes = 0;
	uint64_t totalEgressBytes = 0;
	
	GetPortQueueBytes(port, qIndex, ingressBytes, egressBytes, ingressLpfBytes, egressLpfBytes);
	GetPortTotalBytes(port, qIndex, totalIngressBytes, totalEgressBytes);
	
	std::ofstream flowstatsFile;
	std::ios_base::openmode mode = g_isFirstOpenSwitchStats ? std::ios::out : std::ios::app;
	std::string flowStatsSwitchPath = GetOutputDirectory() + "/flow_stats_switch.txt";
	flowstatsFile.open(flowStatsSwitchPath.c_str(), mode);
	if (flowstatsFile.is_open()) {
		std::string portType = isIngress ? "Ingress" : "Egress";
		
		flowstatsFile << "Switch " << m_id << " Port " << port << " (" << portType << ")";
		
		if (!flowid.empty()) {
			flowstatsFile << " Flow " << flowid;
		}
		
		flowstatsFile << " Queue " << qIndex;
		
		// 同时输出入端口和出端口的所有数据（瞬时值和累积值）
		flowstatsFile << " - IngressBytes: " << ingressBytes << ", IngressLpfBytes: " << ingressLpfBytes
		              << ", EgressBytes: " << egressBytes << ", EgressLpfBytes: " << egressLpfBytes
		              << ", TotalIngressBytes: " << totalIngressBytes << ", TotalEgressBytes: " << totalEgressBytes;
		
		flowstatsFile << ", currentTime: " << currentTime << std::endl;
		flowstatsFile.close();
		g_isFirstOpenSwitchStats = false;
	}
}

// 输出速率到CSV文件
void SwitchNode::LogRateToCsv(uint32_t port, uint32_t qIndex, bool isIngress, const std::string& flowid, double avgRate, double instantRate, 
                              uint64_t windowStart, uint64_t windowEnd, uint64_t windowBytes, uint64_t packetCount, uint64_t currentTime) {
	if (!flag_ENABLE_SWITCH_PORT_RATE_LOG) {
		return;
	}
	
	std::ofstream csvFile;
	std::ios_base::openmode mode = g_isFirstOpenRateCsv ? std::ios::out : std::ios::app;
	std::string switchRatePath = GetOutputDirectory() + "/flow_stats_switch_rate.csv";
	csvFile.open(switchRatePath.c_str(), mode);
	if (csvFile.is_open()) {
		// 如果是第一次打开，写入CSV头部
		if (g_isFirstOpenRateCsv) {
			csvFile << "Switch-Port,FlowID,Queue,PortType,AvgRate(Gbps),InstantRate(Gbps),WindowStart(ns),WindowEnd(ns),WindowBytes,PacketCount,Time(ns)" << std::endl;
			g_isFirstOpenRateCsv = false;
		}
		
		std::ostringstream switchPort;
		switchPort << "Switch" << m_id << "-Port" << port;
		std::string portType = isIngress ? "Ingress" : "Egress";
		
		csvFile << switchPort.str() << ","
		        << flowid << ","
		        << qIndex << ","
		        << portType << ","
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

// 输出端口数据量到CSV文件
void SwitchNode::LogPortQueueBytesToCsv(uint32_t port, uint32_t qIndex, bool isIngress, const std::string& flowid, uint64_t currentTime) {
	if (!flag_ENABLE_SWITCH_PORT_QUEUE_BYTES_LOG) {
		return;
	}
	
	if (!m_mmu || qIndex >= qCnt || port >= pCnt) {
		return;
	}
	
	uint64_t ingressBytes = 0;
	uint64_t egressBytes = 0;
	uint64_t ingressLpfBytes = 0;
	uint64_t egressLpfBytes = 0;
	uint64_t totalIngressBytes = 0;
	uint64_t totalEgressBytes = 0;
	
	GetPortQueueBytes(port, qIndex, ingressBytes, egressBytes, ingressLpfBytes, egressLpfBytes);
	GetPortTotalBytes(port, qIndex, totalIngressBytes, totalEgressBytes);
	
	std::ofstream csvFile;
	std::ios_base::openmode mode = g_isFirstOpenQueueBytesCsv ? std::ios::out : std::ios::app;
	std::string switchQueueBytesPath = GetOutputDirectory() + "/flow_stats_switch_queue_bytes.csv";
	csvFile.open(switchQueueBytesPath.c_str(), mode);
	if (csvFile.is_open()) {
		// 如果是第一次打开，写入CSV头部
		if (g_isFirstOpenQueueBytesCsv) {
			csvFile << "Switch-Port,FlowID,Queue,PortType,IngressBytes,IngressLpfBytes,EgressBytes,EgressLpfBytes,TotalIngressBytes,TotalEgressBytes,Time(ns)" << std::endl;
			g_isFirstOpenQueueBytesCsv = false;
		}
		
		std::ostringstream switchPort;
		switchPort << "Switch" << m_id << "-Port" << port;
		std::string portType = isIngress ? "Ingress" : "Egress";
		
		csvFile << switchPort.str() << ","
		        << flowid << ","
		        << qIndex << ","
		        << portType << ","
		        << ingressBytes << ","
		        << ingressLpfBytes << ","
		        << egressBytes << ","
		        << egressLpfBytes << ","
		        << totalIngressBytes << ","
		        << totalEgressBytes << ","
		        << currentTime << std::endl;
		csvFile.close();
	}
}

// 输出与流相关的交换机端口数据量（输出所有有数据的端口）
void SwitchNode::LogFlowRelatedPortsQueueBytes(const std::string& flowid, uint32_t inPort, uint32_t outPort, uint32_t qIndex, uint64_t currentTime) {
	if (!flag_ENABLE_SWITCH_PORT_QUEUE_BYTES_LOG || !m_mmu || flowid.empty()) {
		return;
	}
	
	// 输出到文本文件
	std::ofstream flowstatsFile;
	std::ios_base::openmode mode = g_isFirstOpenSwitchStats ? std::ios::out : std::ios::app;
	std::string flowStatsSwitchPath = GetOutputDirectory() + "/flow_stats_switch.txt";
	flowstatsFile.open(flowStatsSwitchPath.c_str(), mode);
	if (flowstatsFile.is_open()) {
		flowstatsFile << "=== Switch " << m_id << " Flow " << flowid << " Triggered - All Ports with Data at Time " << currentTime << " ===" << std::endl;
		
		// 遍历所有端口和队列，输出有数据的端口
		for (uint32_t port = 0; port < SwitchMmu::pCnt; ++port) {
			for (uint32_t qIdx = 0; qIdx < SwitchMmu::qCnt; ++qIdx) {
				uint64_t ingressBytes = 0;
				uint64_t egressBytes = 0;
				uint64_t ingressLpfBytes = 0;
				uint64_t egressLpfBytes = 0;
				uint64_t totalIngressBytes = 0;
				uint64_t totalEgressBytes = 0;
				
				GetPortQueueBytes(port, qIdx, ingressBytes, egressBytes, ingressLpfBytes, egressLpfBytes);
				GetPortTotalBytes(port, qIdx, totalIngressBytes, totalEgressBytes);
				
				// 只要有任何数据不为0，就输出
				if (ingressBytes > 0 || egressBytes > 0 || ingressLpfBytes > 0 || egressLpfBytes > 0 || 
				    totalIngressBytes > 0 || totalEgressBytes > 0) {
					flowstatsFile << "  Port " << port << " Queue " << qIdx 
					              << " - IngressBytes: " << ingressBytes 
					              << ", IngressLpfBytes: " << ingressLpfBytes
					              << ", EgressBytes: " << egressBytes 
					              << ", EgressLpfBytes: " << egressLpfBytes
					              << ", TotalIngressBytes: " << totalIngressBytes 
					              << ", TotalEgressBytes: " << totalEgressBytes << std::endl;
				}
			}
		}
		
		flowstatsFile << "=== End of Switch " << m_id << " Flow " << flowid << " Triggered Ports Queue Bytes ===" << std::endl;
		flowstatsFile.close();
		g_isFirstOpenSwitchStats = false;
	}
	
	// 输出到CSV文件
	std::ofstream csvFile;
	std::ios_base::openmode csvMode = g_isFirstOpenQueueBytesCsv ? std::ios::out : std::ios::app;
	std::string switchQueueBytesPath = GetOutputDirectory() + "/flow_stats_switch_queue_bytes.csv";
	csvFile.open(switchQueueBytesPath.c_str(), csvMode);
	if (csvFile.is_open()) {
		// 如果是第一次打开，写入CSV头部
		if (g_isFirstOpenQueueBytesCsv) {
			csvFile << "Switch-Port,FlowID,Queue,PortType,IngressBytes,IngressLpfBytes,EgressBytes,EgressLpfBytes,TotalIngressBytes,TotalEgressBytes,Time(ns)" << std::endl;
			g_isFirstOpenQueueBytesCsv = false;
		}
		
		// 遍历所有端口和队列，输出有数据的端口
		for (uint32_t port = 0; port < SwitchMmu::pCnt; ++port) {
			for (uint32_t qIdx = 0; qIdx < SwitchMmu::qCnt; ++qIdx) {
				uint64_t ingressBytes = 0;
				uint64_t egressBytes = 0;
				uint64_t ingressLpfBytes = 0;
				uint64_t egressLpfBytes = 0;
				uint64_t totalIngressBytes = 0;
				uint64_t totalEgressBytes = 0;
				
				GetPortQueueBytes(port, qIdx, ingressBytes, egressBytes, ingressLpfBytes, egressLpfBytes);
				GetPortTotalBytes(port, qIdx, totalIngressBytes, totalEgressBytes);
				
				std::ostringstream switchPort;
				switchPort << "Switch" << m_id << "-Port" << port;
				
				// 如果有入端口数据，输出入端口记录
				if (ingressBytes > 0 || ingressLpfBytes > 0 || totalIngressBytes > 0) {
					csvFile << switchPort.str() << ","
					        << flowid << ","  // 记录触发输出的流ID
					        << qIdx << ","
					        << "Ingress" << ","  // PortType设为"Ingress"表示入端口
					        << ingressBytes << ","
					        << ingressLpfBytes << ","
					        << egressBytes << ","
					        << egressLpfBytes << ","
					        << totalIngressBytes << ","
					        << totalEgressBytes << ","
					        << currentTime << std::endl;
				}
				
				// 如果有出端口数据，输出出端口记录
				if (egressBytes > 0 || egressLpfBytes > 0 || totalEgressBytes > 0) {
					csvFile << switchPort.str() << ","
					        << flowid << ","  // 记录触发输出的流ID
					        << qIdx << ","
					        << "Egress" << ","  // PortType设为"Egress"表示出端口
					        << ingressBytes << ","
					        << ingressLpfBytes << ","
					        << egressBytes << ","
					        << egressLpfBytes << ","
					        << totalIngressBytes << ","
					        << totalEgressBytes << ","
					        << currentTime << std::endl;
				}
			}
		}
		
		csvFile.close();
	}
}

void SwitchNode::LogPfcDetailedStats(uint32_t port, uint32_t queue, bool pause) {
	if (!m_mmu) {
		return;
	}
	
	static std::ofstream pfcStatsFile;
	static bool pfcStatsFileOpened = false;
	
	if (!pfcStatsFileOpened) {
		std::string pfcStatsPath = GetOutputDirectory() + "/pfc_detailed_stats.csv";
		pfcStatsFile.open(pfcStatsPath.c_str(), std::ios::out);
		pfcStatsFile << "Time(ns),SwitchID,Port,Queue,Event,"
		             << "HeadroomUsed,HeadroomLimit,IngressBytes,EgressBytes,"
		             << "IngressThreshold,EgressThreshold,XonThreshold,XonOffset,"
		             << "IngressPoolUsed,IngressPoolTotal,EgressPoolUsed,EgressPoolTotal,"
		             << "TotalBufferUsed,TotalBufferSize,PauseDuration" << std::endl;
		pfcStatsFileOpened = true;
	}
	
	uint64_t currentTime = Simulator::Now().GetNanoSeconds();
	auto key = std::make_pair(port, queue);
	
	// 获取缓冲区状态信息
	uint64_t headroomUsed = m_mmu->GetHdrmBytes(port, queue);
	uint64_t headroomLimit = m_mmu->xoff[port][queue];
	uint64_t ingressBytes = m_mmu->ingress_bytes[port][queue];
	uint64_t egressBytes = m_mmu->egress_bytes[port][queue];
	uint64_t xonThreshold = m_mmu->xon[port][queue];
	uint64_t xonOffset = m_mmu->xon_offset[port][queue];
	
	// 获取阈值（根据缓冲区模型）
	uint64_t ingressThreshold = 0;
	uint64_t egressThreshold = 0;
	std::string model = m_mmu->bufferModel;
	if (model == "sonic") {
		ingressThreshold = m_mmu->Threshold(port, queue, "ingress", 0, 0);  // LOSSLESS
		egressThreshold = m_mmu->Threshold(port, queue, "egress", 0, 0);
	} else if (model == "reverie") {
		ingressThreshold = m_mmu->ReverieThreshold(port, queue, 0, 0);  // LOSSLESS
		egressThreshold = m_mmu->ReverieThreshold(port, queue, 1, 0);    // LOSSY
	}
	
	// 获取缓冲区池使用情况
	uint64_t ingressPoolUsed = m_mmu->GetIngressSharedUsed();
	uint64_t ingressPoolTotal = m_mmu->ingressPool - m_mmu->totalIngressReserved;
	uint64_t egressPoolUsed = m_mmu->egressPoolUsed[0];  // LOSSLESS
	uint64_t egressPoolTotal = m_mmu->egressPool[0];
	uint64_t totalBufferUsed = m_mmu->totalUsed;
	uint64_t totalBufferSize = m_mmu->bufferPool;
	
	// 计算PFC持续时间（如果是恢复事件）
	uint64_t pauseDuration = 0;
	if (!pause) {  // 恢复事件
		if (g_pfcPauseTime.find(key) != g_pfcPauseTime.end()) {
			pauseDuration = currentTime - g_pfcPauseTime[key];
			g_pfcPauseTime.erase(key);
		}
	} else {  // 暂停事件
		g_pfcPauseTime[key] = currentTime;
	}
	
	// 写入详细统计信息
	pfcStatsFile << currentTime << ","
	             << m_id << ","
	             << port << ","
	             << queue << ","
	             << (pause ? "PAUSE" : "RESUME") << ","
	             << headroomUsed << ","
	             << headroomLimit << ","
	             << ingressBytes << ","
	             << egressBytes << ","
	             << ingressThreshold << ","
	             << egressThreshold << ","
	             << xonThreshold << ","
	             << xonOffset << ","
	             << ingressPoolUsed << ","
	             << ingressPoolTotal << ","
	             << egressPoolUsed << ","
	             << egressPoolTotal << ","
	             << totalBufferUsed << ","
	             << totalBufferSize << ","
	             << pauseDuration << std::endl;
	
	pfcStatsFile.flush();  // 确保数据及时写入
}

} /* namespace ns3 */
