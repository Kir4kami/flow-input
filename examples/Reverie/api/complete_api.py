#!/usr/bin/env python3
# 完整的六功能汇总API接口文件
# 包含：拓扑切分、负载设置、拓扑设置、仿真控制、混合粒度控制、结果分析

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import sys
import subprocess
import json
import time
import shutil
import re
from pathlib import Path
from typing import Optional, Dict, List, Any
import threading
import asyncio

# 添加父目录到路径，以便导入TreeCut
sys.path.append(str(Path(__file__).parent.parent))
from TreeCut.TreeCut import performTreeCut
import networkx as nx
import matplotlib.pyplot as plt
import copy
from collections import defaultdict

app = FastAPI(
    title="Complete Network Simulation API",
    description="包含拓扑切分、负载设置、拓扑设置、仿真控制、混合粒度控制和结果分析的完整 API 接口",
    version="2.0.0"
)

# 添加CORS中间件，允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有源
    allow_credentials=True,
    allow_methods=["*"],  # 允许所有方法
    allow_headers=["*"],  # 允许所有头
)

# ==================== 全局状态管理 ====================

class SimulationStatus:
    def __init__(self):
        self.is_running = False
        self.current_task = None
        self.current_process = None  # 当前仿真进程
        self.steady_state = False
        self.simulation_start_time = None
        self.simulation_end_time = None
        self.results = {}

simulation_status = SimulationStatus()

# ==================== TreeCut 完整功能实现 ====================

# 根节点
root_node = 'Root'

# 切割后树的列表集合
Tree_list = []

#分别设置DP,PP,TP的rdma_operate数量
DP = 128
PP = 1
TP = 128

out_dependence_list = []

# 定义添加节点的方法
def addCommunicationEdge(G, layer, comm_type, pre_node):
    node_name = f"{comm_type}{layer}_{len(G.nodes)}"
    file_path = f"{node_name}.txt"
    # huawei主机
    try:
        from TreeCut.DocProcess import process_file
        nodes_passed = process_file(file_path)
    except:
        # 如果DocProcess不可用，使用默认值
        nodes_passed = ['A', 'B', 'C']
    G.add_node(node_name, name=node_name, type=comm_type, layer=layer, nodes_passed=nodes_passed, children=[]
               , isBurr=False)
    G.add_edge(pre_node, node_name)
    return node_name

# 构建通信树
def constructTree(G, root_node):
    DP1 = addCommunicationEdge(G, 1, "DP", root_node)
    PP1 = addCommunicationEdge(G, 1, "PP", root_node)
    # TP1 = addCommunicationEdge(G, 2, "TP", PP1)
    # TP2 = addCommunicationEdge(G, 3, "TP", TP1)
    # DP2 = addCommunicationEdge(G, 4, "DP", TP2)
    # PP2 = addCommunicationEdge(G, 4, "PP", TP2)
    # TP3 = addCommunicationEdge(G, 5, "TP", PP2)
    # TP4 = addCommunicationEdge(G, 6, "TP", TP3)
    # DP3 = addCommunicationEdge(G, 7, "DP", TP4)
    # PP3 = addCommunicationEdge(G, 7, "PP", TP4)
    # TP5 = addCommunicationEdge(G, 8, "TP", PP3)
    # TP6 = addCommunicationEdge(G, 9, "TP", TP5)
    # DP4 = addCommunicationEdge(G, 10, "DP", TP6)

# 从外部数据构建通信树
def constructTreeFromData(G, root_node, tree_data):
    """
    从外部数据构建通信树
    
    Args:
        G: NetworkX有向图对象
        root_node: 根节点名称
        tree_data: 包含树结构的字典，格式如下：
        {
            "nodes": [
                {"name": "node1", "type": "DP", "layer": 1, "nodes_passed": ["A", "B"]},
                {"name": "node2", "type": "PP", "layer": 1, "nodes_passed": ["C", "D"]}
            ],
            "edges": [
                {"from": "Root", "to": "node1"},
                {"from": "Root", "to": "node2"}
            ]
        }
    """
    # 添加所有节点
    for node_data in tree_data.get("nodes", []):
        # 检查是否是根节点
        if node_data["name"] == "Root" or node_data["name"] == root_node:
            G.add_node(
                root_node,
                name='Root',
                type=node_data.get("type", "Root"),
                layer=node_data.get("layer", 0),
                nodes_passed=node_data.get("nodes_passed", []),
                children=[],
                isBurr=False
            )
        else:
            G.add_node(
                node_data["name"], 
                name=node_data["name"], 
                type=node_data["type"], 
                layer=node_data["layer"], 
                nodes_passed=node_data.get("nodes_passed", []), 
                children=[],
                isBurr=False
            )
    
    # 添加所有边
    for edge_data in tree_data.get("edges", []):
        G.add_edge(edge_data["from"], edge_data["to"])
    
    return G

# 合并节点
def mergeInfo(Tree, remove_list, merge_in_node):
    # 将所有节点信息merge
    for node in remove_list:
        if merge_in_node != node:
            Tree.nodes[merge_in_node]['nodes_passed'].extend(Tree.nodes[node]['nodes_passed'])
            Tree.nodes[merge_in_node]['children'].append(Tree.nodes[node]['name'])
            for item in Tree.nodes[node]['children']:
                Tree.nodes[merge_in_node]['children'].append(item)

# 将节点从Tree中cut掉，还原节点后添加root节点后插入到Tree_list中
def recoverTree(node, tree_copy=None):
    global Tree_copy
    if tree_copy is None:
        tree_copy = Tree_copy
    
    if node['name'] == 'Root' and len(node['children']) == 0:
        return 0
    node_list = [node['name']]
    node_list.extend(node['children'])
    cut_tree = tree_copy.subgraph(node_list)
    cut_tree = nx.DiGraph(cut_tree)
    if node['name'] != 'Root':
        cut_tree.add_node(root_node, name='Root')
        cut_tree.add_edge(root_node, node['name'])
    Tree_list.append(cut_tree)

def get_parent(graph, node):
    parents = list(graph.predecessors(node))
    if parents:
        return parents[0]
    else:
        return None

# 将节点从Tree中cut掉，添加root节点后插入到Tree_list中
def cutBurrNode(Tree, node):
    parents = get_parent(Tree, node)
    out_dependence_list.append((node, parents))
    Tree.remove_node(node)
    cut_tree = nx.DiGraph()
    cut_tree.add_node(root_node, name='root')
    cut_tree.add_edge(root_node, node)
    Tree_list.append(cut_tree)

# 找出所有的叶子节点("毛刺")，将无兄弟节点的叶子节点向上合并（视为"揉球"操作）
def findBurr(Tree, out_degrees):

    # 找到所有的叶子节点（出度为0的节点）
    leaves = [n for n, d in out_degrees.items() if d == 0]

    # 查找所有有兄弟的叶子节点
    leaves_with_siblings = []
    for leaf in leaves:
        parents = list(Tree.predecessors(leaf))
        # 如果父节点的出度等于2，则说明当前叶子节点有兄弟
        if out_degrees[parents[0]] == 2:
            leaves_with_siblings.append(Tree.nodes[leaf])
            Tree.nodes[leaf]['isBurr'] = True
        # else:
        #     # 接收merge信息
        #     leaf_ball = mergeNodes(Tree, leaf, out_degrees)
        #     leaves_without_siblings.append(leaf_ball)
    return leaves_with_siblings

# 对通信树进行预处理，修剪"毛刺"节点
def preTreatment(Tree):
    # 获取所有节点的出度字典
    out_degrees = dict(Tree.out_degree())
    burr_list = findBurr(Tree, out_degrees)
    double_break = False
    for burr_node in burr_list:
        burr_node['checked'] = True
        path_to_root = nx.shortest_path(Tree, source=root_node, target=burr_node["name"])
        path_nodes = set(path_to_root)
        # 获取目标节点的nodes_passed列表
        target_nodes_passed = set(burr_node.get('nodes_passed', []))
        for _, other_node in Tree.nodes(data=True):
            # 排除到时间序列上的节点和自身
            if other_node['name'] not in path_nodes and other_node != burr_node:
                other_nodes_passed = set(other_node.get('nodes_passed', []))
                # 判断是否有交集，有则无法切割，将标记标为相应的
                if target_nodes_passed.intersection(other_nodes_passed):
                    double_break = True
                    break
        # 若内循环break则说明burr节点不能切割，外循环也要break
        if double_break:
            double_break = False
            continue
        # 将该节点从Tree中cut掉
        cutBurrNode(Tree, burr_node['name'])
    return Tree

