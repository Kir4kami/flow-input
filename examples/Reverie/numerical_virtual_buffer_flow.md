# 数值仿真（虚拟缓冲区 + 逻辑延后释放）流程图与函数 I/O 说明

本文档对应当前代码路径：`SimplifiedSwitchNode` 的**虚拟缓冲区模式**，且走“按逻辑时间延后释放”分支。

## 1) 前置条件（本说明成立的开关）

- `flag_ENABLE_LOGICAL_VIRTUAL_BUFFER = true`
- `flag_ENABLE_TRUE_TIME_ACCELERATION = true`
- `flag_ENABLE_VB_DELAYED_RELEASE = true`
- 可选：`flag_ENABLE_VB_RELEASE_DELAY_SUBTRACT` 与 `g_VB_RELEASE_DELAY_SUBTRACT_NS`

---

## 2) 无 PFC 场景流程（headroom 不进入 >0）

```mermaid
flowchart TD
  A[包到达交换机<br/>SwitchReceiveFromDevice(device, packet, ch)] --> B[继承/修正逻辑时间标签<br/>SwitchTimingTag.ingress]
  B --> C[SendToDev(packet, ch)]
  C --> D[ResolveQueueIndex + GetOutDev]
  D --> E[VirtualBufferEnqueue(inDev,outDev,qIndex,packetSize)]
  E --> F{m_virtualHeadroomBytes[inDev][qIndex] > 0 ?}
  F -- 否 --> G[不发送 PFC Pause]
  G --> H[m_kernel.ComputeIngressTimestamp(...)]
  H --> I[打入新的 ingress 时间标签]
  I --> J[DispatchToDevice / Schedule(1ns 打散)]
  J --> K[SwitchNotifyDequeue(ifIndex,qIndex,p)]
  K --> L[m_kernel.ComputeEgressTimestamp(now,uid,&predictedReleaseNs)]
  L --> M[计算 releaseDelayNs<br/>= max(0, rawReleaseDelayNs - subtract)]
  M --> N[Schedule(releaseDelayNs, VirtualBufferReleaseAndResume)]
  N --> O[VirtualBufferReleaseAndResume(...)]
  O --> P{满足 Resume 条件?}
  P -- 否 --> Q[结束（无 PFC 事件）]
```

### 无 PFC 场景关键点

- `VirtualBufferEnqueue` 里如果未进入 headroom（`m_virtualHeadroomBytes==0`），不会触发 Pause。
- `SwitchNotifyDequeue` 仍会按逻辑时刻调度释放（这是“延后释放路径”的核心）。
- 释放后 `CheckAndSendVirtualResume` 会检查，但若从未 Pause，一般不会发送 Resume。

---

## 3) 触发 PFC 场景流程（headroom 进入 >0）

```mermaid
flowchart TD
  A[SwitchReceiveFromDevice(...)] --> B[SendToDev(...)]
  B --> C[VirtualBufferEnqueue(inDev,outDev,qIndex,packetSize)]
  C --> D[ComputeVirtualIngressThreshold(inDev,qIndex)]
  D --> E{newIngress > threshold<br/>或已在 headroom 中?}
  E -- 是 --> F[增加 m_virtualHeadroomBytes]
  F --> G[CheckAndSendVirtualPfc(inDev,qIndex)]
  G --> H{!m_virtualPaused && headroom>0 ?}
  H -- 是 --> I[device->SendPfc(qIndex,0)<br/>发送 Pause]
  I --> J[记录 pfc_events / pfc_detailed_stats]
  H -- 否 --> K[不重复发送 Pause]
  J --> L[正常发包 + 出队回调]
  K --> L
  L --> M[SwitchNotifyDequeue -> 计算 releaseDelayNs]
  M --> N[Schedule(releaseDelayNs, VirtualBufferReleaseAndResume)]
  N --> O[VirtualBufferReleaseAndResume(...)]
  O --> P[CheckAndSendVirtualResume(inDev,qIndex)]
  P --> R{paused && headroom==0 &&<br/> (ingress<xon 或 ingress+xon_offset<=threshold)}
  R -- 是 --> S[device->SendPfc(qIndex,1)<br/>发送 Resume]
  S --> T[记录 pfc_events / pfc_detailed_stats]
  R -- 否 --> U[保持 Pause 状态]
```

### 触发 PFC 场景关键点

- Pause 的触发条件本质是：队列进入 headroom 使用阶段（`m_virtualHeadroomBytes > 0`）。
- Resume 的触发条件本质是：headroom 清零 + 满足 `xon/xon_offset` 与阈值判定。
- Pause/Resume 都由 `QbbNetDevice::SendPfc(...)` 发控制帧。

---

## 4) 核心函数：输入 / 输出 / 副作用

### `SwitchReceiveFromDevice(device, packet, ch) -> bool`

- **输入**：`NetDevice*`, `Packet*`, `CustomHeader&`
- **输出**：`true`
- **副作用**：
  - 读取并修正 `SwitchTimingTag`（逻辑时间继承）
  - 调用 `SendToDev(packet, ch)`

### `SendToDev(packet, ch) -> void`

- **输入**：`Packet*`, `CustomHeader&`
- **输出**：无直接返回
- **副作用**：
  - 路由与队列选择（`GetOutDev`, `ResolveQueueIndex`）
  - 虚拟缓冲区入队（`VirtualBufferEnqueue`）
  - 调用 `m_kernel.ComputeIngressTimestamp(...)`
  - 更新包时间标签并下发 `DispatchToDevice`

