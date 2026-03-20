#include "simplified-switch-node.h"

#include "ns3/boolean.h"
#include "ns3/custom-priority-tag.h"
#include "ns3/int-header.h"
#include "ns3/interface-tag.h"
#include "ns3/ipv4-header.h"
#include "ns3/packet.h"
#include "ns3/pause-header.h"
#include "ppp-header.h"
#include "qbb-net-device.h"
#include "qbb-channel.h"
#include "ns3/simulator.h"
#include "ns3/tcp-header.h"
#include "ns3/udp-header.h"
#include "ns3/uinteger.h"
#include "ns3/unsched-tag.h"
#include "switch-timing-tag.h"
#include "output-directory.h"
#include "stat-config.h"

#include <algorithm>
#include <chrono>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>

namespace ns3 {

// 注册类型到ns-3对象系统。
NS_OBJECT_ENSURE_REGISTERED (SimplifiedSwitchNode);

namespace {
// 获取当前“墙钟时间”纳秒，用于与仿真时间并行记录。
uint64_t
GetWallClockNs()
{
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
           std::chrono::steady_clock::now().time_since_epoch())
    .count();
}

void
LogPacketDropDebug (uint64_t timeNs,
                    uint32_t switchId,
                    uint64_t packetUid,
                    uint32_t inDev,
                    int outDev,
                    uint32_t qIndex,
                    uint8_t protocol,
                    uint32_t packetSize,
                    const std::string &reason)
{
  if (!flag_ENABLE_STAT_FILE_OUTPUT)
    {
      return;
    }

  static std::ofstream dropDebugFile;
  static bool dropDebugFileOpened = false;
  if (!dropDebugFileOpened)
    {
      std::string dropPath = GetOutputDirectory() + "/packet_drop_debug.csv";
      dropDebugFile.open(dropPath.c_str(), std::ios::out);
      if (!dropDebugFile.is_open())
        {
          return;
        }
      dropDebugFile << "Time(ns),SwitchID,PacketUid,InDev,OutDev,Queue,Protocol,PacketSize(Bytes),Reason" << std::endl;
      dropDebugFileOpened = true;
    }

  dropDebugFile << timeNs << ","
                << switchId << ","
                << packetUid << ","
                << inDev << ","
                << outDev << ","
                << qIndex << ","
                << static_cast<uint32_t>(protocol) << ","
                << packetSize << ","
                << reason << std::endl;
}

void
LogPfcEventSent (uint64_t timeNs,
                 uint32_t switchId,
                 uint32_t inDev,
                 uint32_t qIndex,
                 bool isPause)
{
  if (!flag_ENABLE_STAT_FILE_OUTPUT || !flag_ENABLE_PFC_EVENTS_LOG)
    {
      return;
    }

  static std::ofstream pfcLogFile;
  static bool pfcLogOpened = false;
  if (!pfcLogOpened)
    {
      std::string pfcPath = GetOutputDirectory() + "/pfc_events.csv";
      std::ifstream existing(pfcPath.c_str());
      const bool hasExisting = existing.good() && existing.peek() != std::ifstream::traits_type::eof();
      existing.close();
      pfcLogFile.open(pfcPath.c_str(), std::ios::app);
      if (!pfcLogFile.is_open())
        {
          return;
        }
      if (!hasExisting)
        {
          pfcLogFile << "Time(ns),Event,NodeType,NodeID,Port/DeviceIndex,Queue,Action" << std::endl;
        }
      pfcLogOpened = true;
    }

  if (isPause)
    {
      pfcLogFile << timeNs << ",PFC_PAUSE_SENT,Switch," << switchId << "," << inDev << "," << qIndex << ",Pause" << std::endl;
    }
  else
    {
      pfcLogFile << timeNs << ",PFC_RESUME_SENT,Switch," << switchId << "," << inDev << "," << qIndex << ",Resume" << std::endl;
    }
  pfcLogFile.flush();
}

void
LogReleaseDelayDebug (uint64_t nowNs,
                      uint64_t adjustedEgressNs,
                      uint64_t rawReleaseDelayNs,
                      uint64_t appliedReleaseDelayNs,
                      uint64_t rawReleaseTimeNs,
                      uint64_t appliedReleaseTimeNs,
                      uint64_t subtractNs,
                      uint64_t packetUid,
                      uint32_t switchId,
                      uint32_t inDev,
                      uint32_t outDev,
                      uint32_t qIndex,
                      uint32_t packetSize,
                      bool trueTimeAccelerationEnabled)
{
  if (!flag_ENABLE_STAT_FILE_OUTPUT || !flag_ENABLE_RELEASE_DELAY_DEBUG_CSV)
    {
      return;
    }

  static std::ofstream releaseDelayFile;
  static bool releaseDelayFileOpened = false;
  if (!releaseDelayFileOpened)
    {
      const std::string path = GetOutputDirectory() + "/release_delay_debug.csv";
      releaseDelayFile.open(path.c_str(), std::ios::out);
      if (!releaseDelayFile.is_open())
        {
          return;
        }
      releaseDelayFile << "NowNs,AdjustedEgressNs,RawReleaseDelayNs,AppliedReleaseDelayNs,RawReleaseTimeNs,AppliedReleaseTimeNs,SubtractNs,PacketUid,SwitchID,InDev,OutDev,Queue,PacketSize(Bytes),TrueTimeAccelerationEnabled"
                       << std::endl;
      releaseDelayFileOpened = true;
    }

  releaseDelayFile << nowNs << ","
                   << adjustedEgressNs << ","
                   << rawReleaseDelayNs << ","
                   << appliedReleaseDelayNs << ","
                   << rawReleaseTimeNs << ","
                   << appliedReleaseTimeNs << ","
                   << subtractNs << ","
                   << packetUid << ","
                   << switchId << ","
                   << inDev << ","
                   << outDev << ","
                   << qIndex << ","
                   << packetSize << ","
                   << (trueTimeAccelerationEnabled ? 1 : 0)
                   << std::endl;
  releaseDelayFile.flush();
}

// 记录每个(端口,队列)最近一次PAUSE时刻，用于在RESUME时计算持续时间。
std::map<std::pair<uint32_t, uint32_t>, uint64_t> g_simplifiedPfcPauseTime;
}

