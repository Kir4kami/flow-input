#!/usr/bin/env python3
"""拓扑可视化脚本
"""

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import networkx as nx
from pathlib import Path
import numpy as np

# 设置默认字体
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

def parse_topology_file_corrected(file_path):
    """
    正确解析拓扑文件
    """
    with open(file_path, 'r') as f:
        lines = f.readlines()
    
    # 第一行：总链路数 leaf数 spine数 主机数 带宽 带宽
    first_line = lines[0].strip().split()
    total_links = int(first_line[0])
    num_leaves = int(first_line[1])
    num_spines = int(first_line[2])
    num_hosts = int(first_line[3])
    
    # 第二行：spine交换机ID列表
    spine_ids_list = [int(x) for x in lines[1].strip().split()]
    
    # 根据连接关系正确分类节点
    nodes = {}
    edges = []
    
    # 先解析所有连接
    for line in lines[2:]:
        parts = line.strip().split()
        if len(parts) >= 4:
            node1 = int(parts[0])
            node2 = int(parts[1])
            bandwidth = parts[2]
            delay = parts[3]
            edges.append((node1, node2, bandwidth, delay))
    
    # 根据连接关系推断节点类型
    all_nodes = set()
    for node1, node2, _, _ in edges:
        all_nodes.add(node1)
        all_nodes.add(node2)
    
    # 使用文件中提供的信息来分类节点
    hosts = set()
    leaves = set()
    spines = set(spine_ids_list)  # Spine节点从文件第二行获取
    
    # 主机范围：0 到 num_hosts-1
    # Leaf范围：num_hosts 到 num_hosts+num_leaves-1
    # Spine范围：从文件第二行读取
    
    host_max_id = num_hosts - 1
    leaf_start_id = num_hosts
    leaf_end_id = num_hosts + num_leaves - 1
    
    # 根据ID范围和连接关系分类节点
    for node in all_nodes:
        if node in spines:
            nodes[node] = 'spine'
        elif leaf_start_id <= node <= leaf_end_id:
            nodes[node] = 'leaf'
            leaves.add(node)
        elif node <= host_max_id:
            nodes[node] = 'host'
            hosts.add(node)
        else:
            # 未知节点，通过连接关系推断
            nodes[node] = 'unknown'
    
    return nodes, edges, len(hosts), len(leaves), len(spines)

def create_improved_layout(nodes, edges):
    """
    创建改进的布局算法
    """
    G = nx.Graph()
    
    # 添加节点和边
    for node_id, node_type in nodes.items():
        G.add_node(node_id, type=node_type)
    
    for node1, node2, _, _ in edges:
        G.add_edge(node1, node2)
    
    # 分层布局
    pos = {}
    
    # 获取各层节点
    spine_nodes = [n for n, t in nodes.items() if t == 'spine']
    leaf_nodes = [n for n, t in nodes.items() if t == 'leaf']
    host_nodes = [n for n, t in nodes.items() if t == 'host']
    
    # Spine层（最上层）
    if spine_nodes:
        spine_y = 3.0
        spine_x = np.linspace(-2, 2, len(spine_nodes))
        for i, node in enumerate(spine_nodes):
            pos[node] = (spine_x[i], spine_y)
    
    # Leaf层（中间层）
    if leaf_nodes:
        leaf_y = 1.5
        leaf_x = np.linspace(-2, 2, len(leaf_nodes))
        for i, node in enumerate(leaf_nodes):
            pos[node] = (leaf_x[i], leaf_y)
    
    # Host层（最下层）- 完全分散在宽网格中
    if host_nodes and leaf_nodes:
        # 为所有主机创建宽水平布局
        total_hosts = len(host_nodes)
        hosts_per_row = 16  # 每行16个主机以获得更好的分散效果
        host_spacing_x = 0.4  # 主机间水平间距
        host_spacing_y = 0.4  # 行间垂直间距
        
        # 计算需要多少行
        num_rows = (total_hosts + hosts_per_row - 1) // hosts_per_row
        
        # 从底部开始向上排列
        start_y = -1.0 - (num_rows - 1) * host_spacing_y
        
        for i, host in enumerate(sorted(host_nodes)):
            row = i // hosts_per_row
            col = i % hosts_per_row
            
            # 在宽网格中计算位置
            x_pos = (col - hosts_per_row / 2) * host_spacing_x
            y_pos = start_y + row * host_spacing_y
            
            pos[host] = (x_pos, y_pos)
    
    return G, pos, spine_nodes, leaf_nodes, host_nodes

