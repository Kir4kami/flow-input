#include "stat-config.h"

// ===========================
// 全局统计开关（默认值集中在此）
// ===========================

// 统计文件总开关：
// - true ：允许所有统计类 csv/txt 落盘
// - false：停止写出统计文件（仿真流程与计算逻辑仍可继续）
// 主要影响文件：
//   flow_stats.txt
//   flow_stats_receiver_rate.csv
//   flow_stats_switch.txt
//   flow_stats_switch_rate.csv
//   flow_stats_switch_queue_bytes.csv
//   flow_switch_diff.txt
//   pfc_events.csv
//   pfc_detailed_stats.csv
//   sender_round_robin_debug.csv
//   switch_ingress_round_robin_debug.csv
//   switch_egress_round_robin_debug.csv
//   packet_switch_net_time.csv
//   packet_switch_net_time_report.txt
bool flag_ENABLE_STAT_FILE_OUTPUT = true;

// 是否启用交换机端口速率计算逻辑（入口/出口速率与窗口统计）。
// 注意：该开关控制“是否计算”，不直接决定文件写出；
// 若需要落盘，还需 flag_ENABLE_STAT_FILE_OUTPUT=true。
bool flag_ENABLE_SWITCH_PORT_RATE_CALC = true;

// 是否输出交换机端口速率日志。
// 相关输出文件：
// - flow_stats_switch.txt：可读文本（平均速率、瞬时速率、稳态进入/退出）
// - flow_stats_switch_rate.csv：结构化速率明细（便于画图和后处理）
bool flag_ENABLE_SWITCH_PORT_RATE_LOG = true;

// 是否输出交换机端口/队列字节统计日志。
// 相关输出文件：
// - flow_stats_switch.txt：触发流相关端口的队列字节文本
// - flow_stats_switch_queue_bytes.csv：Ingress/Egress 及累计字节明细
bool flag_ENABLE_SWITCH_PORT_QUEUE_BYTES_LOG = false;

// 是否启用接收端 QbbNetDevice“速率计算逻辑”。
// 说明：
// - true：执行 calculateRate()，并允许输出接收端速率结果（受其它文件开关约束）
// - false：不再计算接收端窗口平均/瞬时速率（CPU开销更低）
// 相关输出文件：
// - flow_stats_receiver_rate.csv：接收端窗口平均/瞬时速率（直接受本开关影响）
// - flow_stats.txt：其中“速率相关文本段”受本开关影响；但系统阶段日志是否写入由 flag_ENABLE_FLOW_STATS_TXT 决定
bool flag_ENABLE_QBB_DEVICE_RATE_CALC = false;

// 是否输出 flow_stats.txt（文本统计主日志，独立于是否做速率计算）。
// 说明：
// - true：允许写入 flow_stats.txt（如系统进入/退出稳态、系统退出、队列快照、以及可用时的速率文本）
// - false：完全不创建/不写 flow_stats.txt（即使启用了速率计算）
bool flag_ENABLE_FLOW_STATS_TXT = false;

// 是否输出交换机队列状态日志（稳态分析用）。
// 相关输出文件：
// - flow_stats.txt：Simulation Start/End 的全交换机队列快照、流触发队列状态
bool flag_ENABLE_SWITCH_QUEUE_LOGGING = false;

// 是否输出轮询调度调试日志（用于排查调度公平性、PFC 影响）。
// 相关输出文件：
// - sender_round_robin_debug.csv：发送端主机侧出队轨迹
// - receiver_round_robin_debug.csv：接收端主机侧到达轨迹（与 sender 同列格式）
// - switch_ingress_round_robin_debug.csv：交换机入口调试
// - switch_egress_round_robin_debug.csv：交false换机出口调试
bool flag_ENABLE_ROUND_ROBIN_DEBUG = false;

// 是否输出 PFC 事件日志（Pause/Resume 的发送与接收）。
// 相关输出文件：
// - pfc_events.csv
bool flag_ENABLE_PFC_EVENTS_LOG = false;

