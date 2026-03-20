#ifndef SIMPLIFIED_SWITCH_SIMULATOR_WRAPPER_H
#define SIMPLIFIED_SWITCH_SIMULATOR_WRAPPER_H

#include <cstdint>
#include <unordered_map>
#include <vector>

namespace ns3 {

// 数值仿真内核：
// 基于“包到达时刻 + 端口带宽 + 队列状态”推进时序，
// 并将排队时延折算到包时间戳中，达到统计时间压缩（加速）效果。
class SimplifiedSwitchSimulatorWrapper
{
public:
  // 构造函数：创建空内核对象，具体规模由Initialize设置
  SimplifiedSwitchSimulatorWrapper ();

  // 初始化端口/队列规模，并清空队列时序状态
  void Initialize (uint32_t portCount, uint32_t queueCount);

  // 计算入口阶段的“数值仿真时间戳”。
  // 参数：
  // - nowNs: 当前仿真时刻
  // - outDev/qIndex: 即将进入的出端口与队列
  // - packetSizeBytes: 数据包大小（字节）
  // - bitRateBps: 端口速率（bps）
  // - packetUid: 包唯一ID，用于后续出队时回查预测时刻
  uint64_t ComputeIngressTimestamp (uint64_t nowNs,
                                    uint32_t outDev,
                                    uint32_t qIndex,
                                    uint32_t packetSizeBytes,
                                    uint64_t bitRateBps,
                                    uint64_t propagationDelayNs,
                                    uint64_t packetUid);

  // 计算出口阶段时间戳（结合入口时记录的预测时刻）
  // 可选返回 predictedReleaseNs（交换机“出队/开始服务”时刻），
  // 用于与原始仿真的 SwitchNotifyDequeue/MMU释放时刻对齐。
  uint64_t ComputeEgressTimestamp (uint64_t nowNs,
                                   uint64_t packetUid,
                                   uint64_t* predictedReleaseNs);

private:
  // 序列化发送时延（ns）= 包长(bit)/带宽(bps)
  uint64_t SerializationDelayNs (uint32_t packetSizeBytes, uint64_t bitRateBps) const;
  // 计算二维(port,qIndex)在一维数组中的下标
  uint64_t QueueIndex (uint32_t port, uint32_t qIndex) const;

  uint32_t m_portCount;                                // 端口数
  uint32_t m_queueCount;                               // 每端口队列数
  std::vector<uint64_t> m_queueNextAvailableNs;        // 每个(port,q)下一次可服务时刻
  std::unordered_map<uint64_t, uint64_t> m_predictedReleaseByPacketUid;   // 包UID -> 预测出队(开始服务)时刻
  std::unordered_map<uint64_t, uint64_t> m_predictedEgressByPacketUid; // 包UID -> 预测出队时刻
};

} // namespace ns3

#endif /* SIMPLIFIED_SWITCH_SIMULATOR_WRAPPER_H */