TypeId
SimplifiedSwitchNode::GetTypeId (void)
{
  // 声明并缓存类型描述对象（静态局部只构造一次）。
  static TypeId tid = TypeId ("ns3::SimplifiedSwitchNode")
    .SetParent<Node> ()
    .SetGroupName ("PointToPoint")
    .AddAttribute("EcnEnabled",
                  "Enable ECN marking.",
                  BooleanValue(false),
                  MakeBooleanAccessor(&SimplifiedSwitchNode::m_ecnEnabled),
                  MakeBooleanChecker())
    .AddAttribute("CcMode",
                  "CC mode.",
                  UintegerValue(0),
                  MakeUintegerAccessor(&SimplifiedSwitchNode::m_ccMode),
                  MakeUintegerChecker<uint32_t>())
    .AddAttribute("AckHighPrio",
                  "Set high priority for ACK/NACK or not.",
                  UintegerValue(0),
                  MakeUintegerAccessor(&SimplifiedSwitchNode::m_ackHighPrio),
                  MakeUintegerChecker<uint32_t>())
    .AddAttribute("MaxRtt",
                  "Max RTT of the network.",
                  UintegerValue(9000),
                  MakeUintegerAccessor(&SimplifiedSwitchNode::m_maxRtt),
                  MakeUintegerChecker<uint64_t>())
    .AddAttribute("PowerEnabled",
                  "Insert Rxbytes instead of Txbytes in INT header.",
                  BooleanValue(false),
                  MakeBooleanAccessor(&SimplifiedSwitchNode::m_powerEnabled),
                  MakeBooleanChecker())
    .AddConstructor<SimplifiedSwitchNode> ();
  return tid;
}

SimplifiedSwitchNode::SimplifiedSwitchNode ()
  : m_ecmpSeed (0),
    m_ecnEnabled (false),
    m_ccMode (0),
    m_maxRtt (9000),
    m_ackHighPrio (0),
    m_powerEnabled (false)
{
  m_node_type = 1;                         // 标记为交换机节点
  m_ecmpSeed = m_id;                       // 默认用节点ID作为ECMP种子
  m_mmu = CreateObject<SwitchMmu>();       // 初始化独立MMU
  std::memset(m_bytes, 0, sizeof(m_bytes)); // 清零入-出端口-队列占用统计
  std::memset(m_lastPortDispatchNs, 0, sizeof(m_lastPortDispatchNs)); // 清零发送打散时间状态
  std::memset(m_virtualIngressBytes, 0, sizeof(m_virtualIngressBytes));
  std::memset(m_virtualEgressBytes, 0, sizeof(m_virtualEgressBytes));
  std::memset(m_virtualHeadroomBytes, 0, sizeof(m_virtualHeadroomBytes));
  std::memset(m_virtualPaused, 0, sizeof(m_virtualPaused));
  m_virtualTotalBytes = 0;
  m_virtualHeadroomTotalUsed = 0;
  m_virtualTotalIngressReservedUsed = 0;
  m_kernel.Initialize(pCnt, qCnt);         // 初始化数值仿真时序内核
}

// 设置ECMP哈希种子。
void
SimplifiedSwitchNode::SetEcmpSeed (uint32_t seed)
{
  m_ecmpSeed = seed;
}

// 添加一条路由项：目标IP -> 出端口。
void
SimplifiedSwitchNode::AddTableEntry (Ipv4Address &dstAddr, uint32_t intf_idx)
{
  m_rtTable[dstAddr.Get()].push_back(static_cast<int>(intf_idx));
}

// 清空路由表。
void
SimplifiedSwitchNode::ClearTable ()
{
  m_rtTable.clear();
}

// 解析优先级队列索引：
// 1) 控制包/高优先ACK走队列0；
// 2) 若存在自定义优先级标签则用标签；
// 3) 否则TCP走1，UDP走PG。
uint32_t
SimplifiedSwitchNode::ResolveQueueIndex (Ptr<Packet> p, CustomHeader &ch) const
{
  MyPriorityTag priotag;                  // 包内优先级标签
  const bool found = p->PeekPacketTag(priotag); // 是否存在优先级标签
  if (ch.l3Prot == 0xFF || ch.l3Prot == 0xFE || (m_ackHighPrio && (ch.l3Prot == 0xFD || ch.l3Prot == 0xFC)))
    {
      return 0;
    }
  if (found)
    {
      return priotag.GetPriority();
    }
  return (ch.l3Prot == 0x06) ? 1 : ch.udp.pg;
}

