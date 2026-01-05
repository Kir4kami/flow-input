#!/usr/bin/env python3
"""
分析负载生成的路径，找出从头到尾完全共享所有链路的流组
"""

import json
import requests
from collections import defaultdict
from typing import List, Dict, Tuple, Set

def extract_links_from_path(node_path: List[int]) -> List[Tuple[int, int]]:
    """从节点路径中提取所有链路"""
    if not node_path or len(node_path) < 2:
        return []
    links = []
    for i in range(len(node_path) - 1):
        links.append((node_path[i], node_path[i + 1]))
    return links

def find_complete_shared_flows(api_url: str = "http://localhost:8000"):
    """
    调用API获取路径数据，然后分析是否有完全共享所有链路的流组
    """
    print("=" * 60)
    print("分析完全共享所有链路的流组")
    print("=" * 60)
    
    # 1. 调用API获取路径数据
    print("\n步骤1: 获取路径数据...")
    try:
        response = requests.get(f"{api_url}/parse-load-files?use_latest_workflow=true", timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        print(f"错误: 无法获取路径数据: {e}")
        return
    
    if not data.get("success"):
        print(f"错误: API返回失败: {data.get('message', '未知错误')}")
        return
    
    # 2. 提取路径信息
    ecmp_paths = data.get("ecmp_paths", {})
    actual_data = ecmp_paths.get("actual", {})
    expected_data = ecmp_paths.get("expected", {})
    
    actual_paths = actual_data.get("paths", []) if isinstance(actual_data, dict) else []
    expected_paths = expected_data.get("paths", []) if isinstance(expected_data, dict) else []
    
    # 选择路径数据
    if len(actual_paths) >= 100:
        paths_list = actual_paths
        print(f"使用 actual 路径数据: {len(actual_paths)} 条")
    elif len(expected_paths) > 0:
        paths_list = expected_paths
        print(f"使用 expected 路径数据: {len(expected_paths)} 条")
    else:
        print("错误: 未找到路径数据")
        return
    
    # 3. 建立流到路径的映射
    flow_to_path = {}
    for path_item in paths_list:
        src = path_item.get("src")
        dst = path_item.get("dst")
        node_path = path_item.get("node_path", [])
        if src is not None and dst is not None and node_path:
            flow_key = (src, dst)
            if flow_key not in flow_to_path:
                flow_to_path[flow_key] = node_path
    
    print(f"有路径信息的流数: {len(flow_to_path)}")
    
    # 4. 找出完全共享所有链路的流组
    print("\n步骤2: 分析完全共享所有链路的流组...")
    
    # 将路径转换为链路集合，然后按链路集合分组
    # 注意：使用 flow_key 去重，避免同一条流重复计算
    path_links_to_flows = defaultdict(lambda: defaultdict(list))
    
    for flow_key, node_path in flow_to_path.items():
        if not node_path or len(node_path) < 2:
            continue
        # 提取所有链路并转换为有序的元组（用于比较）
        links = tuple(extract_links_from_path(node_path))
        # 使用 flow_key 作为键，确保同一条流只计算一次
        if flow_key not in path_links_to_flows[links]:
            path_links_to_flows[links][flow_key] = {
                "src": flow_key[0],
                "dst": flow_key[1],
                "path": node_path,
                "links": links
            }
    
    # 找出共享所有链路的流组（不同的流数量 >= 2）
    complete_shared_groups = []
    for links_tuple, flows_dict in path_links_to_flows.items():
        flows_list = list(flows_dict.values())
        if len(flows_list) >= 2:  # 至少2条不同的流
            complete_shared_groups.append({
                "flows": flows_list,
                "shared_links": list(links_tuple),
                "link_count": len(links_tuple),
                "flow_count": len(flows_list)
            })
    
    # 按流数量降序排序
    complete_shared_groups.sort(key=lambda x: x["flow_count"], reverse=True)
    
    # 5. 输出结果
    print(f"\n找到 {len(complete_shared_groups)} 个完全共享所有链路的流组\n")
    
    if complete_shared_groups:
        print("=" * 60)
        print("完全共享所有链路的流组（前10个）:")
        print("=" * 60)
        
        for i, group in enumerate(complete_shared_groups[:10], 1):
            print(f"\n组 {i}:")
            print(f"  流数量: {group['flow_count']} 条")
            print(f"  共享链路数: {group['link_count']} 条")
            print(f"  共享链路: {' -> '.join([f'{l[0]}->{l[1]}' for l in group['shared_links']])}")
            print(f"  流列表:")
            for flow in group['flows'][:5]:  # 只显示前5条
                path_str = " -> ".join(map(str, flow['path']))
                print(f"    {flow['src']} -> {flow['dst']}: {path_str}")
            if len(group['flows']) > 5:
                print(f"    ... 还有 {len(group['flows']) - 5} 条流")
        
        # 统计信息
        print("\n" + "=" * 60)
        print("统计信息:")
        print("=" * 60)
        total_flows_in_groups = sum(g['flow_count'] for g in complete_shared_groups)
        avg_links = sum(g['link_count'] for g in complete_shared_groups) / len(complete_shared_groups) if complete_shared_groups else 0
        max_flow_count = max(g['flow_count'] for g in complete_shared_groups) if complete_shared_groups else 0
        max_link_count = max(g['link_count'] for g in complete_shared_groups) if complete_shared_groups else 0
        
        print(f"  总流组数: {len(complete_shared_groups)}")
        print(f"  总流数（在完全共享组中）: {total_flows_in_groups}")
        print(f"  平均链路数: {avg_links:.2f}")
        print(f"  最大流组大小: {max_flow_count} 条流")
        print(f"  最长路径: {max_link_count} 条链路")
        
        # 可行性分析
        print("\n" + "=" * 60)
        print("可行性分析:")
        print("=" * 60)
        
        if max_flow_count >= 2:
            print(f"✓ 找到 {len(complete_shared_groups)} 个完全共享所有链路的流组")
            print(f"✓ 最大的流组包含 {max_flow_count} 条流")
            print(f"✓ 这些流从头到尾共享所有 {max_link_count} 条链路")
            print(f"\n建议:")
            print(f"  1. 可以使用这些流组进行竞争带宽测试")
            print(f"  2. 这些流会从头到尾竞争所有链路的带宽")
            print(f"  3. 更容易达到稳态（因为路径完全相同）")
        else:
            print("✗ 未找到完全共享所有链路的流组")
    else:
        print("=" * 60)
        print("未找到完全共享所有链路的流组")
        print("=" * 60)
        print("\n分析原因:")
        print("  1. 在Leaf-Spine拓扑中，流通常只在部分链路共享（如TOR->Spine）")
        print("  2. 到达不同目标主机的流会在Spine之后分流")
        print("  3. 这是正常的网络行为")
        print("\n建议:")
        print("  1. 可以接受部分共享链路的流组（如只共享TOR->Spine链路）")
        print("  2. 或者手动创建完全共享所有链路的测试流组")
        print("  3. 或者修改负载生成逻辑，生成完全共享路径的流组")

if __name__ == "__main__":
    import sys
    api_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    find_complete_shared_flows(api_url)

