# 数值仿真中入队/出队与 PFC 触发流程分析（当前实现）

本文基于当前代码路径（`SimplifiedSwitchNode` + `QbbNetDevice` + `QbbChannel` + `SwitchMmu`）说明：

- 数据包在数值交换机中的入队/出队如何进行；
- PFC Pause/Resume 在哪里判定、何时发送；
- “真实时间加速”与 PFC 之间目前如何解耦。

---

## 1. 总体链路（先看全貌）

在数值仿真路径中，一次普通无损数据包（`qIndex != 0`）大致经历：

1. `SimplifiedSwitchNode::SwitchReceiveFromDevice()`  
   收包入口，整理/继承 `SwitchTimingTag`，然后进入转发流程。
2. `SimplifiedSwitchNode::SendToDev()`  
   查路由、选队列、MMU 准入检查与占用更新，必要时触发 `CheckAndSendPfc()`。
3. `QbbNetDevice::SwitchSend()`  
   将包放入设备队列（`m_queue->Enqueue`），随后触发 `DequeueAndTransmit()`。
4. `QbbNetDevice::DequeueAndTransmit()`（交换机分支）  
   轮询队列出队（`DequeueRR`），出队后回调 `m_node->SwitchNotifyDequeue(...)`。
5. `SimplifiedSwitchNode::SwitchNotifyDequeue()`  
   写出队时间戳，计算 `releaseDelayNs`，根据加速开关决定“立即释放”还是“延后释放MMU占用”。
6. `SimplifiedSwitchNode::ReleaseAdmissionAndResume()`  
   真正释放 ingress/egress admission，并执行 `CheckAndSendResume()`。

---

## 2. 入队阶段：何时记账、何时触发 Pause

### 2.1 队列与路由确定

`SendToDev()` 先做：

- `InterfaceTag` 得到 `inDev`；
- `ResolveQueueIndex()` 得到 `qIndex`（ACK/NACK/控制包优先级规则也在这里）；
- `GetOutDev()` 做 ECMP 选路。

### 2.2 MMU 准入与占用更新（关键）

对于 `qIndex != 0`（无损业务队列）：

1. `CheckIngressAdmission(...)`
2. `CheckEgressAdmission(...)`
3. 成功后立刻：
   - `UpdateIngressAdmission(...)`
   - `UpdateEgressAdmission(...)`
4. 随即执行 `CheckAndSendPfc(inDev, qIndex)`

也就是：**入队时先增占用，再判定是否需要 Pause**。  
Pause 判定来自 `SwitchMmu::CheckShouldPause()`：

- 条件为 `!paused && GetHdrmBytes(...) > 0`
- 本质是该队列已进入 headroom 使用区间。

### 2.3 设备入队

`QbbNetDevice::SwitchSend()` 里直接：

- `m_queue->Enqueue(packet, qIndex)`
- `DequeueAndTransmit()`

说明“入队动作”在设备层是显式发生的，且是立即触发发送调度。

---

## 3. 出队阶段：何时回调、何时释放

### 3.1 设备出队

在交换机分支的 `DequeueAndTransmit()`：

- `p = m_queue->DequeueRR(m_paused)`（轮询）
- `qIndex = m_queue->GetLastQueue()`
- 调用 `m_node->SwitchNotifyDequeue(m_ifIndex, qIndex, p)`
- 再调用 `TransmitStart(p)` 发往信道

即：**出队后先通知节点，再进入链路发送**。

### 3.2 节点出队回调内的“慢释放”

`SwitchNotifyDequeue()` 做了三件关键事：

1. 用 `m_kernel.ComputeEgressTimestamp(...)` 得到 `adjustedEgressNs`
2. 计算
   - `rawReleaseDelayNs = max(0, adjustedEgressNs - nowNs)`
   - `releaseDelayNs = max(0, rawReleaseDelayNs - g_RELEASE_DELAY_SUBTRACT_NS)`（若开关开启）
3. 对 `qIndex != 0`：
   - 若 `flag_ENABLE_TRUE_TIME_ACCELERATION && adjustedEgressNs > nowNs`：  
     `Simulator::Schedule(releaseDelayNs, ReleaseAdmissionAndResume, ...)`
   - 否则立即 `ReleaseAdmissionAndResume(...)`

