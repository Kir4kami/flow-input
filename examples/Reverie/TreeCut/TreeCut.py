import networkx as nx
import matplotlib.pyplot as plt
import copy
from collections import defaultdict
from .DocProcess import process_file
import os
import json

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
    nodes_passed = process_file(file_path)
    # nodes_passed = [random.choice(['A', 'B', 'C', 'D', 'E']) for _ in range(random.randint(1, 3))]
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

# 找出所有的叶子节点(“毛刺”)，将无兄弟节点的叶子节点向上合并（视为“揉球”操作）
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

# 对通信树进行预处理，修剪“毛刺”节点
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

# 主要的拓扑切分函数
def performTreeCut(tree_data=None, output_dir="TreeGroup", show_graphs=False):
    """
    执行拓扑切分的主要函数
    
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

if __name__ == '__main__':
    # 创建一个有向图
    T = nx.DiGraph()
    # 添加根节点
    T.add_node(root_node, name='Root', nodes_passed=[], children=[])
    # 构建通信树
    constructTree(T, root_node)
    ShowGraph(T)
    T = preTreatment(T)
    Tree_copy = copy.deepcopy(T)
    splitCommunicationTree(T)
    for item in Tree_list:
        print(item.edges())
        ShowGraph(item)
    makeInDependenceInfo(Tree_list)
    makeOutDependenceInfo(out_dependence_list, Tree_list)