#ifndef SIMPLIFIED_SWITCH_NODE_H
#define SIMPLIFIED_SWITCH_NODE_H

#include <map>
#include <unordered_map>
#include <vector>

#include "ns3/node.h"
#include "switch-mmu.h"
#include "simplified-switch-simulator-wrapper.h"

namespace ns3 {

class Packet;
class NetDevice;
class Ipv4Address;
struct CustomHeader;

// 数值仿真交换机节点（独立实现，不继承 SwitchNode）。
// 负责：收包、路由选端口、队列选择、MMU准入、PFC触发、时间戳更新、发包。
class SimplifiedSwitchNode : public Node
{
public:
  static const uint32_t pCnt = 257; // 交换机支持的最大端口数（与现有模型保持一致）
  static const uint32_t qCnt = 8;   // 每端口优先级队列数

  // ns-3 运行时类型信息（注册属性与构造器）
  static TypeId GetTypeId (void);
  // 构造函数：初始化MMU、内部统计状态和数值仿真内核
  SimplifiedSwitchNode ();

  // 设置ECMP哈希种子
  void SetEcmpSeed (uint32_t seed);
  // 添加目的IP到出端口映射（支持ECMP多下一跳）
  void AddTableEntry (Ipv4Address &dstAddr, uint32_t intf_idx);
  // 清空路由表
  void ClearTable ();

  // 交换机收包入口：由QbbNetDevice调用，负责入口时间戳与后续转发
  bool SwitchReceiveFromDevice (Ptr<NetDevice> device, Ptr<Packet> packet, CustomHeader &ch) override;
  // 交换机出队回调：由QbbNetDevice调用，负责释放MMU占用与出口时间戳
  void SwitchNotifyDequeue (uint32_t ifIndex, uint32_t qIndex, Ptr<Packet> p) override;
  // 兼容Node虚接口：统计入口（当前为占位）
  void SwitchStatsCount (int flag) override;
  // 兼容Node虚接口：统计更新（当前为占位）
  void SwitchStatsUpdate (int flag, uint32_t switchid) override;
  // 兼容Node虚接口：时延补偿（当前为占位）
  void SwitchTimeDelay (int flag) override;

  // 从数据包头提取流标识（srcId-dstId-sport-dport）
  std::string GenerateFlowIdFromPacket (Ptr<Packet> packet, CustomHeader &ch);

  Ptr<SwitchMmu> m_mmu;                  // 数值仿真交换机的MMU对象（准入/PFC/占用统计）
  uint32_t m_bytes[pCnt][pCnt][qCnt];    // 队列占用矩阵：m_bytes[inDev][outDev][qIndex]

private:
  // 根据包头与路由表选择出端口（ECMP）
  int GetOutDev (Ptr<const Packet> p, CustomHeader &ch);
  // 核心转发逻辑：准入、标签、PFC、发包
  void SendToDev (Ptr<Packet> p, CustomHeader &ch);
  // 检查并发送PFC Pause
  void CheckAndSendPfc (uint32_t inDev, uint32_t qIndex);
  // 检查并发送PFC Resume
  void CheckAndSendResume (uint32_t inDev, uint32_t qIndex);
  // 记录PFC详细统计（字段/顺序对齐原始仿真的 pfc_detailed_stats.csv）
  void LogPfcDetailedStats (uint32_t port, uint32_t queue, bool pause);
  // 在真实时间加速模式下，按逻辑时刻延后释放MMU占用，保持PFC判定有效。
  void ReleaseAdmissionAndResume (uint32_t inDev, uint32_t outDev, uint32_t qIndex, uint32_t packetSize, bool foundPrio);
  // 逻辑虚拟缓冲区入队：仅做数值计数，不依赖 MMU admission/update。
  void VirtualBufferEnqueue (uint32_t inDev, uint32_t outDev, uint32_t qIndex, uint32_t packetSize);
  // 逻辑虚拟缓冲区释放：按逻辑时间调度，释放后执行 Resume 判定。
  void VirtualBufferReleaseAndResume (uint32_t inDev, uint32_t outDev, uint32_t qIndex, uint32_t packetSize);
  // 逻辑虚拟缓冲区 Pause 判定与发送。
  void CheckAndSendVirtualPfc (uint32_t inDev, uint32_t qIndex);
  // 逻辑虚拟缓冲区 Resume 判定与发送。
  void CheckAndSendVirtualResume (uint32_t inDev, uint32_t qIndex);
  // 计算逻辑虚拟缓冲区的动态阈值（与 DT 思路一致，随剩余共享池动态变化）。
  uint64_t ComputeVirtualIngressThreshold (uint32_t inDev, uint32_t qIndex) const;
  // 将包真正下发到指定设备（用于支持“发送前微小打散”调度）。
  void DispatchToDevice (uint32_t outDev, uint32_t qIndex, Ptr<Packet> p, CustomHeader ch);
  // ECMP哈希函数（Murmur风格）
  static uint32_t EcmpHash (const uint8_t* key, size_t len, uint32_t seed);
  // 根据协议/标签计算队列优先级
  uint32_t ResolveQueueIndex (Ptr<Packet> p, CustomHeader &ch) const;

private:
  uint32_t m_ecmpSeed;                                   // ECMP哈希种子
  bool m_ecnEnabled;                                     // 是否启用ECN标记
  uint32_t m_ccMode;                                     // 拥塞控制模式（与原模型配置对齐）
  uint64_t m_maxRtt;                                     // 最大RTT（用于INT/PINT相关逻辑兼容）
  uint32_t m_ackHighPrio;                                // ACK/NACK是否走高优先级
  bool m_powerEnabled;                                   // INT统计模式开关（TxBytes/RxBytes）
  uint64_t m_lastPortDispatchNs[pCnt];                   // 每个出端口最近一次下发时刻（用于发送前1ns打散）
  uint64_t m_virtualIngressBytes[pCnt][qCnt];            // 逻辑虚拟缓冲区：入端口队列占用
  uint64_t m_virtualEgressBytes[pCnt][qCnt];             // 逻辑虚拟缓冲区：出端口队列占用
  uint64_t m_virtualHeadroomBytes[pCnt][qCnt];           // 逻辑虚拟缓冲区：headroom 占用
  uint64_t m_virtualTotalBytes;                          // 逻辑虚拟缓冲区：总占用
  uint64_t m_virtualHeadroomTotalUsed;                   // 逻辑虚拟缓冲区：总 headroom 占用
  uint64_t m_virtualTotalIngressReservedUsed;            // 逻辑虚拟缓冲区：总 ingress reserved 使用量
  bool m_virtualPaused[pCnt][qCnt];                      // 逻辑虚拟缓冲区：每队列 pause 状态
  std::unordered_map<uint32_t, std::vector<int> > m_rtTable; // 路由表：dstIP -> 候选出端口列表
  SimplifiedSwitchSimulatorWrapper m_kernel;             // 数值仿真时序内核（队列时间推进/时间戳加速）
};

} // namespace ns3

#endif /* SIMPLIFIED_SWITCH_NODE_H */