// 根据ECMP路由表计算出端口。
int
SimplifiedSwitchNode::GetOutDev (Ptr<const Packet> p, CustomHeader &ch)
{
  Ptr<Packet> cp = p->Copy(); // 使用拷贝解析头，避免修改原包
  PppHeader ph;               // 二层头
  Ipv4Header ih;              // 三层头
  cp->RemoveHeader(ph);
  cp->RemoveHeader(ih);

  auto entry = m_rtTable.find(ih.GetDestination().Get()); // 路由查表
  if (entry == m_rtTable.end() || entry->second.empty())
    {
      return -1;
    }

  union // 组装五元组相关字段作为哈希输入
  {
    uint8_t u8[12];
    uint32_t u32[3];
  } buf{};

  buf.u32[0] = ih.GetSource().Get();
  buf.u32[1] = ih.GetDestination().Get();
  if (ih.GetProtocol() == 0x6)
    {
      TcpHeader th;
      cp->PeekHeader(th);
      buf.u32[2] = th.GetSourcePort() | (static_cast<uint32_t>(th.GetDestinationPort()) << 16);
    }
  else if (ch.l3Prot == 0x11)
    {
      buf.u32[2] = ch.udp.sport | (static_cast<uint32_t>(ch.udp.dport) << 16);
    }
  else if (ch.l3Prot == 0xFC || ch.l3Prot == 0xFD)
    {
      buf.u32[2] = ch.ack.sport | (static_cast<uint32_t>(ch.ack.dport) << 16);
    }

  const auto &nexthops = entry->second; // 候选下一跳集合
  uint32_t idx = EcmpHash(buf.u8, sizeof(buf.u8), m_ecmpSeed) % nexthops.size(); // ECMP选择
  return nexthops[idx];
}

// 判断是否触发PFC Pause并发送。
void
SimplifiedSwitchNode::CheckAndSendPfc (uint32_t inDev, uint32_t qIndex)
{
  Ptr<QbbNetDevice> device = DynamicCast<QbbNetDevice>(m_devices[inDev]); // 入端口设备
  if (!device)
    {
      return;
    }
  if (m_mmu->CheckShouldPause(inDev, qIndex))
    {
      device->SendPfc(qIndex, 0);
      m_mmu->SetPause(inDev, qIndex);//防止重复触发/重复发送 pause，形成状态闭环
      LogPfcEventSent(Simulator::Now().GetNanoSeconds(), m_id, inDev, qIndex, true);
      LogPfcDetailedStats(inDev, qIndex, true);
    }
}

// 判断是否触发PFC Resume并发送。
void
SimplifiedSwitchNode::CheckAndSendResume (uint32_t inDev, uint32_t qIndex)
{
  Ptr<QbbNetDevice> device = DynamicCast<QbbNetDevice>(m_devices[inDev]); // 入端口设备
  if (!device)
    {
      return;
    }
  if (m_mmu->CheckShouldResume(inDev, qIndex))
    {
      device->SendPfc(qIndex, 1);
      m_mmu->SetResume(inDev, qIndex);
      LogPfcEventSent(Simulator::Now().GetNanoSeconds(), m_id, inDev, qIndex, false);
      LogPfcDetailedStats(inDev, qIndex, false);
    }
}

uint64_t
SimplifiedSwitchNode::ComputeVirtualIngressThreshold (uint32_t inDev, uint32_t qIndex) const
{
  // 仅实现 DT 思路：阈值随“剩余共享池”动态变化。
  const uint64_t ingressSharedPool = (m_mmu->ingressPool > m_mmu->totalIngressReserved)
                                       ? (m_mmu->ingressPool - m_mmu->totalIngressReserved)
                                       : 0;
  const uint64_t sharedUsed = (m_virtualTotalBytes >= m_virtualHeadroomTotalUsed + m_virtualTotalIngressReservedUsed)
                                ? (m_virtualTotalBytes - m_virtualHeadroomTotalUsed - m_virtualTotalIngressReservedUsed)
                                : 0;
  const uint64_t remaining = (ingressSharedPool > sharedUsed) ? (ingressSharedPool - sharedUsed) : 0;
  const double alpha = m_mmu->alphaIngress[inDev][qIndex];
  const long double scaled = static_cast<long double>(alpha) * static_cast<long double>(remaining);
  const long double cap = static_cast<long double>(std::numeric_limits<uint64_t>::max() - 1024ULL * 1024ULL);
  return static_cast<uint64_t>(std::min(scaled, cap));
}

void
SimplifiedSwitchNode::CheckAndSendVirtualPfc (uint32_t inDev, uint32_t qIndex)
{
  Ptr<QbbNetDevice> device = DynamicCast<QbbNetDevice>(m_devices[inDev]);
  if (!device)
    {
      return;
    }
  if (!m_virtualPaused[inDev][qIndex] && m_virtualHeadroomBytes[inDev][qIndex] > 0)
    {
      device->SendPfc(qIndex, 0);
      m_virtualPaused[inDev][qIndex] = true;
      LogPfcEventSent(Simulator::Now().GetNanoSeconds(), m_id, inDev, qIndex, true);
      LogPfcDetailedStats(inDev, qIndex, true);
    }
}

void
SimplifiedSwitchNode::CheckAndSendVirtualResume (uint32_t inDev, uint32_t qIndex)
{
  Ptr<QbbNetDevice> device = DynamicCast<QbbNetDevice>(m_devices[inDev]);
  if (!device || !m_virtualPaused[inDev][qIndex])
    {
      return;
    }
  const uint64_t ingressBytes = m_virtualIngressBytes[inDev][qIndex];
  const uint64_t threshold = ComputeVirtualIngressThreshold(inDev, qIndex);
  if (m_virtualHeadroomBytes[inDev][qIndex] == 0 &&
      (ingressBytes < m_mmu->xon[inDev][qIndex] ||
       ingressBytes + m_mmu->xon_offset[inDev][qIndex] <= threshold))
    {
      device->SendPfc(qIndex, 1);
      m_virtualPaused[inDev][qIndex] = false;
      LogPfcEventSent(Simulator::Now().GetNanoSeconds(), m_id, inDev, qIndex, false);
      LogPfcDetailedStats(inDev, qIndex, false);
    }
}