这就是“出队发生了，但占用释放可能延后”的机制来源。

---

## 4. Resume 触发：释放后再判定

`ReleaseAdmissionAndResume()` 中顺序是：

1. `RemoveFromIngressAdmission(...)`
2. `RemoveFromEgressAdmission(...)`
3. 更新 `m_bytes[in][out][q]`
4. 调 `CheckAndSendResume(inDev, qIndex)`

`CheckAndSendResume()` 最终依赖 `SwitchMmu::CheckShouldResume()`：

- 必须先处于 paused；
- `GetHdrmBytes(...) == 0`；
- 且 ingress（或 LPF ingress）已低于 `xon`/阈值条件。

因此 Resume 的触发是“释放后检查”，不是定时硬触发。

---

## 5. PFC 控制帧当前实现（重点）

### 5.1 PFC 发送侧

`CheckAndSendPfc/Resume()` -> `QbbNetDevice::SendPfc(...)`。

`SendPfc(...)` 当前走统一发送路径：

- 直接 `DispatchPfcControlFrame(...)` 进入设备发送与信道传播；
- PFC 时延由常规 `txTime + channelDelay` 体现，不再使用额外“控制帧附加时延”配置。

其中 `serializationNs` 由帧长与 `GetDataRate()` 计算。

### 5.2 PFC 接收侧

`QbbNetDevice::Receive()` 识别 `ch.l3Prot == 0xFE`：

- Pause：`m_paused[qIndex] = true`
- Resume：调用 `Resume(qIndex)`，恢复该队列发送

这部分功能逻辑与日志开关解耦，日志只控制写文件，不控制 PFC 生效。

---

## 6. “真实时间加速”目前如何影响（以及不影响）PFC

当前实现里，已做了“PFC 相关包不受 true acceleration 影响”的处理：

1. `SimplifiedSwitchNode::SendToDev()`  
   `applyTrueAccelToPacket = flag_ENABLE_TRUE_TIME_ACCELERATION && (ch.l3Prot != 0xFE)`  
   - PFC 包不走 `ComputeIngressTimestamp(...)` 折算；
   - PFC 包不走 1ns dispatch 打散加速分支。

2. `QbbChannel::TransmitStart()`  
   在数值交换机路径下，非 PFC 才会 `channelDelay = 0`；  
   PFC 保持 `channelDelay = m_delay`。

也就是说：

- 数据面包（UDP/ACK/NACK 等）仍可用 true acceleration；
- PFC 控制面包按正常链路时序 + `SendPfc` 里的显式控制帧延迟传播。

---

## 7. 为什么数值仿真中的 PFC 仍可能与原始有差异

即使做了上述解耦，仍可能出现少量差异，常见原因：

1. **释放机制不同**：数值仿真存在“延后释放 admission”；
2. **离散事件边界**：仿真结束时可能多出末尾 Pause（未等到对应 Resume）；
3. **控制帧参数敏感**：`g_PFC_CONTROL_PROPAGATION_DELAY_NS` 与 `g_RELEASE_DELAY_SUBTRACT_NS` 会改变触发相位；
4. **阈值边界效应**：`CheckShouldPause/Resume` 在阈值附近对时间相位很敏感。

---

## 8. 当前与本分析直接相关的开关

- `flag_ENABLE_TRUE_TIME_ACCELERATION`
- `flag_ENABLE_RELEASE_DELAY_SUBTRACT`
- `g_RELEASE_DELAY_SUBTRACT_NS`
- `flag_ENABLE_DELAYED_MMU_RELEASE`
- `flag_ENABLE_PFC_EVENTS_LOG`
- `flag_ENABLE_PFC_DETAILED_CSV`
- `flag_ENABLE_RELEASE_DELAY_DEBUG_CSV`

---

## 9. 一句话总结

当前数值仿真中：**包会正常入队/出队，但无损队列占用可按逻辑出队时刻延后释放；Pause 在入队增压后触发，Resume 在释放后判定；PFC 控制帧已从 true acceleration 中剥离，改为显式可配置时延传播。**

