#!/usr/bin/env python3
import networkx as nx
import matplotlib
# 设置非交互模式（避免在无GUI环境下报错）
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import copy
from collections import defaultdict
from DocProcess import process_file
import os


# 可配置的目录路径（支持环境变量）
ECMP_OUTPUTS_DIR = os.getenv('ECMP_OUTPUTS_DIR', './ecmp_outputs')
TREE_GROUP_DIR = os.getenv('TREE_GROUP_DIR', './TreeGroup')

# 根节点
root_node = 'Root'

# 切割后树的列表集合
Tree_list = []

# 分别设置dp，pp，tp的rdma_operate的数量
DP = 16
PP = 8
TP = 8
EP = 8

#存储外部依赖关系
out_dependence_list = []

# 定义添加节点的方法
# 向图G添加一个新节点和边。新节点代表通信操作（如TP、EP、PP、DP
def addCommunicationEdge(G, layer, comm_type, pre_node):
    #node_name = f"{comm_type}{layer}_{len(G.nodes)}" # 基于类型、层级和当前节点总数
    node_name = f"{len(G.nodes)}_{comm_type}{layer}" # 基于类型、层级和当前节点总数
    # 使用函数
    file_path = f"{ECMP_OUTPUTS_DIR}/{node_name}.txt" # 使用可配置的路径
    nodes_passed = process_file(file_path)
    # nodes_passed = [random.choice(['A', 'B', 'C', 'D', 'E']) for _ in range(random.randint(1, 3))]
    G.add_node(node_name, name=node_name, type=comm_type, layer=layer, nodes_passed=nodes_passed, children=[])
    G.add_edge(pre_node, node_name)
    return node_name

# 构建通信树 - 动态版本，从流量输入文件构建
def constructTreeDynamic(G, root_node, traffic_input_file):
    """
    从流量输入文件动态构建通信树
    
    参数:
        G: NetworkX有向图
        root_node: 根节点名称
        traffic_input_file: 流量输入文件路径（如 qwen.txt）
    """
    import re
    
    if not os.path.exists(traffic_input_file):
        raise FileNotFoundError(f"流量输入文件不存在: {traffic_input_file}")
    
    node_name_mapping = {}  # 映射逻辑节点名（如TP1）到实际生成名（如1_TP1）
    global_node_counter = 1  # 与 trafficGen_add.py 保持一致
    
    with open(traffic_input_file, 'r') as f:
        lines = f.readlines()
    
    # 跳过第一行（模型配置）
    for line_num, line in enumerate(lines[1:], 2):
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        parts = re.split(r'\s+', line)
        if len(parts) < 3:
            continue
        
        layer = parts[0]
        mode = parts[1]  # TP, EP, PP, DP
        parent_nodes_str = parts[2]
        
        # 解析父节点（支持 / 分割的多父节点）
        parent_nodes = parent_nodes_str.split('/')
        
        # 映射父节点名称
        mapped_parent_nodes = []
        for parent_node in parent_nodes:
            if parent_node == 'Root':
                mapped_parent_nodes.append(root_node)
            elif parent_node in node_name_mapping:
                mapped_parent_nodes.append(node_name_mapping[parent_node])
            else:
                print(f"警告: 未找到父节点 {parent_node}，跳过")
                continue
        
        if not mapped_parent_nodes:
            print(f"警告: 行{line_num}没有有效的父节点，跳过")
            continue
        
        # 生成节点名称（与 trafficGen_add.py 一致）
        generated_node_name = f"{global_node_counter}_{mode}{layer}"
        
        # 检查对应的 ecmp_outputs 文件是否存在
        file_path = f"{ECMP_OUTPUTS_DIR}/{generated_node_name}.txt"
        if not os.path.exists(file_path):
            print(f"警告: 文件不存在 {file_path}，使用空节点列表")
            nodes_passed = []
        else:
            nodes_passed = process_file(file_path)
        
        # 添加节点
        G.add_node(generated_node_name, name=generated_node_name, type=mode, 
                   layer=layer, nodes_passed=nodes_passed, children=[])
        
        # 添加边（连接所有父节点）
        for parent_node in mapped_parent_nodes:
            G.add_edge(parent_node, generated_node_name)
        
        # 更新映射
        # 从输入文件推断逻辑节点名
        mode_count = sum(1 for k in node_name_mapping.keys() if k.startswith(mode)) + 1
        logical_name = f"{mode}{mode_count}"
        node_name_mapping[logical_name] = generated_node_name
        
        global_node_counter += 1

