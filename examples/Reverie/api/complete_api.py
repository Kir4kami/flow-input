#!/usr/bin/env python3
# 完整的六功能汇总API接口文件
# 包含：拓扑切分、负载设置、拓扑设置、仿真控制、混合粒度控制、结果分析

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse, Response
from pydantic import BaseModel
import os
import sys
import subprocess
import json
import time
import shutil
import re
import math
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple, Set
import threading
import asyncio
from datetime import datetime
import hashlib
import zipfile
import tempfile

# 路径解析：优先使用环境变量，其次基于当前文件自动定位
def _detect_reverie_root() -> Path:
    env_reverie_root = os.getenv("REVERIE_ROOT")
    if env_reverie_root:
        candidate = Path(env_reverie_root).expanduser().resolve()
        if (candidate / "api").exists():
            return candidate
        print(f"[WARN] REVERIE_ROOT 无效，未找到 api 目录: {candidate}")

    try:
        return Path(__file__).resolve().parent.parent
    except Exception:
        cwd = Path.cwd().resolve()
        if (cwd / "api").exists() and (cwd / "sim.sh").exists():
            return cwd
        if (cwd / "examples" / "Reverie").exists():
            return (cwd / "examples" / "Reverie").resolve()
        raise RuntimeError("无法定位 Reverie 根目录，请设置环境变量 REVERIE_ROOT")


REVERIE_ROOT = _detect_reverie_root()
API_DIR = REVERIE_ROOT / "api"
PROJECT_ROOT = REVERIE_ROOT.parent.parent
SRC_ROOT = PROJECT_ROOT / "src"

if str(REVERIE_ROOT) not in sys.path:
    sys.path.insert(0, str(REVERIE_ROOT))
# 若 venv 无 matplotlib，添加系统路径（TreeCut 依赖）
try:
    import matplotlib.pyplot as plt
except ImportError:
    sys.path.insert(0, '/usr/lib/python3/dist-packages')
    import matplotlib.pyplot as plt
from TreeCut.TreeCut import performTreeCut, visualize3DSplitTreeHTML
import networkx as nx
import copy
from collections import defaultdict

# 添加TreeCut下ECMP脚本路径
ECMP_MODULE_ROOT = REVERIE_ROOT / "Generator" / "Generator" / "TreeCut"
if ECMP_MODULE_ROOT.exists():
    sys.path.append(str(ECMP_MODULE_ROOT))

try:
    from ecmp_path import get_rdma_files as ecmp_get_rdma_files, load_file as ecmp_load_file, find_ecmp_path as ecmp_find_paths
except Exception:
    ecmp_get_rdma_files = None
    ecmp_load_file = None
    ecmp_find_paths = None

ECMP_CACHE_FILE = API_DIR / "ecmp_paths_cache.json"
ECMP_CACHE_LOCK = threading.Lock()

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

class BaselineStatus:
    def __init__(self):
        self.is_running = False
        self.last_started = None
        self.last_finished = None


baseline_status = BaselineStatus()

# ==================== TreeCut 完整功能实现 ====================

# 根节点
root_node = 'Root'

# 切割后树的列表集合
Tree_list = []

# 切分树组数量（0表示自动切分）
TASK_NUM = 0

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
    cut_tree.add_node(root_node, name='Root')
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
    
    # 删除旧的group子目录，避免与新结果混淆
    import glob
    old_group_dirs = glob.glob(os.path.join(target_directory, "group*"))
    for old_dir in old_group_dirs:
        if os.path.isdir(old_dir):
            try:
                import shutil
                shutil.rmtree(old_dir)
                print(f"[INFO] 已删除旧目录: {os.path.basename(old_dir)}")
            except Exception as e:
                print(f"[WARNING] 删除旧目录失败: {old_dir}, 错误: {e}")
    
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
        node_dict = {"name": node}  # 使用节点id作为name，保证Root等显示一致
        # 只保留可序列化的数据（不覆盖name，避免data中的name覆盖节点id）
        for key, value in data.items():
            if key == "name":
                continue
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
    import glob
    
    # 确保输出目录存在
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 删除旧的树组JSON文件，避免与新结果混淆
    old_tree_files = glob.glob(os.path.join(output_dir, "tree_group_*.json"))
    for old_file in old_tree_files:
        try:
            os.remove(old_file)
            print(f"[INFO] 已删除旧文件: {os.path.basename(old_file)}")
        except Exception as e:
            print(f"[WARNING] 删除旧文件失败: {old_file}, 错误: {e}")
    
    # 删除旧的overview文件
    old_overview = os.path.join(output_dir, "tree_group_overview.json")
    if os.path.exists(old_overview):
        try:
            os.remove(old_overview)
            print(f"[INFO] 已删除旧的overview文件")
        except Exception as e:
            print(f"[WARNING] 删除旧overview文件失败: {e}")
    
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

def adjustTreeGroupCount(tree_list, target_count):
    """
    调整树组数量以匹配目标数量
    
    Args:
        tree_list: 当前的树组列表
        target_count: 目标树组数量
    
    Returns:
        调整后的树组列表（新列表）
    """
    import networkx as nx
    import copy
    
    # 创建副本，避免修改原列表
    tree_list = copy.copy(tree_list)
    
    current_count = len(tree_list)
    
    print(f"[INFO] 当前树组数量: {current_count}, 目标数量: {target_count}")
    
    # 如果已经匹配，直接返回
    if current_count == target_count:
        return tree_list
    
    # 如果当前数量少于目标，需要进一步切分
    while len(tree_list) < target_count:
        # 找到节点数最多的树组
        max_size = 0
        max_index = 0
        for i, tree in enumerate(tree_list):
            size = tree.number_of_nodes()
            if size > max_size and size > 1:  # 只切分节点数>1的树
                max_size = size
                max_index = i
        
        # 如果所有树都只有1个节点，无法继续切分
        if max_size <= 1:
            print(f"[WARNING] 无法继续切分，当前树组数量: {len(tree_list)}")
            break
        
        # 切分最大的树
        tree_to_split = tree_list[max_index]
        
        # 简单切分：找到所有叶节点，分成两组
        leaves = [node for node in tree_to_split.nodes() if tree_to_split.out_degree(node) == 0]
        if len(leaves) <= 1:
            # 如果叶节点<=1，找所有节点
            all_nodes = list(tree_to_split.nodes())
            if len(all_nodes) <= 1:
                print(f"[WARNING] 树组{max_index}只有1个节点，无法切分")
                break
            leaves = all_nodes
        
        # 分成两半
        mid = len(leaves) // 2
        group1_leaves = leaves[:mid]
        group2_leaves = leaves[mid:]
        
        # 创建两个新树
        tree1 = nx.DiGraph()
        tree2 = nx.DiGraph()
        
        # 将节点分配到两个树中（包括所有祖先节点）
        def get_ancestors(graph, nodes):
            """获取所有节点的祖先节点"""
            ancestors = set(nodes)
            for node in nodes:
                for ancestor in nx.ancestors(graph, node):
                    ancestors.add(ancestor)
            return ancestors
        
        group1_nodes = get_ancestors(tree_to_split, group1_leaves)
        group2_nodes = get_ancestors(tree_to_split, group2_leaves)
        
        for node in tree_to_split.nodes():
            node_data = dict(tree_to_split.nodes[node])
            if node in group1_nodes:
                tree1.add_node(node, **node_data)
            if node in group2_nodes:
                tree2.add_node(node, **node_data)
        
        # 复制边
        for u, v in tree_to_split.edges():
            if tree1.has_node(u) and tree1.has_node(v):
                tree1.add_edge(u, v, **tree_to_split.edges[u, v])
            if tree2.has_node(u) and tree2.has_node(v):
                tree2.add_edge(u, v, **tree_to_split.edges[u, v])
        
        # 如果切分成功（两个树都非空）
        if tree1.number_of_nodes() > 0 and tree2.number_of_nodes() > 0:
            tree_list[max_index] = tree1
            tree_list.append(tree2)
            print(f"[INFO] 已切分树组{max_index}，当前树组数量: {len(tree_list)}")
        else:
            print(f"[WARNING] 切分失败，无法继续")
            break
    
    # 如果当前数量多于目标，需要合并
    while len(tree_list) > target_count:
        # 找到两个最小的树组并合并
        sizes = [(i, tree.number_of_nodes()) for i, tree in enumerate(tree_list)]
        sizes.sort(key=lambda x: x[1])
        
        if len(sizes) < 2:
            break
        
        idx1, idx2 = sizes[0][0], sizes[1][0]
        
        # 确保idx1 < idx2，方便删除
        if idx1 > idx2:
            idx1, idx2 = idx2, idx1
        
        # 合并两个树
        merged_tree = nx.compose(tree_list[idx1], tree_list[idx2])
        
        # 先删除索引大的，再删除索引小的，避免索引变化
        del tree_list[idx2]
        del tree_list[idx1]
        tree_list.append(merged_tree)
        print(f"[INFO] 已合并树组{idx1}和{idx2}，当前树组数量: {len(tree_list)}")
    
    final_count = len(tree_list)
    print(f"[INFO] 最终树组数量: {final_count}")
    
    # 验证返回的列表
    if final_count == 0:
        print(f"[ERROR] 返回的tree_list为空！这是一个BUG！")
    
    return tree_list

# 主要的拓扑切分函数（完整版本）
def performTreeCutComplete(tree_data=None, output_dir="TreeGroup", num_groups=0, show_graphs=False):
    """
    执行拓扑切分的主要函数（基于依赖分析的自动切分）
    
    Args:
        tree_data: 外部通信树数据，如果为None则使用默认构建方式
        output_dir: 输出目录，默认为"TreeGroup"
        num_groups: 保留参数（兼容性），实际只使用0（自动切分），不再支持强制指定数量
        show_graphs: 是否显示图形，默认为False
    
    切分算法：
        1. 预处理阶段 (PreTreatment):
           - 识别叶子节点（出度为0）
           - 标记"毛刺"节点（父节点出度为2的叶子节点）
           - 剪除无冲突的"毛刺"节点（路径信息无交集）
        
        2. 递归切割阶段 (SplitCommunicationTree):
           - 寻找从根节点出发的所有最长路径
           - 按父节点对路径末端节点分组
           - 单个子节点：检测冲突并决定剪除或合并
           - 多个子节点：批量合并到父节点
           - 递归处理直到只剩根节点
    
    Returns:
        dict: 包含切分结果的字典（保证依赖关系完整）
    """
    global Tree_list, out_dependence_list, TASK_NUM
    
    # 将output_dir转换为绝对路径（相对于API目录）
    if not os.path.isabs(output_dir):
        api_dir = API_DIR
        output_dir = str((api_dir / output_dir).resolve())
    
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
    
    # 保存原始通信树用于3D可视化
    original_tree_for_viz = copy.deepcopy(T)
    
    if show_graphs:
        ShowGraph(T)
    
    # 预处理
    T = preTreatment(T)
    Tree_copy = copy.deepcopy(T)
    
    # 执行切分（基于依赖分析的自动切分）
    splitCommunicationTree(T, Tree_copy)
    
    # 只使用自动切分，不再支持强制调整数量（避免破坏依赖关系）
    if num_groups > 0:
        print(f"[WARNING] 忽略手动指定的切分数量({num_groups})，只使用基于依赖分析的自动切分")
        print(f"[WARNING] 强制调整数量可能破坏节点间的依赖关系，已禁用此功能")
    
    print(f"[INFO] 基于依赖分析的自动切分完成，最终树组数量: {len(Tree_list)}")
    print(f"[INFO] 切分算法已保证所有依赖关系完整，未被破坏")
    
    if show_graphs:
        for item in Tree_list:
            print(item.edges())
            ShowGraph(item)
    
    # 生成输出文件
    makeInDependenceInfo(Tree_list, output_dir)
    makeOutDependenceInfo(out_dependence_list, Tree_list, output_dir)
    
    # 保存TreeGroup为JSON文件
    json_overview = saveTreeGroupToJson(Tree_list, output_dir)
    
    # 生成3D分层可视化HTML（使用TreeCut中的可视化函数）
    viz_path_relative: Optional[str] = None
    try:
        os.makedirs(output_dir, exist_ok=True)
        viz_output_file = os.path.join(output_dir, "tree_split_3d.html")
        visualize3DSplitTreeHTML(original_tree_for_viz, Tree_list, viz_output_file)
        print(f"[INFO] 3D树组可视化HTML已生成: {viz_output_file}")
        
        api_dir_for_viz = API_DIR
        try:
            viz_path_relative = str(Path(viz_output_file).relative_to(api_dir_for_viz))
        except ValueError:
            viz_path_relative = viz_output_file
    except Exception as e:
        print(f"[WARNING] 3D树组可视化HTML生成失败: {e}")
        viz_path_relative = None
    
    # 返回结果（output_directory使用相对路径，相对于api目录）
    api_dir = API_DIR
    try:
        output_dir_relative = str(Path(output_dir).relative_to(api_dir))
    except ValueError:
        # 如果无法计算相对路径，使用原始值
        output_dir_relative = output_dir
    
    result = {
        "success": True,
        "tree_groups": len(Tree_list),
        "output_directory": output_dir_relative,
        "json_overview": json_overview,
        "tree_list": Tree_list,
        "out_dependence_list": out_dependence_list,
        "tree_split_3d_html": viz_path_relative,
    }
    
    return result

# ==================== 通信树解析接口 ====================
# 从模块二（负载）输出中解析通信树，不再重新运行 trafficGen

class GenerateTreeRequest(BaseModel):
    model: Optional[str] = None  # 保留兼容，不再使用
    load_source: Optional[str] = None  # "custom" 或 "generated"(trafficGen)，用于选择解析来源

class GenerateTreeResponse(BaseModel):
    success: bool
    message: str
    tree_file: Optional[str] = None
    tree_data: Optional[Dict[str, Any]] = None
    nodes_count: int = 0
    edges_count: int = 0
    rdma_root: Optional[str] = None  # rdma_result 绝对路径，用于 tree-cut 时计算真实 nodes_passed

def _find_communication_tree_json() -> tuple:
    """
    从模块二输出中查找 communication_tree_iter0.json。
    返回 (json_path, rdma_root_path)，未找到则 (None, None)。
    """
    base_dir = REVERIE_ROOT
    # 1. TrafficGenerator/rdma_result（模块二 qwen/deepseek 模式输出）
    traffic_gen_paths = [
        REVERIE_ROOT / "TrafficGenerator",
        REVERIE_ROOT.parent / "Generator" / "Generator" / "TrafficGenerator",
        REVERIE_ROOT / "Generator" / "Generator" / "TrafficGenerator",
    ]
    for tg in traffic_gen_paths:
        json_path = tg / "rdma_result" / "communication_tree_iter0.json"
        if json_path.exists():
            rdma_root = tg / "rdma_result"
            return json_path, rdma_root if rdma_root.exists() else None

    # 2. workflow_output 最新目录
    wf_output = REVERIE_ROOT / "Generator" / "Generator" / "workflow_output"
    if wf_output.exists():
        dirs = sorted([d for d in wf_output.iterdir() if d.is_dir()], key=lambda x: x.stat().st_mtime, reverse=True)
        for d in dirs[:5]:
            json_path = d / "2_traffic" / "rdma_result" / "communication_tree_iter0.json"
            if json_path.exists():
                rdma_root = d / "2_traffic" / "rdma_result"
                return json_path, rdma_root if rdma_root.exists() else None

    return None, None


def _build_communication_tree_from_custom_load(base_dir: Path) -> Tuple[Dict[str, Any], Path]:
    """
    从自定义负载（rdma_operate*.txt + dependence.txt）构建通信树。
    返回 (tree_data, rdma_root_path)。
    """
    rdma_root = base_dir / "rdma_result"
    if not rdma_root.exists():
        return None, None
    operate_dir = rdma_root / "task1"
    if not operate_dir.exists():
        operate_dir = rdma_root / "all_rdma_files"
    if not operate_dir.exists():
        return None, None
    operate_files = sorted(
        operate_dir.glob("rdma_operate*.txt"),
        key=lambda p: (int(re.search(r"(\d+)", p.name).group(1)) if re.search(r"(\d+)", p.name) else 0, p.name)
    )
    if not operate_files:
        return None, None
    dep_file = operate_dir / "dependence.txt"
    if not dep_file.exists():
        dep_file = base_dir / "dependence.txt"
    if not dep_file.exists():
        dep_file = base_dir / "task1" / "dependence.txt"
    deps: List[Tuple[int, int, int, int]] = []
    if dep_file.exists():
        with open(dep_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                m = re.match(r"(\d+)-(\d+):(\d+)-(\d+)", line)
                if m:
                    deps.append((int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))))
    nodes = [{"name": "Root", "type": "Root", "layer": 0, "nodes_passed": [], "children": [], "isBurr": False}]
    edges = []
    parent_of: Dict[int, int] = {}
    for start, end, p_start, p_end in deps:
        for i in range(start, end + 1):
            parent_of[i] = p_start
    for i in range(len(operate_files)):
        node_name = f"operate{i}"
        parent_name = "Root" if i not in parent_of else f"operate{parent_of[i]}"
        nodes.append({
            "name": node_name,
            "type": "OP",
            "layer": 0,  # 稍后按树深度计算
            "nodes_passed": [],
            "children": [],
            "isBurr": False
        })
        edges.append({"from_node": parent_name, "to_node": node_name})
    # 按树深度设置 layer，使可视化正确显示分支（同层节点并排）
    child_of: Dict[str, List[str]] = defaultdict(list)
    for e in edges:
        child_of[e["from_node"]].append(e["to_node"])
    depth_of: Dict[str, int] = {"Root": 0}
    queue = ["Root"]
    while queue:
        u = queue.pop(0)
        for v in child_of[u]:
            depth_of[v] = depth_of[u] + 1
            queue.append(v)
    for n in nodes:
        if n["name"] in depth_of:
            n["layer"] = depth_of[n["name"]]
    for n in nodes[1:]:
        children = [e["to_node"] for e in edges if e["from_node"] == n["name"]]
        n["children"] = children
    root_children = [e["to_node"] for e in edges if e["from_node"] == "Root"]
    nodes[0]["children"] = root_children
    tree_data = {"nodes": nodes, "edges": edges}
    return tree_data, rdma_root


@app.post("/generate-communication-tree", response_model=GenerateTreeResponse)
async def generate_communication_tree(request: GenerateTreeRequest):
    """
    从模块二（负载）输出中解析通信树。
    - load_source=custom: 从自定义负载（rdma_operate + dependence）构建
    - 否则: 从 trafficGen 的 communication_tree_iter0.json 读取
    """
    try:
        base_dir = REVERIE_ROOT
        load_source = (request.load_source or "").lower()

        if load_source == "custom":
            tree_data, rdma_root_path = _build_communication_tree_from_custom_load(REVERIE_ROOT)
            if tree_data is None:
                raise HTTPException(
                    status_code=404,
                    detail="未找到自定义负载。请先在第二步上传 ZIP 并解析生成负载。"
                )
            rdma_root = str(rdma_root_path.resolve()) if rdma_root_path else None
            return GenerateTreeResponse(
                success=True,
                message="通信树解析成功（来自自定义负载）",
                tree_file="",
                tree_data=tree_data,
                nodes_count=len(tree_data.get("nodes", [])),
                edges_count=len(tree_data.get("edges", [])),
                rdma_root=rdma_root
            )

        json_path, rdma_root_path = _find_communication_tree_json()
        if json_path is None:
            raise HTTPException(
                status_code=404,
                detail="未找到通信树文件。请先在第二步使用 qwen/deepseek 模式生成负载。"
            )
        with open(json_path, 'r', encoding='utf-8') as f:
            tree_data = json.load(f)
        rdma_root = str(rdma_root_path.resolve()) if rdma_root_path else None
        return GenerateTreeResponse(
            success=True,
            message="通信树解析成功（来自模块二负载输出）",
            tree_file=str(json_path),
            tree_data=tree_data,
            nodes_count=len(tree_data.get("nodes", [])),
            edges_count=len(tree_data.get("edges", [])),
            rdma_root=rdma_root
        )
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] 解析通信树时发生异常: {str(e)}\n{error_trace}")
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")

class VisualizeTreeRequest(BaseModel):
    load_source: Optional[str] = None  # "custom" 或 "generated"