void
SimplifiedSwitchNode::VirtualBufferEnqueue (uint32_t inDev, uint32_t outDev, uint32_t qIndex, uint32_t packetSize)
{
  const uint64_t oldIngress = m_virtualIngressBytes[inDev][qIndex];
  const uint64_t reserve = m_mmu->reserveIngress[inDev][qIndex];
  const uint64_t oldReservedUsed = std::min(oldIngress, reserve);

  m_virtualIngressBytes[inDev][qIndex] += packetSize;
  m_virtualEgressBytes[outDev][qIndex] += packetSize;
  m_virtualTotalBytes += packetSize;

  const uint64_t newIngress = m_virtualIngressBytes[inDev][qIndex];
  const uint64_t newReservedUsed = std::min(newIngress, reserve);
  if (newReservedUsed >= oldReservedUsed)
    {
      m_virtualTotalIngressReservedUsed += (newReservedUsed - oldReservedUsed);
    }
  else
    {
      m_virtualTotalIngressReservedUsed -= (oldReservedUsed - newReservedUsed);
    }

  const uint64_t threshold = ComputeVirtualIngressThreshold(inDev, qIndex);
  const uint64_t oldHeadroom = m_virtualHeadroomBytes[inDev][qIndex];
  uint64_t newHeadroom = oldHeadroom;
  if (oldHeadroom == 0)
    {
      if (newIngress > threshold)
        {
          newHeadroom += packetSize;
        }
    }
  else
    {
      newHeadroom += packetSize;
    }
  m_virtualHeadroomBytes[inDev][qIndex] = newHeadroom;
  if (newHeadroom >= oldHeadroom)
    {
      m_virtualHeadroomTotalUsed += (newHeadroom - oldHeadroom);
    }
  else
    {
      m_virtualHeadroomTotalUsed -= (oldHeadroom - newHeadroom);
    }

  // 同步到 MMU 暴露字段，仅用于现有统计日志复用（不走 MMU admission 逻辑）。
  m_mmu->ingress_bytes[inDev][qIndex] = m_virtualIngressBytes[inDev][qIndex];
  m_mmu->egress_bytes[outDev][qIndex] = m_virtualEgressBytes[outDev][qIndex];
  m_mmu->xoffUsed[inDev][qIndex] = m_virtualHeadroomBytes[inDev][qIndex];
  m_mmu->totalUsed = m_virtualTotalBytes;
  m_mmu->xoffTotalUsed = m_virtualHeadroomTotalUsed;
  m_mmu->totalIngressReservedUsed = m_virtualTotalIngressReservedUsed;

  CheckAndSendVirtualPfc(inDev, qIndex);
}

void
SimplifiedSwitchNode::VirtualBufferReleaseAndResume (uint32_t inDev,
                                                     uint32_t outDev,
                                                     uint32_t qIndex,
                                                     uint32_t packetSize)
{
  const uint64_t oldIngress = m_virtualIngressBytes[inDev][qIndex];
  const uint64_t reserve = m_mmu->reserveIngress[inDev][qIndex];
  const uint64_t oldReservedUsed = std::min(oldIngress, reserve);

  if (m_virtualIngressBytes[inDev][qIndex] >= packetSize)
    {
      m_virtualIngressBytes[inDev][qIndex] -= packetSize;
    }
  else
    {
      m_virtualIngressBytes[inDev][qIndex] = 0;
    }
  if (m_virtualEgressBytes[outDev][qIndex] >= packetSize)
    {
      m_virtualEgressBytes[outDev][qIndex] -= packetSize;
    }
  else
    {
      m_virtualEgressBytes[outDev][qIndex] = 0;
    }
  if (m_virtualTotalBytes >= packetSize)
    {
      m_virtualTotalBytes -= packetSize;
    }
  else
    {
      m_virtualTotalBytes = 0;
    }

  const uint64_t newIngress = m_virtualIngressBytes[inDev][qIndex];
  const uint64_t newReservedUsed = std::min(newIngress, reserve);
  if (newReservedUsed >= oldReservedUsed)
    {
      m_virtualTotalIngressReservedUsed += (newReservedUsed - oldReservedUsed);
    }
  else
    {
      m_virtualTotalIngressReservedUsed -= (oldReservedUsed - newReservedUsed);
    }

  const uint64_t oldHeadroom = m_virtualHeadroomBytes[inDev][qIndex];
  const uint64_t reduceHeadroom = std::min(oldHeadroom, static_cast<uint64_t>(packetSize));
  m_virtualHeadroomBytes[inDev][qIndex] = oldHeadroom - reduceHeadroom;
  if (m_virtualHeadroomTotalUsed >= reduceHeadroom)
    {
      m_virtualHeadroomTotalUsed -= reduceHeadroom;
    }
  else
    {
      m_virtualHeadroomTotalUsed = 0;
    }

  // 同步到 MMU 暴露字段，仅用于现有统计日志复用。
  m_mmu->ingress_bytes[inDev][qIndex] = m_virtualIngressBytes[inDev][qIndex];
  m_mmu->egress_bytes[outDev][qIndex] = m_virtualEgressBytes[outDev][qIndex];
  m_mmu->xoffUsed[inDev][qIndex] = m_virtualHeadroomBytes[inDev][qIndex];
  m_mmu->totalUsed = m_virtualTotalBytes;
  m_mmu->xoffTotalUsed = m_virtualHeadroomTotalUsed;
  m_mmu->totalIngressReservedUsed = m_virtualTotalIngressReservedUsed;

  CheckAndSendVirtualResume(inDev, qIndex);
}