# 构建通信树 - 硬编码版本（保留向后兼容）
def constructTreeStatic(G, root_node):
    """
    硬编码的通信树构建（原版本）
    仅在没有提供流量输入文件时使用
    """

   #root0 = addCommunicationEdge(G, 1, "MoE_Dispatch", root_node)
   #root1 = addCommunicationEdge(G, 1, "TopK_Dispatch", root_node)
   #root2 = addCommunicationEdge(G, 1, "AllGather_Aggregation", root_node)
   #root3 = addCommunicationEdge(G, 2, "Score_Expansion", root2)
   #root4 = addCommunicationEdge(G, 3, "Value_Simplification", root3)
   #root5 = addCommunicationEdge(G, 4, "Head_Reduce", root4)
    
    TP1 = addCommunicationEdge(G, 1, "TP", root_node)
    EP1 = addCommunicationEdge(G, 2, "EP", TP1)
    PP1 = addCommunicationEdge(G, 3, "PP", EP1)
    TP2 = addCommunicationEdge(G, 4, "TP", PP1)
    TP3 = addCommunicationEdge(G, 4, "TP", PP1)
    EP2 = addCommunicationEdge(G, 5, "EP", TP2)
    EP3 = addCommunicationEdge(G, 5, "EP", TP3)
    PP2 = addCommunicationEdge(G, 6, "PP", EP2)
    TP4 = addCommunicationEdge(G, 7, "TP", PP2)
    TP4 = addCommunicationEdge(G, 7, "TP", EP3)
    EP4 = addCommunicationEdge(G, 8, "EP", TP4)
    TP5 = addCommunicationEdge(G, 9, "TP", EP4)
    EP5 = addCommunicationEdge(G, 10, "EP", TP5)
    PP3 = addCommunicationEdge(G, 11, "PP", EP5)
    TP6 = addCommunicationEdge(G, 12, "TP", PP3)
    TP7 = addCommunicationEdge(G, 12, "TP", PP3)
    EP6 = addCommunicationEdge(G, 13, "EP", TP6)
    EP7 = addCommunicationEdge(G, 13, "EP", TP7)
    PP4 = addCommunicationEdge(G, 14, "PP", EP7)
    TP8 = addCommunicationEdge(G, 15, "TP", EP6)
    TP8 = addCommunicationEdge(G, 15, "TP", PP4)
    EP8 = addCommunicationEdge(G, 16, "EP", TP8)
    DP1 = addCommunicationEdge(G, 17, "DP", EP8)

# 构建通信树 - 智能选择版本
def constructTree(G, root_node, traffic_input_file=None):
    """
    构建通信树（智能选择静态或动态模式）
    
    参数:
        G: NetworkX有向图
        root_node: 根节点名称
        traffic_input_file: 流量输入文件（可选）
            - 如果提供，使用动态构建
            - 如果不提供，使用硬编码的静态构建
    """
    if traffic_input_file and os.path.exists(traffic_input_file):
        print(f"   使用动态模式构建通信树 (基于 {traffic_input_file})")
        constructTreeDynamic(G, root_node, traffic_input_file)
    else:
        print(f"   使用静态模式构建通信树 (硬编码)")
        constructTreeStatic(G, root_node)

    #DP1 = addCommunicationEdge(G, 1, "DP", root_node)
    #PP1 = addCommunicationEdge(G, 1, "PP", root_node)
    #TP1 = addCommunicationEdge(G, 2, "TP", PP1)
    #TP2 = addCommunicationEdge(G, 3, "TP", TP1)
    #DP2 = addCommunicationEdge(G, 4, "DP", TP2)
    #PP2 = addCommunicationEdge(G, 4, "PP", TP2)
    #TP3 = addCommunicationEdge(G, 5, "TP", PP2)
    #TP4 = addCommunicationEdge(G, 6, "TP", TP3)
    #DP3 = addCommunicationEdge(G, 7, "DP", TP4)
    #PP3 = addCommunicationEdge(G, 7, "PP", TP4)
    #TP5 = addCommunicationEdge(G, 8, "TP", PP3)
    #TP6 = addCommunicationEdge(G, 9, "TP", TP5)
    #DP4 = addCommunicationEdge(G, 10, "DP", TP6)
