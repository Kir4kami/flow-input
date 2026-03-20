# 数值仿真中“延后释放占用，避免 PFC 消失”代码逐句分析

本文只分析数值仿真特有的这一段机制：

- 包在真加速路径下可以很快到达对端；
- 但交换机 MMU 占用不是立刻释放，而是按逻辑时刻延后释放；
- 这样队列在逻辑时间上仍会形成持续占用，从而可以正常触发 Pause/Resume。

---

## 1. 入口：`SwitchNotifyDequeue()` 中的延后释放调度

文件：`src/point-to-point/model/simplified-switch-node.cc`

```cpp
void
SimplifiedSwitchNode::SwitchNotifyDequeue (uint32_t ifIndex, uint32_t qIndex, Ptr<Packet> p)
{
  InterfaceTag ifTag;
  p->PeekPacketTag(ifTag);
  const uint32_t inDev = ifTag.GetPortId();

  SwitchTimingTag timingTag;
  p->RemovePacketTag(timingTag);
  const uint64_t nowNs = Simulator::Now().GetNanoSeconds();
  const uint64_t adjustedEgressNs = m_kernel.ComputeEgressTimestamp(nowNs, p->GetUid());
  timingTag.SetEgressTimeNs(adjustedEgressNs);
  timingTag.SetEgressWallTimeNs(GetWallClockNs());
  timingTag.SetOutDev(ifIndex);
  timingTag.SetQIndex(qIndex);
  p->AddPacketTag(timingTag);

  if (qIndex != 0)
    {
      MyPriorityTag priotag;
      const bool foundPrio = p->PeekPacketTag(priotag);
      const uint32_t packetSize = p->GetSize();
      if (flag_ENABLE_TRUE_TIME_ACCELERATION && adjustedEgressNs > nowNs)
        {
          const uint64_t releaseDelayNs = adjustedEgressNs - nowNs;
          Simulator::Schedule(NanoSeconds(releaseDelayNs),
                              &SimplifiedSwitchNode::ReleaseAdmissionAndResume,
                              this,
                              inDev,
                              ifIndex,
                              qIndex,
                              packetSize,
                              foundPrio);
        }
      else
        {
          ReleaseAdmissionAndResume(inDev, ifIndex, qIndex, packetSize, foundPrio);
        }
    }
}
```

### 逐句解释

1. `InterfaceTag ifTag; p->PeekPacketTag(ifTag);`
   - 从包上拿入端口标签，后续释放 MMU 占用时要知道它是从哪个入口进来的。

2. `const uint32_t inDev = ifTag.GetPortId();`
   - 记录入端口编号，供 ingress 侧占用释放和 Resume 判定使用。

3. `SwitchTimingTag timingTag; p->RemovePacketTag(timingTag);`
   - 取出并准备更新包内交换机时间标签。

4. `const uint64_t nowNs = Simulator::Now().GetNanoSeconds();`
   - 当前仿真时刻。

5. `const uint64_t adjustedEgressNs = m_kernel.ComputeEgressTimestamp(nowNs, p->GetUid());`
   - 查询该包对应的“逻辑出口时刻”。
   - 在真加速下，这个时刻可能晚于 `nowNs`，表示逻辑上还没有真正“完成离开系统”。

6. `timingTag.SetEgressTimeNs(adjustedEgressNs); ... p->AddPacketTag(timingTag);`
   - 把逻辑出口时间写回包标签，供后续接收端统计和 ACK 逻辑继承使用。

7. `if (qIndex != 0)`
   - 仅数据队列参与 MMU admission 释放与 PFC 恢复；控制队列 0 不走此逻辑。

8. `const bool foundPrio = p->PeekPacketTag(priotag);`
   - 释放时也要按同样的优先级语义还原 MMU 统计。

9. `if (flag_ENABLE_TRUE_TIME_ACCELERATION && adjustedEgressNs > nowNs)`
   - 关键分支：
     - 开启真加速；
     - 且逻辑出口在未来；
     - 则不能立刻释放占用。

10. `const uint64_t releaseDelayNs = adjustedEgressNs - nowNs;`
    - 计算从“现在”到“逻辑出口”的剩余时间。

11. `Simulator::Schedule(..., &ReleaseAdmissionAndResume, ...)`
    - 延后到逻辑出口时刻再释放 MMU 占用并判断 Resume。
    - 这是“避免 PFC 消失”的核心。

12. `else { ReleaseAdmissionAndResume(...) }`
    - 若不在真加速路径，或逻辑出口不晚于当前时刻，则按原语义立即释放。

---

## 2. 被调函数：`ReleaseAdmissionAndResume()`

文件：`src/point-to-point/model/simplified-switch-node.cc`

```cpp
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
```

### 逐句解释

1. `RemoveFromIngressAdmission(...)`
   - 从 ingress 维度减去该包占用（含 totalUsed/xoffUsed/sharedPool 等关联统计）。

2. `RemoveFromEgressAdmission(...)`
   - 从 egress 维度减去该包占用。

3. `m_bytes[...] -= packetSize`（带下限保护）
   - 更新交换机内部在途统计矩阵，防止出现负值。

4. `CheckAndSendResume(inDev, qIndex);`
   - 占用已释放，立刻检查是否达到恢复条件，必要时发送 PFC Resume。

---

## 3. 为什么这能“避免 PFC 消失”

若在真加速下仍立刻释放占用，会发生：

1. 包刚入队就近乎立刻出队；
2. MMU 占用瞬时上升后马上归零；
3. `CheckShouldPause()` 很难观察到稳定的 `headroom > 0`；
4. 最终 PFC 触发次数显著偏低甚至为 0。

采用“延后释放”后：

1. 包虽可快速投递，但 MMU 占用保留到逻辑出口时刻；
2. 队列在逻辑时间轴上形成连续积压；
3. Pause/Resume 判定接近原始模型节奏；
4. PFC 统计不再异常塌陷。

---

## 4. 与端口发送前 1ns 打散的关系

当前代码还在发送前做了 1ns 级打散（`SendToDev()` 中 `m_lastPortDispatchNs` 逻辑），它的作用是：

- 降低“同一时刻大量包同时到达”的观测噪声；
- 让事件顺序更稳定。

但它不能替代“延后释放”：

- 打散只改变事件微顺序；
- 延后释放才改变 MMU 占用在时间轴上的持续长度；
- PFC 是否触发更依赖后者。

---

## 5. 可验证指标

建议对比以下文件（同一组 workload）：

- `task1.pfc`：Pause/Resume 总量是否恢复
- `pfc_detailed_stats.csv`：Pause/Resume 间隔是否合理
- `comparison_report.txt`：PFC 保真度是否上升

若关闭延后释放逻辑，通常会看到 `numerical` 的 PFC 事件明显下降。