# 找到要移除节点的列表
def getRemoveList(Tree, start_node):
    """
    从给定的节点开始，沿着父节点路径向上遍历，
    直到找到一个有兄弟节点的节点，并返回路径上的所有节点。

    :param G: NetworkX DiGraph, 表示树或DAG的图
    :param start_node: 起始查找的节点
    :return: 一个包含路径上所有节点的列表，有兄弟的节点
    """
    path = []  # 用于存储路径上的节点
    current_node = start_node
    while True:
        path.append(current_node)  # 将当前节点添加到路径列表
        # 获取当前节点的所有前驱节点（即父节点）
        predecessors = list(Tree.predecessors(current_node))
        if not predecessors:
            # 如果没有前驱节点，则到达了根节点，停止搜索
            break
        parent = predecessors[0]  # 假设每个节点最多只有一个父节点
        # 获取父节点的所有后继节点（即子节点/兄弟节点）
        siblings = list(Tree.successors(parent))
        if len(siblings) > 1:
            # 如果有多个子节点，则找到了有兄弟节点的节点
            # path.append(parent)  # 添加这个有兄弟节点的父节点到路径
            break
        # 否则继续向上查找
        current_node = parent
    return path, current_node

# 对通信树的每个节点判断能否能切
def oneNodeTreatment(Tree, node, tree_copy=None):
    # 默认无冲突的标志符，看是否是因为无冲突而裁剪，若是的话需要恢复树形放入Tree_list
    isConflict = False

    # 找到到根节点路径节点的集合
    path_to_root = nx.shortest_path(Tree, source=root_node, target=node["name"])
    path_nodes = set(path_to_root)
    # 获取目标节点的nodes_passed列表
    target_nodes_passed = set(node.get('nodes_passed', []))
    for _, other_node in Tree.nodes(data=True):
        # 排除到时间序列上的节点和自身
        if other_node['name'] not in path_nodes and other_node != node:
            other_nodes_passed = set(other_node.get('nodes_passed', []))
            # 判断是否有交集，有则无法切割，将标记标为相应的
            if target_nodes_passed.intersection(other_nodes_passed):
                # 有交集，有冲突
                isConflict = True
                break
    # 如果没有冲突，将该节点从Tree中cut掉
    if not isConflict:
        # 将NetworkX节点数据转换为recoverTree期望的格式
        node_data = {
            'name': node['name'],
            'children': node.get('children', [])
        }
        recoverTree(node_data, tree_copy)
        Tree.remove_node(node['name'])
    # 如果有冲突，该节点往上到PP都不能切割
    else:
        remove_list, merge_in_node = getRemoveList(Tree, node['name'])
        mergeInfo(Tree, remove_list, merge_in_node)
        for item in remove_list:
            if item != merge_in_node:
                Tree.remove_node(item)
    return Tree

# 找到所有到根节点最长的路径
def findAllLongestPathsFromRoot(G):
    root = root_node
    # Dictionary to store the longest path length from the root to each node
    longest_paths = {node: -1 for node in G.nodes}
    longest_paths[root] = 0  # The distance from the root to itself is 0

    # Dictionary to store all paths from the root to each node
    all_paths = defaultdict(list)
    all_paths[root].append([root])

    def dfs(node):
        for neighbor in G.neighbors(node):
            if longest_paths[neighbor] == -1:  # If the neighbor has not been visited yet
                longest_paths[neighbor] = longest_paths[node] + 1
                for path in all_paths[node]:
                    new_path = path + [neighbor]
                    all_paths[neighbor].append(new_path)
                dfs(neighbor)

    # Start DFS from the root
    dfs(root)

    # Find the maximum distance from the root
    max_distance = max(longest_paths.values())

    # Collect all paths that have the maximum distance
    longest_paths_list = []
    for node, paths in all_paths.items():
        if longest_paths[node] == max_distance:
            longest_paths_list.extend(paths)

    return longest_paths_list

# 分割通信树
def splitCommunicationTree(Tree, tree_copy=None):
    global Tree_copy
    if tree_copy is None:
        tree_copy = Tree_copy

    # 函数出口,如果图中只剩根节点，那么根节点记录着所有子节点的信息
    if Tree.number_of_nodes() == 1:
        root_node_data = {
            'name': 'Root',
            'children': Tree.nodes['Root'].get('children', [])
        }
        recoverTree(root_node_data, tree_copy)
        return 0
    deepest_path_list = findAllLongestPathsFromRoot(Tree)
    deepest_node_list = []
    for deepest_path in deepest_path_list:
        deepest_node_list.append(deepest_path[-1])

    classification = defaultdict(list)

    # 将具有相同父节点的节点分类
    for leaf in deepest_node_list:
        # 获取当前叶子节点的所有前驱节点（即父节点）
        predecessors = list(Tree.predecessors(leaf))
        if predecessors:
            parent = predecessors[0]  # 假设每个节点最多只有一个父节点
            classification[parent].append(leaf)
        else:
            # 如果没有前驱节点，则认为该节点是根节点
            classification[None].append(leaf)
    # 将分类结果转换为一个大列表，每个元素是一个包含叶子节点的小列表
    classified_lists = [children for children in classification.values()]

    # 获取最深的叶子节点
    for deepest_node in classified_lists:
        # 如果没有兄弟节点
        if len(deepest_node) == 1:
            # 对每个节点进行切割和合并处理
            Tree = oneNodeTreatment(Tree, Tree.nodes[deepest_node[0]], tree_copy)
        # 如果有兄弟节点
        else:
            mergeInfo(Tree, deepest_node, list(Tree.predecessors(deepest_node[0]))[0])
            for item in deepest_node:
                Tree.remove_node(item)
    splitCommunicationTree(Tree, tree_copy)

def genInDependence(item, folder_name):
    # 初始化temp
    temp = 0
    # 存储记录结果的字典
    record = {}
    #遍历图中的每个节点
    for node in item.nodes:
        # 提取节点名称的前两个字符
        node_prefix = node[:2]
        # 检查节点前缀是否与全局变量名称匹配
        if node_prefix == 'TP':
            record[node] = (temp,temp + TP - 1)
            temp += TP
        elif node_prefix == 'DP':
            record[node] = (temp,temp + DP - 1)
            temp += DP
        elif node_prefix == 'PP':
            record[node] = (temp,temp + PP - 1)
            temp += PP
    #将record写入到G的节点属性中
    for node,(start,end) in record.items():
        item.nodes[node]['range'] = f"{start}-{end}"
        item.nodes[node]['group'] = folder_name

def makeInDependenceInfo(Tree_list, output_dir="TreeGroup"):
    # 定义目标目录
    target_directory = output_dir
    # 如果目标目录不存在，创建
    if not os.path.exists(target_directory):
        os.makedirs(target_directory)
    # 从后向前遍历 Tree_list
    for index, item in enumerate(reversed(Tree_list), start=1):
        # 创建子目录,命名规则为group1,group2,...,groupn
        folder_name = f"group{index}"
        folder_path = os.path.join(target_directory, folder_name)
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        genInDependence(item, folder_name)
    # 定义输出文件路径
    for index, item in enumerate(reversed(Tree_list), start=1):
        output_file = f"{target_directory}/group{index}/In_dependence_Info.txt"
        isWrite = False
        # 打开文件以写入
        with open(output_file, 'w') as file:
            # 遍历图中的每条边
            for u, v in item.edges:
                # 如果起点是根节点,跳过
                if u == 'Root':
                    continue
                # 检查节点是否有range属性
                if 'range' in item.nodes[u] and 'range' in item.nodes[v]:
                    # 获取起点和终点的range属性
                    start_range = item.nodes[u]['range']
                    end_range = item.nodes[v]['range']
                    isWrite = True
                    # 以指定格式写入文件
                    file.write(f"({end_range},{start_range})\n")
            if not isWrite:
                file.write("Null\n")
            file.write(f"---------------------------------------------------\n")
            # 遍历图中的每个节点
            for node in item.nodes:
                # 如果起点是根节点, 跳过
                if node == 'Root':
                    continue
                # 检查节点是否有必需的属性
                node_data = item.nodes[node]
                if 'name' in node_data and 'range' in node_data:
                    # 以指定格式写入文件
                    file.write(f"({node_data['name']}):({node_data['range']})\n")