// 是否输出 PFC 详细统计日志（阈值、缓冲区占用、暂停时长）。
// 相关输出文件：
// - pfc_detailed_stats.csv
bool flag_ENABLE_PFC_DETAILED_CSV = false;

// 是否输出逐包交换机/网侧时间明细。
// 相关输出文件：
// - packet_switch_net_time.csv
bool flag_ENABLE_PACKET_SWITCH_NET_TIME_CSV = false;

// 是否输出交换机/网侧时间汇总报告。
// 相关输出文件：
// - packet_switch_net_time_report.txt
bool flag_ENABLE_PACKET_SWITCH_NET_TIME_REPORT = true;

// 是否输出数值仿真“延后释放”调试明细。
// 相关输出文件：
// - release_delay_debug.csv
bool flag_ENABLE_RELEASE_DELAY_DEBUG_CSV = false;

// 是否输出原始仿真“出队时间 vs MMU释放时间”调试明细。
// 相关输出文件：
// - switch_dequeue_release_time.csv
bool flag_ENABLE_SWITCH_DEQUEUE_RELEASE_TIME_CSV = false;

// 是否输出 FCT 逻辑时间分解追踪。
// 相关输出文件：
// - fct_logical_trace.csv
bool flag_ENABLE_FCT_LOGICAL_TRACE = false;

// 是否启用“真实时间加速”（仅数值交换机路径）：
// - 交换机将排队/序列化/传播时延折算到包时间戳；
// - 设备与链路层不再等待真实发送/传播时延，直接投递到接收端。
bool flag_ENABLE_TRUE_TIME_ACCELERATION = true;

// 是否在数值仿真中对 releaseDelayNs 扣减一个固定偏移。
// true 时，实际释放调度延迟 = max(0, 原始releaseDelayNs - g_RELEASE_DELAY_SUBTRACT_NS)。
// 该功能仅作用于 SimplifiedSwitchNode 的传统MMU延后释放逻辑。
bool flag_ENABLE_RELEASE_DELAY_SUBTRACT = false;

// releaseDelayNs 固定扣减值（单位：ns）。
// 默认 2000ns，可按实验需求调整。
uint64_t g_RELEASE_DELAY_SUBTRACT_NS = 2335;

// 数值仿真中是否启用“MMU延后释放”。
// true: 按逻辑时刻延后释放；false: 出队即释放。
bool flag_ENABLE_DELAYED_MMU_RELEASE = false;

// 数值仿真中是否启用“逻辑虚拟缓冲区”（默认关闭，按需通过命令行开启）。
bool flag_ENABLE_LOGICAL_VIRTUAL_BUFFER = true;

// 逻辑虚拟缓冲区路径是否启用“按逻辑时刻延后释放”。
bool flag_ENABLE_VB_DELAYED_RELEASE = true;

// 逻辑虚拟缓冲区路径是否对 releaseDelayNs 进行固定偏移扣减。
bool flag_ENABLE_VB_RELEASE_DELAY_SUBTRACT = false;

// 逻辑虚拟缓冲区路径 releaseDelayNs 固定扣减值（单位：ns）。
uint64_t g_VB_RELEASE_DELAY_SUBTRACT_NS = 2335;

// 是否启用“跃迁”逻辑（系统进入稳态后进行快速推进）。
// 该开关会影响稳态阶段推进与日志出现时机，但不直接指定某个文件开关。
bool flag_ENABLE_JUMP_TRANSITION = false;

// 是否输出跃迁阶段前后 SwitchStats 差异。
// 相关输出文件：
// - flow_switch_diff.txt：按 Transition Stage 记录 enter/exit 差异
bool g_enableSwitchDiffLogging = false;

void
SetStatFileOutputEnabled(bool enable)
{
  flag_ENABLE_STAT_FILE_OUTPUT = enable;
}

bool
GetStatFileOutputEnabled()
{
  return flag_ENABLE_STAT_FILE_OUTPUT;
}

void
SetJumpTransitionEnabled(bool enable)
{
  flag_ENABLE_JUMP_TRANSITION = enable;
}

bool
GetJumpTransitionEnabled()
{
  return flag_ENABLE_JUMP_TRANSITION;
}
