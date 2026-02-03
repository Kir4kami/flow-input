#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
计算数值仿真相对于原始仿真的保真度和加速比

保真度（Fidelity）计算：
1. FCT（流完成时间）的相对误差
2. PFC事件的匹配度（事件数量、时间序列）
3. 其他关键指标的匹配度

加速比（Speedup）计算：
加速比 = 原始仿真时间 / 数值仿真时间
"""

import re
import sys
import os
from collections import defaultdict

def extract_simulation_time(log_file):
    """从system1.log中提取仿真时间"""
    with open(log_file, 'r') as f:
        content = f.read()
    
    match = re.search(r'simulation time:\s*(\d+)\s*ms', content)
    if match:
        return int(match.group(1))
    return None

def calculate_speedup(old_log_file, new_log_file):
    """计算加速比"""
    old_time = extract_simulation_time(old_log_file)
    new_time = extract_simulation_time(new_log_file)
    
    if old_time is None or new_time is None:
        return None
    
    speedup = old_time / new_time
    return {
        'old_time_ms': old_time,
        'new_time_ms': new_time,
        'speedup': speedup
    }

def parse_fct_file(fct_file):
    """解析FCT文件"""
    fcts = []
    with open(fct_file, 'r') as f:
        lines = f.readlines()
        if len(lines) < 2:
            return fcts
        
        # 跳过标题行
        for line in lines[1:]:
            parts = line.strip().split('\t')
            if len(parts) >= 3:
                try:
                    timestamp = float(parts[0])
                    flowsize = int(parts[1])
                    fct = float(parts[2])  # fctus (纳秒)
                    basefct = float(parts[3]) if len(parts) > 3 else 0
                    slowdown = float(parts[4]) if len(parts) > 4 else 0
                    fcts.append({
                        'timestamp': timestamp,
                        'flowsize': flowsize,
                        'fct': fct,
                        'basefct': basefct,
                        'slowdown': slowdown
                    })
                except (ValueError, IndexError):
                    continue
    return fcts

def calculate_fct_fidelity(old_fct_file, new_fct_file):
    """计算FCT保真度"""
    old_fcts = parse_fct_file(old_fct_file)
    new_fcts = parse_fct_file(new_fct_file)
    
    if len(old_fcts) != len(new_fcts):
        return {
            'error': f'FCT记录数不匹配: 原始={len(old_fcts)}, 数值={len(new_fcts)}'
        }
    
    errors = []
    for i, (old_fct, new_fct) in enumerate(zip(old_fcts, new_fcts)):
        if old_fct['fct'] > 0:
            relative_error = abs(old_fct['fct'] - new_fct['fct']) / old_fct['fct'] * 100
            errors.append(relative_error)
    
    if not errors:
        return {'error': '没有有效的FCT数据'}
    
    avg_error = sum(errors) / len(errors)
    max_error = max(errors)
    min_error = min(errors)
    fidelity = 100 - avg_error
    
    return {
        'count': len(old_fcts),
        'avg_error_percent': avg_error,
        'max_error_percent': max_error,
        'min_error_percent': min_error,
        'fidelity_percent': fidelity,
        'errors': errors
    }

def parse_pfc_file(pfc_file):
    """解析PFC文件"""
    pfc_events = []
    with open(pfc_file, 'r') as f:
        lines = f.readlines()
        if len(lines) < 2:
            return pfc_events
        
        # 跳过标题行
        for line in lines[1:]:
            parts = line.strip().split()
            if len(parts) >= 5:
                try:
                    time = float(parts[0])
                    node_id = int(parts[1])
                    node_type = int(parts[2])
                    if_index = int(parts[3])
                    pfc_type = int(parts[4])  # 1=pause, 0=resume
                    pfc_events.append({
                        'time': time,
                        'node_id': node_id,
                        'node_type': node_type,
                        'if_index': if_index,
                        'type': pfc_type
                    })
                except (ValueError, IndexError):
                    continue
    return pfc_events

def calculate_pfc_fidelity(old_pfc_file, new_pfc_file):
    """计算PFC事件保真度"""
    old_pfc = parse_pfc_file(old_pfc_file)
    new_pfc = parse_pfc_file(new_pfc_file)
    
    # 统计PFC事件数量
    old_pause = sum(1 for e in old_pfc if e['type'] == 1)
    old_resume = sum(1 for e in old_pfc if e['type'] == 0)
    new_pause = sum(1 for e in new_pfc if e['type'] == 1)
    new_resume = sum(1 for e in new_pfc if e['type'] == 0)
    
    pause_error = abs(old_pause - new_pause) / old_pause * 100 if old_pause > 0 else 0
    resume_error = abs(old_resume - new_resume) / old_resume * 100 if old_resume > 0 else 0
    
    # 计算总事件数的匹配度
    total_old = len(old_pfc)
    total_new = len(new_pfc)
    total_error = abs(total_old - total_new) / total_old * 100 if total_old > 0 else 0
    
    # 尝试匹配时间序列（如果事件数量相同）
    time_match_count = 0
    if len(old_pfc) == len(new_pfc):
        # 按时间排序
        old_sorted = sorted(old_pfc, key=lambda x: x['time'])
        new_sorted = sorted(new_pfc, key=lambda x: x['time'])
        
        # 检查时间匹配（允许1%的误差）
        for old_e, new_e in zip(old_sorted, new_sorted):
            time_diff = abs(old_e['time'] - new_e['time']) / old_e['time'] * 100 if old_e['time'] > 0 else 0
            if time_diff < 1.0:  # 时间误差小于1%
                time_match_count += 1
        
        time_match_rate = time_match_count / len(old_pfc) * 100 if len(old_pfc) > 0 else 0
    else:
        time_match_rate = 0
    
    return {
        'old_total': total_old,
        'new_total': total_new,
        'old_pause': old_pause,
        'new_pause': new_pause,
        'old_resume': old_resume,
        'new_resume': new_resume,
        'pause_error_percent': pause_error,
        'resume_error_percent': resume_error,
        'total_error_percent': total_error,
        'time_match_rate_percent': time_match_rate,
        'fidelity_percent': 100 - (pause_error + resume_error) / 2
    }

def main():
    if len(sys.argv) < 3:
        print("用法: python3 calculate_fidelity_speedup.py <原始仿真目录> <数值仿真目录>")
        print("示例: python3 calculate_fidelity_speedup.py dump_old dump")
        sys.exit(1)
    
    old_dir = sys.argv[1]
    new_dir = sys.argv[2]
    
    old_log = os.path.join(old_dir, 'system1.log')
    new_log = os.path.join(new_dir, 'system1.log')
    old_fct = os.path.join(old_dir, 'task1.fct1')
    new_fct = os.path.join(new_dir, 'task1.fct1')
    old_pfc = os.path.join(old_dir, 'task1.pfc')
    new_pfc = os.path.join(new_dir, 'task1.pfc')
    
    print("=" * 80)
    print("保真度和加速比计算报告")
    print("=" * 80)
    
    # 1. 计算加速比
    print("\n【1. 加速比（Speedup）】")
    print("-" * 80)
    speedup_result = calculate_speedup(old_log, new_log)
    if speedup_result:
        print(f"原始仿真时间: {speedup_result['old_time_ms']} ms")
        print(f"数值仿真时间: {speedup_result['new_time_ms']} ms")
        print(f"加速比: {speedup_result['speedup']:.2f}x")
    else:
        print("无法提取仿真时间")
    
    # 2. 计算FCT保真度
    print("\n【2. FCT（流完成时间）保真度】")
    print("-" * 80)
    if os.path.exists(old_fct) and os.path.exists(new_fct):
        fct_result = calculate_fct_fidelity(old_fct, new_fct)
        if 'error' in fct_result:
            print(f"错误: {fct_result['error']}")
        else:
            print(f"FCT记录数: {fct_result['count']}")
            print(f"平均相对误差: {fct_result['avg_error_percent']:.4f}%")
            print(f"最大相对误差: {fct_result['max_error_percent']:.4f}%")
            print(f"最小相对误差: {fct_result['min_error_percent']:.4f}%")
            print(f"FCT保真度: {fct_result['fidelity_percent']:.2f}%")
    else:
        print("FCT文件不存在")
    
    # 3. 计算PFC保真度
    print("\n【3. PFC事件保真度】")
    print("-" * 80)
    if os.path.exists(old_pfc) and os.path.exists(new_pfc):
        pfc_result = calculate_pfc_fidelity(old_pfc, new_pfc)
        print(f"原始仿真PFC事件总数: {pfc_result['old_total']}")
        print(f"数值仿真PFC事件总数: {pfc_result['new_total']}")
        print(f"\n原始仿真: Pause={pfc_result['old_pause']}, Resume={pfc_result['old_resume']}")
        print(f"数值仿真: Pause={pfc_result['new_pause']}, Resume={pfc_result['new_resume']}")
        print(f"\nPause事件相对误差: {pfc_result['pause_error_percent']:.2f}%")
        print(f"Resume事件相对误差: {pfc_result['resume_error_percent']:.2f}%")
        print(f"总事件数相对误差: {pfc_result['total_error_percent']:.2f}%")
        if pfc_result['time_match_rate_percent'] > 0:
            print(f"时间序列匹配率: {pfc_result['time_match_rate_percent']:.2f}%")
        print(f"PFC保真度: {pfc_result['fidelity_percent']:.2f}%")
    else:
        print("PFC文件不存在")
    
    # 4. 综合保真度
    print("\n【4. 综合保真度】")
    print("-" * 80)
    fidelity_scores = []
    if os.path.exists(old_fct) and os.path.exists(new_fct):
        fct_result = calculate_fct_fidelity(old_fct, new_fct)
        if 'fidelity_percent' in fct_result:
            fidelity_scores.append(fct_result['fidelity_percent'])
    
    if os.path.exists(old_pfc) and os.path.exists(new_pfc):
        pfc_result = calculate_pfc_fidelity(old_pfc, new_pfc)
        if 'fidelity_percent' in pfc_result:
            fidelity_scores.append(pfc_result['fidelity_percent'])
    
    if fidelity_scores:
        overall_fidelity = sum(fidelity_scores) / len(fidelity_scores)
        print(f"综合保真度: {overall_fidelity:.2f}%")
        print(f"  - FCT保真度权重: 50%")
        print(f"  - PFC保真度权重: 50%")
    else:
        print("无法计算综合保真度（缺少数据）")
    
    print("\n" + "=" * 80)

if __name__ == '__main__':
    main()
