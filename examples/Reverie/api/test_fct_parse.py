#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 FCT 文件解析"""

def analyze_fct_metrics(content):
    """分析FCT指标"""
    lines = content.strip().split('\n')
    if len(lines) <= 1:
        return {
            "total_flows": 0,
            "average_fct": 0.0,
            "fct_distribution": {}
        }
    
    # 跳过标题行
    data_lines = [line.strip() for line in lines[1:] if line.strip()]  # 过滤空行
    total_flows = len(data_lines)
    
    fct_values = []
    flow_sizes = []
    slowdowns = []
    
    for line in data_lines:
        # 支持制表符和空格分隔
        parts = line.split()
        if len(parts) >= 5:
            try:
                fct_us = float(parts[2])  # fctus列（第3列）
                flow_size = float(parts[1])  # flowsize列（第2列）
                slowdown = float(parts[4])  # slowdown列（第5列）
                fct_values.append(fct_us)
                flow_sizes.append(flow_size)
                slowdowns.append(slowdown)
            except (ValueError, IndexError) as e:
                # 调试：记录解析失败的行
                print(f"[DEBUG] FCT解析失败: {line[:50]}... 错误: {e}, parts数量: {len(parts)}")
                continue
        else:
            # 调试：记录列数不足的行
            print(f"[DEBUG] FCT行列数不足: {line[:50]}... parts数量: {len(parts)}")
    
    # 调试：输出解析统计
    print(f"[DEBUG] FCT解析统计: 总行数={total_flows}, 成功解析={len(fct_values)}, 失败={total_flows - len(fct_values)}")
    
    if not fct_values:
        print(f"[WARNING] FCT解析结果为空，但数据行数={total_flows}")
        return {
            "total_flows": total_flows,
            "average_fct_us": 0.0,
            "average_fct_ms": 0.0,
            "average_slowdown": 0.0,
            "min_fct_us": 0.0,
            "max_fct_us": 0.0,
            "fct_distribution": {},
            "parse_error": f"解析失败：成功解析0条，总数据行{total_flows}条"
        }
    
    # 计算统计数据
    avg_fct = sum(fct_values) / len(fct_values)
    avg_slowdown = sum(slowdowns) / len(slowdowns)
    
    return {
        "total_flows": total_flows,
        "average_fct_us": avg_fct,
        "average_fct_ms": avg_fct / 1000,
        "average_slowdown": avg_slowdown,
        "min_fct_us": min(fct_values),
        "max_fct_us": max(fct_values),
        "fct_distribution": {
            "p50": sorted(fct_values)[len(fct_values)//2] if fct_values else 0,
            "p95": sorted(fct_values)[int(len(fct_values)*0.95)] if fct_values else 0,
            "p99": sorted(fct_values)[int(len(fct_values)*0.99)] if fct_values else 0
        }
    }

if __name__ == "__main__":
    import sys
    from pathlib import Path
    
    fct_file = Path(__file__).parent.parent / "dump" / "evaluation.fct1"
    
    if not fct_file.exists():
        print(f"文件不存在: {fct_file}")
        sys.exit(1)
    
    print(f"读取文件: {fct_file}")
    with open(fct_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    print(f"文件内容长度: {len(content)} 字符")
    print(f"文件行数: {len(content.strip().split(chr(10)))}")
    print("\n前3行:")
    for i, line in enumerate(content.strip().split('\n')[:3], 1):
        print(f"  {i}: {repr(line)}")
        if i > 1:
            parts = line.split()
            print(f"      分割后: {len(parts)} 列")
            if len(parts) >= 5:
                print(f"      parts[1] (flowsize): {parts[1]}")
                print(f"      parts[2] (fctus): {parts[2]}")
                print(f"      parts[4] (slowdown): {parts[4]}")
    
    print("\n开始解析...")
    result = analyze_fct_metrics(content)
    
    print("\n解析结果:")
    print(f"  total_flows: {result.get('total_flows', 0)}")
    print(f"  average_fct_us: {result.get('average_fct_us', 0)}")
    print(f"  average_fct_ms: {result.get('average_fct_ms', 0)}")
    print(f"  average_slowdown: {result.get('average_slowdown', 0)}")
    if 'parse_error' in result:
        print(f"  parse_error: {result['parse_error']}")











