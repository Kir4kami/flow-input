#ifndef STAT_CONFIG_H
#define STAT_CONFIG_H

// 总开关：false 时停止写出所有统计类 csv/txt 文件（仿真逻辑仍运行，仅关闭落盘）。
// 典型受影响文件包括：
// - flow_stats.txt：接收端流速率、稳态进入/退出、系统阶段日志
// - flow_stats_receiver_rate.csv：接收端每条流的窗口平均/瞬时速率
// - flow_stats_switch.txt：交换机端口速率、稳态进入/退出、端口队列信息
// - flow_stats_switch_rate.csv：交换机端口速率明细（按窗口）
// - flow_stats_switch_queue_bytes.csv：交换机端口/队列字节统计
// - flow_switch_diff.txt：跃迁阶段前后 SwitchStats 差异
// - pfc_events.csv：PFC Pause/Resume 收发事件
// - pfc_detailed_stats.csv：PFC 触发时缓冲区阈值与占用细节
// - switch_ingress_round_robin_debug.csv：交换机入口侧轮询调度调试
// - switch_egress_round_robin_debug.csv：交换机出口侧轮询调度调试
// - sender_round_robin_debug.csv：发送端（主机）轮询出队调试
// - packet_switch_net_time.csv：分包交换机内/网侧时间明细
// - packet_switch_net_time_report.txt：交换机内/网侧时间汇总报告
extern bool flag_ENABLE_STAT_FILE_OUTPUT;

// 是否执行“交换机端口速率计算”逻辑（计算入口/出口速率、稳态判定基础数据）。
// 说明：该开关控制计算路径；若需真正输出文件，还需 flag_ENABLE_STAT_FILE_OUTPUT=true。
extern bool flag_ENABLE_SWITCH_PORT_RATE_CALC;

// 是否输出交换机端口速率日志。
// 相关文件：
// - flow_stats_switch.txt：可读文本日志（速率、稳态进入/退出、窗口信息）
// - flow_stats_switch_rate.csv：结构化速率数据（便于后处理/画图）
extern bool flag_ENABLE_SWITCH_PORT_RATE_LOG;

// 是否输出交换机端口/队列字节量日志。
// 相关文件：
// - flow_stats_switch.txt：触发流相关端口的队列字节文本
// - flow_stats_switch_queue_bytes.csv：端口/队列 ingress/egress 字节明细
extern bool flag_ENABLE_SWITCH_PORT_QUEUE_BYTES_LOG;

// 是否启用 QbbNetDevice 接收端“速率计算逻辑”。
// 说明：
// - true：执行接收端窗口平均/瞬时速率计算
// - false：不计算接收端速率（但不等于关闭 flow_stats.txt 文本文件）
// 相关文件：
// - flow_stats_receiver_rate.csv：直接受本开关影响
// - flow_stats.txt：仅其中速率相关段受本开关影响；文件本身由 flag_ENABLE_FLOW_STATS_TXT 控制
extern bool flag_ENABLE_QBB_DEVICE_RATE_CALC;

// 是否输出 flow_stats.txt（文本统计主日志，独立于速率计算开关）。
// 相关文件：
// - flow_stats.txt：接收端速率文本、稳态进入/退出、系统阶段日志等
extern bool flag_ENABLE_FLOW_STATS_TXT;

// 是否输出“交换机队列状态”日志（主要用于稳态分析与阶段切换观察）。
// 相关文件：
// - flow_stats.txt：Simulation Start/End 时全交换机队列快照，以及流触发的队列状态
extern bool flag_ENABLE_SWITCH_QUEUE_LOGGING;

// 是否输出轮询调度调试日志（用于定位队列调度、出队公平性、PFC影响）。
// 相关文件：
// - sender_round_robin_debug.csv：发送端主机侧出队顺序/流信息
// - receiver_round_robin_debug.csv：接收端主机侧到达轨迹（与 sender 同格式）
// - switch_ingress_round_robin_debug.csv：交换机入口方向调试
// - switch_egress_round_robin_debug.csv：交换机出口方向调试
extern bool flag_ENABLE_ROUND_ROBIN_DEBUG;

// 是否输出 PFC 事件日志（Pause/Resume 的发送与接收）。
// 相关文件：
// - pfc_events.csv：PFC 事件时间、节点类型、端口、队列、动作
extern bool flag_ENABLE_PFC_EVENTS_LOG;

// 是否输出 PFC 详细统计日志（阈值、缓冲区占用、暂停时长）。
// 相关文件：
// - pfc_detailed_stats.csv：PFC 触发时细粒度缓冲与阈值数据
extern bool flag_ENABLE_PFC_DETAILED_CSV;

// 是否输出逐包交换机/网侧时间明细。
// 相关文件：
// - packet_switch_net_time.csv：每个数据包的交换机内耗时与网侧耗时明细
extern bool flag_ENABLE_PACKET_SWITCH_NET_TIME_CSV;