def draw_improved_topology(file_path, output_path='improved_topology.png'):
    """
    绘制拓扑图
    """
    print(f"正在解析拓扑文件: {file_path}")
    nodes, edges, num_hosts, num_leaves, num_spines = parse_topology_file_corrected(file_path)
    
    print(f"解析结果: {num_hosts}个主机, {num_leaves}个Leaf交换机, {num_spines}个Spine交换机")
    
    # 创建改进的布局
    G, pos, spine_nodes, leaf_nodes, host_nodes = create_improved_layout(nodes, edges)
    
    # 设置图形大小和样式
    plt.figure(figsize=(20, 12))
    plt.style.use('default')
    
    #定义颜色方案
    colors = {
        'spine': '#FF4444',    # 红色
        'leaf': '#44AA44',     # 绿色  
        'host': '#4488FF',     # 蓝色
        'unknown': '#888888'   # 灰色
    }
    
    # 定义节点大小
    sizes = {
        'spine': 1500,  
        'leaf': 1500,   
        'host': 350,  
        'unknown': 300
    }
    
    # 绘制边（分层绘制以避免混乱）
    edge_colors = []
    edge_widths = []
    
    for edge in G.edges():
        node1, node2 = edge
        type1 = nodes[node1]
        type2 = nodes[node2]
        
        # 根据连接类型设置不同的样式
        if type1 == 'spine' and type2 == 'leaf':
            edge_colors.append('#FF6666')  # Spine-Leaf: 红色
            edge_widths.append(2.0)
        elif type1 == 'leaf' and type2 == 'host':
            edge_colors.append('#66AA66')  # Leaf-Host: 绿色
            edge_widths.append(1.5)
        else:
            edge_colors.append('#CCCCCC')  # 其他: 灰色
            edge_widths.append(1.0)
    
    # 绘制边
    nx.draw_networkx_edges(G, pos, 
                          edge_color=edge_colors,
                          width=edge_widths,
                          alpha=0.6)
    
    # 绘制节点（分层绘制）
    for node_type in ['spine', 'leaf', 'host']:
        type_nodes = [n for n, t in nodes.items() if t == node_type]
        if type_nodes:
            nx.draw_networkx_nodes(G, pos,
                                 nodelist=type_nodes,
                                 node_color=colors[node_type],
                                 node_size=sizes[node_type],
                                 alpha=0.8)
    
    # 绘制标签（显示所有节点以便更好地识别）
    labels = {}
    for node in G.nodes():
        node_type = nodes[node]
        if node_type == 'spine':
            labels[node] = f'Spine{node}'
        elif node_type == 'leaf':
            labels[node] = f'Leaf{node}'
        elif node_type == 'host':
            labels[node] = f'H{node}'  # 显示所有主机标签
    
    # 为不同节点类型绘制不同字体大小的标签
    spine_labels = {node: labels[node] for node in G.nodes() if nodes[node] == 'spine'}
    leaf_labels = {node: labels[node] for node in G.nodes() if nodes[node] == 'leaf'}
    host_labels = {node: labels[node] for node in G.nodes() if nodes[node] == 'host'}
    
    # 绘制Spine标签
    if spine_labels:
        nx.draw_networkx_labels(G, pos, spine_labels, 
                               font_size=9,  # 大圆圈用较小字体
                               font_weight='bold',
                               font_color='white')
    
    # 绘制Leaf标签
    if leaf_labels:
        nx.draw_networkx_labels(G, pos, leaf_labels, 
                               font_size=9,  # 大圆圈用较小字体
                               font_weight='bold',
                               font_color='white')
    
    #绘制Host标签
    if host_labels:
        nx.draw_networkx_labels(G, pos, host_labels, 
                               font_size=8,  # 增加字体大小以获得更好的可见性
                               font_weight='bold',
                               font_color='white')
    
    # 添加图例
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=colors['spine'], label=f'Spine Switches ({len(spine_nodes)})'),
        Patch(facecolor=colors['leaf'], label=f'Leaf Switches ({len(leaf_nodes)})'),
        Patch(facecolor=colors['host'], label=f'Hosts ({len(host_nodes)})')
    ]
    plt.legend(handles=legend_elements, loc='upper right', fontsize=12)
    
    # 添加标题和统计信息
    plt.title(f'Leaf-Spine Network Topology\n'
              f'Total Nodes: {len(nodes)} | Total Links: {len(edges)} | '
              f'Hosts: {len(host_nodes)} | Leaf: {len(leaf_nodes)} | Spine: {len(spine_nodes)}',
              fontsize=16, fontweight='bold', pad=20)
    
    # 添加分层说明
    plt.text(-4.2, 3.2, 'Spine Layer', fontsize=12, fontweight='bold', color=colors['spine'])
    plt.text(-4.2, 1.7, 'Leaf Layer', fontsize=12, fontweight='bold', color=colors['leaf'])
    plt.text(-4.2, -2.5, 'Host Layer', fontsize=12, fontweight='bold', color=colors['host'])
    
    # 设置坐标轴（扩展以容纳宽主机布局）
    plt.xlim(-4.5, 4.5)  # 水平扩展以容纳宽主机网格
    plt.ylim(-3.0, 4.0)  # 向下扩展以容纳多行主机
    plt.axis('off')
    plt.tight_layout()
    
    # 保存图片
    plt.savefig(output_path, dpi=200, bbox_inches='tight', facecolor='white')
    print(f"拓扑图已保存到: {output_path}")
    plt.close()
    
    return output_path

def main():
    """主函数"""
    topology_file = Path(__file__).parent.parent / "leaf-spine.txt"
    
    if not topology_file.exists():
        print(f"错误: 找不到拓扑文件 {topology_file}")
        return
    
    print("=" * 60)
    print("拓扑可视化")
    print("=" * 60)
    
    # 绘制改进的拓扑图
    output_file = Path(__file__).parent / "topology.png"
    draw_improved_topology(topology_file, output_file)
    
    print("\n完成！")
    print(f"请查看生成的图片: {output_file}")
    print("=" * 60)

if __name__ == "__main__":
    main()
