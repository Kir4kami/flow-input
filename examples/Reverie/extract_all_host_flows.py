#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从生成的负载文件中提取所有主机节点之间的流
直接在Linux上运行，自动查找负载文件并提取所有主机对之间的流
"""

import sys
import os
import json
from pathlib import Path
from collections import defaultdict

# 添加必要的路径
base_dir = Path(__file__).parent
sys.path.insert(0, str(base_dir / "Generator" / "Generator" / "TreeCut"))

try:
    from ecmp_path import parse_rdma_operate, FlowInfo
except ImportError as e:
    print(f"错误: 无法导入ecmp_path模块: {e}")
    print("请确保在 examples/Reverie 目录下运行此脚本")
    sys.exit(1)

def find_all_load_files():
    """查找所有可用的负载文件"""
    workflow_dir = base_dir / "Generator" / "Generator" / "workflow_output"
    
    if not workflow_dir.exists():
        print(f"错误: 工作流输出目录不存在: {workflow_dir}")
        return []
    
    load_files = []
    
    # 查找所有 rdma_operate*.txt 文件
    for rdma_file in workflow_dir.rglob("rdma_operate*.txt"):
        # 排除一些明显不是负载文件的路径
        if "rdma_result" in str(rdma_file):
            load_files.append(rdma_file)
    
    # 按修改时间排序，最新的在前
    load_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    
    return load_files

def find_all_rdma_files_in_directory(directory):
    """查找指定目录下所有的rdma_operate*.txt文件"""
    dir_path = Path(directory)
    if not dir_path.exists():
        return []
    
    rdma_files = []
    for rdma_file in dir_path.glob("rdma_operate*.txt"):
        rdma_files.append(rdma_file)
    
    # 按文件名排序（rdma_operate0.txt, rdma_operate1.txt, ...）
    rdma_files.sort(key=lambda x: x.name)
    
    return rdma_files

def extract_all_host_flows(load_file):
    """从负载文件中提取所有主机节点之间的流"""
    
    if not os.path.exists(load_file):
        print(f"错误: 负载文件不存在: {load_file}")
        return []
    
    print(f"正在解析负载文件: {load_file}")
    
    # 解析负载文件
    flows = parse_rdma_operate(load_file)
    print(f"总流数: {len(flows)}")
    
    # 筛选出主机节点之间的流（节点ID < 64）
    host_flows = []
    for flow in flows:
        if flow.src_node < 64 and flow.dst_node < 64:
            host_flows.append(flow)
    
    print(f"找到 {len(host_flows)} 条主机节点之间的流")
    
    return host_flows

def generate_rdma_operate_file(flows, output_file, source_file=None):
    """生成rdma_operate格式的文件"""
    # 从源文件中读取phase信息，或使用默认值
    phase = 3000
    if source_file and os.path.exists(source_file):
        try:
            with open(source_file, 'r') as f:
                for line in f:
                    if line.startswith("phase:"):
                        phase = int(line.split(":")[1].strip())
                        break
        except:
            pass
    
    # 为每条流分配唯一的端口号（从1040开始）
    base_port = 1040
    
    # 按主机对分组，统计信息
    host_pairs = defaultdict(int)
    for flow in flows:
        host_pairs[(flow.src_node, flow.dst_node)] += 1
    
    # 生成文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("stat rdma operate:\n")
        f.write(f"phase:{phase}\n")
        f.write(f"# 所有主机节点之间的流（共 {len(flows)} 条）\n")
        f.write(f"# 唯一主机对数: {len(host_pairs)}\n")
        f.write("# 注意：每条流使用不同的端口号以避免队列对冲突\n")
        f.write("\n")
        
        for i, flow in enumerate(flows):
            port = base_port + i
            msg_len = flow.msg_len if hasattr(flow, 'msg_len') else 33554432
            f.write(f"Type rdma_send src_node {flow.src_node} src_port {port} "
                   f"dst_node {flow.dst_node} dst_port {port} "
                   f"priority 0 msg_len {msg_len}\n")
    
    print(f"\n✓ 已生成文件: {output_file}")
    print(f"   包含 {len(flows)} 条流")
    print(f"   涉及 {len(host_pairs)} 个主机对")
    
    # 显示前10个主机对的统计
    sorted_pairs = sorted(host_pairs.items(), key=lambda x: x[1], reverse=True)
    print(f"\n前10个主机对（按流数量）:")
    for (src, dst), count in sorted_pairs[:10]:
        print(f"   H{src:2d} -> H{dst:2d}: {count:3d} 条流")
    
    return output_file

def extract_all_host_flows_from_files(load_files):
    """从多个负载文件中提取所有主机节点之间的流并合并（去重）"""
    all_host_flows = []
    total_flows = 0
    processed_files = 0
    seen_flows = set()  # 用于去重：存储 (src_node, dst_node, src_port, dst_port, msg_len)
    
    for load_file in load_files:
        try:
            flows = extract_all_host_flows(load_file)
            for flow in flows:
                # 使用 (src_node, dst_node, src_port, dst_port, msg_len) 作为唯一标识
                flow_key = (
                    flow.src_node,
                    flow.dst_node,
                    getattr(flow, 'src_port', 0),
                    getattr(flow, 'dst_port', 0),
                    getattr(flow, 'msg_len', 33554432)
                )
                
                # 如果流未出现过，添加到结果中
                if flow_key not in seen_flows:
                    seen_flows.add(flow_key)
                    all_host_flows.append(flow)
            
            total_flows += len(flows)
            processed_files += 1
            
            # 每处理10个文件显示一次进度
            if processed_files % 10 == 0:
                print(f"  已处理 {processed_files}/{len(load_files)} 个文件，当前去重后流数: {len(all_host_flows)}")
                
        except Exception as e:
            print(f"警告: 处理文件 {load_file} 时出错: {e}")
            continue
    
    print(f"\n处理了 {processed_files}/{len(load_files)} 个文件")
    print(f"原始流总数: {total_flows} 条")
    print(f"去重后流数: {len(all_host_flows)} 条主机节点之间的流")
    if total_flows > len(all_host_flows):
        print(f"去除了 {total_flows - len(all_host_flows)} 条重复流")
    
    return all_host_flows

def find_latest_workflow_rdma_dir():
    """找到最新的workflow输出目录中的rdma_result目录"""
    workflow_dir = base_dir / "Generator" / "Generator" / "workflow_output"
    
    if not workflow_dir.exists():
        return None
    
    # 查找所有包含 2_traffic/rdma_result 的目录
    output_dirs = []
    for d in workflow_dir.iterdir():
        if d.is_dir():
            rdma_dir = d / "2_traffic" / "rdma_result"
            if rdma_dir.exists():
                output_dirs.append((d, rdma_dir))
    
    if not output_dirs:
        return None
    
    # 按修改时间排序，返回最新的
    output_dirs.sort(key=lambda x: x[0].stat().st_mtime, reverse=True)
    return output_dirs[0][1]

def find_all_rdma_files_in_workflow(rdma_dir):
    """在workflow的rdma_result目录中查找所有rdma_operate*.txt文件"""
    if not rdma_dir or not rdma_dir.exists():
        return []
    
    rdma_files = []
    # 遍历所有子目录（递归查找）
    for rdma_file in rdma_dir.rglob("rdma_operate*.txt"):
        # 排除一些明显不是负载文件的路径（如备份文件）
        if "backup" not in str(rdma_file).lower() and "old" not in str(rdma_file).lower():
            rdma_files.append(rdma_file)
    
    # 按路径排序（先按目录，再按文件名）
    rdma_files.sort(key=lambda x: (str(x.parent), x.name))
    
    return rdma_files

def filter_host_pairs(flows, host_pairs):
    """
    筛选指定的主机对之间的流
    
    Args:
        flows: 流列表
        host_pairs: 主机对列表，格式为 [(src1, dst1), (src2, dst2), ...]
    
    Returns:
        筛选后的流列表
    """
    filtered_flows = []
    host_pairs_set = set(host_pairs)
    
    for flow in flows:
        flow_pair = (flow.src_node, flow.dst_node)
        if flow_pair in host_pairs_set:
            filtered_flows.append(flow)
    
    return filtered_flows

def main():
    print("=" * 60)
    print("从生成的负载中提取所有主机节点之间的流")
    print("=" * 60)
    print()
    
    # 解析命令行参数：支持 --filter 参数来指定主机对
    filter_pairs = None
    args_to_process = []
    
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--filter" and i + 1 < len(sys.argv):
            # 解析 --filter 参数，格式：--filter "14,2;12,4;2,14;4,12"
            filter_str = sys.argv[i + 1]
            filter_pairs = []
            for pair_str in filter_str.split(';'):
                pair_str = pair_str.strip()
                if pair_str:
                    parts = pair_str.split(',')
                    if len(parts) == 2:
                        try:
                            src = int(parts[0].strip())
                            dst = int(parts[1].strip())
                            filter_pairs.append((src, dst))
                        except ValueError:
                            print(f"警告: 无效的主机对格式: {pair_str}")
            i += 2
        else:
            args_to_process.append(sys.argv[i])
            i += 1
    
    # 如果用户指定了目录或文件
    if args_to_process:
        specified_path = Path(args_to_process[0])
        if specified_path.is_file():
            # 单个文件
            print(f"使用指定的文件: {specified_path}")
            host_flows = extract_all_host_flows(specified_path)
            load_files = [specified_path]
        elif specified_path.is_dir():
            # 目录
            print(f"使用指定的目录: {specified_path}")
            rdma_files = find_all_rdma_files_in_workflow(specified_path)
            if not rdma_files:
                print(f"错误: 在目录 {specified_path} 中未找到任何 rdma_operate*.txt 文件")
                return
            print(f"找到 {len(rdma_files)} 个负载文件")
            host_flows = extract_all_host_flows_from_files(rdma_files)
            load_files = rdma_files
        else:
            print(f"错误: 指定的路径不存在: {specified_path}")
            return
    else:
        # 自动查找最新的workflow输出
        rdma_dir = find_latest_workflow_rdma_dir()
        
        if not rdma_dir:
            # 回退到旧方法：查找所有文件
            load_files = find_all_load_files()
            if not load_files:
                print("错误: 未找到任何负载文件")
                print(f"请检查目录: {base_dir / 'Generator' / 'Generator' / 'workflow_output'}")
                return
            
            print(f"找到 {len(load_files)} 个负载文件（旧方法）")
            print("使用最新的负载文件:")
            print(f"  {load_files[0]}")
            print()
            host_flows = extract_all_host_flows(load_files[0])
            load_files = [load_files[0]]
        else:
            # 使用最新的workflow目录
            print(f"使用最新的workflow输出目录:")
            print(f"  {rdma_dir}")
            print()
            
            # 查找该目录下的所有rdma_operate*.txt文件
            rdma_files = find_all_rdma_files_in_workflow(rdma_dir)
            
            if not rdma_files:
                print(f"错误: 在目录 {rdma_dir} 中未找到任何 rdma_operate*.txt 文件")
                return
            
            print(f"找到 {len(rdma_files)} 个负载文件")
            
            # 统计文件分布
            file_by_dir = defaultdict(int)
            for f in rdma_files:
                file_by_dir[str(f.parent)] += 1
            
            print(f"分布在 {len(file_by_dir)} 个子目录中")
            print("正在处理所有文件...")
            print()
            
            # 从所有文件中提取并合并（自动去重）
            host_flows = extract_all_host_flows_from_files(rdma_files)
            load_files = rdma_files
    
    if not host_flows:
        print("\n未找到主机节点之间的流")
        return
    
    # 如果指定了过滤条件，进行筛选
    if filter_pairs:
        print()
        print("=" * 60)
        print("筛选指定的主机对:")
        for src, dst in filter_pairs:
            print(f"  H{src} -> H{dst}")
        print("=" * 60)
        print()
        
        original_count = len(host_flows)
        host_flows = filter_host_pairs(host_flows, filter_pairs)
        filtered_count = len(host_flows)
        
        print(f"筛选前: {original_count} 条流")
        print(f"筛选后: {filtered_count} 条流")
        
        if filtered_count == 0:
            print("\n警告: 未找到匹配的主机对流")
            return
    
    # 生成输出文件
    output_file = base_dir / "task1" / "rdma_operate0.txt"
    
    # 确保输出目录存在
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 使用第一个文件作为源文件（用于获取phase信息）
    source_file = load_files[0] if load_files else None
    generate_rdma_operate_file(host_flows, output_file, source_file)
    
    print()
    print("=" * 60)
    print(f"✓ 完成！文件已保存到: {output_file}")
    print(f"   总共提取了 {len(host_flows)} 条主机节点之间的流")
    if filter_pairs:
        print(f"   筛选的主机对: {len(filter_pairs)} 个")
    print("   可以直接用于仿真")
    print("=" * 60)

if __name__ == "__main__":
    main()