// 是否输出交换机/网侧时间汇总报告。
// 相关文件：
// - packet_switch_net_time_report.txt：平均时延与占比统计
extern bool flag_ENABLE_PACKET_SWITCH_NET_TIME_REPORT;

// 是否输出数值仿真“延后释放”调试明细。
// 相关文件：
// - release_delay_debug.csv：now/adjustedEgress/releaseDelay 等逐包明细
extern bool flag_ENABLE_RELEASE_DELAY_DEBUG_CSV;

// 是否输出原始仿真“出队时间 vs MMU释放时间”调试明细。
// 相关文件：
// - switch_dequeue_release_time.csv
extern bool flag_ENABLE_SWITCH_DEQUEUE_RELEASE_TIME_CSV;

// 是否输出 FCT 逻辑时间分解追踪（ACK 生成/接收等关键节点）。
// 相关输出文件：
// - fct_logical_trace.csv
extern bool flag_ENABLE_FCT_LOGICAL_TRACE;

// 是否启用“真实时间加速”（仅数值交换机路径）：
// - 把排队/序列化/链路传播时延直接写入包时间戳；
// - 发送与链路不再按真实等待，数据包可直接到达接收端；
// - 便于进行事件级数值仿真加速（而非仅统计口径加速）。
extern bool flag_ENABLE_TRUE_TIME_ACCELERATION;

// 是否在数值仿真中对 releaseDelayNs 做“固定偏移扣减”。
// 说明：
// - true ：调度释放延迟 = max(0, 原始releaseDelayNs - g_RELEASE_DELAY_SUBTRACT_NS)
// - false：调度释放延迟 = 原始releaseDelayNs
// 该开关仅影响 SimplifiedSwitchNode 的“传统MMU路径延后释放”调度，不影响原始仿真路径。
extern bool flag_ENABLE_RELEASE_DELAY_SUBTRACT;

// 数值仿真中 releaseDelayNs 的扣减值（单位：ns）。
// 典型用途：在“真实时间加速”下补偿固定链路段/处理段，降低过度保守的占用延迟。
// 仅在 flag_ENABLE_RELEASE_DELAY_SUBTRACT=true 时生效。
extern uint64_t g_RELEASE_DELAY_SUBTRACT_NS;

// 数值仿真中是否启用“MMU延后释放”。
// - true ：按逻辑时刻延后释放（保留更强缓冲压力）
// - false：在出队回调中立即释放（更接近原始交换机行为）
extern bool flag_ENABLE_DELAYED_MMU_RELEASE;

// 数值仿真中是否启用“逻辑虚拟缓冲区”：
// - true ：不走 MMU admission/update/remove 计数路径，改为独立虚拟缓冲区计数并按逻辑时间释放；
//          PFC pause/resume 依据虚拟缓冲区占用和动态阈值触发。
// - false：沿用现有 SimplifiedSwitchNode 的 MMU 计数路径。
extern bool flag_ENABLE_LOGICAL_VIRTUAL_BUFFER;

// 逻辑虚拟缓冲区路径是否启用“延后释放”（按逻辑时刻释放）。
// - true ：在真实时间加速下按逻辑时刻调度释放（更符合数值时序）。
// - false：在出队回调中立即释放虚拟占用。
extern bool flag_ENABLE_VB_DELAYED_RELEASE;

// 逻辑虚拟缓冲区路径是否启用 releaseDelayNs 固定偏移扣减。
// - true ：虚拟缓冲区释放延迟 = max(0, 原始releaseDelayNs - g_VB_RELEASE_DELAY_SUBTRACT_NS)
// - false：虚拟缓冲区释放延迟 = 原始releaseDelayNs
extern bool flag_ENABLE_VB_RELEASE_DELAY_SUBTRACT;

// 逻辑虚拟缓冲区路径的 releaseDelayNs 扣减值（单位：ns）。
extern uint64_t g_VB_RELEASE_DELAY_SUBTRACT_NS;

// 是否启用“跃迁”逻辑（系统进入稳态后进行快速推进/状态更新）。
// 说明：该开关本身不直接决定文件输出，但会影响下列日志何时产生：
// - flow_stats.txt：稳态进入/退出、系统阶段切换日志
// - flow_switch_diff.txt：阶段前后交换机状态差异（配合 g_enableSwitchDiffLogging）
extern bool flag_ENABLE_JUMP_TRANSITION;

// 是否输出跃迁阶段前后 SwitchStats 差异日志。
// 相关文件：
// - flow_switch_diff.txt：按 Transition Stage 输出 enter/exit 差异
extern bool g_enableSwitchDiffLogging;

// 设置/查询“统计文件总开关”（csv/txt 是否落盘）。
void SetStatFileOutputEnabled(bool enable);
bool GetStatFileOutputEnabled();

// 设置/查询“跃迁逻辑开关”。
void SetJumpTransitionEnabled(bool enable);
bool GetJumpTransitionEnabled();

#endif /* STAT_CONFIG_H */