#
    # DP1 = addCommunicationEdge(G, 1, "DP", root_node)
    # PP1 = addCommunicationEdge(G, 1, "PP", root_node)
    # TP1 = addCommunicationEdge(G, 2, "TP", PP1)
    # TP2 = addCommunicationEdge(G, 3, "TP", TP1)
    # DP2 = addCommunicationEdge(G, 4, "DP", TP2)


# 合并节点
# 将 remove_list 中节点的 nodes_passed 和 children 属性合并到 merge_in_node，用于：
# 预处理阶段（preTreatment）：处理有冲突的“毛刺”节点（叶子节点）。
# 分割阶段（splitCommunicationTree）：合并有兄弟关系的叶子节点到其父节点。
def mergeInfo(Tree, remove_list, merge_in_node):
    # 将所有节点信息merge
    for node in remove_list:
        if merge_in_node != node:
            Tree.nodes[merge_in_node]['nodes_passed'].extend(Tree.nodes[node]['nodes_passed'])
            Tree.nodes[merge_in_node]['children'].append(Tree.nodes[node]['name'])
            for item in Tree.nodes[node]['children']:
                Tree.nodes[merge_in_node]['children'].append(item)


# 将节点从Tree中cut掉，还原节点后添加root节点后插入到Tree_list中
# 从 Tree_copy 中提取以指定节点为根的子树，添加根节点（若非根），并存储到 Tree_list，用于记录分割后的独立子树
def recoverTree(node):
    if node['name'] == 'Root' and len(node['children']) == 0:
        return 0
    node_list = [node['name']]
    node_list.extend(node['children'])
    cut_tree = Tree_copy.subgraph(node_list) # 从 Tree_copy 中提取 node_list 对应节点的子图（包括节点和边）
    cut_tree = nx.DiGraph(cut_tree) # 转换为 nx.DiGraph，确保子图是有向图，保留原始边方向
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

# 从通信树 Tree 中移除指定的毛刺节点（通常是无冲突的叶子节点）。
# 创建一个单节点子树（包含 Root 和该节点），添加到 Tree_list。
# 记录移除节点的外部依赖（节点与其父节点的关系）到 out_dependence_list
def cutBurrNode(Tree, node):
    parents = get_parent(Tree, node)
    out_dependence_list.append((node, parents))
    Tree.remove_node(node)
    cut_tree = nx.DiGraph()
    cut_tree.add_node(root_node)
    cut_tree.add_edge(root_node, node)
    Tree_list.append(cut_tree)


# 找出所有的叶子节点(“毛刺”)，将无兄弟节点的叶子节点向上合并（视为“揉球”操作）
# 识别通信树中的“毛刺”节点（burr nodes），即具有兄弟节点的叶子节点。
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
        # else:
        #     # 接收merge信息
        #     leaf_ball = mergeNodes(Tree, leaf, out_degrees)
        #     leaves_without_siblings.append(leaf_ball)
    return leaves_with_siblings


# 对通信树进行预处理，修剪“毛刺”节点
# 预处理通信树，移除无冲突的毛刺节点（具有兄弟关系的叶子节点，nodes_passed 与非路径节点无交集）。
# 将移除的节点保存为单节点子树（通过 cutBurrNode），并记录外部依赖。
# 简化树结构，为后续分割（splitCommunicationTree）做准备。
def preTreatment(Tree): 
    # 获取所有节点的出度字典
    out_degrees = dict(Tree.out_degree())
    burr_list = findBurr(Tree, out_degrees) #返回有兄弟的叶子节点（父节点出度为 2）
    double_break = False
    for burr_node in burr_list:
        burr_node['checked'] = True
        path_to_root = nx.shortest_path(Tree, source=root_node, target=burr_node["name"])# 从根到当前毛刺节点的路径
        path_nodes = set(path_to_root)# 转换为集合 path_nodes，用于排除路径上的节点，避免重复检查
        # 获取目标节点（毛刺节点）的nodes_passed列表
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
# 从 start_node 开始，向上遍历父节点路径，直到找到一个有兄弟的节点（父节点出度大于 1）或根节点。
# 返回路径上的节点列表（path）和合并目标节点（current_node），用于合并操作（如 mergeInfo）
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
# 处理单个节点，判断其 nodes_passed 是否与其他非路径节点有交集（冲突）。
# 无冲突：切除节点，保存为子树（recoverTree），记录外部依赖。
# 有冲突：向上合并到最近的有兄弟节点或根节点（getRemoveList 和 mergeInfo）
def oneNodeTreatment(Tree, node):
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
        recoverTree(node)
        parents = get_parent(Tree, node["name"])
        out_dependence_list.append((parents, node["name"]))
        Tree.remove_node(node['name'])
    # 如果有冲突，该节点往上到PP都不能切割
    else:
        remove_list, merge_in_node = getRemoveList(Tree, node['name'])
        mergeInfo(Tree, remove_list, merge_in_node)
        for item in remove_list:
            if item != merge_in_node:
                Tree.remove_node(item)
    return Tree