def makeOutDependenceInfo(outdependence_list, Tree_list, output_dir="TreeGroup"):
    output_file_path = f"{output_dir}/Out_Dependence_Info.txt"
    os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
    # 打开文件准备写入
    with open(output_file_path, 'w') as file:
        for name, second_element in out_dependence_list:
            # 找元组的第二个位置
            found = False
            for graph in Tree_list:
                for node in graph.nodes(data=True):
                    if node[1].get('name') == second_element:
                        # 检查节点是否有group属性
                        if 'group' in node[1]:
                            file.write(f"{node[1]['group']}:")
                        break
                if found:
                    break
            # 找元组的第一个位置
            found = False
            for graph in Tree_list:
                for node in graph.nodes(data=True):
                    if node[1].get('name') == name:
                        # 检查节点是否有必需的属性
                        if 'group' in node[1] and 'range' in node[1]:
                            file.write(f"{node[1]['group']}->{node[1]['range']}\n")
                        found = True
                        break
                if found:
                    break

# 生成图像
def ShowGraph(G):
    pos = nx.spring_layout(G, seed=10)  # 通过Spring布局来展示图
    nx.draw(G, pos, with_labels=True, node_size=500, node_color='skyblue', font_size=10, font_weight='bold',
            edge_color='gray')
    plt.show()

# 将NetworkX图转换为可序列化的格式
def graphToDict(graph):
    """将NetworkX图转换为字典格式"""
    nodes = []
    for node, data in graph.nodes(data=True):
        node_dict = {"name": node}
        # 只保留可序列化的数据
        for key, value in data.items():
            if isinstance(value, (str, int, float, bool, list, dict)) or value is None:
                node_dict[key] = value
        nodes.append(node_dict)
    
    edges = []
    for u, v in graph.edges():
        edges.append({"from_node": u, "to_node": v})
    
    return {"nodes": nodes, "edges": edges}

