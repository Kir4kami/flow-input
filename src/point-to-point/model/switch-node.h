#ifndef SWITCH_NODE_H
#define SWITCH_NODE_H

#include <unordered_map>
#include <map>
#include <string>
#include <sstream>
#include <fstream>
#include <deque>
#include <ns3/node.h>
#include "qbb-net-device.h"
#include "switch-mmu.h"
#include "pint.h"

namespace ns3 {

class Packet;

class SwitchNode : public Node{
	static const uint32_t pCnt = 257;	// Number of ports used 支持的端口数
	static const uint32_t qCnt = 8;	// Number of queues/priorities used 优先级队列数
	uint32_t m_ecmpSeed; //哈希种子
	std::unordered_map<uint32_t, std::vector<int> > m_rtTable; // map from ip address (u32) to possible ECMP port (index of dev)

	// monitor of PFC
	//记录从 inDev 入端口流入的、准备从 outDev 出端口发出的、排队在第 qidx 队列的字节数，用于触发 PFC Pause
	 // m_bytes[inDev][outDev][qidx] is the bytes from inDev enqueued for outDev at qidx
	
	uint64_t m_txBytes[pCnt]; // counter of tx bytes 每个端口发出的总字节数


	uint32_t m_lastPktSize[pCnt];
	uint64_t m_lastPktTs[pCnt]; // ns
	double m_u[pCnt]; // 估算的带宽利用率

protected:
	bool m_ecnEnabled;
	uint32_t m_ccMode;
	uint64_t m_maxRtt;

	uint32_t m_ackHighPrio; // set high priority for ACK/NACK

	// vamsi
	bool PowerEnabled;

private:
	int GetOutDev(Ptr<const Packet>, CustomHeader &ch);
	void SendToDev(Ptr<Packet>p, CustomHeader &ch);
	static uint32_t EcmpHash(const uint8_t* key, size_t len, uint32_t seed);
	void CheckAndSendPfc(uint32_t inDev, uint32_t qIndex);//检查是否需要向 inDev 发 Pause Frame
	void CheckAndSendResume(uint32_t inDev, uint32_t qIndex);//释放流控
public:
	Ptr<SwitchMmu> m_mmu;
	uint32_t m_bytes[pCnt][pCnt][qCnt];//这里把私变成了public
	
	static TypeId GetTypeId (void);
	SwitchNode();
	void SetEcmpSeed(uint32_t seed);
	void AddTableEntry(Ipv4Address &dstAddr, uint32_t intf_idx);
	void ClearTable();
	//交换机从某个设备收到包的入口，决定转发路径并入队
	bool SwitchReceiveFromDevice(Ptr<NetDevice> device, Ptr<Packet> packet, CustomHeader &ch);
	//从某个端口队列出队时的回调，可能更新 m_bytes、检测 Resume 条件
	void SwitchNotifyDequeue(uint32_t ifIndex, uint32_t qIndex, Ptr<Packet> p);

	//补偿
	void SwitchStatsUpdate(int flag, uint32_t switchid);

	//时延
	void SwitchTimeDelay(int flag);

	//统计交换机上的数据
	void SwitchStatsCount(int flag);

	void BandWidthMonitor(Ptr<Packet> packet, CustomHeader &ch);
	void Caculate(Ptr<Packet> packet, CustomHeader &ch);

	// 交换机端口流速率计算
	void CalculateFlowRateAtPort(uint32_t port, const std::string& flowid, uint16_t packetSize, bool isIngress = true, uint32_t qIndex = 0);
	std::string GenerateFlowIdFromPacket(Ptr<Packet> packet, CustomHeader &ch);
	
	// 获取端口数据量
	void GetPortQueueBytes(uint32_t port, uint32_t qIndex, uint64_t& ingressBytes, uint64_t& egressBytes, uint64_t& ingressLpfBytes, uint64_t& egressLpfBytes);
	
	// 获取端口累积统计（进入和离开的总字节数）
	void GetPortTotalBytes(uint32_t port, uint32_t qIndex, uint64_t& totalIngressBytes, uint64_t& totalEgressBytes);
	
	// 输出端口数据量
	void LogPortQueueBytes(uint32_t port, uint32_t qIndex, bool isIngress, uint64_t currentTime, const std::string& flowid = "");
	
	// 输出速率到CSV文件
	void LogRateToCsv(uint32_t port, uint32_t qIndex, bool isIngress, const std::string& flowid, double avgRate, double instantRate, 
	                  uint64_t windowStart, uint64_t windowEnd, uint64_t windowBytes, uint64_t packetCount, uint64_t currentTime);
	
	// 输出端口数据量到CSV文件
	void LogPortQueueBytesToCsv(uint32_t port, uint32_t qIndex, bool isIngress, const std::string& flowid, uint64_t currentTime);
	
	// 输出与流相关的交换机端口数据量（该流经过的入端口和出端口）
	void LogFlowRelatedPortsQueueBytes(const std::string& flowid, uint32_t inPort, uint32_t outPort, uint32_t qIndex, uint64_t currentTime);
	
	// 记录PFC详细统计信息到CSV文件
	void LogPfcDetailedStats(uint32_t port, uint32_t queue, bool pause);
	
	// for approximate calc in PINT
	int logres_shift(int b, int l);
	int log2apprx(int x, int b, int m, int l); // given x of at most b bits, use most significant m bits of x, calc the result in l bits

private:
	// 每个交换机的每个端口的流统计信息：switchId -> port -> flowid -> FlowStat
	// 使用交换机ID作为第一层键，确保不同交换机的数据完全隔离
	std::map<uint32_t, std::map<uint32_t, std::map<std::string, FlowStat>>> m_switchPortFlowStats;
};
} /* namespace ns3 */

#endif /* SWITCH_NODE_H */