void
SimplifiedSwitchNode::LogPfcDetailedStats (uint32_t port, uint32_t queue, bool pause)
{
  if (!flag_ENABLE_STAT_FILE_OUTPUT || !flag_ENABLE_PFC_DETAILED_CSV || !m_mmu)
    {
      return;
    }

  static std::ofstream pfcStatsFile;
  static bool pfcStatsFileOpened = false;
  if (!pfcStatsFileOpened)
    {
      std::string pfcStatsPath = GetOutputDirectory() + "/pfc_detailed_stats.csv";
      pfcStatsFile.open(pfcStatsPath.c_str(), std::ios::out);
      if (!pfcStatsFile.is_open())
        {
          return;
        }
      pfcStatsFile << "Time(ns),SwitchID,Port,Queue,Event,"
                   << "HeadroomUsed,HeadroomLimit,IngressBytes,EgressBytes,"
                   << "IngressThreshold,EgressThreshold,XonThreshold,XonOffset,"
                   << "IngressPoolUsed,IngressPoolTotal,EgressPoolUsed,EgressPoolTotal,"
                   << "TotalBufferUsed,TotalBufferSize,PauseDuration" << std::endl;
      pfcStatsFileOpened = true;
    }

  const uint64_t currentTime = Simulator::Now().GetNanoSeconds();
  const auto key = std::make_pair(port, queue);

  const uint64_t headroomUsed = m_mmu->GetHdrmBytes(port, queue);
  const uint64_t headroomLimit = m_mmu->xoff[port][queue];
  const uint64_t ingressBytes = m_mmu->ingress_bytes[port][queue];
  const uint64_t egressBytes = m_mmu->egress_bytes[port][queue];
  const uint64_t xonThreshold = m_mmu->xon[port][queue];
  const uint64_t xonOffset = m_mmu->xon_offset[port][queue];

  uint64_t ingressThreshold = 0;
  uint64_t egressThreshold = 0;
  const std::string model = m_mmu->bufferModel;
  if (model == "sonic")
    {
      ingressThreshold = m_mmu->Threshold(port, queue, "ingress", 0, 0);
      egressThreshold = m_mmu->Threshold(port, queue, "egress", 0, 0);
    }
  else if (model == "reverie")
    {
      ingressThreshold = m_mmu->ReverieThreshold(port, queue, 0, 0);
      egressThreshold = m_mmu->ReverieThreshold(port, queue, 1, 0);
    }

  const uint64_t ingressPoolUsed = m_mmu->GetIngressSharedUsed();
  const uint64_t ingressPoolTotal = m_mmu->ingressPool - m_mmu->totalIngressReserved;
  const uint64_t egressPoolUsed = m_mmu->egressPoolUsed[0];
  const uint64_t egressPoolTotal = m_mmu->egressPool[0];
  const uint64_t totalBufferUsed = m_mmu->totalUsed;
  const uint64_t totalBufferSize = m_mmu->bufferPool;

  uint64_t pauseDuration = 0;
  if (pause)
    {
      g_simplifiedPfcPauseTime[key] = currentTime;
    }
  else
    {
      auto it = g_simplifiedPfcPauseTime.find(key);
      if (it != g_simplifiedPfcPauseTime.end())
        {
          pauseDuration = currentTime - it->second;
          g_simplifiedPfcPauseTime.erase(it);
        }
    }

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
  pfcStatsFile.flush();
}

void
SimplifiedSwitchNode::ReleaseAdmissionAndResume (uint32_t inDev,
                                                 uint32_t outDev,
                                                 uint32_t qIndex,
                                                 uint32_t packetSize,
                                                 bool foundPrio)
{
  m_mmu->RemoveFromIngressAdmission(inDev, qIndex, packetSize, foundPrio);
  m_mmu->RemoveFromEgressAdmission(outDev, qIndex, packetSize, foundPrio);
  if (m_bytes[inDev][outDev][qIndex] >= packetSize)
    {
      m_bytes[inDev][outDev][qIndex] -= packetSize;
    }
  else
    {
      m_bytes[inDev][outDev][qIndex] = 0;
    }
  CheckAndSendResume(inDev, qIndex);
}

void
SimplifiedSwitchNode::DispatchToDevice (uint32_t outDev, uint32_t qIndex, Ptr<Packet> p, CustomHeader ch)
{
  m_devices[outDev]->SwitchSend(qIndex, p, ch);
  Ptr<QbbNetDevice> outQbb = DynamicCast<QbbNetDevice>(m_devices[outDev]);
  if (outQbb)
    {
      outQbb->totalBytesRcvd += p->GetSize();
    }
}

