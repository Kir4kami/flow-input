#!/usr/bin/env python3
"""
修复 qbb-net-device.cc 中的重复 bandwidthAnimPath 定义
"""
import re

file_path = "/home/chanel/flow-input-local/src/point-to-point/model/qbb-net-device.cc"

with open(file_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 查找并删除重复的动态定义行
new_lines = []
skip_next = False
for i, line in enumerate(lines):
    # 跳过包含 std::to_string(taskIndex) 的 bandwidthAnimPath 定义行
    if 'std::string bandwidthAnimPath = "/tmp/bandwidth_animation_task" + std::to_string(taskIndex)' in line:
        print(f"删除第 {i+1} 行: {line.strip()}")
        continue
    new_lines.append(line)

# 写回文件
with open(file_path, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f"修复完成: {file_path}")
print("请检查 880-900 行确认修复结果")