# 找到从根节点（root_node）到所有叶子节点的最长路径（以边数计）。
# 返回所有最长路径的列表，供 splitCommunicationTree 确定最深层的叶子节点，用于递归分割或合并。
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
# 递归分割通信树，将其分解为独立子树，存储在 Tree_list。
# 处理最深层的叶子节点：无冲突的节点切除为子树，有冲突的节点合并到父节点。
# 记录外部依赖（通过 oneNodeTreatment），确保跨子树关系保存
def splitCommunicationTree(Tree):

    # 函数出口,如果图中只剩根节点，那么根节点记录着所有子节点的信息
    if Tree.number_of_nodes() == 1:
        recoverTree(Tree.nodes['Root'])
        return 0
    deepest_path_list = findAllLongestPathsFromRoot(Tree)
    deepest_node_list = []
    for deepest_path in deepest_path_list:
        deepest_node_list.append(deepest_path[-1])

    classification = defaultdict(list)#按路径的最后一个节点（叶子节点）分类

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
            # 对每个节点进行切割和合并
            # +处理
            Tree = oneNodeTreatment(Tree, Tree.nodes[deepest_node[0]])
        # 如果有兄弟节点，进行merge
        else:
            mergeInfo(Tree, deepest_node, list(Tree.predecessors(deepest_node[0]))[0])
            for item in deepest_node:
                Tree.remove_node(item)
    splitCommunicationTree(Tree)

# 为子图中的每个节点分配资源范围（range），基于节点类型（TP, DP, PP）和全局资源大小（TP, DP, PP）。
# 设置节点的 group 属性，标记子图所属组。
# 支持生成内部依赖信息（In_Dependence_Info.txt），用于记录子树内节点的资源分配
def genInDependence(item, folder_name):
    # 初始化 temp
    temp = 0
    # 存储记录结果的字典
    record = {}
    # 遍历图中的每个节点
    for node in item.nodes:
        # 跳过Root节点
        if node == 'Root':
            continue
            
        # 从节点名称中提取类型（格式: "1_TP1" -> "TP"）
        if '_' in node:
            node_type = node.split('_')[1][:2]  # "1_TP1" -> "TP1" -> "TP"
        else:
            node_type = node[:2]  # 兼容旧格式
        
        # 检查节点类型是否与全局变量名称匹配
        if node_type == 'TP':
            record[node] = (temp, temp + TP - 1)
            temp += TP
        elif node_type == 'DP':
            record[node] = (temp, temp + DP - 1)
            temp += DP
        elif node_type == 'PP':
            record[node] = (temp, temp + PP - 1)
            temp += PP
        elif node_type == 'EP':
            record[node] = (temp, temp + EP - 1)
            temp += EP
    # 将 record 写入到 G 的节点属性中
    for node, (start, end) in record.items():
        item.nodes[node]['range'] = f"{start}-{end}"
        item.nodes[node]['group'] = folder_name

def makeInDependenceInfo(Tree_list):
    # 定义目标目录（使用全局变量）
    target_directory = TREE_GROUP_DIR
    # 如果目标目录不存在，则创建
    if not os.path.exists(target_directory):
        os.makedirs(target_directory)
    # 从后向前遍历 Tree_list
    for index, item in enumerate(reversed(Tree_list), start=1):
        # 创建子目录，命名规则为 group1, group2, ..., groupn
        folder_name = f"group{index}"
        folder_path = os.path.join(target_directory, folder_name)
        # 如果子目录不存在，则创建
        if not os.path.exists(folder_path):
            os.makedirs(folder_path)
        genInDependence(item, folder_name);
            
    # 定义输出文件路径
    for index, item in enumerate(reversed(Tree_list), start=1):
        output_file = f"{TREE_GROUP_DIR}/group{index}/In_Dependence_Info.txt"
        isWrite = False
        # 打开文件以写入
        with open(output_file, 'w') as file:
            # 遍历图中的每条边
            for u, v in item.edges:
                # 如果起点是根节点，跳过
                if u == 'Root':
                    continue

                # 获取起点和终点的 range 属性
                start_range = item.nodes[u]['range']
                end_range = item.nodes[v]['range']
                isWrite = True
                # 以指定格式写入文件
                file.write(f"({end_range}):({start_range})\n")
            if not isWrite:
                file.write("Null\n")
            file.write(f"----------------------------------------------------\n")
            # 遍历图中的每条边
            for node in item.nodes:
                # 如果起点是根节点，跳过
                if node == 'Root':
                    continue
                if 'name' not in item.nodes[node] or 'range' not in item.nodes[node]:
                    print(f"Warning: Node {node} missing 'name' or 'range' attributes")
                    continue
                # 以指定格式写入文件
                file.write(f"({item.nodes[node]['name']}):({item.nodes[node]['range']})\n")