@app.post("/visualize-full-tree")
async def visualize_full_tree(request: Optional[VisualizeTreeRequest] = Body(default=None)):
    """可视化完整通信树（从模块二负载输出解析，或自定义负载构建）"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import networkx as nx

        load_source = (request.load_source if request else None) or ""
        load_source = load_source.lower()
        tree_data = None

        if load_source == "custom":
            tree_data, _ = _build_communication_tree_from_custom_load(REVERIE_ROOT)

        if tree_data is None:
            json_path, _ = _find_communication_tree_json()
            if json_path is None:
                raise HTTPException(status_code=404, detail="未找到通信树文件，请先在第二步生成负载")
            with open(json_path, 'r', encoding='utf-8') as f:
                tree_data = json.load(f)
        
        G = nx.DiGraph()
        node_types = {}
        for node in tree_data['nodes']:
            G.add_node(node['name'])
            node_types[node['name']] = node['type']
        
        for edge in tree_data['edges']:
            u = edge.get('from_node') or edge.get('from')
            v = edge.get('to_node') or edge.get('to')
            if u and v:
                G.add_edge(u, v)
        
        layers = {}
        for node in tree_data['nodes']:
            layer = node['layer']
            if layer not in layers:
                layers[layer] = []
            layers[layer].append(node['name'])
        
        num_layers = len(layers)
        plt.figure(figsize=(24, num_layers * 2.5))
        
        pos = {}
        for layer_num, nodes in sorted(layers.items()):
            y = -layer_num * 6
            if len(nodes) == 1:
                pos[nodes[0]] = (0, y)
            else:
                for i, node in enumerate(nodes):
                    x = (i - (len(nodes) - 1) / 2) * 6
                    pos[node] = (x, y)
        
        color_map = {'Root': '#FFD700', 'TP': '#90EE90', 'EP': '#87CEEB', 'PP': '#FFA500', 'DP': '#FF6B6B', 'OP': '#90EE90'}
        node_colors = [color_map.get(node_types.get(node, 'Root'), '#CCCCCC') for node in G.nodes()]
        
        nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=8000, alpha=0.95, edgecolors='black', linewidths=4)
        nx.draw_networkx_edges(G, pos, edge_color='#333333', arrows=True, arrowsize=40, arrowstyle='->', width=4, alpha=0.85)
        nx.draw_networkx_labels(G, pos, font_size=16, font_weight='bold')
        
        plt.title(f'Complete Communication Tree\n(Nodes: {len(G.nodes())}, Edges: {len(G.edges())})', fontsize=24, fontweight='bold', pad=15)
        
        from matplotlib.patches import Patch
        plt.legend(handles=[Patch(facecolor=color_map[k], edgecolor='black', linewidth=2, label=k) for k in ['Root', 'TP', 'EP', 'PP', 'DP']], loc='upper right', fontsize=14)
        
        plt.axis('off')
        plt.tight_layout(pad=0.5)
        
        output_file = API_DIR / 'full_communication_tree.png'
        plt.savefig(output_file, dpi=200, bbox_inches='tight', facecolor='white')
        plt.close()
        
        return {"success": True, "message": "可视化成功", "nodes_count": len(G.nodes()), "edges_count": len(G.edges())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"可视化失败: {str(e)}")

@app.get("/get-full-tree-image")
async def get_full_tree_image():
    """获取完整通信树图片"""
    image_path = API_DIR / 'full_communication_tree.png'
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(str(image_path), media_type='image/png')

@app.post("/visualize-tree-groups")
async def visualize_tree_groups(output_dir: str = "TreeGroup"):
    """可视化树组"""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import networkx as nx
        import glob
        
        # 删除旧的树组可视化图片
        api_dir = API_DIR
        old_images = glob.glob(str(api_dir / "tree_group_*.png"))
        for old_img in old_images:
            try:
                os.remove(old_img)
                print(f"[INFO] 已删除旧图片: {os.path.basename(old_img)}")
            except Exception as e:
                print(f"[WARNING] 删除旧图片失败: {old_img}, 错误: {e}")
        
        api_dir = API_DIR
        base_dir = REVERIE_ROOT
        # 尝试多个可能路径（兼容不同项目结构）
        candidates = [
            (api_dir / output_dir).resolve(),
            (base_dir / output_dir).resolve(),
        ]
        if output_dir and os.path.isabs(output_dir):
            candidates.insert(0, Path(output_dir))
        tree_dir = None
        for cand in candidates:
            if cand and cand.exists() and (cand / "tree_group_overview.json").exists():
                tree_dir = cand
                break
        if tree_dir is None:
            raise HTTPException(status_code=404, detail=f"树组目录不存在或未找到 tree_group_overview.json。尝试路径: {[str(c) for c in candidates if c]}")
        
        overview_file = tree_dir / "tree_group_overview.json"
        if not overview_file.exists():
            raise HTTPException(status_code=404, detail="未找到tree_group_overview.json")
        
        with open(overview_file, 'r', encoding='utf-8') as f:
            overview = json.load(f)
        
        total_groups = overview.get('total_groups', 0)
        visualized_groups = []
        
        for i in range(1, total_groups + 1):
            tree_file = tree_dir / f"tree_group_{i}.json"
            if not tree_file.exists():
                continue
            
            with open(tree_file, 'r', encoding='utf-8') as f:
                tree_data = json.load(f)
            
            G = nx.DiGraph()
            for node in tree_data.get('nodes', []):
                G.add_node(node.get('name', 'Unknown'))
            for edge in tree_data.get('edges', []):
                u = edge.get('from_node') or edge.get('from')
                v = edge.get('to_node') or edge.get('to')
                if u and v:
                    G.add_edge(u, v)
            
            # 从图结构计算 layer（树深度），兼容无 layer 的节点
            layers = {}
            root_candidates = [n for n in G.nodes() if G.in_degree(n) == 0]
            root_name = root_candidates[0] if root_candidates else list(G.nodes())[0]
            depth_map = {root_name: 0}
            for u, v in nx.bfs_edges(G, root_name):
                depth_map[v] = depth_map[u] + 1
            for node in tree_data.get('nodes', []):
                name = node.get('name', 'Unknown')
                layer = node.get('layer') if node.get('layer') is not None else depth_map.get(name, 0)
                if layer not in layers:
                    layers[layer] = []
                layers[layer].append(name)
            
            num_layers = len(layers) if layers else 1
            plt.figure(figsize=(16, max(num_layers * 2.5, 12)), facecolor='white')
            
            pos = {}
            if layers:
                max_layer = max(layers.keys())
                for layer, layer_nodes in sorted(layers.items()):
                    y = (max_layer - layer) * 6
                    if len(layer_nodes) == 1:
                        pos[layer_nodes[0]] = (0, y)
                    elif len(layer_nodes) == 2:
                        pos[layer_nodes[0]] = (-5, y)
                        pos[layer_nodes[1]] = (5, y)
                    else:
                        for idx, node in enumerate(layer_nodes):
                            x = (idx - (len(layer_nodes) - 1) / 2) * 6
                            pos[node] = (x, y)
            else:
                # 无 layer 时使用简单环形布局
                node_list = list(G.nodes())
                for idx, node in enumerate(node_list):
                    angle = 2 * math.pi * idx / max(len(node_list), 1)
                    pos[node] = (10 * math.cos(angle), 10 * math.sin(angle))
            # 确保 G 中每个节点都有位置（避免 "Node 'Root' has no position"）
            max_layer = max(depth_map.values()) if depth_map else 0
            for n in G.nodes():
                if n not in pos:
                    d = depth_map.get(n, 0)
                    pos[n] = (0, (max_layer - d) * 6)
            
            node_colors = []
            for node in G.nodes():
                node_str = str(node).lower()
                if 'root' in node_str:
                    node_colors.append('#ff6b6b')
                elif 'dp' in node_str:
                    node_colors.append('#4ecdc4')
                elif 'pp' in node_str:
                    node_colors.append('#95e1d3')
                elif 'tp' in node_str:
                    node_colors.append('#ffd93d')
                else:
                    node_colors.append('#a8dadc')
            
            nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=10000, alpha=0.95, edgecolors='black', linewidths=4.5)
            nx.draw_networkx_edges(G, pos, edge_color='#333333', arrows=True, arrowsize=45, width=5, arrowstyle='->', alpha=0.85)
            nx.draw_networkx_labels(G, pos, font_size=18, font_weight='bold')
            
            plt.title(f'Tree Group {i}\nNodes: {len(tree_data.get("nodes", []))} | Edges: {len(tree_data.get("edges", []))}', fontsize=24, fontweight='bold', pad=12)
            
            from matplotlib.patches import Patch
            plt.legend(handles=[Patch(facecolor='#ff6b6b', edgecolor='black', linewidth=2, label='Root'), Patch(facecolor='#4ecdc4', edgecolor='black', linewidth=2, label='DP'), Patch(facecolor='#95e1d3', edgecolor='black', linewidth=2, label='PP'), Patch(facecolor='#ffd93d', edgecolor='black', linewidth=2, label='TP')], loc='upper right', fontsize=20)
            
            plt.axis('off')
            plt.tight_layout(pad=0.5)
            
            output_file = API_DIR / f"tree_group_{i}.png"
            plt.savefig(output_file, dpi=200, bbox_inches='tight', facecolor='white')
            plt.close()
            
            visualized_groups.append({"group_id": i, "node_count": len(tree_data.get('nodes', [])), "edge_count": len(tree_data.get('edges', []))})
        
        # 检查是否已经生成了3D树组可视化HTML
        viz_html_file = tree_dir / "tree_split_3d.html"
        has_3d_viz = viz_html_file.exists()
        
        return {
            "success": True,
            "groups": visualized_groups,
            "total_groups": total_groups,
            "has_3d_viz": has_3d_viz
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"可视化失败: {str(e)}")


@app.get("/get-tree-groups-3d")
async def get_tree_groups_3d(output_dir: str = "TreeGroup"):
    """获取树组3D切分可视化HTML"""
    api_dir = API_DIR
    base_dir = REVERIE_ROOT
    
    tree_dir = (api_dir / output_dir).resolve()
    if not tree_dir.exists():
        tree_dir = (base_dir / output_dir).resolve()
    if not tree_dir.exists():
        raise HTTPException(status_code=404, detail=f"树组目录不存在: {output_dir}")
    
    html_file = tree_dir / "tree_split_3d.html"
    if not html_file.exists():
        raise HTTPException(status_code=404, detail="3D树组可视化HTML不存在，请先执行通信树切分")
    
    # 读取并修复模板转义问题：旧版 TreeCut 可能生成 {{ 和 }}，需转为 { 和 }
    html_content = html_file.read_text(encoding="utf-8")
    if "}}" in html_content or "{{" in html_content:
        html_content = html_content.replace("}}", "}").replace("{{", "{")
    
    return HTMLResponse(content=html_content)

@app.get("/get-tree-image/{group_id}")
async def get_tree_image(group_id: int):
    """获取树组图片"""
    image_file = API_DIR / f"tree_group_{group_id}.png"
    if not image_file.exists():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(str(image_file), media_type='image/png')

# ==================== 负载流量可视化接口 ====================

def _build_leaf_spine_fallback_paths(
    flows: List[Dict[str, Any]],
    host_to_tor: Dict[int, int],
    spine_ids: Set[int]
) -> Dict[str, Any]:
    """
    当 ECMP 缓存为空时，基于 Leaf-Spine 拓扑构造默认路径，供前端高亮展示。
    规则：src_host -> src_tor -> spine(任选) -> dst_tor -> dst_host；
         若源宿同 TOR，则为 src_host -> tor -> dst_host。
    """
    fallback_paths: List[Dict[str, Any]] = []
    if not flows:
        return {
            "metadata": {
                "fallback": True,
                "generated_at": time.time(),
                "reason": "no_flows"
            },
            "expected": {"count": 0, "paths": []},
            "actual": {"count": 0, "paths": []}
        }

    sorted_spines: List[int] = sorted(spine_ids) if spine_ids else []
    spine_count = len(sorted_spines)

    flow_id = 1
    for flow in flows:
        src = flow.get("src")
        dst = flow.get("dst")
        if src is None or dst is None:
            continue

        src_tor = host_to_tor.get(src)
        dst_tor = host_to_tor.get(dst)
        if src_tor is None and dst_tor is None:
            continue

        if src_tor is None:
            src_tor = dst_tor
        if dst_tor is None:
            dst_tor = src_tor

        selected_spine: Optional[int] = None
        if spine_count > 0:
            selected_spine = sorted_spines[(src + dst + flow_id) % spine_count]

        node_path: List[int] = [src]
        if src_tor is not None:
            node_path.append(src_tor)
        if selected_spine is not None:
            node_path.append(selected_spine)
        if dst_tor is not None:
            node_path.append(dst_tor)
        node_path.append(dst)

        fallback_paths.append({
            "stage": "leafspine-fallback",
            "flow_id": flow_id,
            "src": src,
            "dst": dst,
            "node_path": node_path,
            "port_steps": [],
            "expanded_sequence": []
        })
        flow_id += 1

    payload = {
        "metadata": {
            "fallback": True,
            "generated_at": time.time(),
            "reason": "ecmp_cache_empty",
            "spine_count": len(sorted_spines)
        },
        "expected": {
            "count": len(fallback_paths),
            "paths": fallback_paths
        },
        "actual": {
            "count": len(fallback_paths),
            "paths": fallback_paths
        }
    }
    return payload


@app.get("/parse-load-files")
async def parse_load_files(directory: str = "rdma_result", use_latest_workflow: bool = False):
    """
    解析负载文件并结合拓扑结构，提取流量数据
    
    Args:
        directory: 如果 use_latest_workflow=False，则使用此目录（相对于 examples/Reverie）
        use_latest_workflow: 如果为 True，则从最新的 workflow 输出目录读取
    
    Returns:
        包含完整拓扑结构和流量信息的数据
    """
    try:
        import re
        from collections import defaultdict
        
        base_dir = REVERIE_ROOT.resolve()
        
        if use_latest_workflow:
            # 从最新的 workflow 输出目录读取
            generator_dir = base_dir / "Generator" / "Generator"
            output_base = generator_dir / "workflow_output"
            print(f"[DEBUG] parse-load-files: base_dir={base_dir}, generator_dir={generator_dir}, output_base={output_base}, exists={output_base.exists()}")
            if not output_base.exists():
                raise HTTPException(status_code=404, detail=f"Workflow输出目录不存在: {output_base}")
            
            # 查找最新的输出目录（只查找包含 2_traffic/rdma_result 的目录）
            output_dirs = []
            for d in output_base.iterdir():
                if d.is_dir():
                    rdma_dir = d / "2_traffic" / "rdma_result"
                    if rdma_dir.exists():
                        output_dirs.append(d)
            
            if not output_dirs:
                # 如果没找到包含 rdma_result 的目录，尝试查找所有目录
                all_dirs = sorted(
                    [d for d in output_base.iterdir() if d.is_dir()],
                    key=lambda x: x.stat().st_mtime,
                    reverse=True
                )
                if not all_dirs:
                    raise HTTPException(status_code=404, detail="未找到Workflow输出目录")
                # 返回所有目录列表供调试
                dir_list = [str(d.name) for d in all_dirs[:5]]
                raise HTTPException(
                    status_code=404, 
                    detail=f"未找到包含 2_traffic/rdma_result 的Workflow目录。最新5个目录: {', '.join(dir_list)}"
                )
            
            # 按修改时间排序，获取最新的包含 rdma_result 的目录
            output_dirs = sorted(
                output_dirs,
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            latest_dir = output_dirs[0]
            load_dir = latest_dir / "2_traffic" / "rdma_result"
            if not load_dir.exists():
                raise HTTPException(status_code=404, detail=f"Workflow RDMA目录不存在: {load_dir}")
            
            # 使用 workflow 生成的拓扑文件
            topology_file = latest_dir / "1_topology" / "leaf-spine.txt"
            if not topology_file.exists():
                # 如果 workflow 没有生成 leaf-spine.txt，使用默认的
                topology_file = base_dir / "leaf-spine.txt"
        else:
            # 使用指定的目录
            load_dir = (base_dir / directory).resolve()
            if not load_dir.exists():
                raise HTTPException(status_code=404, detail=f"负载目录不存在: {directory}")
            topology_file = base_dir / "leaf-spine.txt"
        
        # 1. 读取拓扑文件（已在上面根据 use_latest_workflow 设置）
        if not topology_file.exists():
            raise HTTPException(status_code=404, detail=f"拓扑文件不存在: {topology_file}")
        
        # 解析拓扑文件
        with open(topology_file, 'r') as f:
            topo_lines = f.readlines()
        
        # 第一行：总节点数 总交换机数 TOR数 总链路数 带宽 带宽
        first_line = topo_lines[0].strip().split()
        total_nodes = int(first_line[0])
        total_switches = int(first_line[1])
        num_tors = int(first_line[2])
        
        num_hosts = total_nodes - total_switches
        num_spines = total_switches - num_tors
        
        # 第二行：所有交换机ID（前num_tors个是TOR，后面是Spine）
        all_switch_ids = [int(x) for x in topo_lines[1].strip().split()]
        tor_ids = set(all_switch_ids[:num_tors])
        spine_ids = set(all_switch_ids[num_tors:])
        
        # 解析拓扑连接
        topo_edges = []
        for line in topo_lines[2:]:
            parts = line.strip().split()
            if len(parts) >= 2:
                node1 = int(parts[0])
                node2 = int(parts[1])
                topo_edges.append((node1, node2))
        
        # 记录主机与TOR的映射关系
        host_to_tor = {}
        tor_to_hosts = defaultdict(list)
        for node1, node2 in topo_edges:
            if node1 < num_hosts and node2 in tor_ids:
                host_to_tor[node1] = node2
                tor_to_hosts[node2].append(node1)
            elif node2 < num_hosts and node1 in tor_ids:
                host_to_tor[node2] = node1
                tor_to_hosts[node1].append(node2)
        
        def _infer_flow_type(path_text: str) -> str:
            match = re.search(r"(TP|EP|PP|DP)", path_text.upper())
            return match.group(1) if match else "UNK"

        has_tagged_dirs = False
        if load_dir.exists():
            for entry in load_dir.iterdir():
                if entry.is_dir() and re.match(r"\d+_(TP|EP|PP|DP)\d*", entry.name, re.IGNORECASE):
                    has_tagged_dirs = True
                    break

        # 2. 解析负载流量数据
        flows = []
        host_flow_set = set()  # 只统计主机之间的流量
        
        # 遍历所有rdma_operate*.txt文件
        for root, dirs, files in os.walk(load_dir):
            if has_tagged_dirs and "all_rdma_files" in Path(root).parts:
                continue
            for file in files:
                if file.startswith("rdma_operate") and file.endswith(".txt"):
                    file_path = Path(root) / file
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            
                            for line in lines:
                                line = line.strip()
                                if not line or line.startswith("stat") or line.startswith("phase"):
                                    continue
                                
                                # 解析: Type rdma_send src_node X src_port Y dst_node Z dst_port Y priority 0 msg_len SIZE
                                # 支持两种格式: "src_node 4" 或 "src_node:4"
                                match = re.search(
                                    r'src_node[:\s]+(\d+).*?dst_node[:\s]+(\d+).*?msg_len[:\s]+(\d+)',
                                    line
                                )
                                
                                if match:
                                    src_node = int(match.group(1))
                                    dst_node = int(match.group(2))
                                    msg_len = int(match.group(3))
                                    
                                    # 只记录主机节点的流量
                                    if src_node < num_hosts and dst_node < num_hosts:
                                        host_flow_set.add(src_node)
                                        host_flow_set.add(dst_node)
                                        
                                        flows.append({
                                            "src": src_node,
                                            "dst": dst_node,
                                            "size": msg_len,
                                            "file": str(file_path.relative_to(base_dir)),
                                            "flow_type": _infer_flow_type(str(file_path))
                                        })
                    except Exception as e:
                        print(f"[WARNING] 读取文件失败 {file_path}: {e}")
                        continue
        
        # 3. 统计流量边
        edge_flows = defaultdict(lambda: {"count": 0, "total_size": 0})
        for flow in flows:
            edge_key = f"{flow['src']}-{flow['dst']}"
            edge_flows[edge_key]["count"] += 1
            edge_flows[edge_key]["total_size"] += flow["size"]
        
        # 4. 构建完整的节点列表（包括主机、TOR、Spine）
        nodes = []
        
        # 主机节点
        for i in range(num_hosts):
            nodes.append({
                "id": i,
                "label": f"H{i}",
                "type": "host",
                "has_flow": i in host_flow_set
            })
        
        # TOR节点
        for tor_id in sorted(tor_ids):
            nodes.append({
                "id": tor_id,
                "label": f"TOR{tor_id}",
                "type": "tor"
            })
        
        # Spine节点
        for spine_id in sorted(spine_ids):
            nodes.append({
                "id": spine_id,
                "label": f"Spine{spine_id}",
                "type": "spine"
            })
        
        # 5. 构建边列表（拓扑边+流量边）
        edges = []
        
        # 拓扑边（物理连接）
        for node1, node2 in topo_edges:
            edge_key = f"{node1}-{node2}"
            reverse_key = f"{node2}-{node1}"
            
            # 检查是否有流量（通常拓扑边上没有直接流量）
            has_flow = edge_key in edge_flows or reverse_key in edge_flows
            flow_data = edge_flows.get(edge_key, edge_flows.get(reverse_key, {"count": 0, "total_size": 0}))
            
            edges.append({
                "source": node1,
                "target": node2,
                "type": "physical",  # 物理拓扑边
                "has_flow": has_flow,
                "count": flow_data["count"],
                "total_size": flow_data["total_size"],
                "avg_size": flow_data["total_size"] // flow_data["count"] if flow_data["count"] > 0 else 0
            })
        
        # 主机间的逻辑流量边（host-to-host traffic）
        for edge_key, data in edge_flows.items():
            src, dst = map(int, edge_key.split("-"))
            
            # 只添加主机之间的流量边
            if src < num_hosts and dst < num_hosts:
                edges.append({
                    "source": src,
                    "target": dst,
                    "type": "flow",  # 流量边（逻辑连接）
                    "has_flow": True,
                    "count": data["count"],
                    "total_size": data["total_size"],
                    "avg_size": data["total_size"] // data["count"] if data["count"] > 0 else 0
                })
        
        ecmp_cache = get_cached_ecmp_data() if is_ecmp_module_ready() else {}

        fallback_needed = True
        ecmp_paths: Dict[str, Any] = {}
        if isinstance(ecmp_cache, dict):
            expected_entry = ecmp_cache.get("expected")
            actual_entry = ecmp_cache.get("actual")
            expected_paths = expected_entry.get("paths") if isinstance(expected_entry, dict) else None
            actual_paths = actual_entry.get("paths") if isinstance(actual_entry, dict) else None
            
            # 如果 use_latest_workflow=True，检查缓存中的 rdma_root 是否与当前读取的目录匹配
            if use_latest_workflow and is_ecmp_module_ready():
                cached_rdma_root = expected_entry.get("rdma_root") if isinstance(expected_entry, dict) else None
                current_rdma_root = str(load_dir.resolve())
                # 如果缓存中的路径与当前目录不匹配，或者路径为空，则重新计算
                if cached_rdma_root != current_rdma_root or not expected_paths or len(expected_paths) == 0:
                    print(f"[DEBUG] ECMP缓存路径不匹配或为空，重新计算...")
                    print(f"  缓存路径: {cached_rdma_root}")
                    print(f"  当前路径: {current_rdma_root}")
                    try:
                        computed_result = compute_and_cache_ecmp(mode="expected", rdma_root=load_dir)
                        expected_entry = computed_result
                        expected_paths = expected_entry.get("paths") if isinstance(expected_entry, dict) else None
                        # 重新读取缓存
                        ecmp_cache = get_cached_ecmp_data()
                        expected_entry = ecmp_cache.get("expected")
                        actual_entry = ecmp_cache.get("actual")
                        expected_paths = expected_entry.get("paths") if isinstance(expected_entry, dict) else None
                        actual_paths = actual_entry.get("paths") if isinstance(actual_entry, dict) else None
                        print(f"[DEBUG] ECMP重新计算完成，路径数: {len(expected_paths) if expected_paths else 0}")
                    except Exception as e:
                        print(f"[WARNING] 自动重新计算ECMP失败: {e}")
            
            if expected_paths and len(expected_paths) > 0:
                fallback_needed = False
            if actual_paths and len(actual_paths) > 0:
                fallback_needed = False
            ecmp_paths = {
                "metadata": ecmp_cache.get("metadata", {}),
                "expected": expected_entry,
                "actual": actual_entry
            }
        else:
            ecmp_paths = {}

        if fallback_needed:
            ecmp_paths = _build_leaf_spine_fallback_paths(flows, host_to_tor, spine_ids)
        
        return {
            "success": True,
            "nodes": nodes,
            "edges": edges,
            "total_flows": len(flows),
            "total_nodes": len(nodes),
            "num_hosts": num_hosts,
            "num_tors": num_tors,
            "num_spines": num_spines,
            "topology_info": {
                "hosts": num_hosts,
                "tors": num_tors,
                "spines": num_spines,
                "total_nodes": total_nodes
            },
            "topology_layout": {
                "host_to_tor": host_to_tor,
                "tor_to_hosts": {str(tor): sorted(hosts) for tor, hosts in tor_to_hosts.items()},
                "tor_ids": sorted(list(tor_ids)),  # 添加TOR ID列表
                "spine_ids": sorted(list(spine_ids))  # 添加Spine ID列表
            },
            "flow_records": flows,
            "ecmp_paths": ecmp_paths
        }
        
    except Exception as e:
        print(f"[ERROR] 解析负载文件失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")

# ==================== 链路竞争分析相关 ====================

def _get_node_type(node_id: int, num_hosts: int = 80, tor_ids: Optional[List[int]] = None, spine_ids: Optional[List[int]] = None) -> str:
    """
    判断节点类型（主机/TOR/Spine）
    
    Args:
        node_id: 节点ID
        num_hosts: 主机数量（默认80）
        tor_ids: TOR节点ID列表（可选）
        spine_ids: Spine节点ID列表（可选）
    
    Returns:
        节点类型：'host', 'tor', 'spine', 或 'unknown'
    """
    # 如果提供了明确的ID列表，使用它们
    if tor_ids and node_id in tor_ids:
        return 'tor'
    if spine_ids and node_id in spine_ids:
        return 'spine'
    
    # 默认判断逻辑：如果提供了ID列表，优先使用；否则使用范围判断
    # 通常主机ID < num_hosts，TOR和Spine ID >= num_hosts
    # 但实际拓扑中，TOR和Spine的ID可能不是连续的，所以需要从拓扑文件读取
    if node_id < num_hosts:
        return 'host'
    # 如果没有提供ID列表，使用范围判断（可能不准确）
    # 假设TOR在 num_hosts 到 num_hosts+8 之间，Spine在之后
    elif not tor_ids and not spine_ids:
        if num_hosts <= node_id < num_hosts + 8:  # 假设8个TOR
            return 'tor'
        elif node_id >= num_hosts + 8:
            return 'spine'
    # 如果提供了ID列表但节点不在列表中，可能是未知类型
    return 'unknown'

def _format_path_description(node_path: List[int], num_hosts: int = 80, tor_ids: Optional[List[int]] = None, spine_ids: Optional[List[int]] = None) -> str:
    """
    格式化路径描述，显示每个节点的类型
    
    Args:
        node_path: 节点路径，如 [14, 65, 74, 64, 6]
        num_hosts: 主机数量
        tor_ids: TOR节点ID列表（可选）
        spine_ids: Spine节点ID列表（可选）
    
    Returns:
        格式化的路径描述，如 "H14 -> TOR65 -> Spine74 -> TOR64 -> H6"
    """
    if not node_path:
        return "无路径"
    
    path_parts = []
    for node_id in node_path:
        node_type = _get_node_type(node_id, num_hosts, tor_ids, spine_ids)
        if node_type == 'host':
            path_parts.append(f"H{node_id}")
        elif node_type == 'tor':
            path_parts.append(f"TOR{node_id}")
        elif node_type == 'spine':
            path_parts.append(f"Spine{node_id}")
        else:
            path_parts.append(f"N{node_id}")
    
    return " -> ".join(path_parts)

def _extract_links_from_path(node_path: List[int]) -> List[Tuple[int, int]]:
    """
    从节点路径中提取所有链路（边）
    
    Args:
        node_path: 节点路径，如 [H0, TOR1, Spine2, TOR3, H4]
    
    Returns:
        链路列表，如 [(H0, TOR1), (TOR1, Spine2), (Spine2, TOR3), (TOR3, H4)]
    """
    if not node_path or len(node_path) < 2:
        return []
    links = []
    for i in range(len(node_path) - 1):
        links.append((node_path[i], node_path[i + 1]))
    return links

def _parse_port_from_rdma_file(file_path: Path) -> Tuple[int, int, int]:
    """
    从 rdma_operate*.txt 文件中解析端口号和 phase 值
    
    Args:
        file_path: rdma_operate 文件路径
    
    Returns:
        (src_port, dst_port, phase) 元组，如果解析失败则返回默认值
    """
    default_src_port = 1016
    default_dst_port = 1016
    default_phase = 3000
    
    if not file_path.exists():
        return (default_src_port, default_dst_port, default_phase)
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            phase = default_phase
            src_port = default_src_port
            dst_port = default_dst_port
            
            for line in lines:
                line = line.strip()
                # 解析 phase
                if line.startswith("phase:"):
                    try:
                        phase = int(line.split(":")[1])
                    except:
                        pass
                # 解析端口号（从第一条 Type rdma_send 行）
                elif line.startswith("Type rdma_send") and src_port == default_src_port:
                    # 格式: Type rdma_send src_node X src_port Y dst_node Z dst_port W priority 0 msg_len SIZE
                    match = re.search(r'src_port[:\s]+(\d+).*?dst_port[:\s]+(\d+)', line)
                    if match:
                        src_port = int(match.group(1))
                        dst_port = int(match.group(2))
            
            return (src_port, dst_port, phase)
    except Exception as e:
        print(f"[WARNING] 解析端口号失败 {file_path}: {e}")
        return (default_src_port, default_dst_port, default_phase)

@app.post("/extract-link-competition-flows")
async def extract_link_competition_flows(use_latest_workflow: bool = True):
    """
    找出共享同一链路的流组，并生成 rdma_operate0_new.txt 文件
    
    Args:
        use_latest_workflow: 是否使用最新的 workflow 输出目录
    
    Returns:
        包含提取结果的响应
    """
    try:
        base_dir = REVERIE_ROOT
        
        # 1. 获取流量数据和路径信息
        parse_result = await parse_load_files(directory="rdma_result", use_latest_workflow=use_latest_workflow)
        
        if not parse_result.get("success"):
            raise HTTPException(status_code=500, detail="获取流量数据失败")
        
        flow_records = parse_result.get("flow_records", [])
        ecmp_paths = parse_result.get("ecmp_paths", {})
        
        if not flow_records:
            raise HTTPException(status_code=404, detail="未找到流量数据")
        
        print(f"[DEBUG] 总流量记录数: {len(flow_records)}")
        
        # 2. 获取路径信息（优先使用 actual，但如果 actual 路径太少，则使用 expected）
        actual_data = ecmp_paths.get("actual", {})
        expected_data = ecmp_paths.get("expected", {})
        
        actual_paths = actual_data.get("paths", []) if isinstance(actual_data, dict) else []
        expected_paths = expected_data.get("paths", []) if isinstance(expected_data, dict) else []
        
        # 如果 actual 路径数量少于总流量的10%，则使用 expected 路径
        # 这样可以确保有足够的路径数据进行分析
        min_paths_threshold = max(100, len(flow_records) * 0.1)
        
        if len(actual_paths) >= min_paths_threshold:
            paths_data = actual_data
            paths_list = actual_paths
            print(f"[DEBUG] 使用 actual 路径数据 ({len(actual_paths)} 条)")
        elif len(expected_paths) > 0:
            paths_data = expected_data
            paths_list = expected_paths
            print(f"[DEBUG] 使用 expected 路径数据 ({len(expected_paths)} 条)")
            if len(actual_paths) > 0:
                print(f"[DEBUG] 注意：actual 路径数据太少 ({len(actual_paths)} 条)，已切换到 expected 路径")
        else:
            paths_data = {}
            paths_list = []
            print(f"[DEBUG] 警告：未找到路径数据")
        
        print(f"[DEBUG] 路径数据总数: {len(paths_list)}")
        
        if not paths_list:
            raise HTTPException(status_code=404, detail="未找到路径信息，请先计算 ECMP 路径")
        
        # 3. 建立流到路径的映射
        flow_to_path = {}
        for path_item in paths_list:
            src = path_item.get("src")
            dst = path_item.get("dst")
            node_path = path_item.get("node_path", [])
            if src is not None and dst is not None and node_path:
                flow_key = (src, dst)
                # 如果有多条路径，选择第一条
                if flow_key not in flow_to_path:
                    flow_to_path[flow_key] = node_path
        
        print(f"[DEBUG] 有路径信息的流数: {len(flow_to_path)}")
        print(f"[DEBUG] 无路径信息的流数: {len(flow_records) - len(flow_to_path)}")
        
        # 4. 提取所有流的链路信息，并按链路分组
        link_to_flows = defaultdict(list)
        flows_without_path = 0
        
        for flow in flow_records:
            src = flow.get("src")
            dst = flow.get("dst")
            flow_key = (src, dst)
            
            # 获取该流的路径
            node_path = flow_to_path.get(flow_key)
            if not node_path:
                flows_without_path += 1
                continue
            
            # 提取链路
            links = _extract_links_from_path(node_path)
            
            # 将流添加到每个链路的流组中（使用 flow_key 去重，避免同一条流在同一链路组中重复）
            flow_info = {
                "src": src,
                "dst": dst,
                "size": flow.get("size", 0),
                "file": flow.get("file", ""),
                "path": node_path
            }
            
            for link in links:
                # 检查该流是否已经在该链路组中（避免重复）
                if not any(f["src"] == src and f["dst"] == dst for f in link_to_flows[link]):
                    link_to_flows[link].append(flow_info)
        
        if not link_to_flows:
            raise HTTPException(status_code=404, detail="未找到共享链路的流组")
        
        print(f"[DEBUG] 成功提取链路的流数: {len(flow_records) - flows_without_path}")
        if flows_without_path > 0:
            print(f"[WARNING] 有 {flows_without_path} 条流没有路径信息，已被跳过")
            print(f"[WARNING] 建议：重新计算 ECMP 路径以确保所有流都有路径信息")
        
        # 5. 统计所有链路组的信息
        link_stats = []
        for link, flows in link_to_flows.items():
            total_bandwidth = sum(f['size'] for f in flows)
            link_stats.append({
                "link": {"from": link[0], "to": link[1]},
                "flow_count": len(flows),
                "total_bandwidth": total_bandwidth,
                "flows": flows
            })
        
        # 按流数量降序排序
        link_stats.sort(key=lambda x: x["flow_count"], reverse=True)
        
        # 打印统计信息（前10个）
        print(f"[INFO] 链路组统计（共 {len(link_stats)} 个链路组）:")
        for i, stat in enumerate(link_stats[:10], 1):
            print(f"  {i}. 链路 {stat['link']['from']} -> {stat['link']['to']}: "
                  f"{stat['flow_count']} 条流, 总带宽 {stat['total_bandwidth']} bytes")
        
        # 优先选择流数量>=2的链路组，如果没有则选择流数量最多的
        selected_stat = None
        for stat in link_stats:
            if stat["flow_count"] >= 2:
                selected_stat = stat
                break
        
        if selected_stat is None:
            # 如果没有流数量>=2的，选择流数量最多的
            selected_stat = link_stats[0] if link_stats else None
            print(f"[WARNING] 所有链路组都只有1条流，选择流数量最多的链路组")
        
        if not selected_stat:
            raise HTTPException(status_code=404, detail="未找到有效的流组")
        
        selected_link = (selected_stat["link"]["from"], selected_stat["link"]["to"])
        selected_flows = selected_stat["flows"]
        
        print(f"[INFO] 选择的链路: {selected_link[0]} -> {selected_link[1]}, 流数量: {len(selected_flows)}")
        
        # 6. 解析端口号和 phase（从第一条流的原文件）
        src_port = 1016
        dst_port = 1016
        phase = 3000
        
        if selected_flows and selected_flows[0].get("file"):
            flow_file = selected_flows[0]["file"]
            # 构建完整路径
            if use_latest_workflow:
                generator_dir = base_dir / "Generator" / "Generator"
                output_base = generator_dir / "workflow_output"
                output_dirs = sorted(
                    [d for d in output_base.iterdir() if d.is_dir() and (d / "2_traffic" / "rdma_result").exists()],
                    key=lambda x: x.stat().st_mtime,
                    reverse=True
                )
                if output_dirs:
                    rdma_file_path = output_dirs[0] / "2_traffic" / flow_file
                else:
                    rdma_file_path = base_dir / flow_file
            else:
                rdma_file_path = base_dir / flow_file
            
            parsed_src_port, parsed_dst_port, parsed_phase = _parse_port_from_rdma_file(rdma_file_path)
            src_port = parsed_src_port
            dst_port = parsed_dst_port
            phase = parsed_phase
        
        # 7. 生成输出文件
        output_file = base_dir / "rdma_operate0_new.txt"
        
        # 获取拓扑信息以确定节点类型
        topology_info = parse_result.get("topology_info", {})
        topology_layout = parse_result.get("topology_layout", {})
        num_hosts = topology_info.get("num_hosts", 80)
        tor_ids = topology_layout.get("tor_ids", [])
        spine_ids = topology_layout.get("spine_ids", [])
        
        # 生成共享链路的描述
        link_from_type = _get_node_type(selected_link[0], num_hosts, tor_ids, spine_ids)
        link_to_type = _get_node_type(selected_link[1], num_hosts, tor_ids, spine_ids)
        link_from_label = f"{link_from_type.upper()}{selected_link[0]}" if link_from_type != 'unknown' else f"N{selected_link[0]}"
        link_to_label = f"{link_to_type.upper()}{selected_link[1]}" if link_to_type != 'unknown' else f"N{selected_link[1]}"
        shared_link_desc = f"{link_from_label} -> {link_to_label}"
        
        output_lines = [
            "stat rdma operate:",
            f"phase:{phase}",
            f"# 共享链路: {selected_link[0]} -> {selected_link[1]} ({shared_link_desc})",
            f"# 流数量: {len(selected_flows)}",
            f"# 总带宽需求: {sum(f['size'] for f in selected_flows)} bytes",
            f"# 说明：以下所有流都经过共享链路 {shared_link_desc}，会竞争该链路的带宽",
            ""
        ]
        
        for flow in selected_flows:
            path_desc = _format_path_description(flow.get("path", []), num_hosts, tor_ids, spine_ids)
            output_lines.append(f"# 路径: {path_desc}")
            output_lines.append(
                f"Type rdma_send src_node {flow['src']} src_port {src_port} "
                f"dst_node {flow['dst']} dst_port {dst_port} "
                f"priority 0 msg_len {flow['size']}"
            )
            output_lines.append("")  # 空行分隔
        
        # 写入文件
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(output_lines))
        
        print(f"[INFO] 已生成文件: {output_file}")
        print(f"[INFO] 包含 {len(selected_flows)} 条流，共享链路 {selected_link[0]} -> {selected_link[1]}")
        
        # 获取拓扑信息以确定节点类型（尝试从parse_result获取）
        topology_info = parse_result.get("topology_info", {})
        topology_layout = parse_result.get("topology_layout", {})
        num_hosts = topology_info.get("num_hosts", 80)
        tor_ids = topology_layout.get("tor_ids", [])
        spine_ids = topology_layout.get("spine_ids", [])
        
        # 格式化每条流的路径描述
        flows_with_path_desc = []
        for f in selected_flows:
            path_desc = _format_path_description(f.get("path", []), num_hosts, tor_ids, spine_ids)
            flows_with_path_desc.append({
                "src": f["src"],
                "dst": f["dst"],
                "size": f["size"],
                "path": f["path"],
                "path_description": path_desc
            })
        
        # 生成共享链路的描述
        link_from_type = _get_node_type(selected_link[0], num_hosts, tor_ids, spine_ids)
        link_to_type = _get_node_type(selected_link[1], num_hosts, tor_ids, spine_ids)
        link_from_label = f"{link_from_type.upper()}{selected_link[0]}" if link_from_type != 'unknown' else f"N{selected_link[0]}"
        link_to_label = f"{link_to_type.upper()}{selected_link[1]}" if link_to_type != 'unknown' else f"N{selected_link[1]}"
        shared_link_desc = f"{link_from_label} -> {link_to_label}"
        
        return {
            "success": True,
            "message": f"成功提取 {len(selected_flows)} 条共享链路的流",
            "output_file": str(output_file.relative_to(base_dir)),
            "link": {
                "from": selected_link[0],
                "to": selected_link[1],
                "description": shared_link_desc
            },
            "flow_count": len(selected_flows),
            "total_bandwidth_demand": sum(f['size'] for f in selected_flows),
            "flows": flows_with_path_desc,
            "all_link_stats": [
                {
                    "link": stat["link"],
                    "flow_count": stat["flow_count"],
                    "total_bandwidth": stat["total_bandwidth"]
                }
                for stat in link_stats[:20]  # 返回前20个链路组的统计信息
            ],
            "total_links": len(link_stats),
            "statistics": {
                "total_flows": len(flow_records),
                "flows_with_path": len(flow_to_path),
                "flows_without_path": flows_without_path,
                "flows_with_link": len(flow_records) - flows_without_path,
                "total_paths": len(paths_list)
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] 提取链路竞争流失败: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"提取失败: {str(e)}")

# ==================== 拓扑切分接口相关 ====================

def _generate_ecmp_paths_and_update_nodes_passed(rdma_root: Path, tree_data: dict, base_dir: Path) -> dict:
    """
    从真实流量生成 ECMP 路径，并更新 tree_data 中各节点的 nodes_passed。
    返回更新后的 tree_data（深拷贝）。
    """
    if not is_ecmp_module_ready():
        print("[tree-cut] ECMP 模块不可用，跳过真实路径更新")
        return tree_data
    tree_data = copy.deepcopy(tree_data)
    config_file = None
    router_file = None
    # 1. 优先从 workflow_output 最新目录获取拓扑
    wf_output = base_dir / "Generator" / "Generator" / "workflow_output"
    if wf_output.exists():
        dirs = sorted([d for d in wf_output.iterdir() if d.is_dir()], key=lambda x: x.stat().st_mtime, reverse=True)
        for d in dirs[:5]:
            topo = d / "1_topology"
            if topo.exists():
                cfg, rtr = topo / "dcn2.0_config.xml", topo / "router_mine.xml"
                if cfg.exists() and rtr.exists():
                    config_file, router_file = cfg, rtr
                    break
        if config_file:
            print(f"[tree-cut] 使用拓扑: {config_file.parent}")
    # 2. 若无，尝试 auto_output
    if not config_file:
        auto_out = base_dir / "Generator" / "Generator" / "auto_output"
        if auto_out.exists():
            dirs = sorted([d for d in auto_out.iterdir() if d.is_dir()], key=lambda x: x.stat().st_mtime, reverse=True)
            for d in dirs[:3]:
                cfg, rtr = d / "dcn2.0_config.xml", d / "router_mine.xml"
                if cfg.exists() and rtr.exists():
                    config_file, router_file = cfg, rtr
                    break
    # 3. 若无，运行 auto_gen_topo 生成
    if not config_file or not config_file.exists():
        try:
            topo_gen_dir = base_dir / "Generator" / "Generator" / "TopoGenerator" / "clos"
            auto_script = topo_gen_dir / "auto_gen_topo.py"
            if auto_script.exists():
                host_num, leaf_num, spine_num = 64, 8, 4
                leaf_spine = base_dir / "leaf-spine.txt"
                if leaf_spine.exists():
                    with open(leaf_spine, 'r') as f:
                        parts = f.readline().strip().split()
                        if len(parts) >= 3:
                            host_num, leaf_num, spine_num = int(parts[0]), int(parts[1]), int(parts[2])
                out_dir = base_dir / "Generator" / "Generator" / "auto_output" / "treecut_topo"
                out_dir.mkdir(parents=True, exist_ok=True)
                subprocess.run(
                    [sys.executable, str(auto_script), "--hosts", str(host_num),
                     "--leafs", str(leaf_num), "--spines", str(spine_num),
                     "--output-dir", str(out_dir)],
                    cwd=str(topo_gen_dir), capture_output=True, text=True, timeout=60
                )
                config_file = out_dir / "dcn2.0_config.xml"
                router_file = out_dir / "router_mine.xml"
                if config_file.exists():
                    print(f"[tree-cut] 已生成拓扑: {out_dir}")
        except Exception as e:
            print(f"[tree-cut] 拓扑生成失败: {e}")
    if not config_file or not config_file.exists() or not router_file or not router_file.exists():
        print("[tree-cut] 未找到拓扑文件，使用原始 nodes_passed")
        return tree_data
    for subdir in rdma_root.iterdir():
        if subdir.is_dir() and subdir.name not in ("all_rdma_files",):
            shutil.copy2(config_file, subdir / "dcn2.0_config.xml")
            shutil.copy2(router_file, subdir / "router_mine.xml")
    ecmp_output_dir = base_dir / "Generator" / "Generator" / "TreeCut" / "ecmp_outputs_treecut"
    ecmp_output_dir.mkdir(parents=True, exist_ok=True)
    try:
        from TreeCut.DocProcess import process_file as doc_process_file
    except ImportError:
        sys.path.insert(0, str(ECMP_MODULE_ROOT))
        from DocProcess import process_file as doc_process_file
    updated = 0
    for subdir in rdma_root.iterdir():
        if not subdir.is_dir() or subdir.name in ("all_rdma_files",):
            continue
        try:
            file_list = ecmp_get_rdma_files(str(subdir))
            if not file_list:
                continue
            flow_info, link_info, route_table, link_map, rev_map, *_ = ecmp_load_file(str(subdir), file_list)
            _, flow_paths_port = ecmp_find_paths(flow_info, link_info, route_table, link_map, rev_map)
            out_file = ecmp_output_dir / f"{subdir.name}.txt"
            with open(out_file, 'w') as f:
                for tup in flow_paths_port:
                    if len(tup) > 1 and isinstance(tup[1], list):
                        for item in tup[1]:
                            f.write(f"{item}\n")
        except Exception as e:
            print(f"[tree-cut] ECMP 路径生成失败 {subdir.name}: {e}")
            continue
    for node in tree_data.get("nodes", []):
        name = node.get("name")
        if not name or name == "Root":
            continue
        ecmp_file = ecmp_output_dir / f"{name}.txt"
        if ecmp_file.exists():
            try:
                node["nodes_passed"] = doc_process_file(str(ecmp_file))
                updated += 1
            except Exception as e:
                print(f"[tree-cut] 解析 {name} 失败: {e}")
    print(f"[tree-cut] 已用真实流量更新 {updated} 个节点的 nodes_passed")
    return tree_data


class TreeCutRequest(BaseModel):
    tree_data: Dict[str, Any]
    output_dir: str = "TreeGroup"
    num_groups: int = 0  # 保留参数（兼容性），实际只支持0（自动切分）
    show_graphs: bool = False
    rdma_root: Optional[str] = None  # rdma_result 路径，提供则用真实流量计算 nodes_passed

class TreeCutResponse(BaseModel):
    success: bool
    message: str
    tree_groups: int
    output_directory: str
    json_overview: Dict[str, Any]
    result_files: List[str]
    tree_split_3d_html: Optional[str] = None

@app.post("/tree-cut", response_model=TreeCutResponse)
async def tree_cut(request: TreeCutRequest):
    """
    拓扑切分接口（基于依赖分析的自动切分）
    
    使用智能算法自动切分通信树，保证依赖关系不被破坏：
    - 预处理：识别并剪除无冲突的"毛刺"节点
    - 递归切割：基于最长路径和依赖分析进行切分
    - 冲突检测：确保切分不破坏节点间的依赖关系
    
    若提供 rdma_root，则从真实流量计算 ECMP 路径，用实际流经的网络节点更新 nodes_passed。
    """
    try:
        api_dir = API_DIR
        base_dir = REVERIE_ROOT
        tree_data = request.tree_data.copy()
        # 若提供 rdma_root，用真实流量更新 nodes_passed
        if request.rdma_root:
            rdma_path = Path(request.rdma_root)
            if not rdma_path.is_absolute():
                rdma_path = (base_dir / request.rdma_root.replace("\\", "/")).resolve()
            if rdma_path.exists() and rdma_path.is_dir():
                tree_data = _generate_ecmp_paths_and_update_nodes_passed(rdma_path, tree_data, base_dir)
            else:
                print(f"[tree-cut] rdma_root 不存在: {rdma_path}，使用原始 nodes_passed")
        # 转换edge格式
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
        result = performTreeCutComplete(
            tree_data=tree_data,
            output_dir=request.output_dir,
            num_groups=request.num_groups,
            show_graphs=request.show_graphs
        )
        
        result_files = []
        # 尝试多个可能的路径查找结果文件
        api_dir = API_DIR
        base_dir = REVERIE_ROOT
        possible_output_dirs = [
            api_dir / request.output_dir,  # examples/Reverie/api/TreeGroup
            base_dir / request.output_dir,  # examples/Reverie/TreeGroup
            Path(request.output_dir),  # 相对路径或绝对路径
        ]
        
        found_dir = None
        for dir_path in possible_output_dirs:
            if dir_path.exists() and dir_path.is_dir():
                found_dir = dir_path
                break
        
        if found_dir:
            for root, dirs, files in os.walk(str(found_dir)):
                for file in files:
                    result_files.append(os.path.join(root, file))
        
        return TreeCutResponse(
            success=result["success"],
            message=f"成功切分通信树，生成了{result['tree_groups']}个树组",
            tree_groups=result["tree_groups"],
            output_directory=result["output_directory"],
            json_overview=result["json_overview"],
            result_files=result_files,
            tree_split_3d_html=result.get("tree_split_3d_html")
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
    task_num: int = 1  # 生成的任务数量，默认单任务

class LoadResponse(BaseModel):
    success: bool
    content: str
    filename: str
    message: str
    task_summary: List[Dict[str, Any]] = []
    ecmp_preview: Optional[Dict[str, Any]] = None
    host_num: Optional[int] = None
    load_directory: Optional[str] = None  # 查看负载文件时使用的目录（trafficGen 用 Generator/.../task1）


def _parse_msg_len_expr(msg_len_expr: str) -> int:
    sanitized_msg_len = (msg_len_expr or "").replace('^', '**')
    if not re.fullmatch(r'[\d\+\-\*/\(\)\s\.]+', sanitized_msg_len):
        raise HTTPException(status_code=400, detail="msg_len 格式不合法，请使用仅包含数字和运算符的表达式")
    try:
        msg_len_bytes = int(eval(sanitized_msg_len, {"__builtins__": None}, {}))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"无法解析消息大小: {exc}")
    if msg_len_bytes <= 0:
        raise HTTPException(status_code=400, detail="消息大小必须大于0")
    return msg_len_bytes


def _trafficgen_msg_expr(base_expr: str, mode: str) -> str:
    expr = base_expr or "32*(1024)"
    mode = (mode or "").upper()
    if mode == "PP":
        return f"(({expr})//4)"
    if mode == "DP":
        return f"(({expr})//2)"
    return expr


def _build_trafficgen_config(template_path: Path,
                             host_num: int,
                             msg_len_expr: str,
                             dp: int) -> str:
    if not template_path.exists():
        raise FileNotFoundError(f"模板文件不存在: {template_path}")
    with open(template_path, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    if not lines:
        raise ValueError("模板文件为空")

    output_lines: List[str] = []
    # 第一行保留模板的 model/devices/iterations
    first_parts = re.split(r'\s+', lines[0].strip())
    if len(first_parts) >= 1:
        model_name = first_parts[0]
        devices = first_parts[1] if len(first_parts) >= 2 else "2"
        iterations = first_parts[2] if len(first_parts) >= 3 else "1"
        output_lines.append(f"{model_name} {devices} {iterations}")
    else:
        output_lines.append(lines[0])

    for raw in lines[1:]:
        line = raw.rstrip()
        if not line.strip() or line.strip().startswith("#"):
            output_lines.append(line)
            continue
        tokens = re.split(r'\s+', line.strip())
        mode = tokens[1] if len(tokens) >= 2 else ""
        msg_expr = _trafficgen_msg_expr(msg_len_expr, mode)
        updated = re.sub(r"--host_num\s+\S+", f"--host_num {host_num}", line)
        updated = re.sub(r"--msg_len\s+\S+", f"--msg_len {msg_expr}", updated)
        updated = re.sub(r"--dp\s+\S+", f"--dp {dp}", updated)
        output_lines.append(updated)
    return "\n".join(output_lines).rstrip() + "\n"


def _sync_task_to_reverie_exec_dir(task_sources: List[Path], task_num: int) -> None:
    """将模块二生成的流量复制到仿真执行目录（当后端运行在 repo 外时）"""
    reverie_dir = REVERIE_ROOT
    if not (reverie_dir / "sim.sh").exists():
        return
    for task_index in range(1, task_num + 1):
        src_task = None
        for src_base in task_sources:
            cand = src_base / f"task{task_index}"
            if cand.exists() and (cand / "rdma_operate0.txt").exists():
                src_task = cand
                break
        if src_task is not None:
            dst_task = reverie_dir / f"task{task_index}"
            if src_task.resolve() == dst_task.resolve():
                continue  # 已在 Reverie 内，无需复制
            if dst_task.exists():
                shutil.rmtree(dst_task)
            shutil.copytree(src_task, dst_task)
            print(f"[generate-load] 流量已同步到执行目录: {src_task} -> {dst_task}")


def _write_task_inputs_from_all_rdma_files(base_dir: Path,
                                           task_num: int) -> List[Dict[str, Any]]:
    """从 all_rdma_files 生成 task 目录，保留多个 rdma_operate 文件（不合并）"""
    task_num = max(1, task_num)
    all_files_dir = base_dir / "rdma_result" / "all_rdma_files"
    if not all_files_dir.exists():
        raise FileNotFoundError(f"all_rdma_files 不存在: {all_files_dir}")

    def file_key(path: Path) -> Tuple[int, str]:
        match = re.search(r"(\d+)", path.name)
        return (int(match.group(1)) if match else 0, path.name)

    all_files = sorted(all_files_dir.glob("rdma_operate*.txt"), key=file_key)
    if not all_files:
        raise FileNotFoundError("all_rdma_files 中未找到 rdma_operate 文件")

    files_by_task: List[List[Path]] = [[] for _ in range(task_num)]
    for idx, file_path in enumerate(all_files):
        files_by_task[idx % task_num].append(file_path)

    task_summaries: List[Dict[str, Any]] = []
    for task_index, task_files in enumerate(files_by_task, start=1):
        task_dir = base_dir / f"task{task_index}"
        if task_dir.exists():
            shutil.rmtree(task_dir)
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "logs").mkdir(parents=True, exist_ok=True)

        # 保留多个 rdma_operate 文件，不合并
        flow_files_written: List[str] = []
        for local_idx, file_path in enumerate(task_files):
            operate_path = task_dir / f"rdma_operate{local_idx}.txt"
            shutil.copy2(file_path, operate_path)
            flow_files_written.append(str(operate_path.relative_to(base_dir)))

        # dependence.txt：trafficGen 的 merge_dependency.py 已生成，直接复用；否则写入默认
        dependence_path = task_dir / "dependence.txt"
        src_dependence = base_dir / "dependence.txt"
        if task_num == 1 and src_dependence.exists():
            shutil.copy2(src_dependence, dependence_path)
        else:
            write_dependence_file(dependence_path)

        flow_count = 0
        for fp in task_files:
            with open(fp, 'r', encoding='utf-8') as f:
                flow_count += sum(1 for ln in f if 'Type rdma' in ln)

        task_summaries.append({
            "task": task_index,
            "host_range": "trafficGen",
            "flow_files": flow_files_written,
            "flow_count": flow_count
        })
    return task_summaries


def _copy_dump_files(src_dir: Path, dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    for filename in ["evaluation.fct1", "evaluation.out", "system1.log"]:
        src_file = src_dir / filename
        if src_file.exists():
            shutil.copyfile(src_file, dst_dir / filename)


def _backup_task_dirs(base_dir: Path) -> Optional[Path]:
    task_dirs = sorted([p for p in base_dir.glob("task[0-9]*") if p.is_dir()])
    if not task_dirs:
        return None
    backup_root = base_dir / "task_experiment_backup"
    if backup_root.exists():
        shutil.rmtree(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    for task_dir in task_dirs:
        shutil.copytree(task_dir, backup_root / task_dir.name)
    return backup_root


def _restore_task_dirs(base_dir: Path, backup_root: Optional[Path]) -> None:
    if not backup_root or not backup_root.exists():
        return
    for task_dir in base_dir.glob("task[0-9]*"):
        if task_dir.is_dir():
            shutil.rmtree(task_dir)
    for backup_dir in backup_root.iterdir():
        if backup_dir.is_dir():
            shutil.copytree(backup_dir, base_dir / backup_dir.name)
    shutil.rmtree(backup_root)


def _prepare_single_baseline_task_from_backup(base_dir: Path, backup_root: Optional[Path]) -> None:
    """
    基线仿真需要“未切分”的单任务输入。
    这里直接从实验任务备份(task1..taskN)聚合所有 rdma_operate*.txt 到 task1，
    避免依赖 rdma_result/all_rdma_files（该目录在不同模式下可能不是当前实验源）。
    """
    if not backup_root or not backup_root.exists():
        raise FileNotFoundError("任务备份不存在，无法构建基线单任务输入")

    source_task_dirs = sorted(
        [p for p in backup_root.glob("task[0-9]*") if p.is_dir()],
        key=lambda p: int(re.search(r"(\d+)", p.name).group(1)) if re.search(r"(\d+)", p.name) else 0
    )
    if not source_task_dirs:
        raise FileNotFoundError(f"未在备份目录中找到任务目录: {backup_root}")

    for task_dir in base_dir.glob("task[0-9]*"):
        if task_dir.is_dir():
            shutil.rmtree(task_dir)

    target_task_dir = base_dir / "task1"
    target_task_dir.mkdir(parents=True, exist_ok=True)
    (target_task_dir / "logs").mkdir(parents=True, exist_ok=True)

    flow_file_index = 0
    copied_any = False
    for src_task in source_task_dirs:
        operate_files = sorted(
            src_task.glob("rdma_operate*.txt"),
            key=lambda p: (
                int(re.search(r"(\d+)", p.name).group(1)) if re.search(r"(\d+)", p.name) else 0,
                p.name
            )
        )
        for src_file in operate_files:
            dst_file = target_task_dir / f"rdma_operate{flow_file_index}.txt"
            shutil.copy2(src_file, dst_file)
            flow_file_index += 1
            copied_any = True

    if not copied_any:
        raise FileNotFoundError("备份任务中未找到任何 rdma_operate*.txt，无法构建基线输入")

    dep_candidates = [p / "dependence.txt" for p in source_task_dirs]
    dep_source = next((p for p in dep_candidates if p.exists()), None)
    if dep_source:
        shutil.copy2(dep_source, target_task_dir / "dependence.txt")
    else:
        write_dependence_file(target_task_dir / "dependence.txt")


def _count_task_flow_records(base_dir: Path) -> int:
    """统计 task*/rdma_operate*.txt 中的流记录总数（按 Type rdma 行计数）。"""
    total = 0
    task_dirs = sorted([p for p in base_dir.glob("task[0-9]*") if p.is_dir()])
    for task_dir in task_dirs:
        operate_files = sorted(task_dir.glob("rdma_operate*.txt"))
        for fp in operate_files:
            try:
                with open(fp, 'r', encoding='utf-8', errors='ignore') as f:
                    total += sum(1 for line in f if "Type rdma" in line)
            except Exception:
                continue
    return total


def _has_dump_payload(dump_dir: Path) -> bool:
    return any((dump_dir / name).exists() for name in ["evaluation.fct1", "evaluation.out", "system1.log"])


def _extract_memory_mb(content: str) -> Optional[float]:
    patterns = [
        r"(?:Peak|Max|Maximum)\s+(?:RSS|memory|mem)\s*[:=]\s*([\d\.]+)\s*(KB|MB|GB)",
        r"memory\s+usage\s*[:=]\s*([\d\.]+)\s*(KB|MB|GB)",
        r"mem\s*[:=]\s*([\d\.]+)\s*(KB|MB|GB)"
    ]
    for line in content.splitlines():
        for pattern in patterns:
            match = re.search(pattern, line, flags=re.IGNORECASE)
            if match:
                value = float(match.group(1))
                unit = match.group(2).upper()
                if unit == "KB":
                    return value / 1024.0
                if unit == "GB":
                    return value * 1024.0
                return value
    return None


def _extract_buffer_pool_memory_mb(content: str) -> Optional[float]:
    max_bytes = None
    pattern = (
        r"total headroom:\s*(\d+)\s+ingressPool\s+(\d+)\s+"
        r"egressLosslessPool\s+(\d+)\s+egressLossyPool\s+(\d+)\s+sharedPool\s+(\d+)"
    )
    for line in content.splitlines():
        match = re.search(pattern, line, flags=re.IGNORECASE)
        if match:
            values = [int(v) for v in match.groups()]
            total = sum(values)
            if max_bytes is None or total > max_bytes:
                max_bytes = total
    if max_bytes is None:
        return None
    return max_bytes / (1024 * 1024)


def _compute_load_signature(base_dir: Path) -> str:
    rdma_dir = base_dir / "rdma_result" / "all_rdma_files"
    if not rdma_dir.exists():
        return ""
    files = sorted(rdma_dir.glob("rdma_operate*.txt"), key=lambda p: p.name)
    hasher = hashlib.sha256()
    for file_path in files:
        stat = file_path.stat()
        hasher.update(file_path.name.encode("utf-8"))
        hasher.update(str(stat.st_size).encode("utf-8"))
        hasher.update(str(int(stat.st_mtime)).encode("utf-8"))
    return hasher.hexdigest()


def _read_baseline_meta(meta_path: Path) -> Dict[str, Any]:
    if not meta_path.exists():
        return {}
    try:
        with open(meta_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _write_baseline_meta(meta_path: Path, payload: Dict[str, Any]) -> None:
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)


def _collect_analysis_from_dump(dump_dir: Path, analysis_type: str) -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    file_status = {}

    if analysis_type in ["all", "fct"]:
        fct_file = dump_dir / "evaluation.fct1"
        file_status["fct_file"] = str(fct_file)
        file_status["fct_exists"] = fct_file.exists()
        if fct_file.exists():
            try:
                with open(fct_file, 'r', encoding='utf-8') as f:
                    fct_content = f.read()
                fct_result = analyze_fct_metrics(fct_content)
                fct_result["file_found"] = True
                results["fct_analysis"] = fct_result
            except Exception as e:
                results["fct_analysis"] = {
                    "error": f"读取FCT文件失败: {str(e)}",
                    "file_found": True,
                    "total_flows": 0
                }
        else:
            results["fct_analysis"] = {
                "error": "FCT文件不存在，请先运行仿真",
                "file_path": str(fct_file),
                "file_found": False,
                "total_flows": 0
            }

    if analysis_type in ["all", "steady_state"]:
        evaluation_out = dump_dir / "evaluation.out"
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
                "error": "稳态日志文件不存在，请先运行仿真",
                "file_path": str(evaluation_out),
                "file_found": False
            }

    if analysis_type in ["all", "performance"]:
        log_file = dump_dir / "system1.log"
        file_status["perf_file"] = str(log_file)
        file_status["perf_exists"] = log_file.exists()
        if log_file.exists():
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_content = f.read()
                perf_result = analyze_performance(log_content)
                perf_result["file_found"] = True
                perf_result["memory_mb"] = _extract_memory_mb(log_content)
                perf_result["buffer_pool_mb"] = _extract_buffer_pool_memory_mb(log_content)
                results["performance_analysis"] = perf_result
            except Exception as e:
                results["performance_analysis"] = {
                    "error": f"读取性能文件失败: {str(e)}",
                    "file_found": True
                }
        else:
            results["performance_analysis"] = {
                "error": "性能日志文件不存在，请先运行仿真",
                "file_path": str(log_file),
                "file_found": False
            }

    results["file_status"] = file_status
    return results


def _compute_comparison(exp: Dict[str, Any], baseline: Dict[str, Any]) -> Dict[str, Any]:
    comparison: Dict[str, Any] = {}

    exp_fct = exp.get("fct_analysis", {})
    base_fct = baseline.get("fct_analysis", {})
    exp_avg = exp_fct.get("average_fct_us")
    base_avg = base_fct.get("average_fct_us")
    if exp_avg and base_avg:
        comparison["fct_ratio"] = base_avg / exp_avg if exp_avg else None
        comparison["fct_fidelity"] = max(0.0, 1.0 - abs(exp_avg - base_avg) / exp_avg) if exp_avg else None
        comparison["speedup"] = base_avg / exp_avg if exp_avg else None
        comparison["fct_delta_us"] = base_avg - exp_avg
        comparison["fct_delta_ratio"] = (base_avg - exp_avg) / exp_avg if exp_avg else None

    exp_perf = exp.get("performance_analysis", {})
    base_perf = baseline.get("performance_analysis", {})
    exp_mem = exp_perf.get("memory_mb") or exp_perf.get("buffer_pool_mb")
    base_mem = base_perf.get("memory_mb") or base_perf.get("buffer_pool_mb")
    if exp_mem is not None and base_mem:
        comparison["memory_overhead_ratio"] = base_mem / exp_mem if exp_mem else None
        comparison["memory_overhead_mb"] = base_mem - exp_mem
    else:
        comparison["memory_overhead_ratio"] = None
        comparison["memory_overhead_mb"] = None
        comparison["memory_note"] = "未在 system1.log 中解析到内存字段或buffer pool信息，无法计算内存开销"

    exp_total_ms = exp_perf.get("total_time_ms")
    base_total_ms = base_perf.get("total_time_ms")
    if exp_total_ms and base_total_ms:
        comparison["runtime_ratio"] = base_total_ms / exp_total_ms if exp_total_ms else None
        comparison["runtime_speedup"] = base_total_ms / exp_total_ms if exp_total_ms else None
        comparison["runtime_delta_ms"] = base_total_ms - exp_total_ms
        comparison["runtime_exp_total_ms"] = exp_total_ms
        comparison["runtime_base_total_ms"] = base_total_ms
    else:
        comparison["runtime_ratio"] = None
        comparison["runtime_speedup"] = None
        comparison["runtime_delta_ms"] = None
        comparison["runtime_exp_total_ms"] = None
        comparison["runtime_base_total_ms"] = None
        comparison["runtime_note"] = "未在 system1.log 中解析到 total time，无法计算运行时间对比"

    return comparison


def _parse_custom_traffic_content(content: str, default_msg_len_bytes: int) -> Tuple[List[Tuple[int, int, int]], int]:
    flows: List[Tuple[int, int, int]] = []
    max_node_id = -1
    for line in content.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw.lower().startswith("stat rdma") or raw.lower().startswith("phase:"):
            continue
        if "rdma_send" in raw:
            src_match = re.search(r"src_node\s+(\d+)", raw)
            dst_match = re.search(r"dst_node\s+(\d+)", raw)
            msg_match = re.search(r"msg_len\s+(\d+)", raw)
            if not src_match or not dst_match:
                continue
            src = int(src_match.group(1))
            dst = int(dst_match.group(1))
            msg_len = int(msg_match.group(1)) if msg_match else default_msg_len_bytes
        else:
            tokens = [t for t in re.split(r"[,\s]+", raw) if t]
            if len(tokens) < 2:
                continue
            try:
                src = int(tokens[0])
                dst = int(tokens[1])
            except ValueError:
                continue
            msg_len = default_msg_len_bytes
            if len(tokens) >= 3:
                try:
                    msg_len = int(float(tokens[2]))
                except ValueError:
                    msg_len = default_msg_len_bytes
        flows.append((src, dst, msg_len))
        max_node_id = max(max_node_id, src, dst)
    if not flows:
        raise HTTPException(status_code=400, detail="未识别到任何流量记录，请检查文件格式")
    host_num = max_node_id + 1 if max_node_id >= 0 else 1
    return flows, host_num


def _process_full_format_zip(zip_path: Path, base_dir: Path, task_num: int) -> Tuple[List[Dict[str, Any]], int, str]:
    """
    处理完整格式 ZIP（多 rdma_operate*.txt + dependence.txt）。
    返回 (task_summaries, host_num, load_directory)。
    task_num=4 时暂不支持，会报错。
    """
    if task_num != 1:
        raise HTTPException(
            status_code=400,
            detail="完整格式（ZIP）暂不支持切分，请先关闭「启用通信树分割」或使用简单格式（单 txt）"
        )
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        with zipfile.ZipFile(zip_path, 'r') as zf:
            zf.extractall(tmp)
        operate_files = sorted(tmp.glob("rdma_operate*.txt"), key=lambda p: (int(re.search(r"(\d+)", p.name).group(1)) if re.search(r"(\d+)", p.name) else 0, p.name))
        dep_file = tmp / "dependence.txt"
        if not operate_files:
            raise HTTPException(status_code=400, detail="ZIP 中未找到 rdma_operate*.txt 文件")
        if not dep_file.exists():
            raise HTTPException(status_code=400, detail="ZIP 中缺少 dependence.txt")
        task_dir = base_dir / "task1"
        if task_dir.exists():
            shutil.rmtree(task_dir)
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "logs").mkdir(parents=True, exist_ok=True)
        for i, src in enumerate(operate_files):
            shutil.copy2(src, task_dir / f"rdma_operate{i}.txt")
        shutil.copy2(dep_file, task_dir / "dependence.txt")
        rdma_dir = base_dir / "rdma_result"
        if rdma_dir.exists():
            shutil.rmtree(rdma_dir)
        rdma_dir.mkdir(parents=True, exist_ok=True)
        all_files_dir = rdma_dir / "all_rdma_files"
        all_files_dir.mkdir(parents=True, exist_ok=True)
        for i, src in enumerate(operate_files):
            shutil.copy2(src, all_files_dir / f"rdma_operate{i}.txt")
        rdma_task_dir = rdma_dir / "task1"
        rdma_task_dir.mkdir(parents=True, exist_ok=True)
        for i, src in enumerate(operate_files):
            shutil.copy2(src, rdma_task_dir / f"rdma_operate{i}.txt")
        shutil.copy2(dep_file, base_dir / "dependence.txt")
        flow_count = 0
        for fp in operate_files:
            with open(fp, 'r', encoding='utf-8') as f:
                flow_count += sum(1 for ln in f if 'Type rdma' in ln)
        host_num = 64
        for fp in operate_files:
            with open(fp, 'r', encoding='utf-8') as f:
                for line in f:
                    m = re.search(r"src_node\s+(\d+).*?dst_node\s+(\d+)", line)
                    if m:
                        host_num = max(host_num, int(m.group(1)) + 1, int(m.group(2)) + 1)
        task_summaries = [{
            "task": 1,
            "host_range": "custom",
            "flow_files": [str((task_dir / f.name).relative_to(base_dir)) for f in operate_files],
            "flow_count": flow_count
        }]
        load_directory = "rdma_result/task1"
        return task_summaries, host_num, load_directory


def _write_custom_task_inputs(base_dir: Path,
                              flows: List[Tuple[int, int, int]],
                              task_num: int) -> List[Dict[str, Any]]:
    task_num = max(1, task_num)
    rdma_dir = base_dir / "rdma_result"
    if rdma_dir.exists():
        shutil.rmtree(rdma_dir)
    rdma_dir.mkdir(parents=True, exist_ok=True)
    all_files_dir = rdma_dir / "all_rdma_files"
    all_files_dir.mkdir(parents=True, exist_ok=True)

    task_summaries: List[Dict[str, Any]] = []
    flows_by_task: List[List[Tuple[int, int, int]]] = [[] for _ in range(task_num)]
    for idx, flow in enumerate(flows):
        flows_by_task[idx % task_num].append(flow)
    if flows:
        for task_flows in flows_by_task:
            if not task_flows:
                task_flows.append(flows[0])

    for task_index, task_flows in enumerate(flows_by_task, start=1):
        task_dir = base_dir / f"task{task_index}"
        if task_dir.exists():
            shutil.rmtree(task_dir)
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "logs").mkdir(parents=True, exist_ok=True)

        operate_path = task_dir / "rdma_operate0.txt"
        with open(operate_path, 'w', encoding='utf-8') as f:
            f.write("stat rdma operate:\n")
            f.write("phase:3000\n")
            for src, dst, msg_len in task_flows:
                f.write(
                    f"Type rdma_send src_node {src} src_port 1000 dst_node {dst} dst_port 1000 priority 0 msg_len {msg_len}\n"
                )

        dependence_path = task_dir / "dependence.txt"
        write_dependence_file(dependence_path)

        rdma_task_dir = rdma_dir / f"task{task_index}"
        rdma_task_dir.mkdir(parents=True, exist_ok=True)
        rdma_operate_copy = rdma_task_dir / "rdma_operate0.txt"
        shutil.copyfile(operate_path, rdma_operate_copy)

        all_file_path = all_files_dir / f"rdma_operate{task_index - 1}.txt"
        shutil.copyfile(operate_path, all_file_path)

        task_summaries.append({
            "task": task_index,
            "host_range": "custom",
            "flow_files": [str(operate_path.relative_to(base_dir))],
            "flow_count": len(task_flows)
        })

    return task_summaries

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

def write_rdm_operate_file(file_path: Path, host_start: int, host_end: int, msg_len_bytes: int) -> int:
    hosts = list(range(host_start, host_end))
    flows: List[tuple[int, int]] = []
    if not hosts:
        hosts = [0]
    if len(hosts) == 1:
        flows.append((hosts[0], hosts[0]))
    else:
        for idx in range(len(hosts) - 1):
            flows.append((hosts[idx], hosts[idx + 1]))
        # 增加最后一个回到第一个，形成环，避免单向流
        flows.append((hosts[-1], hosts[0]))
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("stat rdma operate:\n")
        f.write("phase:3000\n")
        for src, dst in flows:
            f.write(
                f"Type rdma_send src_node {src} src_port 1000 dst_node {dst} dst_port 1000 priority 0 msg_len {msg_len_bytes}\n"
            )
    return len(flows)


def write_dependence_file(file_path: Path) -> None:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write("# auto-generated: no explicit operate dependencies\n")


def generate_task_inputs(base_dir: Path, host_num: int, msg_len_bytes: int, task_num: int) -> List[Dict[str, Any]]:
    task_num = max(1, task_num)
    host_num = max(1, host_num)
    hosts_per_task = math.ceil(host_num / task_num)

    rdma_dir = base_dir / "rdma_result"
    if rdma_dir.exists():
        shutil.rmtree(rdma_dir)
    rdma_dir.mkdir(parents=True, exist_ok=True)
    all_files_dir = rdma_dir / "all_rdma_files"
    all_files_dir.mkdir(parents=True, exist_ok=True)
    (base_dir / "logs").mkdir(parents=True, exist_ok=True)

    task_summaries: List[Dict[str, Any]] = []
    global_file_index = 0

    for task_index in range(task_num):
        host_start = task_index * hosts_per_task
        host_end = min(host_num, host_start + hosts_per_task)
        if host_start >= host_num:
            host_start = host_num - 1
            host_end = host_num
        if host_end <= host_start:
            host_end = host_start + 1

        task_dir = base_dir / f"task{task_index + 1}"
        if task_dir.exists():
            shutil.rmtree(task_dir)
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "logs").mkdir(parents=True, exist_ok=True)

        operate_path = task_dir / "rdma_operate0.txt"
        flows_written = write_rdm_operate_file(operate_path, host_start, host_end, msg_len_bytes)

        dependence_path = task_dir / "dependence.txt"
        write_dependence_file(dependence_path)

        rdma_task_dir = rdma_dir / f"task{task_index + 1}"
        rdma_task_dir.mkdir(parents=True, exist_ok=True)
        rdma_operate_copy = rdma_task_dir / "rdma_operate0.txt"
        shutil.copyfile(operate_path, rdma_operate_copy)

        all_file_path = all_files_dir / f"rdma_operate{global_file_index}.txt"
        shutil.copyfile(operate_path, all_file_path)
        global_file_index += 1

        task_summaries.append({
            "task": task_index + 1,
            "host_range": f"{host_start}-{host_end - 1}",
            "flow_files": [str(operate_path.relative_to(base_dir))],
            "flow_count": flows_written
        })

    return task_summaries


def is_ecmp_module_ready() -> bool:
    return all(callable(fn) for fn in (ecmp_get_rdma_files, ecmp_load_file, ecmp_find_paths))


def _split_token(token: str) -> Dict[str, Any]:
    token = token.strip()
    entry: Dict[str, Any] = {"raw": token}
    if not token:
        return entry
    prefix = token[0]
    suffix = token[1:] if len(token) > 1 else ""
    if prefix == "N":
        entry["kind"] = "node"
        try:
            entry["id"] = int(suffix)
        except ValueError:
            entry["id"] = suffix or token
    elif prefix == "P":
        entry["kind"] = "port"
        try:
            entry["id"] = int(suffix)
        except ValueError:
            entry["id"] = suffix or token
    else:
        entry["kind"] = "unknown"
        entry["id"] = token
    return entry


def _expand_port_segments(port_segments: List[str]) -> List[Dict[str, Any]]:
    expanded: List[Dict[str, Any]] = []
    for segment in port_segments:
        pieces = [piece for piece in segment.split("->") if piece]
        expanded.extend(_split_token(piece) for piece in pieces)
    return expanded


def _normalize_ecmp_flow(stage_name: str,
                         flow_info_map: Dict[int, Tuple[int, int]],
                         flow_paths: List[Tuple[int, List[int]]],
                         flow_ports: List[Tuple[int, List[str]]]) -> List[Dict[str, Any]]:
    node_lookup = {fid: nodes for fid, nodes in flow_paths}
    port_lookup = {fid: ports for fid, ports in flow_ports}
    normalized: List[Dict[str, Any]] = []
    for flow_id, (src_node, dst_node) in flow_info_map.items():
        nodes = node_lookup.get(flow_id, [])
        ports = port_lookup.get(flow_id, [])
        normalized.append({
            "stage": stage_name,
            "flow_id": flow_id,
            "src": src_node,
            "dst": dst_node,
            "node_path": nodes,
            "port_steps": ports,
            "expanded_sequence": _expand_port_segments(ports)
        })
    return normalized


def _parse_actual_paths_from_logs(dump_dir: Path) -> List[Dict[str, Any]]:
    """
    从仿真日志文件中解析实际路径
    
    Args:
        dump_dir: dump 目录路径（包含 system*.log 文件）
    
    Returns:
        解析后的实际路径列表，格式与 expected 路径相同
    """
    import re
    actual_paths = []
    
    if not dump_dir.exists() or not dump_dir.is_dir():
        print(f"[WARNING] dump目录不存在: {dump_dir}")
        return []
    
    # 查找所有 system*.log 文件
    log_files = sorted(dump_dir.glob("system*.log"))
    if not log_files:
        print(f"[WARNING] 未找到仿真日志文件: {dump_dir}/system*.log")
        return []
    
    print(f"[INFO] 从 {len(log_files)} 个日志文件中解析实际路径...")
    
    for log_file in log_files:
        try:
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or "Flow actual path:" not in line:
                        continue
                    
                    # 解析格式: "system 0 from 0 to 1 ... Flow actual path: 0:1 -> 64:2 -> 1:0"
                    # 使用正则表达式提取源节点、目标节点和路径
                    match = re.search(r'from\s+(\d+)\s+to\s+(\d+).*?Flow actual path:\s*(.+)', line)
                    if not match:
                        continue
                    
                    src_node = int(match.group(1))
                    dst_node = int(match.group(2))
                    path_str = match.group(3).strip()
                    
                    # 解析路径: "0:1 -> 64:2 -> 1:0" -> [0, 64, 1]
                    node_path = []
                    port_steps = []
                    for part in path_str.split(' -> '):
                        part = part.strip()
                        if ':' in part:
                            node_id_str, port_str = part.split(':', 1)
                            node_id = int(node_id_str)
                            port_id = int(port_str)
                            node_path.append(node_id)
                            port_steps.append(f"N{node_id}->P{port_id}")
                        else:
                            # 如果没有端口号，只提取节点ID
                            try:
                                node_id = int(part)
                                node_path.append(node_id)
                            except ValueError:
                                continue
                    
                    if len(node_path) < 2:
                        continue
                    
                    # 构建与 expected 路径相同格式的数据
                    actual_paths.append({
                        "stage": log_file.stem,  # 例如 "system1"
                        "flow_id": len(actual_paths) + 1,  # 简单的ID分配
                        "src": src_node,
                        "dst": dst_node,
                        "node_path": node_path,
                        "port_steps": port_steps,
                        "expanded_sequence": port_steps  # 简化处理，直接使用 port_steps
                    })
        
        except Exception as e:
            print(f"[WARNING] 解析日志文件失败 {log_file}: {e}")
            continue
    
    print(f"[INFO] 解析完成，共 {len(actual_paths)} 条实际路径")
    return actual_paths


def _compute_ecmp_for_directory(rdma_stage_dir: Path, mode: str = "expected") -> List[Dict[str, Any]]:
    """
    计算 ECMP 路径
    
    Args:
        rdma_stage_dir: rdma_result 目录路径
        mode: 计算模式，"expected" 或 "actual"
    
    Returns:
        ECMP 路径列表
    """
    if mode == "actual":
        # 实际路径：从仿真日志文件中解析
        # 查找 dump 目录（通常在 examples/Reverie/dump/）
        # 尝试多个可能的路径找到Reverie目录
        possible_reverie_paths = [
            REVERIE_ROOT,
            REVERIE_ROOT / "examples" / "Reverie",
            REVERIE_ROOT,
        ]
        
        reverie_dir = None
        for path in possible_reverie_paths:
            if path.exists():
                reverie_dir = path
                break
        
        if reverie_dir is None:
            reverie_dir = REVERIE_ROOT  # 默认路径
        
        base_dir = reverie_dir
        dump_dir = reverie_dir / "dump"
        
        # 如果当前目录是 workflow 输出目录，尝试从 workflow 输出中查找 dump
        if "workflow_output" in str(rdma_stage_dir):
            # 尝试从 workflow 输出目录的上级目录查找 dump
            workflow_base = rdma_stage_dir.parent.parent.parent
            dump_dir = workflow_base / "dump"
            if not dump_dir.exists():
                # 如果 workflow 输出中没有 dump，使用默认的 dump 目录
                dump_dir = base_dir / "dump"
        
        return _parse_actual_paths_from_logs(dump_dir)
    
    # Expected 路径：基于 XML 文件计算
    if not is_ecmp_module_ready():
        return []

    if not rdma_stage_dir.exists() or not rdma_stage_dir.is_dir():
        return []

    results: List[Dict[str, Any]] = []
    for stage_entry in sorted(rdma_stage_dir.iterdir()):
        if not stage_entry.is_dir():
            continue
        rdma_files = ecmp_get_rdma_files(str(stage_entry))
        if not rdma_files:
            continue
        try:
            flow_info_list, link_info_list, route_table, link_map, reverse_link_map, *_ = ecmp_load_file(
                str(stage_entry), rdma_files
            )
            flow_map = {flow.flow_id: (flow.src_node, flow.dst_node) for flow in flow_info_list}
            node_paths, port_paths = ecmp_find_paths(
                flow_info_list, link_info_list, route_table, link_map, reverse_link_map
            )
            normalized = _normalize_ecmp_flow(stage_entry.name, flow_map, node_paths, port_paths)
            results.extend(normalized)
        except Exception as exc:
            print(f"[WARNING] ECMP计算失败 {stage_entry}: {exc}")
    return results


def _read_ecmp_cache() -> Dict[str, Any]:
    if not ECMP_CACHE_FILE.exists():
        return {}
    try:
        with open(ECMP_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_ecmp_cache(payload: Dict[str, Any]) -> None:
    ECMP_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = ECMP_CACHE_FILE.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp_path.replace(ECMP_CACHE_FILE)


def compute_and_cache_ecmp(mode: str, rdma_root: Optional[Path] = None) -> Dict[str, Any]:
    """
    计算并缓存 ECMP 路径
    
    Args:
        mode: 计算模式，"expected" 或 "actual"
        rdma_root: rdma_result 目录路径（对于 actual 模式，用于查找 dump 目录）
    
    Returns:
        计算结果的字典
    """
    mode_key = "actual" if mode == "actual" else "expected"
    
    # 对于 actual 模式，不需要 ecmp_module，直接从日志解析
    if mode == "actual":
        rdma_root = rdma_root or (REVERIE_ROOT / "rdma_result")
    else:
        # expected 模式需要 ecmp_module
        if not is_ecmp_module_ready():
            return {}
        rdma_root = rdma_root or (REVERIE_ROOT / "rdma_result")

    with ECMP_CACHE_LOCK:
        cache = _read_ecmp_cache()
        computed = _compute_ecmp_for_directory(rdma_root, mode=mode)
        cache.setdefault("metadata", {})
        cache[mode_key] = {
            "timestamp": time.time(),
            "rdma_root": str(rdma_root),
            "count": len(computed),
            "paths": computed
        }
        cache["metadata"]["last_mode"] = mode_key
        cache["metadata"]["updated_at"] = time.time()
        _write_ecmp_cache(cache)
        return cache[mode_key]


@app.post("/compute-ecmp")
async def compute_ecmp_endpoint(mode: str = "expected", directory: str = "rdma_result", use_latest_workflow: bool = False):
    """
    手动触发 ECMP 计算，补齐 ecmp_paths_cache.json。
    
    Args:
        mode: 计算模式，'expected' 或 'actual'
        directory: 如果 use_latest_workflow=False，则使用此目录（相对于 examples/Reverie）
        use_latest_workflow: 如果为 True，则从最新的 workflow 输出目录读取
    """
    try:
        if use_latest_workflow:
            # 从最新的 workflow 输出目录读取
            generator_dir = REVERIE_ROOT / "Generator" / "Generator"
            output_base = generator_dir / "workflow_output"
            if not output_base.exists():
                raise HTTPException(status_code=404, detail=f"Workflow输出目录不存在: {output_base}")
            
            # 查找最新的输出目录
            output_dirs = sorted(
                [d for d in output_base.iterdir() if d.is_dir()],
                key=lambda x: x.stat().st_mtime,
                reverse=True
            )
            if not output_dirs:
                raise HTTPException(status_code=404, detail="未找到Workflow输出目录")
            
            latest_dir = output_dirs[0]
            rdma_root = latest_dir / "2_traffic" / "rdma_result"
            if not rdma_root.exists():
                raise HTTPException(status_code=404, detail=f"Workflow RDMA目录不存在: {rdma_root}")
        else:
            # 使用指定的目录
            rdma_root = (REVERIE_ROOT / directory).resolve()
            if not rdma_root.exists():
                raise HTTPException(status_code=404, detail=f"RDMA目录不存在: {rdma_root}")
        
        result = compute_and_cache_ecmp(mode=mode, rdma_root=rdma_root)
        return {
            "success": True,
            "mode": mode,
            "rdma_root": str(rdma_root),
            "count": result.get("count", 0)
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"计算ECMP失败: {exc}")


def get_cached_ecmp_data() -> Dict[str, Any]:
    with ECMP_CACHE_LOCK:
        return _read_ecmp_cache()

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
        
        if request.task_num <= 0:
            raise HTTPException(status_code=400, detail="task_num必须大于0")

        msg_len_bytes = _parse_msg_len_expr(request.msg_len)

        base_dir = REVERIE_ROOT
        model_key = (request.model_name or "").lower()
        
        # 优先使用 Generator/Generator/TrafficGenerator（与 workflow 一致，有 merge_dependency.py）
        # Reverie/TrafficGenerator 作为备选
        possible_base_paths = [
            REVERIE_ROOT / "Generator" / "Generator" / "TrafficGenerator",
            REVERIE_ROOT / "TrafficGenerator",
        ]
        rel_paths_map = {
            0: "Generator/Generator/TrafficGenerator/task1",
            1: "TrafficGenerator/task1",
        }
        
        traffic_gen_dir = None
        load_directory_candidate = None
        for i, path in enumerate(possible_base_paths):
            if path.exists() and (path / "trafficGen.py").exists():
                traffic_gen_dir = path
                load_directory_candidate = rel_paths_map.get(i, rel_paths_map[0])
                break
        
        # 如果找不到 TrafficGenerator，只在需要时（qwen/deepseek模型）才报错
        # 对于 custom 模型，不需要 TrafficGenerator
        if traffic_gen_dir is None and model_key in {"deepseek", "qwen"}:
            raise HTTPException(status_code=500, detail=f"未找到 TrafficGenerator 目录，尝试的路径: {[str(p) for p in possible_base_paths]}")

        if model_key in {"deepseek", "qwen"}:
            template_path = traffic_gen_dir / f"{model_key}.txt"
            trafficgen_config = _build_trafficgen_config(
                template_path=template_path,
                host_num=request.host_num,
                msg_len_expr=request.msg_len,
                dp=request.dp
            )
            input_path = traffic_gen_dir / f"{model_key}_input_autogen.txt"
            with open(input_path, 'w', encoding='utf-8') as f:
                f.write(trafficgen_config)

            traffic_gen_script = traffic_gen_dir / "trafficGen.py"
            if not traffic_gen_script.exists():
                raise FileNotFoundError(f"trafficGen.py 不存在: {traffic_gen_script}")

            traffic_run = subprocess.run(
                [sys.executable, str(traffic_gen_script), "--input_file", str(input_path)],
                cwd=str(traffic_gen_dir),
                capture_output=True,
                text=True
            )
            if traffic_run.returncode != 0:
                raise RuntimeError(
                    "trafficGen.py 执行失败\n"
                    f"stdout: {traffic_run.stdout}\n"
                    f"stderr: {traffic_run.stderr}"
                )

            merge_script = traffic_gen_dir / "merge_rdma.sh"
            if merge_script.exists():
                merge_run = subprocess.run(
                    ["bash", str(merge_script)],
                    cwd=str(traffic_gen_dir),
                    capture_output=True,
                    text=True
                )
                if merge_run.returncode != 0:
                    raise RuntimeError(
                        "merge_rdma.sh 执行失败\n"
                        f"stdout: {merge_run.stdout}\n"
                        f"stderr: {merge_run.stderr}"
                    )

            # 用实际配置生成 dependence.txt（64 节点等），与 trafficGen 输出 operate 数量一致
            merge_dep_script = traffic_gen_dir / "merge_dependency.py"
            autogen_input = traffic_gen_dir / f"{model_key}_input_autogen.txt"
            if merge_dep_script.exists() and autogen_input.exists():
                merge_dep_run = subprocess.run(
                    [sys.executable, str(merge_dep_script), str(autogen_input)],
                    cwd=str(traffic_gen_dir),
                    capture_output=True,
                    text=True
                )
                if merge_dep_run.returncode != 0:
                    print(f"[WARNING] merge_dependency 失败，将使用默认无依赖: {merge_dep_run.stderr}")

            # _write_task_inputs_from_all_rdma_files 需要包含 rdma_result 的 base_dir
            # rdma_result 在 traffic_gen_dir 下，所以使用 traffic_gen_dir 作为 base_dir
            task_summaries = _write_task_inputs_from_all_rdma_files(
                base_dir=traffic_gen_dir,
                task_num=request.task_num
            )
            load_content = trafficgen_config
            load_filename = f"{model_key}_trafficgen.txt"
            load_mode_text = "trafficGen"
        else:
            # 生成负载配置内容（返回给前端展示）
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
            # 生成任务目录与操作文件
            task_summaries = generate_task_inputs(
                base_dir=base_dir,
                host_num=request.host_num,
                msg_len_bytes=msg_len_bytes,
                task_num=request.task_num
            )
            load_filename = f"{request.model_name}_load.txt"
            load_mode_text = "simple"

        ecmp_preview_payload: Optional[Dict[str, Any]] = None
        if is_ecmp_module_ready():
            try:
                ecmp_preview_payload = compute_and_cache_ecmp(
                    mode="expected",
                    rdma_root=base_dir / "rdma_result"
                )
            except Exception as compute_exc:
                print(f"[WARNING] ECMP预览生成失败: {compute_exc}")

        if not task_summaries:
            raise HTTPException(status_code=500, detail="未能生成任何任务流量，请检查输入参数")

        # 将流量复制到仿真执行目录 flow-input-repo/examples/Reverie/task1/
        task_sources = [base_dir]
        if traffic_gen_dir is not None:
            task_sources.insert(0, traffic_gen_dir)
        _sync_task_to_reverie_exec_dir(task_sources, request.task_num)

        task_info_text = "; ".join(
            f"任务{item['task']} 主机范围 {item['host_range']} 流量文件 {len(item['flow_files'])} 个"
            for item in task_summaries
        )
        
        load_directory = load_directory_candidate if (model_key in {"deepseek", "qwen"} and traffic_gen_dir is not None) else None

        return LoadResponse(
            success=True,
            content=load_content,
            filename=load_filename,
            message=f"成功生成负载配置（模式: {load_mode_text}）：{request.host_num}个节点，流量大小{request.msg_len}，任务数 {len(task_summaries)}。{task_info_text}",
            task_summary=task_summaries,
            ecmp_preview=ecmp_preview_payload,
            host_num=request.host_num,
            load_directory=load_directory
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] 生成负载配置时发生异常: {str(e)}\n{error_trace}")
        raise HTTPException(status_code=500, detail=f"生成负载配置时出错: {str(e)}")


@app.post("/generate-load-from-file", response_model=LoadResponse)
async def generate_load_from_file(
    traffic_file: UploadFile = File(...),
    task_num: int = Form(1)
):
    """
    通过上传自定义流量 ZIP 包生成负载配置。
    ZIP 需包含：多 rdma_operate*.txt + dependence.txt，仅支持 task_num=1。
    """
    try:
        if task_num <= 0:
            raise HTTPException(status_code=400, detail="task_num必须大于0")

        base_dir = REVERIE_ROOT
        raw_bytes = await traffic_file.read()
        filename = traffic_file.filename or "custom_traffic.zip"

        if not filename.lower().endswith(".zip"):
            raise HTTPException(status_code=400, detail="请上传 ZIP 包（多 rdma_operate*.txt + dependence.txt）")

        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
            tmp.write(raw_bytes)
            tmp_path = Path(tmp.name)
        try:
            task_summaries, host_num, load_directory = _process_full_format_zip(tmp_path, base_dir, task_num)
        finally:
            tmp_path.unlink(missing_ok=True)
        _sync_task_to_reverie_exec_dir([base_dir], task_num)
        ecmp_preview_payload: Optional[Dict[str, Any]] = None
        if is_ecmp_module_ready():
            try:
                ecmp_preview_payload = compute_and_cache_ecmp(
                    mode="expected",
                    rdma_root=base_dir / "rdma_result"
                )
            except Exception as exc:
                print(f"[WARNING] 自定义流量ECMP预览失败: {exc}")
        total_flows = sum(s.get("flow_count", 0) for s in task_summaries)
        return LoadResponse(
            success=True,
            content="",
            filename=filename,
            message=f"自定义流量解析完成，共 {total_flows} 条流量，任务数 1",
            task_summary=task_summaries,
            ecmp_preview=ecmp_preview_payload,
            host_num=host_num,
            load_directory=load_directory
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"自定义流量解析失败: {str(e)}")

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
    num_hosts: int = 0  # 主机数量
    num_tor: int = 0    # TOR数量
    num_spine: int = 0  # Spine数量

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
    total_nodes = num_hosts + num_leaves + num_spines  # 总节点数
    total_switches = num_leaves + num_spines  # 总交换机数
    total_links = num_hosts + (num_leaves * num_spines)  # 主机到Leaf的链路 + Leaf到Spine的链路
    
    # 生成拓扑内容
    content_lines = []
    
    # 第一行：总节点数 总交换机数 TOR数 总链路数 服务器带宽 交换机带宽
    # 这个格式与sim.cc的期望匹配：node_num switch_num tors link_num LEAF_SERVER_CAPACITY SPINE_LEAF_CAPACITY
    content_lines.append(f"{total_nodes} {total_switches} {num_leaves} {total_links} {int(serverDataRate*1e9)} {int(allOtherDataRate*1e9)}")
    
    # 第二行：所有交换机节点ID列表（先Leaf再Spine）
    # sim.cc期望读取switch_num个交换机ID，前tors个是Leaf，后面是Spine
    leafIndexBegin = num_hosts  # Leaf从主机数后开始
    spineIndexBegin = num_hosts + num_leaves  # Spine从Leaf后开始
    
    switch_ids = []
    # 先添加所有Leaf交换机ID
    for i in range(num_leaves):
        switch_ids.append(str(leafIndexBegin + i))
    # 再添加所有Spine交换机ID
    for i in range(num_spines):
        switch_ids.append(str(spineIndexBegin + i))
    
    content_lines.append(" ".join(switch_ids))
    
    # 服务器到TOR的连接
    for i in range(torSwitches):
        for j in range(serversPerTor):
            server_id = j + serversPerTor * i
            tor_id = leafIndexBegin + i  # 使用之前定义的leafIndexBegin
            content_lines.append(f"{server_id} {tor_id} {int(serverDataRate*1e9)} {serverTorDelay} {errorRate}")
    
    # TOR到Spine的连接
    for i in range(torSwitches):
        for j in range(spineSwitches):
            tor_id = leafIndexBegin + i  # TOR就是Leaf
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
        topology_file = REVERIE_ROOT / "leaf-spine.txt"
        with open(topology_file, 'w', encoding='utf-8') as f:
            f.write(topology_content)
        
        # 计算主机数量
        num_hosts = request.torSwitches * request.serversPerTor
        
        return TopologyResponse(
            success=True,
            content=topology_content,
            filename="leaf-spine.txt",
            message=f"成功生成拓扑：{request.torSwitches}个TOR，{request.spineSwitches}个Spine，{num_hosts}个主机，已保存到 {topology_file}",
            num_hosts=num_hosts,
            num_tor=request.torSwitches,
            num_spine=request.spineSwitches
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成拓扑时出错: {str(e)}")

# ==================== Workflow 自动化接口 ====================

class WorkflowRequest(BaseModel):
    """Workflow 执行请求模型"""
    hosts: int = 64  # 主机数量
    leafs: int = 8   # Leaf交换机数量
    spines: int = 4  # Spine交换机数量
    host_bw: int = 200  # 主机到Leaf带宽 (Gbps)，与 auto_gen_topo.py 默认值一致
    leaf_spine_bw: int = 400  # Leaf到Spine带宽 (Gbps)，与 auto_gen_topo.py 默认值一致（原为800，已修正）
    model: str = "qwen"  # 大模型类型: qwen 或 deepseek
    enable_treecut: bool = True  # 是否启用通信树分割

class WorkflowResponse(BaseModel):
    """Workflow 执行响应模型"""
    success: bool
    message: str
    workflow_id: str
    output_directory: str = ""
    status: str = "running"  # running, completed, failed

@app.post("/run-workflow", response_model=WorkflowResponse)
async def run_workflow(request: WorkflowRequest, background_tasks: BackgroundTasks):
    """
    执行完整的 Workflow 自动化流程
    
    包括：
    1. 生成拓扑 → dcn2.0_config.xml 和 router_mine.xml
    2. 生成流量 → rdma_operate*.txt
    3. 生成 ECMP 路径 → 将 XML 文件复制到 rdma_result 子目录
    4. 通信树分割（可选）
    """
    try:
        import subprocess
        import time
        
        # 生成唯一的 workflow ID
        workflow_id = f"workflow_{int(time.time())}"
        
        # 构建 run_all.py 的命令
        generator_dir = REVERIE_ROOT / "Generator" / "Generator"
        run_all_script = generator_dir / "run_all.py"
        
        print(f"[DEBUG] run-workflow: generator_dir={generator_dir}, run_all_script={run_all_script}, exists={run_all_script.exists()}")
        
        if not run_all_script.exists():
            raise HTTPException(
                status_code=404, 
                detail=f"Workflow脚本不存在: {run_all_script}"
            )
        
        # 构建命令行参数
        cmd = [
            sys.executable,
            str(run_all_script),
            "--hosts", str(request.hosts),
            "--leafs", str(request.leafs),
            "--spines", str(request.spines),
            "--host-bw", str(request.host_bw),
            "--leaf-spine-bw", str(request.leaf_spine_bw),
            "--model", request.model
        ]
        
        # 注意：run_all.py 默认启用 treecut，所以不需要额外参数
        # 如果 disable_treecut，可以添加 --skip-treecut（如果支持的话）
        
        # 在后台执行 workflow
        def execute_workflow():
            try:
                result = subprocess.run(
                    cmd,
                    cwd=str(generator_dir),
                    capture_output=True,
                    text=True,
                    timeout=3600  # 1小时超时
                )
                # 可以在这里处理结果，比如更新状态等
                print(f"Workflow {workflow_id} completed with return code: {result.returncode}")
            except subprocess.TimeoutExpired:
                print(f"Workflow {workflow_id} timed out")
            except Exception as e:
                print(f"Workflow {workflow_id} failed: {e}")
        
        # 添加到后台任务
        background_tasks.add_task(execute_workflow)
        
        # 计算输出目录（workflow 会在 workflow_output 下创建时间戳目录）
        output_base = generator_dir / "workflow_output"
        
        return WorkflowResponse(
            success=True,
            message=f"Workflow已启动，正在后台执行。ID: {workflow_id}",
            workflow_id=workflow_id,
            output_directory=str(output_base),
            status="running"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"启动Workflow失败: {str(e)}"
        )

@app.get("/workflow-status/{workflow_id}")
async def get_workflow_status(workflow_id: str):
    """
    获取 Workflow 执行状态
    
    通过检查 workflow_output 目录下的最新输出目录来判断状态
    """
    try:
        generator_dir = REVERIE_ROOT / "Generator" / "Generator"
        output_base = generator_dir / "workflow_output"
        
        if not output_base.exists():
            return {
                "success": False,
                "status": "not_found",
                "message": "Workflow输出目录不存在"
            }
        
        # 查找最新的输出目录
        output_dirs = sorted(
            [d for d in output_base.iterdir() if d.is_dir()],
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )
        
        if not output_dirs:
            return {
                "success": False,
                "status": "not_found",
                "message": "未找到Workflow输出目录"
            }
        
        latest_dir = output_dirs[0]
        
        # 检查各个步骤的输出
        has_topology = (latest_dir / "1_topology" / "dcn2.0_config.xml").exists()
        has_traffic = (latest_dir / "2_traffic" / "rdma_result").exists()
        has_paths = (latest_dir / "3_paths" / "ecmp_outputs").exists()
        has_treecut = (latest_dir / "4_treecut").exists()
        
        # 判断状态
        if has_topology and has_traffic and has_paths and has_treecut:
            status = "completed"
        elif has_topology:
            status = "in_progress"
        else:
            status = "running"
        
        return {
            "success": True,
            "status": status,
            "workflow_id": workflow_id,
            "output_directory": str(latest_dir),
            "steps": {
                "topology": has_topology,
                "traffic": has_traffic,
                "paths": has_paths,
                "treecut": has_treecut
            }
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"获取Workflow状态失败: {str(e)}"
        )

# ==================== 仿真控制接口相关 ====================

class SimulationRequest(BaseModel):
    task_num: int = 1  # 1=不开启切分，4=开启切分
    llm_model: str = "deepseek"  # 模型名称
    enable_mixed_granularity: bool = True  # 是否启用混合粒度
    simulation_time: float = 10.0  # 仿真时间（秒）
    use_custom_config: bool = False  # 是否使用前端生成的自定义拓扑/负载输入
    load_source: Optional[str] = None  # "custom"=自定义ZIP, "generated"/"workflow"=trafficGen(qwen/deepseek)

class SimulationResponse(BaseModel):
    success: bool
    message: str
    simulation_id: str
    status: str
    results: Dict[str, Any]

def modify_sim_script(task_num: int, llm_model: str):
    """修改sim.sh脚本中的参数"""
    sim_script_path = REVERIE_ROOT / "sim.sh"
    
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
    # qbb-net-device.cc 在 flow-input-repo 中
    # 尝试多个可能的路径
    possible_qbb_paths = [
        SRC_ROOT / "point-to-point" / "model" / "qbb-net-device.cc",
        REVERIE_ROOT.parent.parent / "src" / "point-to-point" / "model" / "qbb-net-device.cc",
    ]
    
    qbb_file_path = None
    for path in possible_qbb_paths:
        if path.exists():
            qbb_file_path = path
            break
    
    print(f"[DEBUG] modify_qbb_device: qbb_file_path={qbb_file_path}, exists={qbb_file_path.exists() if qbb_file_path else False}")
    
    if qbb_file_path is None or not qbb_file_path.exists():
        raise FileNotFoundError(f"qbb-net-device.cc文件不存在，尝试的路径: {[str(p) for p in possible_qbb_paths]}")
    
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
                  enable_mixed_granularity: bool, simulation_time: float,
                  use_custom_config: bool, load_source: Optional[str] = None):
    """运行仿真（后台任务）"""
    # 创建日志目录
    api_dir = API_DIR
    logs_dir = api_dir / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    # 生成带时间戳的日志文件名
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    log_filename = f"simulation_{simulation_id}_{timestamp}.log"
    log_file_path = logs_dir / log_filename
    
    try:
        # 修改配置文件
        modify_qbb_device(enable_mixed_granularity)
        
        # 切换到Reverie目录（NS3代码在flow-input-repo中）
        # 尝试多个可能的路径
        possible_reverie_paths = [
            REVERIE_ROOT,
            REVERIE_ROOT / "examples" / "Reverie",
            REVERIE_ROOT,
        ]
        
        reverie_dir = None
        for path in possible_reverie_paths:
            if path.exists() and (path / "sim.sh").exists():
                reverie_dir = path
                break
        
        if reverie_dir is None:
            raise RuntimeError(f"未找到Reverie目录，尝试的路径: {[str(p) for p in possible_reverie_paths]}")
        
        # 写入日志文件头部
        with open(log_file_path, 'w', encoding='utf-8') as log_file:
            log_file.write("=" * 80 + "\n")
            log_file.write(f"仿真日志 - {simulation_id}\n")
            log_file.write(f"时间戳: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            log_file.write("=" * 80 + "\n")
            log_file.write(f"仿真ID: {simulation_id}\n")
            log_file.write(f"工作目录: {reverie_dir}\n")
            log_file.write(f"任务数: {task_num}\n")
            log_file.write(f"模型: {llm_model}\n")
            log_file.write(f"混合粒度: {enable_mixed_granularity}\n")
            log_file.write(f"仿真模式: 跑完为止（END_TIME 上限 10 天）\n")
            log_file.write(f"使用自定义配置: {use_custom_config}\n")
            log_file.write("=" * 80 + "\n\n")
        
        print(f"[仿真启动] {simulation_id}, 日志文件: {log_file_path}")
        if use_custom_config:
            # 同步：将模块1/2生成的数据复制到 flow-input-repo
            # load_source=custom 时自定义流量在 api_base/task1，必须优先用 api_base，否则会误用 tg_dir 的 deepseek
            api_base = REVERIE_ROOT
            tg_dir = api_base / "Generator" / "Generator" / "TrafficGenerator"
            tg_parent = api_base.parent / "Generator" / "Generator" / "TrafficGenerator"
            if (load_source or "").lower() == "custom":
                possible_task_sources = [api_base, tg_dir, tg_parent]
            else:
                possible_task_sources = [tg_dir, tg_parent, api_base]
            # 1. 同步拓扑 leaf-spine.txt（若 src 与 dst 相同则跳过，避免 SameFileError）
            src_topology = api_base / "leaf-spine.txt"
            dst_topology = reverie_dir / "leaf-spine.txt"
            if src_topology.exists():
                if src_topology.resolve() != dst_topology.resolve():
                    shutil.copy2(src_topology, dst_topology)
                    with open(log_file_path, 'a', encoding='utf-8') as log_file:
                        log_file.write(f"[同步] 拓扑已复制: {src_topology} -> {dst_topology}\n")
                else:
                    with open(log_file_path, 'a', encoding='utf-8') as log_file:
                        log_file.write(f"[同步] 拓扑已在 Reverie 内，无需复制\n")
            else:
                with open(log_file_path, 'a', encoding='utf-8') as log_file:
                    log_file.write(f"[警告] 源拓扑文件不存在: {src_topology}，使用 reverie 目录现有文件\n")
            # 2. 同步 task1, task2, ...
            for task_index in range(1, task_num + 1):
                src_task = None
                for src_base in possible_task_sources:
                    cand = src_base / f"task{task_index}"
                    if cand.exists() and (cand / "rdma_operate0.txt").exists():
                        src_task = cand
                        break
                if src_task is not None:
                    dst_task = reverie_dir / f"task{task_index}"
                    if src_task.resolve() == dst_task.resolve():
                        with open(log_file_path, 'a', encoding='utf-8') as log_file:
                            log_file.write(f"[同步] 任务{task_index}已在 Reverie 内，无需复制\n")
                    else:
                        if dst_task.exists():
                            shutil.rmtree(dst_task)
                        shutil.copytree(src_task, dst_task)
                        with open(log_file_path, 'a', encoding='utf-8') as log_file:
                            log_file.write(f"[同步] 任务{task_index}已复制: {src_task} -> {dst_task}\n")
            for task_index in range(1, task_num + 1):
                task_dir = reverie_dir / f"task{task_index}"
                if not task_dir.exists():
                    raise RuntimeError(f"找不到自定义任务目录: {task_dir}")
                rdma_file = task_dir / "rdma_operate0.txt"
                dependence_file = task_dir / "dependence.txt"
                if not rdma_file.exists() or not dependence_file.exists():
                    raise RuntimeError(f"自定义任务 {task_index} 缺少必要文件 rdma_operate0.txt 或 dependence.txt")
        
        # 设置运行状态
        simulation_status.is_running = True
        simulation_status.current_task = simulation_id
        simulation_status.simulation_start_time = time.time()
        
        # 使用Popen启动仿真进程（非阻塞）
        sim_script_path = reverie_dir / "sim.sh"
        
        # 记录路径信息到日志
        with open(log_file_path, 'a', encoding='utf-8') as log_file:
            log_file.write(f"脚本路径: {sim_script_path}\n")
            log_file.write(f"脚本存在: {sim_script_path.exists()}\n")
            log_file.write(f"dump目录: {reverie_dir / 'dump'}\n")
            log_file.write(f"dump目录存在: {(reverie_dir / 'dump').exists()}\n\n")
        
        if not sim_script_path.exists():
            error_msg = f"sim.sh文件不存在: {sim_script_path}"
            with open(log_file_path, 'a', encoding='utf-8') as log_file:
                log_file.write(f"错误: {error_msg}\n")
            raise FileNotFoundError(error_msg)
        
        # 启动仿真进程
        env = os.environ.copy()
        # 设置编码环境变量，避免 Windows 上的编码问题
        env["PYTHONIOENCODING"] = "utf-8"
        env["LC_ALL"] = "C.UTF-8"
        env["LLM_OVERRIDE"] = llm_model
        env["TASKNUM_OVERRIDE"] = str(task_num)
        if use_custom_config:
            env["USE_CUSTOM_LOAD"] = "1"
        else:
            env.pop("USE_CUSTOM_LOAD", None)

        try:
            sim_time_seconds = float(simulation_time)
        except (TypeError, ValueError):
            sim_time_seconds = 10.0
        sim_time_seconds = max(sim_time_seconds, 0.1)
        flow_launch_seconds = max(sim_time_seconds * 0.1, 0.001)
        # sim.cc 期望 END_TIME 单位为秒，直接传秒
        env["SIM_END_TIME_SEC_OVERRIDE"] = str(sim_time_seconds)
        env["SIM_FLOW_LAUNCH_END_SEC_OVERRIDE"] = str(flow_launch_seconds)
        
        with open(log_file_path, 'a', encoding='utf-8') as log_file:
            log_file.write(f"环境变量:\n")
            log_file.write(f"  LLM_OVERRIDE={env.get('LLM_OVERRIDE')}\n")
            log_file.write(f"  TASKNUM_OVERRIDE={env.get('TASKNUM_OVERRIDE')}\n")
            log_file.write(f"  USE_CUSTOM_LOAD={env.get('USE_CUSTOM_LOAD', '0')}\n")
            log_file.write(f"  SIM_END_TIME_SEC_OVERRIDE={env.get('SIM_END_TIME_SEC_OVERRIDE')}\n")
            log_file.write(f"  SIM_FLOW_LAUNCH_END_SEC_OVERRIDE={env.get('SIM_FLOW_LAUNCH_END_SEC_OVERRIDE')}\n\n")
            log_file.write(f"开始执行仿真脚本...\n")
        
        process = subprocess.Popen(
            ['bash', str(sim_script_path)],
            cwd=str(reverie_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env
        )
        
        # 保存进程信息
        simulation_status.current_process = process
        
        # 等待进程完成（在后台任务中）；仿真为“跑完为止”，预留至少 2 倍 sim 上限时间
        timeout_duration = max(sim_time_seconds * 2, 86400.0 * 2)  # 至少 2 天，避免提前杀进程
        with open(log_file_path, 'a', encoding='utf-8') as log_file:
            log_file.write(f"等待进程完成，超时时间: {timeout_duration}秒\n")
        
        stdout, stderr = process.communicate(timeout=timeout_duration)
        
        # 写入详细日志到文件
        with open(log_file_path, 'a', encoding='utf-8') as log_file:
            log_file.write("\n" + "=" * 80 + "\n")
            log_file.write("仿真执行结果\n")
            log_file.write("=" * 80 + "\n")
            log_file.write(f"返回码: {process.returncode}\n")
            log_file.write(f"执行时间: {time.time() - simulation_status.simulation_start_time:.2f}秒\n")
            log_file.write("\n" + "=" * 80 + "\n")
            log_file.write("STDOUT 输出:\n")
            log_file.write("=" * 80 + "\n")
            if stdout:
                log_file.write(stdout)
            else:
                log_file.write("(无输出)\n")
            log_file.write("\n" + "=" * 80 + "\n")
            log_file.write("STDERR 输出:\n")
            log_file.write("=" * 80 + "\n")
            if stderr:
                log_file.write(stderr)
            else:
                log_file.write("(无错误输出)\n")
        
        # 仿真完成
        simulation_status.simulation_end_time = time.time()
        simulation_status.is_running = False
        simulation_status.current_process = None

        # 确保 evaluation.fct1 与前端期望一致
        try:
            dump_dir = reverie_dir / "dump"
            primary_fct = dump_dir / "evaluation.fct1"
            if dump_dir.exists():
                needs_copy = True
                if primary_fct.exists() and primary_fct.stat().st_size > 0:
                    needs_copy = False
                if needs_copy:
                    for candidate in sorted(dump_dir.glob("evaluation.fct*")):
                        if candidate == primary_fct:
                            continue
                        try:
                            if candidate.stat().st_size > 0:
                                shutil.copyfile(candidate, primary_fct)
                                break
                        except FileNotFoundError:
                            continue
        except Exception as copy_err:
            print(f"[WARNING] Failed to normalize evaluation.fct1: {copy_err}")
        
        # 分析结果
        results = analyze_simulation_results()

        try:
            if is_ecmp_module_ready():
                compute_and_cache_ecmp(
                    mode="actual",
                    rdma_root=REVERIE_ROOT / "rdma_result"
                )
        except Exception as ecmp_exc:
            print(f"[WARNING] ECMP实际路径计算失败: {ecmp_exc}")

        # 增强稳态信息（包含仿真时间和挂钟时间）
        steady_times_ns: List[float] = []
        evaluation_out_path = reverie_dir / "dump" / "evaluation.out"
        if evaluation_out_path.exists():
            try:
                with open(evaluation_out_path, 'r', encoding='utf-8', errors='ignore') as f:
                    eval_log_content = f.read()
                steady_analysis = analyze_steady_state_from_evaluation(eval_log_content)
                results["steady_state_analysis"] = steady_analysis
                steady_times_ns = steady_analysis.get("steady_times_ns", []) or []
            except Exception as eval_err:
                print(f"[WARNING] Failed to analyze evaluation.out for steady state: {eval_err}")

        steady_events: List[Dict[str, Any]] = []
        simulation_start_wall = simulation_status.simulation_start_time
        for ns_value in steady_times_ns:
            try:
                ns_float = float(ns_value)
            except (TypeError, ValueError):
                continue
            if not simulation_start_wall:
                wall_clock_ts = None
            else:
                wall_clock_ts = simulation_start_wall + (ns_float / 1e9)
            steady_events.append({
                "sim_time_ns": ns_float,
                "wall_clock_ts": wall_clock_ts,
                "wall_clock_iso": datetime.fromtimestamp(wall_clock_ts).isoformat() if wall_clock_ts else None
            })
        steady_events = sorted(steady_events, key=lambda x: x["sim_time_ns"])
        deduped_events: List[Dict[str, Any]] = []
        last_ns = None
        epsilon_ns = 1.0  # 1ns tolerance
        for event in steady_events:
            ns_float = event.get("sim_time_ns")
            if last_ns is not None and ns_float is not None and abs(ns_float - last_ns) <= epsilon_ns:
                continue
            deduped_events.append(event)
            last_ns = ns_float

        if deduped_events:
            results.setdefault("steady_state_info", {}).setdefault("steady_times_ns", steady_times_ns)
            results["steady_state_wall_times"] = deduped_events
            results["steady_state_info"]["steady_wall_times"] = deduped_events

        simulation_status.results[simulation_id] = results
        
        # 检查输出文件
        dump_dir = reverie_dir / "dump"
        with open(log_file_path, 'a', encoding='utf-8') as log_file:
            log_file.write("\n" + "=" * 80 + "\n")
            log_file.write("输出文件检查\n")
            log_file.write("=" * 80 + "\n")
            if dump_dir.exists():
                log_file.write(f"dump目录存在: {dump_dir}\n")
                for f in dump_dir.glob("*"):
                    size = f.stat().st_size if f.is_file() else 0
                    log_file.write(f"  {f.name}: {size} 字节\n")
            else:
                log_file.write(f"警告: dump目录不存在: {dump_dir}\n")
        
        print(f"仿真完成: {simulation_id}, 耗时: {simulation_status.simulation_end_time - simulation_status.simulation_start_time:.2f}秒, 日志: {log_file_path}")
        
        return {
            "success": True,
            "simulation_id": simulation_id,
            "execution_time": simulation_status.simulation_end_time - simulation_status.simulation_start_time,
            "results": results,
            "stdout": stdout,
            "stderr": stderr,
            "log_file": str(log_file_path)
        }
        
    except subprocess.TimeoutExpired:
        simulation_status.is_running = False
        simulation_status.current_process = None
        error_msg = "仿真超时"
        with open(log_file_path, 'a', encoding='utf-8') as log_file:
            log_file.write(f"\n错误: {error_msg}\n")
        print(f"[仿真超时] {simulation_id}, 日志: {log_file_path}")
        return {
            "success": False,
            "error": error_msg,
            "simulation_id": simulation_id,
            "log_file": str(log_file_path)
        }
    except Exception as e:
        simulation_status.is_running = False
        simulation_status.current_process = None
        error_msg = str(e)
        import traceback
        error_trace = traceback.format_exc()
        
        with open(log_file_path, 'a', encoding='utf-8') as log_file:
            log_file.write("\n" + "=" * 80 + "\n")
            log_file.write("仿真执行异常\n")
            log_file.write("=" * 80 + "\n")
            log_file.write(f"错误信息: {error_msg}\n")
            log_file.write(f"\n堆栈跟踪:\n")
            log_file.write(error_trace)
        
        print(f"[仿真异常] {simulation_id}: {error_msg}, 日志: {log_file_path}")
        return {
            "success": False,
            "error": error_msg,
            "simulation_id": simulation_id,
            "log_file": str(log_file_path)
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
        fct_file = REVERIE_ROOT / "dump" / "evaluation.fct1"
        if fct_file.exists():
            with open(fct_file, 'r') as f:
                fct_content = f.read()
            results["fct_results"] = parse_fct_results(fct_content)
        
        # 分析系统日志
        log_file = REVERIE_ROOT / "dump" / "system1.log"
        if log_file.exists():
            with open(log_file, 'r') as f:
                log_content = f.read()
            results["steady_state_info"] = parse_steady_state_info(log_content)
            results["performance_metrics"] = parse_performance_metrics(log_content)
        
        # 分析流统计
        flow_stats_file = REVERIE_ROOT / "flow_stats.txt"
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

@app.get("/check-task-dirs")
async def check_task_dirs(task_num: int = 4):
    """检查 task 目录是否存在且包含必要文件"""
    # 尝试多个可能的路径找到Reverie目录
    possible_reverie_paths = [
        REVERIE_ROOT,
        REVERIE_ROOT / "examples" / "Reverie",
        REVERIE_ROOT,
    ]
    
    reverie_dir = None
    for path in possible_reverie_paths:
        if path.exists():
            reverie_dir = path
            break
    
    if reverie_dir is None:
        reverie_dir = REVERIE_ROOT  # 默认路径
    missing_dirs = []
    missing_files = []
    
    for task_index in range(1, task_num + 1):
        task_dir = reverie_dir / f"task{task_index}"
        if not task_dir.exists():
            missing_dirs.append(f"task{task_index}")
            continue
        
        rdma_file = task_dir / "rdma_operate0.txt"
        dependence_file = task_dir / "dependence.txt"
        
        if not rdma_file.exists():
            missing_files.append(f"task{task_index}/rdma_operate0.txt")
        if not dependence_file.exists():
            missing_files.append(f"task{task_index}/dependence.txt")
    
    all_exist = len(missing_dirs) == 0 and len(missing_files) == 0
    
    return {
        "success": True,
        "all_exist": all_exist,
        "task_num": task_num,
        "missing_dirs": missing_dirs,
        "missing_files": missing_files,
        "message": "所有目录和文件都存在" if all_exist else f"缺少目录: {missing_dirs}, 缺少文件: {missing_files}"
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
        request.simulation_time,
        request.use_custom_config,
        request.load_source
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

def analyze_flow_rates_for_steady_state(flow_stats_file: Path) -> dict:
    """
    分析flow_stats.txt中的流速率,判断是否达到稳态
    稳态条件: 每个流的速率在连续10个周期内保持稳定(变化 < 1e-6 Gbps)
    """
    flow_rates = {}  # {flow_id: [rate1, rate2, ...]}
    
    with open(flow_stats_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            # 解析: Flow ID: 0-1-1000-1000 - Rate: 24.336 Gbps currentTime: 14689
            match = re.search(r'Flow ID:\s+([\d\-]+)\s+-\s+Rate:\s+([\d.]+)\s+Gbps', line)
            if match:
                flow_id = match.group(1)
                rate = float(match.group(2))
                
                if flow_id not in flow_rates:
                    flow_rates[flow_id] = []
                flow_rates[flow_id].append(rate)
    
    # 判断每个流是否稳态(最近10个点速率变化 < 1e-6)
    steady_flows = 0
    total_flows = len(flow_rates)
    flow_details = []
    
    for flow_id, rates in flow_rates.items():
        if len(rates) >= 10:
            recent_rates = rates[-10:]
            rate_diff = max(recent_rates) - min(recent_rates)
            is_flow_steady = rate_diff < 1e-6
            
            if is_flow_steady:
                steady_flows += 1
            
            flow_details.append({
                "flow_id": flow_id,
                "rate_count": len(rates),
                "recent_avg": sum(recent_rates) / len(recent_rates),
                "rate_variation": rate_diff,
                "is_steady": is_flow_steady
            })
    
    # 系统稳态: 所有流都稳态
    is_system_steady = (total_flows > 0 and steady_flows == total_flows)
    
    return {
        "is_steady": is_system_steady,
        "steady_count": 1 if is_system_steady else 0,
        "message": f"系统稳态: {steady_flows}/{total_flows} 个流达到稳态" if total_flows > 0 else "无流数据",
        "details": flow_details[:20],  # 只返回前20个流的详情
        "flow_stats": {
            "total_flows": total_flows,
            "steady_flows": steady_flows,
            "unstable_flows": total_flows - steady_flows
        }
    }

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
    dump_dir = REVERIE_ROOT / "dump"
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
    获取稳态状态（通过分析flow_stats.txt中的流速率数据来判断稳态）
    不再依赖C++代码输出,而是Python自己分析
    """
    # 使用相对路径查找 flow_stats.txt
    base_dir = REVERIE_ROOT
    flow_stats_file = base_dir / "flow_stats.txt"
    
    if not flow_stats_file.exists():
        # 尝试其他可能的路径
        flow_stats_file = REVERIE_ROOT.parent / "flow_stats.txt"
    
    if not flow_stats_file.exists():
        return {
            "is_steady": False,
            "message": "flow_stats.txt 文件不存在",
            "timestamp": time.time(),
            "details": []
        }
    
    try:
        # 分析流速率数据来判断稳态
        steady_info = analyze_flow_rates_for_steady_state(flow_stats_file)
        
        return {
            "is_monitoring": True,
            "is_steady": steady_info["is_steady"],
            "steady_state_count": steady_info["steady_count"],
            "timestamp": time.time(),
            "message": steady_info["message"],
            "details": steady_info["details"],
            "flow_analysis": steady_info["flow_stats"]
        }
    except Exception as e:
        return {
            "is_steady": False,
            "message": f"分析失败: {str(e)}",
            "timestamp": time.time(),
            "details": []
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
        file_path = REVERIE_ROOT / "TrafficGenerator" / request.filename
        
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
        # 尝试多个可能的路径找到Reverie目录
        possible_reverie_paths = [
            REVERIE_ROOT,
            REVERIE_ROOT / "examples" / "Reverie",
            REVERIE_ROOT,
        ]
        
        reverie_dir = None
        for path in possible_reverie_paths:
            if path.exists():
                reverie_dir = path
                break
        
        if reverie_dir is None:
            reverie_dir = REVERIE_ROOT  # 默认路径
        
        base_dir = reverie_dir
        exp_dump = reverie_dir / "dump"
        baseline_dump = reverie_dir / "dump_baseline"
        exp_backup = reverie_dir / "dump_experiment"
        baseline_meta_path = baseline_dump / "metadata.json"

        current_signature = _compute_load_signature(base_dir)
        current_task_flow_count = _count_task_flow_records(base_dir)
        baseline_meta = _read_baseline_meta(baseline_meta_path)
        baseline_signature = baseline_meta.get("load_signature")
        baseline_strategy = "task_backup_v2"
        baseline_strategy_meta = baseline_meta.get("baseline_strategy")
        baseline_task_flow_count_meta = int(baseline_meta.get("task_flow_count", -1))
        
        # 检查实验 dump 是否比基线 dump 新（如果实验重新运行了，即使流量相同，也应该刷新基线）
        exp_dump_newer = False
        if exp_dump.exists() and baseline_dump.exists():
            exp_fct = exp_dump / "evaluation.fct1"
            base_fct = baseline_dump / "evaluation.fct1"
            if exp_fct.exists() and base_fct.exists():
                exp_mtime = exp_fct.stat().st_mtime
                base_mtime = base_fct.stat().st_mtime
                if exp_mtime > base_mtime:
                    exp_dump_newer = True
                    print(f"[INFO] 检测到实验 dump 比基线 dump 新（实验: {exp_mtime}, 基线: {base_mtime}），将刷新基线")
        
        baseline_needs_refresh = (
            (not _has_dump_payload(baseline_dump))
            or (current_signature and current_signature != baseline_signature)
            or (baseline_strategy_meta != baseline_strategy)
            or (baseline_task_flow_count_meta != current_task_flow_count)
            or exp_dump_newer  # 如果实验 dump 比基线 dump 新，强制刷新基线
        )

        if not exp_dump.exists():
            raise HTTPException(status_code=404, detail="实验dump目录不存在，请先运行仿真")

        if baseline_needs_refresh:
            # 保存当前实验结果
            if _has_dump_payload(exp_dump):
                _copy_dump_files(exp_dump, exp_backup)
            task_backup_root = None
            # 运行包粒度基线（不开切分 + 不开混合粒度）
            baseline_status.is_running = True
            baseline_status.last_started = time.time()
            try:
                # 基线应使用与当前实验完全一致的流量集合（仅关闭切分/混合粒度）。
                # 直接从实验任务备份聚合到单任务，避免 all_rdma_files 来源不一致导致流数偏差。
                task_backup_root = _backup_task_dirs(base_dir)
                _prepare_single_baseline_task_from_backup(base_dir=base_dir, backup_root=task_backup_root)
                # 清空 dump 目录，确保基线仿真生成新的结果文件
                if exp_dump.exists():
                    for f in exp_dump.glob("*"):
                        if f.is_file():
                            f.unlink()
                        elif f.is_dir():
                            shutil.rmtree(f)
                run_simulation(
                    simulation_id="baseline_packet",
                    task_num=1,
                    llm_model="deepseek",
                    enable_mixed_granularity=False,
                    simulation_time=10.0,
                    use_custom_config=True
                )
                _copy_dump_files(exp_dump, baseline_dump)
            finally:
                # 恢复实验任务目录与结果
                _restore_task_dirs(base_dir, task_backup_root)
                if _has_dump_payload(exp_backup):
                    _copy_dump_files(exp_backup, exp_dump)
                baseline_status.is_running = False
                baseline_status.last_finished = time.time()
            _write_baseline_meta(baseline_meta_path, {
                "load_signature": current_signature,
                "generated_at": time.time(),
                "baseline_strategy": baseline_strategy,
                "task_flow_count": current_task_flow_count
            })

        results = _collect_analysis_from_dump(exp_dump, request.analysis_type)
        baseline_results = _collect_analysis_from_dump(baseline_dump, request.analysis_type)
        results["baseline_analysis"] = baseline_results
        results["baseline_status"] = {
            "load_signature": baseline_signature,
            "current_signature": current_signature,
            "needs_refresh": baseline_needs_refresh
        }
        results["comparison"] = _compute_comparison(results, baseline_results)

        summary = generate_analysis_summary(results)
        
        return AnalysisResponse(
            success=True,
            analysis_type=request.analysis_type,
            results=results,
            summary=summary
        )
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] 分析结果时发生异常: {str(e)}\n{error_trace}")
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
    
    # 对FCT值进行抽样，用于绘制折线图（最多1000个点）
    sorted_fct = sorted(fct_values)
    sample_size = min(1000, len(sorted_fct))
    sampled_fct_values = []
    if sample_size > 0:
        step = len(sorted_fct) / sample_size
        for i in range(sample_size):
            idx = int(i * step)
            if idx < len(sorted_fct):
                sampled_fct_values.append(sorted_fct[idx])
    
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
        },
        "sampled_fct_values": sampled_fct_values  # 抽样后的FCT值列表，用于绘制折线图
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
    
    total_time_ms = None
    simulation_time_ms = None

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
        
        # 提取总时间/仿真时间（ms）
        if total_time_ms is None:
            time_match = re.search(r'total\s+time:\s*([\d\.]+)\s*ms', line, flags=re.IGNORECASE)
            if time_match:
                total_time_ms = float(time_match.group(1))
        if simulation_time_ms is None:
            sim_match = re.search(r'simulation\s+time:\s*([\d\.]+)\s*ms', line, flags=re.IGNORECASE)
            if sim_match:
                simulation_time_ms = float(sim_match.group(1))
    
    # 计算统计信息
    result = {
        "has_data": True,
        "file_size": len(content),
        "total_lines": len(lines),
        "total_time_ms": total_time_ms,
        "simulation_time_ms": simulation_time_ms,
        "total_time_sec": total_time_ms / 1000.0 if total_time_ms is not None else None,
        "simulation_time_sec": simulation_time_ms / 1000.0 if simulation_time_ms is not None else None,
        "runtime_ratio": (total_time_ms / simulation_time_ms) if total_time_ms and simulation_time_ms else None,
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
            # 检查是否有实际解析成功的数据（不仅检查total_flows，还要检查是否有average_fct_us等有效数据）
            has_valid_data = fct.get('average_fct_us', 0) > 0 or (fct.get('total_flows', 0) > 0 and fct.get('average_fct_us') is not None)
            if has_valid_data:
                summary_parts.append(
                    f"FCT分析: 总流数={fct.get('total_flows', 0)}, "
                    f"平均FCT={fct.get('average_fct_us', 0):.2f}μs ({fct.get('average_fct_ms', 0):.2f}ms), "
                    f"平均slowdown={fct.get('average_slowdown', 0):.2f}"
                )
            else:
                parse_error = fct.get('parse_error', '')
                if parse_error:
                    summary_parts.append(f"FCT分析: 文件已找到但解析失败 - {parse_error}")
                else:
                    summary_parts.append(f"FCT分析: 文件已找到但数据为空 (总行数={fct.get('total_flows', 0)})")
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

    comparison = results.get("comparison")
    if isinstance(comparison, dict) and comparison.get("fct_fidelity") is not None:
        summary_parts.append(
            f"对比分析: FCT保真度={comparison.get('fct_fidelity'):.3f}, "
            f"加速比={comparison.get('speedup', 0):.3f}"
        )
    
    return "; ".join(summary_parts) if summary_parts else "暂无仿真结果，请先运行仿真"

# ==================== 通用接口 ====================

@app.get("/complete_frontend.html")
async def get_frontend():
    """提供前端HTML页面"""
    html_file = API_DIR / "complete_frontend.html"
    if html_file.exists():
        return FileResponse(html_file, media_type="text/html")
    else:
        raise HTTPException(status_code=404, detail="前端页面未找到")

@app.get("/vue.global.js")
async def get_vuejs():
    """提供Vue.js文件"""
    js_file = API_DIR / "vue.global.js"
    if js_file.exists():
        return FileResponse(js_file, media_type="application/javascript")
    else:
        raise HTTPException(status_code=404, detail="Vue.js文件未找到")

@app.get("/d3.v7.min.js")
async def get_d3js():
    """提供D3.js文件"""
    js_file = API_DIR / "d3.v7.min.js"
    if js_file.exists():
        return FileResponse(js_file, media_type="application/javascript")
    else:
        raise HTTPException(status_code=404, detail="D3.js文件未找到")

@app.get("/three.min.js")
async def get_threejs():
    """提供Three.js文件（离线可用）"""
    js_file = API_DIR / "three.min.js"
    if js_file.exists():
        return FileResponse(js_file, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="Three.js文件未找到，请下载到api目录")

@app.get("/OrbitControls.js")
async def get_orbit_controls():
    """提供OrbitControls.js文件（离线可用）"""
    js_file = API_DIR / "OrbitControls.js"
    if js_file.exists():
        return FileResponse(js_file, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="OrbitControls.js文件未找到，请下载到api目录")

@app.get("/custom-traffic-example.zip")
async def get_custom_traffic_example_zip():
    """提供自定义流量完整格式示例（多 operate + dependence，ZIP 包）"""
    full_dir = API_DIR / "examples" / "custom_traffic_full"
    zip_path = full_dir / "custom_traffic_full.zip"
    if zip_path.exists():
        return FileResponse(zip_path, media_type="application/zip", filename="custom_traffic_full.zip")
    # 从目录动态打包
    operate_files = sorted(full_dir.glob("rdma_operate*.txt"), key=lambda p: (int(re.search(r"(\d+)", p.name).group(1)) if re.search(r"(\d+)", p.name) else 0, p.name))
    dep_file = full_dir / "dependence.txt"
    if not operate_files:
        raise HTTPException(status_code=404, detail="完整格式示例不存在，请检查 examples/custom_traffic_full 目录")
    from io import BytesIO
    buf = BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in operate_files:
            zf.write(f, f.name)
        if dep_file.exists():
            zf.write(dep_file, dep_file.name)
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type="application/zip", headers={"Content-Disposition": "attachment; filename=custom_traffic_full.zip"})

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