// 交换机转发主流程：
// 查路由 -> 选队列 -> MMU准入 -> 时间戳更新 -> 发包。
void
SimplifiedSwitchNode::SendToDev (Ptr<Packet> p, CustomHeader &ch)
{
  InterfaceTag ifTag;
  p->PeekPacketTag(ifTag);
  const uint32_t inDev = ifTag.GetPortId();      // 入端口编号
  const uint32_t qIndex = ResolveQueueIndex(p, ch); // 队列编号

  const uint64_t nowNs = Simulator::Now().GetNanoSeconds();
  const bool applyTrueAccelToPacket = flag_ENABLE_TRUE_TIME_ACCELERATION && (ch.l3Prot != 0xFE);
  uint64_t logicalNowNs = nowNs;
  SwitchTimingTag carriedTimingTag;
  if (p->PeekPacketTag(carriedTimingTag))
    {
      const uint64_t carriedIngressNs = carriedTimingTag.GetIngressTimeNs();
      const uint64_t carriedEgressNs = carriedTimingTag.GetEgressTimeNs();
      if (carriedIngressNs > 0)
        {
          logicalNowNs = std::max(logicalNowNs, carriedIngressNs);
        }
      if (carriedEgressNs >= carriedIngressNs && carriedIngressNs > 0)
        {
          logicalNowNs = std::max(logicalNowNs, carriedEgressNs);
        }
      else if (carriedEgressNs > 0)
        {
          logicalNowNs = std::max(logicalNowNs, carriedEgressNs);
        }
    }
  const uint64_t packetUid = p->GetUid();
  const uint32_t packetSize = p->GetSize();
  const uint8_t protocol = ch.l3Prot;

  const int outDev = GetOutDev(p, ch); // 选出端口
  if (outDev < 0 || static_cast<uint32_t>(outDev) >= m_devices.size())
    {
      LogPacketDropDebug(nowNs, m_id, packetUid, inDev, outDev, qIndex, protocol, packetSize, "ROUTE_NOT_FOUND");
      return;
    }
  if (!m_devices[outDev]->IsLinkUp())
    {
      LogPacketDropDebug(nowNs, m_id, packetUid, inDev, outDev, qIndex, protocol, packetSize, "LINK_DOWN");
      return;
    }

  UnSchedTag unschedTag;                              // ABM未调度标签
  const bool foundUnsched = p->PeekPacketTag(unschedTag); // 是否带unsched标签
  const uint32_t unsched = foundUnsched ? unschedTag.GetValue() : 0; // unsched值
  MyPriorityTag priotag;                              // 优先级标签
  const bool foundPrio = p->PeekPacketTag(priotag);  // 是否带优先级标签

  if (qIndex != 0)
    {
      if (flag_ENABLE_LOGICAL_VIRTUAL_BUFFER)
        {
          // 逻辑模式：不走 MMU admission/update，仅做虚拟缓冲计数与 PFC 判定。
          VirtualBufferEnqueue(inDev, static_cast<uint32_t>(outDev), qIndex, p->GetSize());
        }
      else
        {
          const bool ingressOk = m_mmu->CheckIngressAdmission(inDev, qIndex, p->GetSize(), foundPrio, unsched);
          if (!ingressOk)
            {
              LogPacketDropDebug(nowNs, m_id, packetUid, inDev, outDev, qIndex, protocol, packetSize, "INGRESS_ADMISSION_FAIL");
              return;
            }
          const bool egressOk = m_mmu->CheckEgressAdmission(outDev, qIndex, p->GetSize(), foundPrio, unsched);
          if (!egressOk)
            {
              LogPacketDropDebug(nowNs, m_id, packetUid, inDev, outDev, qIndex, protocol, packetSize, "EGRESS_ADMISSION_FAIL");
              return;
            }
          m_mmu->UpdateIngressAdmission(inDev, qIndex, p->GetSize(), foundPrio, unsched);
          m_mmu->UpdateEgressAdmission(outDev, qIndex, p->GetSize(), foundPrio);
          CheckAndSendPfc(inDev, qIndex);
        }
    }

  m_bytes[inDev][outDev][qIndex] += p->GetSize(); // 记录在途占用

  // 记录交换机入口轮询调试日志（与 switch_egress_round_robin_debug.csv 同列格式）。
  if (flag_ENABLE_STAT_FILE_OUTPUT && flag_ENABLE_ROUND_ROBIN_DEBUG && qIndex != 0)
    {
      uint64_t currentTime = Simulator::Now().GetNanoSeconds();

      std::string flowid = "";
      if (ch.l3Prot == 0x11)
        {
          flowid = GenerateFlowIdFromPacket(p, ch);
        }

      std::string protocolStr = "";
      const uint8_t protocol = ch.l3Prot;
      if (protocol == 0x06)
        {
          protocolStr = "TCP";
        }
      else if (protocol == 0x11)
        {
          protocolStr = "UDP";
        }
      else if (protocol == 0xFC)
        {
          protocolStr = "ACK";
        }
      else if (protocol == 0xFD)
        {
          protocolStr = "NACK";
        }
      else if (protocol == 0xFE)
        {
          protocolStr = "PFC";
        }
      else if (protocol == 0xFF)
        {
          protocolStr = "QCN";
        }
      else
        {
          std::ostringstream oss;
          oss << "0x" << std::hex << std::setfill('0') << std::setw(2) << static_cast<uint32_t>(protocol);
          protocolStr = oss.str();
        }

      static std::ofstream switchIngressDebugFile;
      static bool switchIngressDebugFileOpened = false;
      if (!switchIngressDebugFileOpened)
        {
          std::string switchIngressPath = GetOutputDirectory() + "/switch_ingress_round_robin_debug.csv";
          switchIngressDebugFile.open(switchIngressPath.c_str(), std::ios::out);
          switchIngressDebugFile << "Time(ns),SwitchID,Port,Queue,Protocol,FlowID" << std::endl;
          switchIngressDebugFileOpened = true;
        }
      switchIngressDebugFile << currentTime << "," << m_id << "," << inDev << "," << qIndex << "," << protocolStr << "," << flowid << std::endl;
    }

  SwitchTimingTag timingTag; // 包内时间标签
  p->RemovePacketTag(timingTag);
  uint64_t bitRate = 25ULL * 1000ULL * 1000ULL * 1000ULL; // 默认带宽25Gbps
  Ptr<QbbNetDevice> outQbb = DynamicCast<QbbNetDevice>(m_devices[outDev]); // 出端口设备
  if (outQbb)
    {
      bitRate = outQbb->GetDataRate().GetBitRate();
    }
  uint64_t propagationNs = 0;
  if (outQbb)
    {
      Ptr<QbbChannel> outChannel = DynamicCast<QbbChannel>(outQbb->GetChannel());
      if (outChannel)
        {
          propagationNs = outChannel->GetDelay().GetNanoSeconds();
        }
    }
  const uint64_t adjustedIngressNs = applyTrueAccelToPacket
                                       ? m_kernel.ComputeIngressTimestamp(logicalNowNs, outDev, qIndex, p->GetSize(), bitRate, propagationNs, p->GetUid())
                                       : nowNs; // PFC相关包不使用“真实时间加速”时序折算
  timingTag.SetIngressTimeNs(adjustedIngressNs);
  timingTag.SetIngressWallTimeNs(GetWallClockNs());
  timingTag.SetSwitchId(m_id);
  timingTag.SetInDev(inDev);
  timingTag.SetOutDev(outDev);
  timingTag.SetQIndex(qIndex);
  p->AddPacketTag(timingTag);

  uint64_t dispatchBaseNs = nowNs;
  if (applyTrueAccelToPacket)
    {
      const uint64_t nextDispatchNs = std::max(nowNs, m_lastPortDispatchNs[outDev] + 1);
      m_lastPortDispatchNs[outDev] = nextDispatchNs;
      dispatchBaseNs = nextDispatchNs;
    }
  const uint64_t dispatchDelayNs = dispatchBaseNs > nowNs ? (dispatchBaseNs - nowNs) : 0;
  if (dispatchDelayNs == 0)
    {
      DispatchToDevice(outDev, qIndex, p, ch);
    }
  else
    {
      Simulator::Schedule(NanoSeconds(dispatchDelayNs),
                          &SimplifiedSwitchNode::DispatchToDevice,
                          this,
                          static_cast<uint32_t>(outDev),
                          qIndex,
                          p,
                          ch);
    }
}

