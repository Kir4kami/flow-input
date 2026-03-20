#include "simplified-switch-simulator-wrapper.h"

#include <algorithm>
#include <limits>

namespace ns3 {

// 构造：默认不分配队列状态，等待Initialize传入规模。
SimplifiedSwitchSimulatorWrapper::SimplifiedSwitchSimulatorWrapper ()
  : m_portCount (0),   // 端口数初始化为0
    m_queueCount (0)   // 队列数初始化为0
{
}

// 初始化内核规模并重置状态。
void
SimplifiedSwitchSimulatorWrapper::Initialize (uint32_t portCount, uint32_t queueCount)
{
  m_portCount = portCount;    // 记录端口数
  m_queueCount = queueCount;  // 记录队列数
  // 为每个(port,q)分配一个“下一次可服务时刻”槽位，初始为0。
  m_queueNextAvailableNs.assign(static_cast<size_t>(portCount) * static_cast<size_t>(queueCount), 0);
  // 清空包UID到预测出队时刻的映射，避免跨仿真阶段污染。
  m_predictedReleaseByPacketUid.clear();
  m_predictedEgressByPacketUid.clear();
}

// 计算链路序列化时延（单位ns）。
uint64_t
SimplifiedSwitchSimulatorWrapper::SerializationDelayNs (uint32_t packetSizeBytes, uint64_t bitRateBps) const
{
  if (bitRateBps == 0) // 带宽为0时避免除零，按0处理
    {
      return 0;
    }
  const long double bits = static_cast<long double>(packetSizeBytes) * 8.0L; // 包长(bit)
  const long double ns = bits * 1e9L / static_cast<long double>(bitRateBps); // 序列化时延(ns)
  if (ns <= 0.0L) // 保护：非正值直接返回0
    {
      return 0;
    }
  if (ns >= static_cast<long double>(std::numeric_limits<uint64_t>::max())) // 饱和保护
    {
      return std::numeric_limits<uint64_t>::max();
    }
  return static_cast<uint64_t>(ns); // 与原始链路时延计算口径对齐：按Time离散步长自然截断
}

// 将(port,qIndex)映射到一维数组下标。
uint64_t
SimplifiedSwitchSimulatorWrapper::QueueIndex (uint32_t port, uint32_t qIndex) const
{
  return static_cast<uint64_t>(port) * static_cast<uint64_t>(m_queueCount) + qIndex; // 行主序
}

// 入口时序推进：
// 1) 计算该队列开始服务时刻 startNs；
// 2) 推进队列下一可用时刻；
// 3) 记录该包预测出队时刻；
// 4) 返回“并入排队等待后的入口时间戳”。
uint64_t
SimplifiedSwitchSimulatorWrapper::ComputeIngressTimestamp (uint64_t nowNs,
                                                           uint32_t outDev,
                                                           uint32_t qIndex,
                                                           uint32_t packetSizeBytes,
                                                           uint64_t bitRateBps,
                                                           uint64_t propagationDelayNs,
                                                           uint64_t packetUid)
{
  if (m_portCount == 0 || m_queueCount == 0 || outDev >= m_portCount || qIndex >= m_queueCount) // 参数保护
    {
      return nowNs;
    }

  const uint64_t idx = QueueIndex(outDev, qIndex);                        // 当前队列下标
  const uint64_t serviceNs = SerializationDelayNs(packetSizeBytes, bitRateBps); // 服务时长
  const uint64_t startNs = std::max(nowNs, m_queueNextAvailableNs[idx]);  // 实际开始服务时刻
  const uint64_t predictedDepartureNs = startNs + serviceNs;              // 预测出队时刻（交换机端口完成发送）
  const uint64_t predictedArrivalNs = predictedDepartureNs + propagationDelayNs; // 预测到达下一跳时刻
  m_queueNextAvailableNs[idx] = predictedDepartureNs;                     // 更新队列“忙到”时间
  m_predictedReleaseByPacketUid[packetUid] = startNs;                     // 记录交换机“出队/开始服务”时刻
  m_predictedEgressByPacketUid[packetUid] = predictedArrivalNs;           // 记录“加速后的有效时间戳”

  // 入口时间戳保持当前时刻；排队/序列化/传播时间统一并入出口阶段时间戳。
  return nowNs;
}

// 出口时间戳计算：
// 返回“预测到达下一跳时刻”（用于逻辑时间标签），并可选返回“预测出队/开始服务时刻”（用于MMU释放对齐）。
uint64_t
SimplifiedSwitchSimulatorWrapper::ComputeEgressTimestamp (uint64_t nowNs,
                                                          uint64_t packetUid,
                                                          uint64_t* predictedReleaseNs)
{
  auto it = m_predictedEgressByPacketUid.find(packetUid); // 查预测出队时刻
  auto relIt = m_predictedReleaseByPacketUid.find(packetUid);
  if (predictedReleaseNs)
    {
      *predictedReleaseNs = (relIt == m_predictedReleaseByPacketUid.end()) ? nowNs : relIt->second;
    }
  if (it == m_predictedEgressByPacketUid.end()) // 若未记录（异常路径），退化为当前时刻
    {
      if (relIt != m_predictedReleaseByPacketUid.end())
        {
          m_predictedReleaseByPacketUid.erase(relIt);
        }
      return nowNs;
    }

  // “真实时间加速”模式下允许 egress 晚于当前仿真时刻，
  // 后续统计会以 max(now, egress) 作为有效接收时刻，避免被过滤。
  const uint64_t predicted = it->second;          // 读取预测时刻
  m_predictedEgressByPacketUid.erase(it);         // 一次性消费，防止重复使用
  if (relIt != m_predictedReleaseByPacketUid.end())
    {
      m_predictedReleaseByPacketUid.erase(relIt);
    }
  return predicted;
}

} // namespace ns3