@app.get("/baseline-status")
async def baseline_status_check():
    """检查包粒度基线结果是否存在"""
    base_dir = REVERIE_ROOT
    baseline_dump = base_dir / "dump_baseline"
    current_signature = _compute_load_signature(base_dir)
    baseline_meta = _read_baseline_meta(baseline_dump / "metadata.json")
    baseline_signature = baseline_meta.get("load_signature")
    return {
        "success": True,
        "has_baseline": _has_dump_payload(baseline_dump),
        "is_running": baseline_status.is_running,
        "last_started": baseline_status.last_started,
        "last_finished": baseline_status.last_finished,
        "needs_refresh": bool(current_signature and current_signature != baseline_signature)
    }

# ==================== 文件访问接口 ====================

import mimetypes

@app.get("/read-file")
async def read_file(file_path: str):
    """读取文件内容"""
    try:
        # 安全检查：确保文件路径在项目目录内
        base_dir = REVERIE_ROOT
        
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
        base_dir = REVERIE_ROOT.resolve()
        api_dir = API_DIR.resolve()
        
        # 处理路径，统一使用正斜杠，去除前导斜杠
        directory = directory.replace('\\', '/').strip('/')
        
        print(f"[DEBUG] list-files: directory={directory}, base_dir={base_dir}, api_dir={api_dir}")
        
        # 尝试多个可能的路径（TreeGroup可能在api/或Reverie/下）
        possible_paths = [
            (base_dir / directory).resolve(),  # 示例：examples/Reverie/rdma_result
            (api_dir / directory).resolve(),   # 示例：examples/Reverie/api/rdma_result
        ]
        
        full_path = None
        for path in possible_paths:
            print(f"[DEBUG] 尝试路径: {path}, exists={path.exists()}, is_dir={path.is_dir() if path.exists() else False}")
            if path.exists() and path.is_dir():
                # 安全检查：确保路径在项目目录内
                try:
                    # 使用 relative_to 进行更可靠的路径检查
                    path.relative_to(base_dir)
                    full_path = path
                    print(f"[DEBUG] 找到路径（相对于base_dir）: {full_path}")
                    break
                except ValueError:
                    try:
                        path.relative_to(api_dir)
                        full_path = path
                        print(f"[DEBUG] 找到路径（相对于api_dir）: {full_path}")
                        break
                    except ValueError:
                        print(f"[DEBUG] 路径安全检查失败: {path}")
                        continue
        
        if full_path is None:
            # 如果都找不到，尝试最后一个：直接使用base_dir/directory
            full_path = (base_dir / directory).resolve()
            print(f"[DEBUG] 尝试最后路径: {full_path}, exists={full_path.exists()}")
            if not full_path.exists():
                raise HTTPException(status_code=404, detail=f"目录不存在: {directory}（已尝试多个路径）")
        
        # 再次安全检查：使用 relative_to 方法更可靠
        try:
            full_path.relative_to(base_dir)
        except ValueError:
            try:
                full_path.relative_to(api_dir)
            except ValueError:
                print(f"[ERROR] 路径安全检查失败: {full_path} 不在 {base_dir} 或 {api_dir} 下")
                raise HTTPException(status_code=403, detail=f"禁止访问此路径: {directory}")
        
        files = []
        for item in full_path.iterdir():
            # 计算相对于base_dir的路径
            try:
                rel_path = str(item.relative_to(base_dir))
            except ValueError:
                # 如果不在base_dir下，尝试相对于api_dir
                try:
                    rel_path = str(item.relative_to(api_dir))
                except ValueError:
                    rel_path = str(item.name)
            
            files.append({
                "name": item.name,
                "path": rel_path,
                "is_dir": item.is_dir(),
                "size": item.stat().st_size if item.is_file() else 0
            })
        
        return {
            "success": True,
            "directory": directory,
            "files": files
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"列出文件时出错: {str(e)}")