### `VirtualBufferEnqueue(inDev, outDev, qIndex, packetSize) -> void`

- **输入**：端口/队列索引、包长
- **输出**：无直接返回
- **副作用**：
  - 增加 `m_virtualIngressBytes/m_virtualEgressBytes/m_virtualTotalBytes`
  - 按阈值更新 `m_virtualHeadroomBytes`
  - 同步镜像统计到 `m_mmu->ingress_bytes/egress_bytes/xoffUsed/totalUsed...`
  - 触发 `CheckAndSendVirtualPfc`

### `ComputeVirtualIngressThreshold(inDev, qIndex) -> uint64_t`

- **输入**：端口、队列
- **输出**：动态阈值（DT 风格）
- **副作用**：无

### `CheckAndSendVirtualPfc(inDev, qIndex) -> void`

- **输入**：端口、队列
- **输出**：无直接返回
- **副作用**：
  - 满足条件时发送 `Pause`（`SendPfc(qIndex,0)`）
  - 更新 `m_virtualPaused`
  - 记录 `pfc_events.csv`、`pfc_detailed_stats.csv`（若开关开启）

### `SwitchNotifyDequeue(ifIndex, qIndex, packet) -> void`

- **输入**：出端口、队列、包对象
- **输出**：无直接返回
- **副作用**：
  - `m_kernel.ComputeEgressTimestamp(...)` 取预测逻辑时刻
  - 计算 `releaseDelayNs`
  - 更新 `SwitchTimingTag.egress`
  - 调度 `VirtualBufferReleaseAndResume`（延后释放路径）
  - 记录 `release_delay_debug.csv`（若开关开启）

### `VirtualBufferReleaseAndResume(inDev, outDev, qIndex, packetSize) -> void`

- **输入**：端口/队列索引、包长
- **输出**：无直接返回
- **副作用**：
  - 释放虚拟占用：`m_virtualIngressBytes/m_virtualEgressBytes/m_virtualTotalBytes`
  - 回收 headroom：`m_virtualHeadroomBytes/m_virtualHeadroomTotalUsed`
  - 同步镜像统计到 `m_mmu` 字段
  - 调用 `CheckAndSendVirtualResume`

### `CheckAndSendVirtualResume(inDev, qIndex) -> void`

- **输入**：端口、队列
- **输出**：无直接返回
- **副作用**：
  - 满足条件时发送 `Resume`（`SendPfc(qIndex,1)`）
  - 清理 `m_virtualPaused`
  - 记录 PFC 事件/详细统计

### `SimplifiedSwitchSimulatorWrapper::ComputeIngressTimestamp(...) -> uint64_t`

- **输入**：`nowNs/outDev/qIndex/packetSize/bitRate/propDelay/packetUid`
- **输出**：入口阶段时间戳（当前实现返回 `nowNs`，排队与传播折算到 egress）
- **副作用**：
  - 更新每队列 `m_queueNextAvailableNs`
  - 记录 `packetUid -> predictedReleaseNs / predictedEgressNs`

### `SimplifiedSwitchSimulatorWrapper::ComputeEgressTimestamp(nowNs, packetUid, *predictedReleaseNs) -> uint64_t`

- **输入**：`nowNs`, `packetUid`, 输出参数指针
- **输出**：预测逻辑到达时刻（egress 时间戳）
- **副作用**：
  - 一次性消费并删除 `packetUid` 对应预测状态

---

## 5) 全局/持久状态变量（需要维护）

## A. 虚拟缓冲区状态（`SimplifiedSwitchNode` 成员）

- `m_virtualIngressBytes[p][q]`
- `m_virtualEgressBytes[p][q]`
- `m_virtualHeadroomBytes[p][q]`
- `m_virtualTotalBytes`
- `m_virtualHeadroomTotalUsed`
- `m_virtualTotalIngressReservedUsed`
- `m_virtualPaused[p][q]`

## B. 数值时序内核状态（`SimplifiedSwitchSimulatorWrapper` 成员）

- `m_queueNextAvailableNs[(outDev,q)]`：每队列下一可服务时刻
- `m_predictedReleaseByPacketUid[uid]`：预测“开始服务/释放对齐时刻”
- `m_predictedEgressByPacketUid[uid]`：预测“逻辑到达时刻”

## C. 复用 MMU 字段（仅用于阈值与统计兼容）

- `m_mmu->reserveIngress/xoff/xon/xon_offset/alphaIngress/...`
- `m_mmu->ingress_bytes/egress_bytes/xoffUsed/totalUsed/...`（由虚拟缓冲区镜像写入）

## D. 关键开关（`stat-config` 全局）

- 路径开关：`flag_ENABLE_LOGICAL_VIRTUAL_BUFFER`
- 延后释放：`flag_ENABLE_VB_DELAYED_RELEASE`
- 扣减配置：`flag_ENABLE_VB_RELEASE_DELAY_SUBTRACT`, `g_VB_RELEASE_DELAY_SUBTRACT_NS`
- 真实时间加速：`flag_ENABLE_TRUE_TIME_ACCELERATION`
- 诊断日志：`flag_ENABLE_RELEASE_DELAY_DEBUG_CSV`, `flag_ENABLE_PFC_EVENTS_LOG`, `flag_ENABLE_PFC_DETAILED_CSV`

---

## 6) 输出文件（虚拟缓冲区路径常用）

- `release_delay_debug.csv`：每包释放延迟分解（raw/applied）
- `pfc_events.csv`：Pause/Resume 事件
- `pfc_detailed_stats.csv`：触发时阈值与占用快照