# 保存TreeGroup为JSON文件
def saveTreeGroupToJson(Tree_list, output_dir="TreeGroup"):
    """将切分后的TreeGroup保存为JSON文件"""
    import json
    import os
    
    # 确保输出目录存在
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 保存每个Tree为单独的JSON文件
    tree_files = []
    for i, tree in enumerate(Tree_list, 1):
        tree_data = graphToDict(tree)
        filename = f"tree_group_{i}.json"
        filepath = os.path.join(output_dir, filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(tree_data, f, indent=2, ensure_ascii=False)
        
        tree_files.append({
            "group_id": i,
            "filename": filename,
            "filepath": filepath,
            "node_count": len(tree_data["nodes"]),
            "edge_count": len(tree_data["edges"])
        })
    
    # 保存TreeGroup总览信息
    overview = {
        "total_groups": len(Tree_list),
        "groups": tree_files,
        "output_directory": output_dir
    }
    
    overview_file = os.path.join(output_dir, "tree_group_overview.json")
    with open(overview_file, 'w', encoding='utf-8') as f:
        json.dump(overview, f, indent=2, ensure_ascii=False)
    
    return overview

# 将字典格式转换为NetworkX图
def dictToGraph(data):
    """将字典格式转换为NetworkX图"""
    G = nx.DiGraph()
    
    # 添加节点
    for node_data in data.get("nodes", []):
        node_name = node_data["name"]
        node_attrs = {k: v for k, v in node_data.items() if k != "name"}
        G.add_node(node_name, **node_attrs)
    
    # 添加边
    for edge_data in data.get("edges", []):
        G.add_edge(edge_data["from"], edge_data["to"])
    
    return G

# 主要的拓扑切分函数（完整版本）
def performTreeCutComplete(tree_data=None, output_dir="TreeGroup", show_graphs=False):
    """
    执行拓扑切分的主要函数（完整版本）
    
    Args:
        tree_data: 外部通信树数据，如果为None则使用默认构建方式
        output_dir: 输出目录，默认为"TreeGroup"
        show_graphs: 是否显示图形，默认为False
    
    Returns:
        dict: 包含切分结果的字典
    """
    global Tree_list, out_dependence_list
    
    # 重置全局变量
    Tree_list = []
    out_dependence_list = []
    
    # 创建一个有向图
    T = nx.DiGraph()
    
    if tree_data is not None:
        # 使用外部数据构建通信树
        T = constructTreeFromData(T, root_node, tree_data)
    else:
        # 使用默认方式构建通信树
        T.add_node(root_node, name='Root', nodes_passed=[], children=[])
        constructTree(T, root_node)
    
    if show_graphs:
        ShowGraph(T)
    
    # 预处理
    T = preTreatment(T)
    Tree_copy = copy.deepcopy(T)
    
    # 执行切分
    splitCommunicationTree(T, Tree_copy)
    
    if show_graphs:
        for item in Tree_list:
            print(item.edges())
            ShowGraph(item)
    
    # 生成输出文件
    makeInDependenceInfo(Tree_list, output_dir)
    makeOutDependenceInfo(out_dependence_list, Tree_list, output_dir)
    
    # 保存TreeGroup为JSON文件
    json_overview = saveTreeGroupToJson(Tree_list, output_dir)
    
    # 返回结果
    result = {
        "success": True,
        "tree_groups": len(Tree_list),
        "output_directory": output_dir,
        "json_overview": json_overview,
        "tree_list": Tree_list,
        "out_dependence_list": out_dependence_list
    }
    
    return result

# ==================== 拓扑切分接口相关 ====================

class TreeCutRequest(BaseModel):
    tree_data: Dict[str, Any]
    output_dir: str = "TreeGroup"
    show_graphs: bool = False

class TreeCutResponse(BaseModel):
    success: bool
    message: str
    tree_groups: int
    output_directory: str
    json_overview: Dict[str, Any]
    result_files: List[str]

@app.post("/tree-cut", response_model=TreeCutResponse)
async def tree_cut(request: TreeCutRequest):
    """拓扑切分接口"""
    try:
        # 转换edge格式
        tree_data = request.tree_data.copy()
        if "edges" in tree_data:
            converted_edges = []
            for edge in tree_data["edges"]:
                if "from_node" in edge and "to_node" in edge:
                    converted_edges.append({
                        "from": edge["from_node"],
                        "to": edge["to_node"]
                    })
                else:
                    converted_edges.append(edge)
            tree_data["edges"] = converted_edges
        
        # 使用完整的TreeCut功能
        result = performTreeCut(
            tree_data=tree_data,
            output_dir=request.output_dir,
            show_graphs=request.show_graphs
        )
        
        result_files = []
        if os.path.exists(request.output_dir):
            for root, dirs, files in os.walk(request.output_dir):
                for file in files:
                    result_files.append(os.path.join(root, file))
        
        return TreeCutResponse(
            success=result["success"],
            message=f"成功切分通信树，生成了{result['tree_groups']}个树组",
            tree_groups=result["tree_groups"],
            output_directory=result["output_directory"],
            json_overview=result["json_overview"],
            result_files=result_files
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"拓扑切分时出错: {str(e)}")

# ==================== 负载设置接口相关 ====================

class LoadRequest(BaseModel):
    """
    网络负载生成请求模型
    
    用于定义生成网络负载配置所需的参数
    """
    host_num: int  # 节点数量，64
    msg_len: str  # 流量大小，"32*(1024)"
    dp: int  # 数据并行度，8
    device: int  # 设备ID，0
    forward: int  # 前向传播标志，1表示前向，0表示后向
    model_name: str = "custom"  # 模型名称，默认为custom
    stage_type: str = "TP"  # 阶段类型，默认为TP（张量并行）
    parent_stage: str = "Root"  # 父阶段，默认为Root

class LoadResponse(BaseModel):
    success: bool
    content: str
    filename: str
    message: str

def generate_load_config(host_num, msg_len, dp, device, forward, 
                        model_name="custom", stage_type="TP", parent_stage="Root"):
    """生成负载配置的核心函数"""
    
    # 生成负载配置内容
    content_lines = []
    
    # 第一行：模型名称 张量并行度 流水线并行度
    content_lines.append(f"{model_name} 1 1")
    
    # 第二行：阶段配置
    stage_line = f"1\t{stage_type}\t{parent_stage}\t--host_num {host_num}\t--msg_len {msg_len}\t--dp {dp} --device {device} --forward {forward}"
    content_lines.append(stage_line)
    
    return "\n".join(content_lines)

def generate_operate_files(load_config_content, output_dir="rdma_result"):
    """根据负载配置生成operate.txt文件"""
    import os
    import re
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 解析配置内容
    lines = load_config_content.strip().split('\n')
    if len(lines) < 2:
        return []
    
    # 解析第一行获取模型信息
    model_info = lines[0].split()
    model_name = model_info[0] if model_info else "custom"
    
    # 解析阶段配置
    stage_line = lines[1]
    parts = stage_line.split('\t')
    if len(parts) < 6:
        return []
    
    stage_id = parts[0]
    stage_type = parts[1]
    parent_stage = parts[2]
    
    # 解析参数
    host_num = 64
    msg_len = "32*(1024)"
    dp = 8
    device = 0
    forward = 1
    
    for part in parts[3:]:
        if part.startswith("--host_num"):
            host_num = int(part.split()[1])
        elif part.startswith("--msg_len"):
            msg_len = part.split()[1]
        elif part.startswith("--dp"):
            dp = int(part.split()[1])
        elif part.startswith("--device"):
            device = int(part.split()[1])
        elif part.startswith("--forward"):
            forward = int(part.split()[1])
    
    # 计算消息长度（字节）
    msg_len_bytes = eval(msg_len.replace('*', '*').replace('(', '').replace(')', ''))
    
    # 生成operate.txt文件
    operate_files = []
    stage_dir = f"{output_dir}/{stage_id}_{stage_type}{stage_id}"
    os.makedirs(stage_dir, exist_ok=True)
    
    # 生成rdma_operate.txt
    operate_file = os.path.join(stage_dir, "rdma_operate.txt")
    with open(operate_file, 'w', encoding='utf-8') as f:
        f.write("stat rdma operate:\n")
        f.write("phase:3000\n")
        
        # 生成RDMA操作指令
        for i in range(host_num - 1):
            src_node = i
            dst_node = i + 1
            f.write(f"Type rdma_send src_node {src_node} src_port 1000 dst_node {dst_node} dst_port 1000 priority 0 msg_len {msg_len_bytes}\n")
    
    operate_files.append(operate_file)
    
    # 生成额外的operate文件（如果需要）
    for i in range(1, min(3, dp)):  # 最多生成3个额外的operate文件
        extra_file = os.path.join(stage_dir, f"rdma_operate{i}.txt")
        with open(extra_file, 'w', encoding='utf-8') as f:
            f.write("stat rdma operate:\n")
            f.write("phase:3000\n")
            
            # 生成额外的RDMA操作指令
            for j in range(0, host_num, dp):
                if j + i < host_num:
                    src_node = j
                    dst_node = j + i
                    f.write(f"Type rdma_send src_node {src_node} src_port 1000 dst_node {dst_node} dst_port 1000 priority 0 msg_len {msg_len_bytes}\n")
        
        operate_files.append(extra_file)
    
    return operate_files

@app.post("/generate-load", response_model=LoadResponse)
async def generate_load(request: LoadRequest):
    """
    生成网络负载配置
    
    - **host_num**: 节点数量
    - **msg_len**: 流量大小，如"32*(1024)"
    - **dp**: 数据并行度
    - **device**: 设备ID
    - **forward**: 前向传播标志（1表示前向，0表示后向）
    - **model_name**: 模型名称（默认custom）
    - **stage_type**: 阶段类型（默认TP）
    - **parent_stage**: 父阶段（默认Root）
    """
    try:
        # 验证输入参数
        if request.host_num <= 0:
            raise HTTPException(status_code=400, detail="host_num必须大于0")
        
        if request.dp <= 0:
            raise HTTPException(status_code=400, detail="dp必须大于0")
        
        if request.device < 0:
            raise HTTPException(status_code=400, detail="device必须大于等于0")
        
        if request.forward not in [0, 1]:
            raise HTTPException(status_code=400, detail="forward必须是0或1")
        
        # 生成负载配置内容
        load_content = generate_load_config(
            host_num=request.host_num,
            msg_len=request.msg_len,
            dp=request.dp,
            device=request.device,
            forward=request.forward,
            model_name=request.model_name,
            stage_type=request.stage_type,
            parent_stage=request.parent_stage
        )
        
        # 生成operate.txt文件
        operate_files = generate_operate_files(load_content)
        
        # 生成文件列表信息
        file_info = f"生成了{len(operate_files)}个operate.txt文件"
        if operate_files:
            file_info += f"：{', '.join([os.path.basename(f) for f in operate_files])}"
        
        return LoadResponse(
            success=True,
            content=load_content,
            filename=f"{request.model_name}_load.txt",
            message=f"成功生成负载配置：{request.host_num}个节点，流量大小{request.msg_len}，{file_info}"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成负载配置时出错: {str(e)}")

# ==================== 拓扑设置接口相关 ====================

class TopologyRequest(BaseModel):
    """
    Leaf-Spine 网络拓扑生成请求模型
    
    用于定义生成 Leaf-Spine 网络拓扑所需的参数
    """
    torSwitches: int  # TOR（Top of Rack）交换机数量，必需参数
    spineSwitches: int  # Spine 核心交换机数量，必需参数
    serversPerTor: int = 8  # 每个 TOR 下连接的服务器数量，默认 8 台
    serverTorDelay: str = "2us"  # 服务器到 TOR 交换机的网络延迟，默认 2 微秒
    torSpineDelay: str = "2us"  # TOR 到 Spine 交换机的网络延迟，默认 2 微秒
    serverDataRate: int = 25  # 服务器链路数据率（Gbps），默认 25 Gbps
    allOtherDataRate: int = 25  # 交换机间链路数据率（Gbps），默认 25 Gbps
    errorRate: float = 0  # 链路传输错误率，默认 0（无错误）

class TopologyResponse(BaseModel):
    success: bool
    content: str
    filename: str
    message: str

def generate_topology_leafspine(torSwitches, spineSwitches, serversPerTor=8, 
                               serverTorDelay="2us", torSpineDelay="2us",
                               serverDataRate=25, allOtherDataRate=25, errorRate=0):
    """生成 Leaf-Spine 拓扑的核心函数"""
    import numpy as np
    
    output_file = "leaf-spine.txt"
    
    # 计算拓扑参数
    num_hosts = serversPerTor * torSwitches
    num_leaves = torSwitches  # TOR就是Leaf
    num_spines = spineSwitches
    link_num = serversPerTor * torSwitches + (torSwitches) * spineSwitches
    
    # 生成拓扑内容
    content_lines = []
    
    # 第一行：总链路数 leaf数 spine数 主机数 服务器带宽 交换机带宽
    # 这个格式与topology_visualization.py的parse_topology_file_corrected()匹配
    content_lines.append(f"{link_num} {num_leaves} {num_spines} {num_hosts} {int(serverDataRate*1e9)} {int(allOtherDataRate*1e9)}")
    
    # 第二行：spine交换机节点ID列表
    spineIndexBegin = serversPerTor * torSwitches + torSwitches
    spine_ids = []
    for i in range(spineSwitches):
        spine_ids.append(str(spineIndexBegin + i))
    content_lines.append(" ".join(spine_ids))
    
    # 服务器到TOR的连接
    for i in range(torSwitches):
        for j in range(serversPerTor):
            server_id = j + serversPerTor * i
            tor_id = serversPerTor * torSwitches + i
            content_lines.append(f"{server_id} {tor_id} {int(serverDataRate*1e9)} {serverTorDelay} {errorRate}")
    
    # TOR到Spine的连接
    torIndexBegin = serversPerTor * torSwitches
    spineIndexBegin = serversPerTor * torSwitches + torSwitches
    
    for i in range(torSwitches):
        for j in range(spineSwitches):
            tor_id = torIndexBegin + i
            spine_id = spineIndexBegin + j
            content_lines.append(f"{tor_id} {spine_id} {int(allOtherDataRate*1e9)} {torSpineDelay} {errorRate}")
    
    return "\n".join(content_lines)

@app.post("/generate-topology", response_model=TopologyResponse)
async def generate_topology(request: TopologyRequest):
    """
    生成 Leaf-Spine 网络拓扑
    
    - **torSwitches**: TOR交换机数量
    - **spineSwitches**: Spine交换机数量
    - **serversPerTor**: 每个TOR下的服务器数量（默认8）
    - **serverTorDelay**: 服务器到TOR的延迟（默认2us）
    - **torSpineDelay**: TOR到Spine的延迟（默认2us）
    - **serverDataRate**: 服务器数据率（默认25Gbps）
    - **allOtherDataRate**: 其他链路数据率（默认25Gbps）
    - **errorRate**: 错误率（默认0）
    """
    try:
        # 验证输入参数
        if request.torSwitches <= 0 or request.spineSwitches <= 0:
            raise HTTPException(status_code=400, detail="torSwitches和spineSwitches必须大于0")
        
        if request.serversPerTor <= 0:
            raise HTTPException(status_code=400, detail="serversPerTor必须大于0")
        
        # 生成拓扑内容
        topology_content = generate_topology_leafspine(
            torSwitches=request.torSwitches,
            spineSwitches=request.spineSwitches,
            serversPerTor=request.serversPerTor,
            serverTorDelay=request.serverTorDelay,
            torSpineDelay=request.torSpineDelay,
            serverDataRate=request.serverDataRate,
            allOtherDataRate=request.allOtherDataRate,
            errorRate=request.errorRate
        )
        
        # 保存到文件
        topology_file = Path(__file__).parent.parent / "leaf-spine.txt"
        with open(topology_file, 'w', encoding='utf-8') as f:
            f.write(topology_content)
        
        return TopologyResponse(
            success=True,
            content=topology_content,
            filename="leaf-spine.txt",
            message=f"成功生成拓扑：{request.torSwitches}个TOR，{request.spineSwitches}个Spine，已保存到 {topology_file}"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成拓扑时出错: {str(e)}")

# ==================== 仿真控制接口相关 ====================

class SimulationRequest(BaseModel):
    task_num: int = 1  # 1=不开启切分，4=开启切分
    llm_model: str = "deepseek"  # 模型名称
    enable_mixed_granularity: bool = True  # 是否启用混合粒度
    simulation_time: float = 10.0  # 仿真时间（秒）

class SimulationResponse(BaseModel):
    success: bool
    message: str
    simulation_id: str
    status: str
    results: Dict[str, Any]

def modify_sim_script(task_num: int, llm_model: str):
    """修改sim.sh脚本中的参数"""
    sim_script_path = Path(__file__).parent.parent / "sim.sh"
    
    if not sim_script_path.exists():
        raise FileNotFoundError(f"sim.sh文件不存在: {sim_script_path}")
    
    # 读取原文件
    with open(sim_script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 修改TASKNUM
    content = re.sub(r'TASKNUM=\d+', f'TASKNUM={task_num}', content)
    # 修改LLM
    content = re.sub(r'LLM="[^"]*"', f'LLM="{llm_model}"', content)
    
    # 写回文件
    with open(sim_script_path, 'w', encoding='utf-8') as f:
        f.write(content)

def modify_qbb_device(enable_mixed_granularity: bool):
    """修改qbb-net-device.cc中的混合粒度设置"""
    qbb_file_path = Path(__file__).parent.parent.parent / "src" / "point-to-point" / "model" / "qbb-net-device.cc"
    
    if not qbb_file_path.exists():
        raise FileNotFoundError(f"qbb-net-device.cc文件不存在: {qbb_file_path}")
    
    # 读取原文件
    with open(qbb_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 修改ENABLE_JUMP_TRANSITION宏定义
    if enable_mixed_granularity:
        content = re.sub(r'//\s*#define\s+ENABLE_JUMP_TRANSITION', '#define ENABLE_JUMP_TRANSITION', content)
        if '#define ENABLE_JUMP_TRANSITION' not in content:
            # 如果不存在，在第61行附近添加
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if i >= 60 and 'ENABLE_JUMP_TRANSITION' in line:
                    lines[i] = '#define ENABLE_JUMP_TRANSITION  // 启用跃迁功能'
                    break
            content = '\n'.join(lines)
    else:
        content = re.sub(r'#define\s+ENABLE_JUMP_TRANSITION', '// #define ENABLE_JUMP_TRANSITION', content)
    
    # 写回文件
    with open(qbb_file_path, 'w', encoding='utf-8') as f:
        f.write(content)

def run_simulation(simulation_id: str, task_num: int, llm_model: str, 
                  enable_mixed_granularity: bool, simulation_time: float):
    """运行仿真（后台任务）"""
    try:
        # 修改配置文件
        modify_sim_script(task_num, llm_model)
        modify_qbb_device(enable_mixed_granularity)
        
        # 切换到Reverie目录
        reverie_dir = Path(__file__).parent.parent
        
        # 设置运行状态
        simulation_status.is_running = True
        simulation_status.current_task = simulation_id
        simulation_status.simulation_start_time = time.time()
        
        # 使用Popen启动仿真进程（非阻塞）
        sim_script_path = reverie_dir / "sim.sh"
        
        # 启动仿真进程
        process = subprocess.Popen(
            ['bash', str(sim_script_path)],
            cwd=str(reverie_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 保存进程信息
        simulation_status.current_process = process
        
        # 等待进程完成（在后台任务中）
        stdout, stderr = process.communicate(timeout=simulation_time * 2)
        
        # 仿真完成
        simulation_status.simulation_end_time = time.time()
        simulation_status.is_running = False
        simulation_status.current_process = None
        
        # 分析结果
        results = analyze_simulation_results()
        simulation_status.results[simulation_id] = results
        
        print(f"仿真完成: {simulation_id}, 耗时: {simulation_status.simulation_end_time - simulation_status.simulation_start_time:.2f}秒")
        
        return {
            "success": True,
            "simulation_id": simulation_id,
            "execution_time": simulation_status.simulation_end_time - simulation_status.simulation_start_time,
            "results": results,
            "stdout": stdout,
            "stderr": stderr
        }
        
    except subprocess.TimeoutExpired:
        simulation_status.is_running = False
        simulation_status.current_process = None
        return {
            "success": False,
            "error": "仿真超时",
            "simulation_id": simulation_id
        }
    except Exception as e:
        simulation_status.is_running = False
        simulation_status.current_process = None
        print(f"仿真出错: {e}")
        return {
            "success": False,
            "error": str(e),
            "simulation_id": simulation_id
        }

def analyze_simulation_results():
    """分析仿真结果"""
    results = {
        "fct_results": {},
        "steady_state_info": {},
        "performance_metrics": {}
    }
    
    try:
        # 分析FCT结果
        fct_file = Path(__file__).parent.parent / "dump" / "evaluation.fct1"
        if fct_file.exists():
            with open(fct_file, 'r') as f:
                fct_content = f.read()
            results["fct_results"] = parse_fct_results(fct_content)
        
        # 分析系统日志
        log_file = Path(__file__).parent.parent / "dump" / "system1.log"
        if log_file.exists():
            with open(log_file, 'r') as f:
                log_content = f.read()
            results["steady_state_info"] = parse_steady_state_info(log_content)
            results["performance_metrics"] = parse_performance_metrics(log_content)
        
        # 分析流统计
        flow_stats_file = Path(__file__).parent.parent / "flow_stats.txt"
        if flow_stats_file.exists():
            with open(flow_stats_file, 'r') as f:
                flow_content = f.read()
            results["flow_statistics"] = parse_flow_statistics(flow_content)
    
    except Exception as e:
        results["analysis_error"] = str(e)
    
    return results

def parse_fct_results(content):
    """解析FCT结果"""
    # 这里需要根据实际的FCT文件格式来解析
    return {"raw_content": content[:1000]}  # 返回前1000个字符作为示例

def parse_steady_state_info(content):
    """解析稳态信息"""
    steady_state_entries = []
    for line in content.split('\n'):
        if 'steady state' in line.lower() or '稳态' in line:
            steady_state_entries.append(line.strip())
    return {
        "entries": steady_state_entries,
        "count": len(steady_state_entries)
    }

def parse_performance_metrics(content):
    """解析性能指标"""
    metrics = {}
    for line in content.split('\n'):
        if 'Rate:' in line and 'Gbps' in line:
            # 提取速率信息
            rate_match = re.search(r'Rate:\s*([\d.]+)\s*Gbps', line)
            if rate_match:
                metrics.setdefault('rates', []).append(float(rate_match.group(1)))
    return metrics

def parse_flow_statistics(content):
    """解析流统计信息"""
    flows = []
    for line in content.split('\n'):
        if 'Flow ID:' in line:
            flows.append(line.strip())
    return {
        "flow_count": len(flows),
        "flows": flows[:10]  # 返回前10个流作为示例
    }

@app.post("/run-simulation", response_model=SimulationResponse)
async def run_simulation_endpoint(request: SimulationRequest, background_tasks: BackgroundTasks):
    """运行仿真"""
    if simulation_status.is_running:
        raise HTTPException(status_code=400, detail="仿真正在运行中，请等待完成")
    
    if request.task_num not in [1, 4]:
        raise HTTPException(status_code=400, detail="task_num必须是1或4")
    
    simulation_id = f"sim_{int(time.time())}"
    
    # 在后台运行仿真
    background_tasks.add_task(
        run_simulation,
        simulation_id,
        request.task_num,
        request.llm_model,
        request.enable_mixed_granularity,
        request.simulation_time
    )
    
    return SimulationResponse(
        success=True,
        message=f"仿真已启动，ID: {simulation_id}",
        simulation_id=simulation_id,
        status="running",
        results={}
    )

# ==================== 状态监控接口 ====================

class StatusResponse(BaseModel):
    is_running: bool
    current_task: Optional[str]
    steady_state: bool
    simulation_time: Optional[float]
    results: Dict[str, Any]

@app.get("/simulation-status", response_model=StatusResponse)
async def get_simulation_status():
    """获取仿真状态"""
    simulation_time = None
    if simulation_status.simulation_start_time and simulation_status.simulation_end_time:
        simulation_time = simulation_status.simulation_end_time - simulation_status.simulation_start_time
    elif simulation_status.simulation_start_time:
        simulation_time = time.time() - simulation_status.simulation_start_time
    
    return StatusResponse(
        is_running=simulation_status.is_running,
        current_task=simulation_status.current_task,
        steady_state=simulation_status.steady_state,
        simulation_time=simulation_time,
        results=simulation_status.results
    )


# ==================== 稳态监控功能（基于已有实现） ====================

# 稳态状态管理类
class SteadyStateMonitor:
    """稳态状态管理类（基于qbb-net-device.cc的日志输出）"""
    def __init__(self):
        self.is_monitoring = False
        self.is_in_steady_state = False
        self.steady_state_count = 0
        self.steady_state_history = []
        self.last_check_time = None
        self.last_log_position = 0
        
    def reset(self):
        """重置状态"""
        self.is_monitoring = False
        self.is_in_steady_state = False
        self.steady_state_count = 0
        self.steady_state_history = []
        self.last_check_time = None
        self.last_log_position = 0

steady_state_monitor = SteadyStateMonitor()

def parse_steady_state_from_log(log_file: Path, last_position: int = 0) -> tuple:
    """
    从日志文件中解析稳态信息（基于qbb-net-device.cc的输出）
    
    参数:
        log_file: 日志文件路径
        last_position: 上次读取的文件位置
    
    返回:
        (is_steady, steady_time, new_position, exit_detected)
    """
    if not log_file.exists():
        return False, None, last_position, False
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            # 从上次读取的位置开始
            f.seek(last_position)
            new_content = f.read()
            new_position = f.tell()
            
            if not new_content:
                return False, None, last_position, False
            
            # 检查是否进入稳态（基于qbb-net-device.cc的输出格式）
            steady_pattern = r"System entered steady state at time:\s+(\d+(?:\.\d+)?)\s*ns"
            steady_match = re.search(steady_pattern, new_content)
            
            # 检查是否退出稳态
            exit_pattern = r"System exit"
            exit_match = re.search(exit_pattern, new_content)
            
            is_steady = steady_match is not None
            steady_time = float(steady_match.group(1)) if is_steady else None
            exit_detected = exit_match is not None
            
            return is_steady, steady_time, new_position, exit_detected
            
    except Exception as e:
        print(f"解析日志文件时出错: {e}")
        return False, None, last_position, False

@app.post("/start-steady-state-monitor")
async def start_steady_state_monitor():
    """启动稳态监控（基于qbb-net-device.cc的实现）"""
    if steady_state_monitor.is_monitoring:
        return {
            "success": False,
            "message": "监控已在运行中"
        }
    
    steady_state_monitor.reset()
    steady_state_monitor.is_monitoring = True
    
    return {
        "success": True,
        "message": "稳态监控已启动",
        "monitoring": True
    }

@app.post("/stop-steady-state-monitor")
async def stop_steady_state_monitor():
    """停止稳态监控"""
    steady_state_monitor.is_monitoring = False
    
    # 保存历史记录
    dump_dir = Path(__file__).parent.parent / "dump"
    dump_dir.mkdir(parents=True, exist_ok=True)
    history_file = dump_dir / "steady_state_history.json"
    
    import json
    with open(history_file, 'w', encoding='utf-8') as f:
        json.dump({
            "stop_time": time.time(),
            "total_count": steady_state_monitor.steady_state_count,
            "history": steady_state_monitor.steady_state_history
        }, f, indent=2, ensure_ascii=False)
    
    return {
        "success": True,
        "message": "稳态监控已停止",
        "total_count": steady_state_monitor.steady_state_count,
        "history_saved": str(history_file)
    }

@app.get("/steady-state-monitor")
async def get_steady_state_status():
    """
    获取稳态状态（基于qbb-net-device.cc输出的evaluation.out日志）
    这是实时读取日志文件来判断稳态的接口
    """
    # 日志文件路径
    evaluation_out = Path(__file__).parent.parent / "dump" / "evaluation.out"
    
    # 如果正在监控，实时检查日志
    if steady_state_monitor.is_monitoring:
        is_steady, steady_time, new_position, exit_detected = parse_steady_state_from_log(
            evaluation_out,
            steady_state_monitor.last_log_position
        )
        steady_state_monitor.last_log_position = new_position
        
        # 检测到进入稳态
        if is_steady and not steady_state_monitor.is_in_steady_state:
            steady_state_monitor.is_in_steady_state = True
            steady_state_monitor.steady_state_count += 1
            
            # 记录稳态历史
            steady_record = {
                "count": steady_state_monitor.steady_state_count,
                "enter_time_ns": steady_time,
                "detected_at": time.time(),
                "status": "entered"
            }
            steady_state_monitor.steady_state_history.append(steady_record)
            simulation_status.steady_state = True
        
        # 检测到退出稳态
        if exit_detected and steady_state_monitor.is_in_steady_state:
            steady_state_monitor.is_in_steady_state = False
            if steady_state_monitor.steady_state_history:
                steady_state_monitor.steady_state_history[-1]["status"] = "exited"
            simulation_status.steady_state = False
    
    # 生成状态消息
    if not steady_state_monitor.is_monitoring:
        message = "监控未启动"
    elif steady_state_monitor.is_in_steady_state:
        message = f"系统处于稳态加速模式（第{steady_state_monitor.steady_state_count}次）"
    else:
        message = "监控中，等待进入稳态..."
    
    return {
        "is_monitoring": steady_state_monitor.is_monitoring,
        "is_steady": steady_state_monitor.is_in_steady_state,
        "is_in_steady_state": steady_state_monitor.is_in_steady_state,
        "steady_state_count": steady_state_monitor.steady_state_count,
        "timestamp": time.time(),
        "message": message,
        "details": [h.get("enter_time_ns") for h in steady_state_monitor.steady_state_history],
        "history": steady_state_monitor.steady_state_history
    }

@app.get("/steady-state-history")
async def get_steady_state_history():
    """获取稳态历史记录"""
    return {
        "success": True,
        "total_count": steady_state_monitor.steady_state_count,
        "history": steady_state_monitor.steady_state_history
    }

# ==================== 负载文件修改接口 ====================

class LoadFileModifyRequest(BaseModel):
    filename: str = "deepseek.txt"
    old_value: str = "128"
    new_value: str = "64"

class LoadFileModifyResponse(BaseModel):
    success: bool
    message: str
    modified_lines: List[str]

@app.post("/modify-load-file", response_model=LoadFileModifyResponse)
async def modify_load_file(request: LoadFileModifyRequest):
    """修改负载文件中的参数"""
    try:
        file_path = Path(__file__).parent.parent / "TrafficGenerator" / request.filename
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"文件不存在: {request.filename}")
        
        # 读取文件
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        modified_lines = []
        changes_count = 0
        
        # 修改文件内容
        for i, line in enumerate(lines):
            if request.old_value in line:
                new_line = line.replace(request.old_value, request.new_value)
                lines[i] = new_line
                modified_lines.append(f"Line {i+1}: {line.strip()} -> {new_line.strip()}")
                changes_count += 1
        
        # 写回文件
        with open(file_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        return LoadFileModifyResponse(
            success=True,
            message=f"成功修改文件，共修改了{changes_count}处",
            modified_lines=modified_lines
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"修改文件时出错: {str(e)}")

# ==================== 结果分析接口 ====================

class AnalysisRequest(BaseModel):
    simulation_id: Optional[str] = None
    analysis_type: str = "all"  # all, fct, steady_state, performance

class AnalysisResponse(BaseModel):
    success: bool
    analysis_type: str
    results: Dict[str, Any]
    summary: str

@app.post("/analyze-results", response_model=AnalysisResponse)
async def analyze_results(request: AnalysisRequest):
    """分析仿真结果"""
    try:
        results = {}
        file_status = {}
        
        if request.analysis_type in ["all", "fct"]:
            # 分析FCT结果
            fct_file = Path(__file__).parent.parent / "dump" / "evaluation.fct1"
            file_status["fct_file"] = str(fct_file)
            file_status["fct_exists"] = fct_file.exists()
            
            if fct_file.exists():
                try:
                    with open(fct_file, 'r', encoding='utf-8') as f:
                        fct_content = f.read()
                    results["fct_analysis"] = analyze_fct_metrics(fct_content)
                    results["fct_analysis"]["file_found"] = True
                except Exception as e:
                    results["fct_analysis"] = {
                        "error": f"读取FCT文件失败: {str(e)}",
                        "file_found": True,
                        "total_flows": 0
                    }
            else:
                results["fct_analysis"] = {
                    "error": f"FCT文件不存在，请先运行仿真",
                    "file_path": str(fct_file),
                    "file_found": False,
                    "total_flows": 0
                }
        
        if request.analysis_type in ["all", "steady_state"]:
            # 分析稳态信息（使用evaluation.out而不是flow_stats.txt）
            evaluation_out = Path(__file__).parent.parent / "dump" / "evaluation.out"
            file_status["steady_file"] = str(evaluation_out)
            file_status["steady_exists"] = evaluation_out.exists()
            
            if evaluation_out.exists():
                try:
                    with open(evaluation_out, 'r', encoding='utf-8', errors='ignore') as f:
                        log_content = f.read()
                    results["steady_state_analysis"] = analyze_steady_state_from_evaluation(log_content)
                    results["steady_state_analysis"]["file_found"] = True
                except Exception as e:
                    results["steady_state_analysis"] = {
                        "error": f"读取稳态文件失败: {str(e)}",
                        "file_found": True
                    }
            else:
                results["steady_state_analysis"] = {
                    "error": f"稳态日志文件不存在，请先运行仿真",
                    "file_path": str(evaluation_out),
                    "file_found": False
                }
        
        if request.analysis_type in ["all", "performance"]:
            # 分析性能指标
            log_file = Path(__file__).parent.parent / "dump" / "system1.log"
            file_status["perf_file"] = str(log_file)
            file_status["perf_exists"] = log_file.exists()
            
            if log_file.exists():
                try:
                    with open(log_file, 'r', encoding='utf-8') as f:
                        log_content = f.read()
                    results["performance_analysis"] = analyze_performance(log_content)
                    results["performance_analysis"]["file_found"] = True
                except Exception as e:
                    results["performance_analysis"] = {
                        "error": f"读取性能文件失败: {str(e)}",
                        "file_found": True
                    }
            else:
                results["performance_analysis"] = {
                    "error": f"性能日志文件不存在，请先运行仿真",
                    "file_path": str(log_file),
                    "file_found": False
                }
        
        # 添加文件状态信息
        results["file_status"] = file_status
        
        # 生成总结
        summary = generate_analysis_summary(results)
        
        return AnalysisResponse(
            success=True,
            analysis_type=request.analysis_type,
            results=results,
            summary=summary
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析结果时出错: {str(e)}")

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
    data_lines = lines[1:]
    total_flows = len(data_lines)
    
    fct_values = []
    flow_sizes = []
    slowdowns = []
    
    for line in data_lines:
        parts = line.split()
        if len(parts) >= 5:
            try:
                fct_us = float(parts[2])  # fctus列
                flow_size = float(parts[1])  # flowsize列
                slowdown = float(parts[4])  # slowdown列
                fct_values.append(fct_us)
                flow_sizes.append(flow_size)
                slowdowns.append(slowdown)
            except ValueError:
                continue
    
    if not fct_values:
        return {
            "total_flows": 0,
            "average_fct": 0.0,
            "fct_distribution": {}
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

def analyze_steady_state(content):
    """分析稳态信息（flow_stats.txt）"""
    steady_entries = []
    for line in content.split('\n'):
        if 'steady state' in line.lower() or '稳态' in line:
            steady_entries.append(line.strip())
    
    return {
        "steady_state_count": len(steady_entries),
        "steady_state_entries": steady_entries,
        "is_system_steady": len(steady_entries) > 0
    }

def analyze_steady_state_from_evaluation(content):
    """分析稳态信息（evaluation.out日志）"""
    steady_entries = []
    steady_times = []
    
    # 匹配稳态进入信息
    pattern = r"System entered steady state at time:\s+(\d+(?:\.\d+)?)\s*ns"
    
    for line in content.split('\n'):
        if 'steady state' in line.lower():
            steady_entries.append(line.strip())
            # 提取时间
            match = re.search(pattern, line)
            if match:
                steady_times.append(float(match.group(1)))
    
    return {
        "steady_state_count": len(steady_times),
        "steady_state_entries": steady_entries[:10],  # 只返回前10条
        "steady_times_ns": steady_times,
        "is_system_steady": len(steady_times) > 0,
        "total_entries": len(steady_entries)
    }

def analyze_performance(content):
    """分析性能指标（基于system1.log的实际格式）"""
    lines = content.split('\n')
    
    # 提取系统配置信息
    server_count = 0
    leaf_count = 0
    spine_count = 0
    link_count = 0
    flow_count = 0
    flow_sizes = []
    
    for line in lines:
        # 提取网络拓扑信息
        if 'SERVER_COUNT' in line:
            match = re.search(r'SERVER_COUNT\s+(\d+)', line)
            if match:
                server_count = int(match.group(1))
            match = re.search(r'LEAF_COUNT\s+(\d+)', line)
            if match:
                leaf_count = int(match.group(1))
            match = re.search(r'SPINE_COUNT\s+(\d+)', line)
            if match:
                spine_count = int(match.group(1))
            match = re.search(r'LINK_COUNT\s+(\d+)', line)
            if match:
                link_count = int(match.group(1))
        
        # 提取流信息
        if 'system' in line and 'flowsize' in line:
            flow_count += 1
            # 提取流大小
            size_match = re.search(r'flowsize\s+(\d+)', line)
            if size_match:
                flow_sizes.append(int(size_match.group(1)))
    
    # 计算统计信息
    result = {
        "has_data": True,
        "file_size": len(content),
        "total_lines": len(lines),
        "network_config": {
            "server_count": server_count,
            "leaf_count": leaf_count,
            "spine_count": spine_count,
            "link_count": link_count
        },
        "flow_statistics": {
            "total_flows": flow_count,
            "unique_flow_sizes": len(set(flow_sizes)),
            "average_flow_size_bytes": sum(flow_sizes) / len(flow_sizes) if flow_sizes else 0,
            "average_flow_size_MB": (sum(flow_sizes) / len(flow_sizes) / (1024*1024)) if flow_sizes else 0,
            "total_data_MB": sum(flow_sizes) / (1024*1024) if flow_sizes else 0
        }
    }
    
    # 如果没有提取到任何有用信息
    if flow_count == 0 and server_count == 0:
        result["has_data"] = False
        result["error"] = "system1.log中未找到流信息或网络配置"
        result["suggestion"] = "请先运行ns3仿真，或检查evaluation.fct1文件"
    
    return result

def generate_analysis_summary(results):
    """生成分析总结"""
    summary_parts = []
    
    if "fct_analysis" in results:
        fct = results["fct_analysis"]
        if fct.get("file_found"):
            if fct.get('total_flows', 0) > 0:
                summary_parts.append(f"FCT分析: 总流数={fct.get('total_flows', 0)}, 平均FCT={fct.get('average_fct_us', 0):.2f}μs")
            else:
                summary_parts.append(f"FCT分析: 文件已找到但数据为空")
        else:
            summary_parts.append(f"FCT分析: {fct.get('error', '文件未找到')}")
    
    if "steady_state_analysis" in results:
        steady = results["steady_state_analysis"]
        if steady.get("file_found"):
            if steady.get('is_system_steady', False):
                summary_parts.append(f"稳态分析: 进入稳态{steady.get('steady_state_count', 0)}次")
            else:
                summary_parts.append(f"稳态分析: 未检测到稳态")
        else:
            summary_parts.append(f"稳态分析: {steady.get('error', '文件未找到')}")
    
    if "performance_analysis" in results:
        perf = results["performance_analysis"]
        if perf.get("has_data"):
            flow_stats = perf.get("flow_statistics", {})
            net_config = perf.get("network_config", {})
            summary_parts.append(
                f"系统分析: {net_config.get('server_count', 0)}服务器, "
                f"{flow_stats.get('total_flows', 0)}个流, "
                f"平均流大小{flow_stats.get('average_flow_size_MB', 0):.2f}MB"
            )
        else:
            summary_parts.append(f"性能分析: {perf.get('error', '无数据')}")
    
    return "; ".join(summary_parts) if summary_parts else "暂无仿真结果，请先运行仿真"

# ==================== 通用接口 ====================

@app.get("/")
async def root():
    """根路径，返回API信息"""
    return {
        "message": "Complete Network Simulation API",
        "version": "2.0.0",
        "endpoints": {
            "POST /tree-cut": "拓扑切分",
            "POST /generate-load": "生成网络负载配置",
            "POST /generate-topology": "生成网络拓扑",
            "POST /visualize-topology": "生成拓扑可视化图片",
            "GET /get-topology-image": "获取拓扑可视化图片",
            "POST /run-simulation": "运行仿真（支持切分和混合粒度开关）",
            "POST /stop-simulation": "停止仿真",
            "GET /simulation-status": "获取仿真状态",
            "POST /start-steady-state-monitor": "启动稳态监控（基于qbb-net-device.cc）",
            "POST /stop-steady-state-monitor": "停止稳态监控",
            "GET /steady-state-monitor": "获取稳态状态（读取evaluation.out日志）",
            "GET /steady-state-history": "获取稳态历史记录",
            "POST /modify-load-file": "修改负载文件",
            "POST /analyze-results": "分析仿真结果",
            "GET /read-file": "读取文件内容",
            "GET /list-files": "列出目录文件",
            "GET /health": "健康检查",
            "GET /docs": "API文档"
        }
    }

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy", 
        "message": "API服务正常运行",
        "simulation_running": simulation_status.is_running,
        "steady_state": simulation_status.steady_state
    }

# ==================== 文件访问接口 ====================

from fastapi.responses import FileResponse, JSONResponse
import mimetypes

@app.get("/read-file")
async def read_file(file_path: str):
    """读取文件内容"""
    try:
        # 安全检查：确保文件路径在项目目录内
        base_dir = Path(__file__).parent.parent
        
        # 清理路径（去除前导/后导斜杠，处理各种格式）
        file_path = file_path.strip().strip('/').strip('\\')
        
        # 构建完整路径
        full_path = (base_dir / file_path).resolve()
        
        print(f"[DEBUG] 读取文件: {file_path}")
        print(f"[DEBUG] 基础目录: {base_dir}")
        print(f"[DEBUG] 完整路径: {full_path}")
        print(f"[DEBUG] 文件存在: {full_path.exists()}")
        
        # 安全检查
        try:
            if not str(full_path).startswith(str(base_dir)):
                raise HTTPException(status_code=403, detail=f"禁止访问此路径: {file_path}")
        except:
            # Windows路径比较可能失败，尝试替代方法
            pass
        
        if not full_path.exists():
            # 尝试检查是否是目录
            if full_path.is_dir():
                raise HTTPException(status_code=400, detail=f"这是一个目录，不是文件: {file_path}")
            raise HTTPException(status_code=404, detail=f"文件不存在: {file_path}, 完整路径: {full_path}")
        
        # 检查是否是目录
        if full_path.is_dir():
            raise HTTPException(status_code=400, detail=f"这是一个目录，请使用/list-files接口")
        
        # 读取文件内容
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return {
                "success": True,
                "file_path": file_path,
                "full_path": str(full_path),
                "content": content,
                "size": len(content),
                "encoding": "utf-8"
            }
        except UnicodeDecodeError:
            # 如果是二进制文件，返回base64编码
            with open(full_path, 'rb') as f:
                import base64
                binary_content = f.read()
                content = base64.b64encode(binary_content).decode()
            return {
                "success": True,
                "file_path": file_path,
                "full_path": str(full_path),
                "content": content,
                "encoding": "base64",
                "size": len(binary_content)
            }
            
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] 读取文件失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"读取文件时出错: {str(e)}")

@app.get("/list-files")
async def list_files(directory: str = "."):
    """列出目录中的文件"""
    try:
        base_dir = Path(__file__).parent.parent
        full_path = (base_dir / directory).resolve()
        
        if not str(full_path).startswith(str(base_dir)):
            raise HTTPException(status_code=403, detail="禁止访问此路径")
        
        if not full_path.exists():
            raise HTTPException(status_code=404, detail=f"目录不存在: {directory}")
        
        files = []
        for item in full_path.iterdir():
            files.append({
                "name": item.name,
                "path": str(item.relative_to(base_dir)),
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else 0
            })
        
        return {
            "success": True,
            "directory": directory,
            "files": files
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"列出文件时出错: {str(e)}")

# ==================== 拓扑可视化接口 ====================

@app.post("/visualize-topology")
async def visualize_topology(background_tasks: BackgroundTasks):
    """生成拓扑可视化图片"""
    try:
        # 导入拓扑可视化模块
        from api.topology_visualization import draw_improved_topology
        
        # 拓扑文件路径
        topology_file = Path(__file__).parent.parent / "leaf-spine.txt"
        
        if not topology_file.exists():
            raise HTTPException(status_code=404, detail="拓扑文件不存在，请先生成拓扑")
        
        # 生成图片
        output_file = Path(__file__).parent / "topology_latest.png"
        draw_improved_topology(topology_file, output_file)
        
        return {
            "success": True,
            "message": "拓扑可视化生成成功",
            "image_path": "api/topology_latest.png"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成拓扑可视化时出错: {str(e)}")

@app.get("/get-topology-image")
async def get_topology_image():
    """获取拓扑可视化图片"""
    try:
        image_file = Path(__file__).parent / "topology_latest.png"
        
        if not image_file.exists():
            raise HTTPException(status_code=404, detail="拓扑图片不存在，请先生成")
        
        return FileResponse(image_file, media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取图片时出错: {str(e)}")

# ==================== 仿真停止接口 ====================

@app.post("/stop-simulation")
async def stop_simulation():
    """停止仿真"""
    try:
        if not simulation_status.is_running:
            return {
                "success": True,
                "message": "当前没有运行中的仿真"
            }
        
        # 终止仿真进程
        if simulation_status.current_process:
            try:
                simulation_status.current_process.terminate()
                simulation_status.current_process.wait(timeout=5)
                print(f"仿真进程已终止: {simulation_status.current_task}")
            except:
                simulation_status.current_process.kill()
                print(f"仿真进程已强制终止: {simulation_status.current_task}")
        
        simulation_status.is_running = False
        simulation_status.current_process = None
        
        return {
            "success": True,
            "message": "仿真已停止"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止仿真时出错: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