// 交换机收包入口：
// 记录入口时间标签并调用转发流程。
bool
SimplifiedSwitchNode::SwitchReceiveFromDevice (Ptr<NetDevice> device, Ptr<Packet> packet, CustomHeader &ch)
{
  (void)device;    // 该实现暂不使用device对象，保留接口一致性
  InterfaceTag tag; // 入端口标签
  packet->PeekPacketTag(tag);

  const uint64_t nowNs = Simulator::Now().GetNanoSeconds();
  SwitchTimingTag timingTag; // 包内时间标签
  const bool hadTimingTag = packet->PeekPacketTag(timingTag);
  packet->RemovePacketTag(timingTag);
  uint64_t inheritedLogicalNs = 0;
  if (hadTimingTag)
    {
      const uint64_t oldIngressNs = timingTag.GetIngressTimeNs();
      const uint64_t oldEgressNs = timingTag.GetEgressTimeNs();
      uint64_t baseLogicalNs = 0;
      if (oldEgressNs >= oldIngressNs && oldIngressNs > 0)
        {
          baseLogicalNs = oldEgressNs;
        }
      else if (oldEgressNs > 0)
        {
          baseLogicalNs = oldEgressNs;
        }

      // 对于主机侧新生成的 ACK/NACK：
      // oldIngressNs 是“ACK 发送时刻”，oldEgressNs 是“继承的数据包逻辑时间”。
      // 到达交换机时，需要把这段已实际经过的主机->交换机时间补到逻辑时间上，
      // 避免少算约一个链路传播时延。
      if (baseLogicalNs > 0)
        {
          inheritedLogicalNs = baseLogicalNs;
          if (oldIngressNs > 0 && nowNs > oldIngressNs)
            {
              inheritedLogicalNs += (nowNs - oldIngressNs);
            }
        }
    }
  timingTag.SetIngressTimeNs(std::max(nowNs, inheritedLogicalNs));
  timingTag.SetIngressWallTimeNs(GetWallClockNs());
  timingTag.SetSwitchId(m_id);
  timingTag.SetInDev(tag.GetPortId());
  packet->AddPacketTag(timingTag);

  SendToDev(packet, ch);
  return true;
}