# ==================== 拓扑可视化接口 ====================

@app.post("/visualize-topology")
async def visualize_topology(background_tasks: BackgroundTasks):
    """生成拓扑可视化图片"""
    try:
        # 尝试多个可能的路径找到Reverie目录
        possible_reverie_paths = [
            REVERIE_ROOT,
            REVERIE_ROOT / "examples" / "Reverie",
            REVERIE_ROOT,
        ]
        
        reverie_dir = None
        for path in possible_reverie_paths:
            if path.exists():
                reverie_dir = path
                break
        
        if reverie_dir is None:
            reverie_dir = REVERIE_ROOT  # 默认路径
        
        # 导入拓扑可视化模块 - 需要添加到sys.path
        api_dir = reverie_dir / "api"
        if str(api_dir) not in sys.path:
            sys.path.insert(0, str(api_dir))
        
        from topology_visualization import draw_improved_topology
        
        # 拓扑文件路径 - 优先使用 generate-topology 写入的路径（与生成拓扑接口一致）
        api_base = REVERIE_ROOT
        possible_topology_files = [
            api_base / "leaf-spine.txt",  # generate-topology 写入的位置，优先使用
            reverie_dir / "leaf-spine.txt",
            reverie_dir / "api" / "leaf-spine.txt",
            REVERIE_ROOT / "leaf-spine.txt",
        ]
        
        topology_file = None
        for path in possible_topology_files:
            if path.exists():
                topology_file = path
                break
        
        if topology_file is None:
            raise HTTPException(status_code=404, detail="拓扑文件不存在，请先生成拓扑")
        
        # 生成图片 - 保存到api目录
        output_file = api_dir / "topology_latest.png"
        draw_improved_topology(topology_file, output_file)
        
        return {
            "success": True,
            "message": "拓扑可视化生成成功",
            "image_path": "api/topology_latest.png"
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] 生成拓扑可视化时发生异常: {str(e)}\n{error_trace}")
        raise HTTPException(status_code=500, detail=f"生成拓扑可视化时出错: {str(e)}")

@app.get("/get-topology-image")
async def get_topology_image():
    """获取拓扑可视化图片"""
    try:
        # 尝试多个可能的路径找到Reverie目录
        possible_reverie_paths = [
            REVERIE_ROOT,
            REVERIE_ROOT / "examples" / "Reverie",
            REVERIE_ROOT,
        ]
        
        reverie_dir = None
        for path in possible_reverie_paths:
            if path.exists():
                reverie_dir = path
                break
        
        if reverie_dir is None:
            reverie_dir = REVERIE_ROOT  # 默认路径
        
        # 尝试多个可能的位置
        possible_image_files = [
            reverie_dir / "api" / "topology_latest.png",
            API_DIR / "topology_latest.png",
        ]
        
        image_file = None
        for path in possible_image_files:
            if path.exists():
                image_file = path
                break
        
        if image_file is None:
            raise HTTPException(status_code=404, detail="拓扑图片不存在，请先生成")
        
        return FileResponse(image_file, media_type="image/png")
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[ERROR] 获取拓扑图片时发生异常: {str(e)}\n{error_trace}")
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