def makeOutDependenceInfo(out_dependence_list, Tree_list):
    output_file_path = f'{TREE_GROUP_DIR}/Out_Dependence_Info.txt'
    os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
    # 打开文件，准备写入
    with open(output_file_path, 'w') as file:
        for name, second_element in out_dependence_list:
            # 找元组的第二个位置
            found = False
            for graph in Tree_list:
                for node in graph.nodes(data=True):
                    if node[1].get('name') == second_element:
                        group = node[1].get('group', 'unknown')
                        file.write(f"{group}:")
                        break
                if found:
                    break
            # 找元组的第一个位置
            found = False
            for graph in Tree_list:
                for node in graph.nodes(data=True):
                    if node[1].get('name') == name:
                        group = node[1].get('group', 'unknown')
                        range_val = node[1].get('range', 'N/A')
                        file.write(f"{group}->{range_val}\n")
                        found = True
                        break
                if found:
                    break
# 生成图像
def ShowGraph(G, save_path=None, show=False):
    """
    生成并显示/保存图像
    
    参数:
        G: NetworkX图
        save_path: 保存路径（如果提供）
        show: 是否显示图形界面（默认False，仅保存）
    """
    pos = nx.spring_layout(G)  # 通过Spring布局来展示图
    plt.figure(figsize=(12, 8))
    nx.draw(G, pos, with_labels=True, node_size=500, node_color='skyblue', 
            font_size=10, font_weight='bold', edge_color='gray')
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"   图像已保存: {save_path}")
    
    if show:
        plt.show()
    else:
        plt.close()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='通信树分割工具')
    parser.add_argument('--traffic-input', type=str, default=None,
                       help='流量输入文件路径（如 qwen.txt）')
    parser.add_argument('--no-plot', action='store_true',
                       help='不显示图形界面')
    args = parser.parse_args()
    
    # 创建一个有向图
    T = nx.DiGraph()
    # 添加根节点
    T.add_node(root_node, name='Root', nodes_passed=[], children=[])
    # 构建通信树（智能选择模式）
    constructTree(T, root_node, args.traffic_input)

    # makeTreeGroupDir功能测试
    # i = []
    # i.append(T)
    # makeInDependenceInfo(i)

    # 保存原始树的图像
    os.makedirs(TREE_GROUP_DIR, exist_ok=True)
    ShowGraph(T, save_path=f"{TREE_GROUP_DIR}/original_tree.png", show=(not args.no_plot))
    
    # T.nodes['DP1_1']['nodes_passed'].clear()
    # T.nodes['DP1_1']['nodes_passed'].append('F')
    # 对毛刺节点预处理
    T = preTreatment(T)
    # 对处理后的树进行深拷贝，用于恢复树形
    Tree_copy = copy.deepcopy(T)
    # 对处理过的树进行切分
    splitCommunicationTree(T)
    
    print(f"\n分割结果: 共生成 {len(Tree_list)} 个子树")
    for idx, item in enumerate(Tree_list, 1):
        print(f"  子树{idx}: {len(item.nodes)} 个节点, {len(item.edges)} 条边")
        # 保存每个子树的图像
        ShowGraph(item, save_path=f"{TREE_GROUP_DIR}/subtree_{idx}.png", show=False)

    # InDependenceInfo
    makeInDependenceInfo(Tree_list)
    # OutDependenceInfo
    makeOutDependenceInfo(out_dependence_list, Tree_list)
    
    print(f"\nTreeCut完成！输出目录: {TREE_GROUP_DIR}")