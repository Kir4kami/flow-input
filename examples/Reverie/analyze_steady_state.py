#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
稳态判断逻辑分析脚本
分析为什么系统没有进入稳态
"""

import re
from collections import defaultdict

EVAL_OUT = "dump/evaluation.out"
SIZE_THRESHOLD = 5  # flow-acc.h 中的 size 参数
RATE_THRESHOLD = 2.22045e-16  # 稳态判断阈值

print("=" * 50)
print("  稳态判断逻辑分析")
print("=" * 50)
print()

# 读取所有数据
flow_data = defaultdict(list)

with open(EVAL_OUT, 'r') as f:
    for line in f:
        match = re.search(r'Flow ID: ([\w-]+) - Rate: ([\d.]+)', line)
        if match:
            flow_id = match.group(1)
            rate = float(match.group(2))
            flow_data[flow_id].append(rate)

print(f"📊 总流数量: {len(flow_data)}")
print()

# 分析每个流
steady_flows = []
unsteady_flows = []

for flow_id, rates in flow_data.items():
    if len(rates) < SIZE_THRESHOLD:
        unsteady_flows.append((flow_id, f"周期不足 ({len(rates)} < {SIZE_THRESHOLD})"))
        continue
    
    # 检查稳态
    recent_rates = rates[-SIZE_THRESHOLD:]  # 取最后5个
    max_rate = max(recent_rates)
    min_rate = min(recent_rates)
    rate_diff = abs(max_rate - min_rate)
    
    if rate_diff <= RATE_THRESHOLD:
        steady_flows.append((flow_id, rate_diff, len(rates)))
    else:
        unsteady_flows.append((flow_id, f"速率差 {rate_diff:.2e} > {RATE_THRESHOLD:.2e}"))

print("✅ 稳定的流:")
print("-" * 50)
if steady_flows:
    for flow_id, diff, periods in steady_flows[:10]:  # 显示前10个
        print(f"  {flow_id}: {periods}个周期, 速率差={diff:.2e}")
    print(f"  ... 共 {len(steady_flows)} 个稳定流")
else:
    print("  ❌ 没有稳定的流")

print()
print("⚠️  不稳定的流:")
print("-" * 50)
if unsteady_flows:
    for flow_id, reason in unsteady_flows[:10]:
        print(f"  {flow_id}: {reason}")
    print(f"  ... 共 {len(unsteady_flows)} 个不稳定流")
else:
    print("  ✅ 所有流都稳定")

print()
print("=" * 50)
print("💡 结论:")
print("-" * 50)

if len(steady_flows) == len(flow_data) and len(steady_flows) > 0:
    print("✅ 所有流都满足稳态条件！")
    print("   但系统还是没有输出稳态，可能原因:")
    print("   1. flag_steady 不为 true（已经进入过稳态了）")
    print("   2. flowStats 在稳态判断时为空（时机问题）")
    print("   3. 稳态判断代码没有被执行到")
elif len(steady_flows) > 0:
    print(f"⚠️  部分流稳定 ({len(steady_flows)}/{len(flow_data)})")
    print("   需要等待所有流都稳定才能进入系统稳态")
    print(f"   还有 {len(unsteady_flows)} 个流阻止了系统进入稳态")
else:
    print("❌ 没有流达到稳态")
    print("   主要原因: ", unsteady_flows[0][1] if unsteady_flows else "未知")

print("=" * 50)



