// 交换机出队回调：
// 更新出口时间标签、释放MMU占用、触发Resume检查。
void
SimplifiedSwitchNode::SwitchNotifyDequeue (uint32_t ifIndex, uint32_t qIndex, Ptr<Packet> p)
{
  InterfaceTag ifTag; // 入端口标签（用于还原inDev）
  p->PeekPacketTag(ifTag);
  const uint32_t inDev = ifTag.GetPortId(); // 入端口

  SwitchTimingTag timingTag; // 包内时间标签
  p->RemovePacketTag(timingTag);
  const uint64_t nowNs = Simulator::Now().GetNanoSeconds(); // 当前仿真时刻
  uint64_t predictedReleaseNs = nowNs;
  const uint64_t adjustedEgressNs = m_kernel.ComputeEgressTimestamp(nowNs, p->GetUid(), &predictedReleaseNs); // 数值加速后的出口时刻（逻辑到达下一跳）
  // MMU释放对齐原始路径中的“SwitchNotifyDequeue时刻”（队列开始服务/出队时刻）。
  const uint64_t rawReleaseDelayNs = (predictedReleaseNs > nowNs) ? (predictedReleaseNs - nowNs) : 0;
  const bool usingVirtualBuffer = flag_ENABLE_LOGICAL_VIRTUAL_BUFFER;
  const uint64_t subtractNs = usingVirtualBuffer
                                ? (flag_ENABLE_VB_RELEASE_DELAY_SUBTRACT ? g_VB_RELEASE_DELAY_SUBTRACT_NS : 0)
                                : (flag_ENABLE_RELEASE_DELAY_SUBTRACT ? g_RELEASE_DELAY_SUBTRACT_NS : 0);
  const uint64_t releaseDelayNs = (rawReleaseDelayNs > subtractNs) ? (rawReleaseDelayNs - subtractNs) : 0;
  const uint64_t rawReleaseTimeNs = nowNs + rawReleaseDelayNs;
  const uint64_t appliedReleaseTimeNs = nowNs + releaseDelayNs;
  timingTag.SetEgressTimeNs(adjustedEgressNs);
  timingTag.SetEgressWallTimeNs(GetWallClockNs());
  timingTag.SetOutDev(ifIndex);
  timingTag.SetQIndex(qIndex);
  p->AddPacketTag(timingTag);
  LogReleaseDelayDebug(nowNs,
                       adjustedEgressNs,
                       rawReleaseDelayNs,
                       releaseDelayNs,
                       rawReleaseTimeNs,
                       appliedReleaseTimeNs,
                       subtractNs,
                       p->GetUid(),
                       m_id,
                       inDev,
                       ifIndex,
                       qIndex,
                       p->GetSize(),
                       flag_ENABLE_TRUE_TIME_ACCELERATION);

  if (qIndex != 0)
    {
      MyPriorityTag priotag;                      // 优先级标签
      const bool foundPrio = p->PeekPacketTag(priotag); // 是否带优先级标签
      const uint32_t packetSize = p->GetSize();
      const bool releaseDelayEnabled = usingVirtualBuffer ? flag_ENABLE_VB_DELAYED_RELEASE : flag_ENABLE_DELAYED_MMU_RELEASE;
      const bool shouldDelayRelease = (flag_ENABLE_TRUE_TIME_ACCELERATION && adjustedEgressNs > nowNs) &&
                                      releaseDelayEnabled;
      if (shouldDelayRelease)
        {
          // 数据包已被“立即投递”，占用按逻辑时刻释放，避免数值路径中 PFC 完全消失。
          if (usingVirtualBuffer)
            {
              Simulator::Schedule(NanoSeconds(releaseDelayNs),
                                  &SimplifiedSwitchNode::VirtualBufferReleaseAndResume,
                                  this,
                                  inDev,
                                  ifIndex,
                                  qIndex,
                                  packetSize);
            }
          else
            {
              Simulator::Schedule(NanoSeconds(releaseDelayNs),
                                  &SimplifiedSwitchNode::ReleaseAdmissionAndResume,
                                  this,
                                  inDev,
                                  ifIndex,
                                  qIndex,
                                  packetSize,
                                  foundPrio);
            }
        }
      else
        {
          if (usingVirtualBuffer)
            {
              VirtualBufferReleaseAndResume(inDev, ifIndex, qIndex, packetSize);
            }
          else
            {
              ReleaseAdmissionAndResume(inDev, ifIndex, qIndex, packetSize, foundPrio);
            }
        }
    }
}

// 统计接口占位（为保持与Node虚接口兼容）。
void
SimplifiedSwitchNode::SwitchStatsCount (int flag)
{
  (void)flag;
}

// 统计更新接口占位（为保持与Node虚接口兼容）。
void
SimplifiedSwitchNode::SwitchStatsUpdate (int flag, uint32_t switchid)
{
  (void)flag;
  (void)switchid;
}

// 时延补偿接口占位（为保持与Node虚接口兼容）。
void
SimplifiedSwitchNode::SwitchTimeDelay (int flag)
{
  (void)flag;
}

// 构造流ID字符串：srcId-dstId-sport-dport。
std::string
SimplifiedSwitchNode::GenerateFlowIdFromPacket (Ptr<Packet> packet, CustomHeader &ch)
{
  (void)packet;
  if (ch.l3Prot != 0x11)
    {
      return "";
    }
  uint32_t srcId = ((ch.sip >> 8) & 0xffff); // 源节点ID
  uint32_t dstId = ((ch.dip >> 8) & 0xffff); // 目的节点ID
  std::ostringstream oss;                     // 组装字符串
  oss << srcId << "-" << dstId << "-" << ch.udp.sport << "-" << ch.udp.dport;
  return oss.str();
}

// ECMP哈希实现（与SwitchNode保持一致的散列策略）。
uint32_t
SimplifiedSwitchNode::EcmpHash (const uint8_t* key, size_t len, uint32_t seed)
{
  uint32_t h = seed; // 哈希累积值
  if (len > 3)
    {
      const uint32_t* key_x4 = reinterpret_cast<const uint32_t*>(key);
      size_t i = len >> 2;
      do
        {
          uint32_t k = *key_x4++;
          k *= 0xcc9e2d51;
          k = (k << 15) | (k >> 17);
          k *= 0x1b873593;
          h ^= k;
          h = (h << 13) | (h >> 19);
          h += (h << 2) + 0xe6546b64;
        }
      while (--i);
      key = reinterpret_cast<const uint8_t*>(key_x4);
    }
  if (len & 3)
    {
      size_t i = len & 3;
      uint32_t k = 0;
      key = &key[i - 1];
      do
        {
          k <<= 8;
          k |= *key--;
        }
      while (--i);
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

} // namespace ns3
