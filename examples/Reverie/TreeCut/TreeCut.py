import networkx as nx
import matplotlib.pyplot as plt
import copy
from collections import defaultdict
import os
import json

# 导入DocProcess，支持相对导入和绝对导入
try:
    from .DocProcess import process_file
except ImportError:
    try:
        from DocProcess import process_file
    except ImportError:
        # 如果都失败，尝试从当前目录导入
        import sys
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
        from DocProcess import process_file

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
    cut_tree.add_node(root_node, name='Root')
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

# 生成3D分层切分可视化HTML（使用D3.js，所有树在同一SVG中）
def visualize3DSplitTreeHTML(original_tree, tree_list, output_path="tree_split_3d.html"):
    """
    生成3D分层切分可视化HTML文件（使用D3.js）
    所有树都绘制在同一个SVG中，确保连接线定位准确
    
    Args:
        original_tree: 原始通信树 (NetworkX DiGraph)
        tree_list: 切分后的子树列表 (list of NetworkX DiGraph)
        output_path: 输出HTML文件路径
    
    Returns:
        str: 保存的HTML文件路径
    """
    import json
    
    # 为每个子树分配颜色（高区分度配色方案）
    colors = [
        '#E74C3C',  # 鲜艳红色
        '#3498DB',  # 明亮蓝色
        '#2ECC71',  # 翠绿色
        '#F39C12',  # 橙色
        '#9B59B6',  # 紫色
        '#1ABC9C',  # 青色
        '#E91E63',  # 粉红色
        '#34495E'   # 深蓝灰色
    ]
    
    # 将NetworkX图转换为JSON格式
    def graph_to_json(graph):
        nodes = []
        edges = []
        for node, data in graph.nodes(data=True):
            nodes.append({
                "id": node,
                "label": node,
                "type": data.get("type", ""),
                "layer": data.get("layer", 0)
            })
        for u, v in graph.edges():
            edges.append({"source": u, "target": v})
        return {"nodes": nodes, "edges": edges}
    
    # 转换原始树
    original_data = graph_to_json(original_tree)
    
    # 转换所有子树
    subtrees_data = []
    for idx, subtree in enumerate(tree_list):
        subtree_data = graph_to_json(subtree)
        subtree_data["color"] = colors[idx % len(colors)]
        subtree_data["index"] = idx + 1
        subtrees_data.append(subtree_data)
    
    # 生成HTML内容 - 使用 application/json 注入数据，避免 {} 转义问题
    _orig = json.dumps(original_data, ensure_ascii=False).replace("</", "<\\/")
    _subt = json.dumps(subtrees_data, ensure_ascii=False).replace("</", "<\\/")
    html_content = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>3D分层切分可视化</title>
    <script src="/d3.v7.min.js"></script>
    <script type="application/json" id="orig-data">""" + _orig + """</script>
    <script type="application/json" id="subt-data">""" + _subt + """</script>
    <style>
        html, body {
            margin: 0;
            padding: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
            background: white;
        }
        body {
            width: 100%;
            height: 100vh;
            margin: 0;
            padding: 0;
            background: white;
            position: relative;
            overflow: hidden;
        }
        h1 {
            position: absolute;
            top: 10px;
            left: 50%;
            transform: translateX(-50%);
            color: #333;
            margin: 0;
            padding: 0;
            font-size: 18px;
            z-index: 100;
            pointer-events: none;
        }
        #svg-container {
            width: 100%;
            height: 100vh;
            margin: 0;
            padding: 0;
            background: white;
            overflow: hidden;
            position: absolute;
            top: 0;
            left: 0;
        }
        .node {
            cursor: pointer;
        }
        .node circle {
            stroke: #333;
            stroke-width: 2px;
        }
        .node text {
            font-size: 12px;
            font-weight: bold;
            fill: white;
            pointer-events: none;
        }
        .link {
            fill: none;
            stroke-width: 2px;
        }
        .connection-line {
            stroke-dasharray: 5,5;
            stroke-width: 2px;
            fill: none;
            opacity: 0.7;
            pointer-events: none;
        }
        .legend-container {
            position: fixed;
            top: 10px;
            right: 10px;
            background: rgba(255, 255, 255, 0.98);
            padding: 10px 12px;
            border-radius: 6px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.2);
            z-index: 10000;
            font-size: 12px;
            pointer-events: none;
            min-width: 160px;
            max-width: 180px;
        }
        .legend-title {
            font-size: 14px;
            font-weight: bold;
            margin-bottom: 10px;
            color: #333;
        }
        .legend-item {
            display: flex;
            align-items: center;
            margin-bottom: 8px;
        }
        .legend-color {
            width: 16px;
            height: 16px;
            border-radius: 50%;
            margin-right: 10px;
            border: 1px solid #333;
            flex-shrink: 0;
        }
        .legend-text {
            font-size: 12px;
            color: #333;
        }
    </style>
</head>
<body style="margin: 0; padding: 0; overflow: hidden;">
    <h1>3D分层切分可视化</h1>
    <svg id="svg-container"></svg>
    <div id="legend-container" class="legend-container"></div>
    
    <script>
        // 数据（从 application/json 读取，避免嵌入 JSON 时的转义问题）
        const originalData = JSON.parse(document.getElementById('orig-data').textContent);
        const subtreesData = JSON.parse(document.getElementById('subt-data').textContent);
        
        // 合并所有节点和边到一个数据集中
        const allNodes = [];
        const allEdges = [];
        
        // 添加原始树节点（添加标记）
        originalData.nodes.forEach(function(node) {
            var newNode = new Object();
            for (var key in node) {
                newNode[key] = node[key];
            }
            newNode.treeType = 'original';
            newNode.color = 'black';
            newNode.original_id = node.id;
            allNodes.push(newNode);
        });
        
        // 添加原始树边
        originalData.edges.forEach(function(edge) {
            allEdges.push(edge);
        });
        
        // 添加子树节点和边（为每个子树创建独立的节点副本）
        subtreesData.forEach(function(subtreeData, idx) {
            subtreeData.nodes.forEach(function(node) {
                // 为子树节点创建唯一ID（添加子树索引前缀）
                var uniqueId = 'subtree' + idx + '_' + node.id;
                var newNode = new Object();
                for (var key in node) {
                    newNode[key] = node[key];
                }
                newNode.id = uniqueId;
                newNode.treeType = 'subtree';
                newNode.subtreeIndex = idx;
                newNode.color = subtreeData.color;
                newNode.original_id = node.id;  // 保存原始ID用于匹配
                allNodes.push(newNode);
            });
            
            // 添加子树边（更新ID以匹配新的节点ID）
            subtreeData.edges.forEach(function(edge) {
                var newEdge = new Object();
                newEdge.source = 'subtree' + idx + '_' + edge.source;
                newEdge.target = 'subtree' + idx + '_' + edge.target;
                allEdges.push(newEdge);
            });
        });
        
        // 设置SVG尺寸 - 使用容器实际尺寸，确保自适应
        const svgContainer = d3.select('#svg-container');
        const containerRect = svgContainer.node().getBoundingClientRect();
        const width = Math.max(1600, containerRect.width || 1600);
        const height = Math.max(1200, containerRect.height || 1200);
        const margin = new Object();
        margin.top = 40;  // 给标题留一点空间
        margin.right = 200;  // 右侧留出空间给图例（图例宽度约180px）
        margin.bottom = 60;
        margin.left = 60;
        
        // 布局参数
        const originalTreeY = 50;   // 原始树Y坐标
        const subtreeY = 550;        // 子树Y坐标
        const subtreeSpacing = 300;   // 子树之间的间距（保留变量，布局未使用）
        
        // 创建SVG - 直接使用svg-container（已经是SVG元素了）
        const svg = d3.select('#svg-container')
            .attr('width', '100%')
            .attr('height', '100%')
            .attr('viewBox', '0 0 ' + width + ' ' + height)
            .attr('preserveAspectRatio', 'xMidYMid meet')
            .style('cursor', 'grab');
        
        const g = svg.append('g')
            .attr('transform', 'translate(' + margin.left + ',' + margin.top + ')');
        
        // 添加缩放和平移（拖动画布）
        const zoomBehavior = d3.zoom()
            .scaleExtent([0.5, 2.5])
            .on('start', function(event) {
                if (event.sourceEvent) {
                    event.sourceEvent.stopPropagation();  // 阻止事件冒泡到主界面
                }
                svg.style('cursor', 'grabbing');
            })
            .on('end', function(event) {
                if (event.sourceEvent) {
                    event.sourceEvent.stopPropagation();  // 阻止事件冒泡到主界面
                }
                svg.style('cursor', 'grab');
            })
            .on('zoom', function(event) {
                if (event.sourceEvent) {
                    event.sourceEvent.stopPropagation();  // 阻止事件冒泡到主界面
                }
                // 保留初始边距，再应用缩放和平移
                const t = event.transform;
                const tx = t.x + margin.left * t.k;
                const ty = t.y + margin.top * t.k;
                g.attr('transform', 'translate(' + tx + ',' + ty + ') scale(' + t.k + ')');
                // 图例使用HTML固定定位，不需要在这里更新
            });
        
        svg.call(zoomBehavior);
        
        // 阻止鼠标滚轮事件冒泡到主界面
        svg.on('wheel', function(event) {
            event.stopPropagation();
        });
        
        // 阻止鼠标拖拽事件冒泡到主界面
        svg.on('mousedown', function(event) {
            event.stopPropagation();
        });
        
        svg.on('mousemove', function(event) {
            if (event.buttons === 1) {
                event.stopPropagation();
            }
        });
        
        svg.on('mouseup', function(event) {
            event.stopPropagation();
        });
        
        // 使用D3树状布局从上到下布局原始树
        const originalNodesOnly = allNodes.filter(function(n) { return n.treeType === 'original'; });
        const originalEdgesOnly = allEdges.filter(function(e) {
            const sourceId = typeof e.source === 'object' ? e.source.id : e.source;
            const targetId = typeof e.target === 'object' ? e.target.id : e.target;
            const sourceNode = originalNodesOnly.find(function(n) { return n.id === sourceId; });
            const targetNode = originalNodesOnly.find(function(n) { return n.id === targetId; });
            return sourceNode && targetNode;
        });
        
        // 构建原始树的层次结构
        function buildHierarchy(nodes, edges, rootId) {
            const nodeMap = new Object();
            nodes.forEach(function(node) {
                nodeMap[node.id] = new Object();
                nodeMap[node.id].data = node;
                nodeMap[node.id].children = [];
            });
            
            edges.forEach(function(edge) {
                const sourceId = typeof edge.source === 'object' ? edge.source.id : edge.source;
                const targetId = typeof edge.target === 'object' ? edge.target.id : edge.target;
                if (nodeMap[sourceId] && nodeMap[targetId]) {
                    // 避免重复添加
                    let exists = false;
                    for (let i = 0; i < nodeMap[sourceId].children.length; i++) {
                        if (nodeMap[sourceId].children[i].data.id === targetId) {
                            exists = true;
                            break;
                        }
                    }
                    if (!exists) {
                        nodeMap[sourceId].children.push(nodeMap[targetId]);
                    }
                }
            });
            
            return nodeMap[rootId] || null;
        }
        
        const rootHierarchy = buildHierarchy(originalNodesOnly, originalEdgesOnly, 'Root');
        const originalPositions = new Object();
        
        if (!rootHierarchy) {
            console.error('无法找到根节点');
            console.log('原始节点:', originalNodesOnly);
            console.log('原始边:', originalEdgesOnly);
            // 如果找不到根节点，使用简单的布局
            originalNodesOnly.forEach(function(node, idx) {
                originalPositions[node.id] = new Object();
                originalPositions[node.id].x = (width - margin.left - margin.right) / 2 + (idx - originalNodesOnly.length / 2) * 100;
                originalPositions[node.id].y = originalTreeY + idx * 80;
            });
        } else {
            // 转换为D3层次结构
            const root = d3.hierarchy(rootHierarchy, function(d) { 
                return d.children && d.children.length > 0 ? d.children : null; 
            });
            
            // 创建树状布局（从上到下，需要交换x和y）
            const treeLayout = d3.tree()
                .nodeSize([200, 120])  // [水平间距, 垂直间距] - D3.tree默认x是垂直，y是水平
                .separation(function(a, b) {
                    return a.parent === b.parent ? 1 : 1.2;
                });
            
            treeLayout(root);
            
            // 计算布局的中心位置（交换x和y，因为D3.tree默认是左右布局）
            const treeWidth = d3.max(root.descendants(), function(d) { return d.y; }) || 0;
            const treeHeight = d3.max(root.descendants(), function(d) { return d.x; }) || 0;
            const treeOffsetX = (width - margin.left - margin.right - treeWidth) / 2;
            const treeOffsetY = originalTreeY;
            
            // 创建节点位置映射（原树节点ID -> 位置）
            // D3.tree的x是垂直方向（从上到下），y是水平方向（从左到右）
            // 我们需要交换：x -> y坐标，y -> x坐标
            root.descendants().forEach(function(d) {
                const nodeData = d.data.data;
                if (nodeData && nodeData.id) {
                    originalPositions[nodeData.id] = new Object();
                    originalPositions[nodeData.id].x = d.y + treeOffsetX;  // 交换：y -> x
                    originalPositions[nodeData.id].y = d.x + treeOffsetY;  // 交换：x -> y
                }
            });
            
            // 确保根节点也有位置
            if (root.data && root.data.data && root.data.data.id) {
                originalPositions[root.data.data.id] = new Object();
                originalPositions[root.data.data.id].x = root.y + treeOffsetX;
                originalPositions[root.data.data.id].y = root.x + treeOffsetY;
            }
        }
        
        // 初始化所有节点位置
        allNodes.forEach(function(node, i) {
            if (node.treeType === 'original') {
                // 原始树节点：使用树状布局后的位置
                if (originalPositions[node.id]) {
                    node.x = originalPositions[node.id].x;
                    node.y = originalPositions[node.id].y;
                } else {
                    node.x = (width - margin.left - margin.right) / 2;
                    node.y = originalTreeY;
                    console.warn('节点 ' + node.id + ' 没有找到位置，使用默认位置');
                }
            } else {
                // 子树节点：使用原树中对应节点的x坐标，y坐标下移
                const originalId = node.original_id;
                if (originalPositions[originalId]) {
                    node.x = originalPositions[originalId].x;
                    node.y = subtreeY;
                } else {
                    node.x = (width - margin.left - margin.right) / 2;
                    node.y = subtreeY;
                }
            }
            // 确保节点有有效的位置
            if (isNaN(node.x) || isNaN(node.y)) {
                node.x = (width - margin.left - margin.right) / 2;
                node.y = node.treeType === 'original' ? originalTreeY : subtreeY;
            }
            node.fx = null;
            node.fy = null;
        });
        
        // --- 全局水平压缩：保证所有节点都在画布可见范围内 ---
        let minX = Infinity;
        let maxX = -Infinity;
        allNodes.forEach(function(node) {
            if (typeof node.x === 'number') {
                if (node.x < minX) { minX = node.x; }
                if (node.x > maxX) { maxX = node.x; }
            }
        });
        
        if (maxX > minX && isFinite(minX) && isFinite(maxX)) {
            const innerWidth = width - margin.left - margin.right - 100;  // 预留左右边距
            const paddingX = 50;
            const scaleX = innerWidth / (maxX - minX);
            
            // 缩放所有节点的x坐标
            allNodes.forEach(function(node) {
                if (typeof node.x === 'number') {
                    node.x = (node.x - minX) * scaleX + paddingX;
                }
            });
            
            // 同时缩放原始位置映射，保持力导向布局对齐
            for (var key in originalPositions) {
                if (originalPositions.hasOwnProperty(key)) {
                    var pos = originalPositions[key];
                    if (pos && typeof pos.x === 'number') {
                        pos.x = (pos.x - minX) * scaleX + paddingX;
                    }
                }
            }
        }
        
        console.log('原始树节点位置(归一化后):', originalPositions);
        console.log('所有节点数量:', allNodes.length);
        
        // 创建力导向布局（子树节点固定x坐标，保持原树形状）
        const simulation = d3.forceSimulation(allNodes)
            .force('link', d3.forceLink(allEdges).id(function(d) {
                return typeof d === 'object' ? d.id : d;
            }).distance(100))
            .force('charge', d3.forceManyBody().strength(-300))
            .force('x', d3.forceX().x(function(d) {
                if (d.treeType === 'original') {
                    return originalPositions[d.id] ? originalPositions[d.id].x : (width - margin.left - margin.right) / 2;
                } else {
                    // 子树节点：保持原树的x坐标
                    const originalId = d.original_id;
                    return originalPositions[originalId] ? originalPositions[originalId].x : (width - margin.left - margin.right) / 2;
                }
            }).strength(1.0))
            .force('y', d3.forceY().y(function(d) {
                return d.treeType === 'original' ? originalTreeY : subtreeY;
            }).strength(1.0))
            .force('collision', d3.forceCollide().radius(35))
            .alphaDecay(0.02);
        
        // 绘制连接线（原始树到子树的虚线）
        const connectionLines = g.append('g')
            .attr('class', 'connection-lines');
        
        // 过滤掉连接到子树Root节点的边
        const visibleEdges = allEdges.filter(function(edge) {
            const sourceId = typeof edge.source === 'object' ? edge.source.id : edge.source;
            const targetId = typeof edge.target === 'object' ? edge.target.id : edge.target;
            // 如果边的源或目标是子树中的Root节点，则过滤掉
            const sourceNode = allNodes.find(function(n) { return n.id === sourceId; });
            const targetNode = allNodes.find(function(n) { return n.id === targetId; });
            if (sourceNode && sourceNode.treeType === 'subtree' && sourceNode.original_id === 'Root') return false;
            if (targetNode && targetNode.treeType === 'subtree' && targetNode.original_id === 'Root') return false;
            return true;
        });
        
        // 绘制树内部的边
        const links = g.append('g')
            .attr('class', 'links')
            .selectAll('line')
            .data(visibleEdges)
            .enter().append('line')
            .attr('class', 'link')
            .attr('stroke', function(d) {
                const source = typeof d.source === 'object' ? d.source : allNodes.find(function(n) { return n.id === d.source; });
                const sourceNode = typeof source === 'object' ? source : allNodes.find(function(n) { return n.id === source; });
                return sourceNode ? sourceNode.color : '#999';
            })
            .attr('stroke-width', 2)
            .attr('marker-end', function(d) {
                const source = typeof d.source === 'object' ? d.source : allNodes.find(function(n) { return n.id === d.source; });
                const sourceNode = typeof source === 'object' ? source : allNodes.find(function(n) { return n.id === source; });
                const color = sourceNode ? sourceNode.color : 'black';
                const markerId = color === 'black' ? 'arrowhead-black' : 'arrowhead-' + (sourceNode.subtreeIndex || '');
                return 'url(#' + markerId + ')';
            });
        
        // 过滤掉子树中的Root节点
        const visibleNodes = allNodes.filter(function(node) {
            // 如果是子树中的Root节点，则不显示
            if (node.treeType === 'subtree' && node.original_id === 'Root') {
                return false;
            }
            return true;
        });
        
        // 绘制节点
        const nodes = g.append('g')
            .attr('class', 'nodes')
            .selectAll('g')
            .data(visibleNodes)
            .enter().append('g')
            .attr('class', 'node');
        
        nodes.append('circle')
            .attr('r', function(d) { return d.treeType === 'original' ? 25 : 20; })
            .attr('fill', function(d) { return d.color; })
            .attr('stroke', '#333')
            .attr('stroke-width', 2);
        
        nodes.append('text')
            .text(function(d) { return d.label; })
            .attr('text-anchor', 'middle')
            .attr('dy', 5)
            .style('font-size', function(d) { return d.treeType === 'original' ? '12px' : '11px'; });
        
        // 添加箭头标记
        svg.append('defs').append('marker')
            .attr('id', 'arrowhead-black')
            .attr('viewBox', '0 -5 10 10')
            .attr('refX', 30)
            .attr('refY', 0)
            .attr('markerWidth', 6)
            .attr('markerHeight', 6)
            .attr('orient', 'auto')
            .append('path')
            .attr('d', 'M0,-5L10,0L0,5')
            .attr('fill', 'black');
        
        subtreesData.forEach(function(subtreeData, idx) {
            svg.append('defs').append('marker')
                .attr('id', 'arrowhead-' + idx)
                .attr('viewBox', '0 -5 10 10')
                .attr('refX', 25)
                .attr('refY', 0)
                .attr('markerWidth', 6)
                .attr('markerHeight', 6)
                .attr('orient', 'auto')
                .append('path')
                .attr('d', 'M0,-5L10,0L0,5')
                .attr('fill', subtreeData.color);
        });
        
        // 更新函数：在simulation tick时更新所有元素
        simulation.on('tick', function() {
            // 更新边的位置
            links
                .attr('x1', function(d) {
                    const source = typeof d.source === 'object' ? d.source : allNodes.find(function(n) { return n.id === d.source; });
                    return source ? source.x : 0;
                })
                .attr('y1', function(d) {
                    const source = typeof d.source === 'object' ? d.source : allNodes.find(function(n) { return n.id === d.source; });
                    return source ? source.y : 0;
                })
                .attr('x2', function(d) {
                    const target = typeof d.target === 'object' ? d.target : allNodes.find(function(n) { return n.id === d.target; });
                    return target ? target.x : 0;
                })
                .attr('y2', function(d) {
                    const target = typeof d.target === 'object' ? d.target : allNodes.find(function(n) { return n.id === d.target; });
                    return target ? target.y : 0;
                });
            
            // 更新节点位置（只更新可见节点）
            nodes.attr('transform', function(d) { return 'translate(' + d.x + ',' + d.y + ')'; });
            
            // 更新连接线（原始树节点到子树节点的虚线，跳过Root节点）
            drawConnectionLines();
        });
        
        // 绘制连接线函数
        function drawConnectionLines() {
            // 清除旧的连接线
            connectionLines.selectAll('path').remove();
            
            // 为每个子树绘制连接线
            subtreesData.forEach(function(subtreeData, idx) {
                subtreeData.nodes.forEach(function(subtreeNode) {
                    const originalId = subtreeNode.id;
                    // 跳过Root节点（不绘制连接线）
                    if (originalId === 'Root') return;
                    
                    // 找到原始树中的对应节点
                    const origNode = allNodes.find(function(n) { return n.original_id === originalId && n.treeType === 'original'; });
                    // 找到子树中的对应节点（使用唯一ID）
                    const uniqueId = 'subtree' + idx + '_' + originalId;
                    const subtreeNodeObj = allNodes.find(function(n) { return n.id === uniqueId && n.treeType === 'subtree'; });
                    
                    // 如果找不到节点或节点位置未定义，跳过
                    if (!origNode || !subtreeNodeObj || !origNode.x || !subtreeNodeObj.x) return;
                    
                    // 绘制连接线（使用贝塞尔曲线）
                    const midX = (origNode.x + subtreeNodeObj.x) / 2;
                    const controlY = Math.min(origNode.y, subtreeNodeObj.y) - 150;
                    
                    connectionLines.append('path')
                        .attr('class', 'connection-line')
                        .attr('d', 'M ' + origNode.x + ' ' + origNode.y + ' Q ' + midX + ' ' + controlY + ' ' + subtreeNodeObj.x + ' ' + subtreeNodeObj.y)
                        .attr('stroke', subtreeData.color)
                        .attr('stroke-width', 2)
                        .attr('stroke-dasharray', '5,5')
                        .attr('fill', 'none')
                        .attr('opacity', 0.7)
                        .attr('marker-end', 'url(#arrow-connection-' + idx + ')');
                });
            });
        }
        
        // 添加连接线箭头标记
        subtreesData.forEach(function(subtreeData, idx) {
            svg.append('defs').append('marker')
                .attr('id', 'arrow-connection-' + idx)
                .attr('viewBox', '0 -5 10 10')
                .attr('refX', 8)
                .attr('refY', 0)
                .attr('markerWidth', 6)
                .attr('markerHeight', 6)
                .attr('orient', 'auto')
                .append('path')
                .attr('d', 'M0,-5L10,0L0,5')
                .attr('fill', subtreeData.color);
        });
        
        // 添加图例（使用HTML元素，固定在viewport右上角，不受SVG缩放影响）
        const legendContainer = d3.select('#legend-container');
        
        // 图例标题
        legendContainer.append('div')
            .attr('class', 'legend-title')
            .text('图例');
        
        // 原始大树图例
        const originalItem = legendContainer.append('div')
            .attr('class', 'legend-item');
        originalItem.append('div')
            .attr('class', 'legend-color')
            .style('background-color', 'black');
        originalItem.append('div')
            .attr('class', 'legend-text')
            .text('原始大树');
        
        // 子树图例
        subtreesData.forEach(function(subtreeData, idx) {
            const item = legendContainer.append('div')
                .attr('class', 'legend-item');
            item.append('div')
                .attr('class', 'legend-color')
                .style('background-color', subtreeData.color);
            item.append('div')
                .attr('class', 'legend-text')
                .style('color', subtreeData.color)
                .text('子树 ' + (idx + 1));
        });
        
        // 子树标签已移除（根据用户需求）
    </script>
</body>
</html>
"""
    
    # 保存HTML文件
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    return output_path

# 生成3D分层切分可视化图片（保留原函数用于PNG生成）
def visualize3DSplitTree(original_tree, tree_list, output_path="tree_split_3d.png", figsize=(16, 12)):
    """
    生成3D分层切分可视化图片
    
    Args:
        original_tree: 原始通信树 (NetworkX DiGraph)
        tree_list: 切分后的子树列表 (list of NetworkX DiGraph)
        output_path: 输出图片路径
        figsize: 图片大小，默认(16, 12)
    
    Returns:
        str: 保存的图片路径
    """
    import matplotlib.patches as mpatches
    from matplotlib.patches import FancyBboxPatch
    
    # 配置matplotlib支持中文（如果可用）
    try:
        plt.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS', 'sans-serif']
        plt.rcParams['axes.unicode_minus'] = False
    except:
        pass
    
    # 创建图形，上下两层布局
    fig = plt.figure(figsize=figsize)
    
    # 上层：原始大树
    ax1 = plt.subplot(2, 1, 1)
    ax1.set_title('Original Tree', fontsize=16, fontweight='bold', pad=20)
    ax1.axis('off')
    
    # 下层：切分后的子树
    ax2 = plt.subplot(2, 1, 2)
    ax2.set_title('Split Subtrees', fontsize=16, fontweight='bold', pad=20)
    ax2.axis('off')
    
    # 为每个子树分配颜色
    # 高区分度配色方案（与HTML版本保持一致）
    colors = [
        '#E74C3C',  # 鲜艳红色
        '#3498DB',  # 明亮蓝色
        '#2ECC71',  # 翠绿色
        '#F39C12',  # 橙色
        '#9B59B6',  # 紫色
        '#1ABC9C',  # 青色
        '#E91E63',  # 粉红色
        '#34495E'   # 深蓝灰色
    ]
    
    # 绘制上层：原始大树（黑色）
    pos1 = nx.spring_layout(original_tree, seed=42, k=2, iterations=50)
    
    # 绘制原始树的节点和边（黑色）
    nx.draw_networkx_nodes(original_tree, pos1, ax=ax1, 
                          node_color='black', node_size=800, alpha=0.9)
    nx.draw_networkx_edges(original_tree, pos1, ax=ax1, 
                          edge_color='black', width=2, alpha=0.8, arrows=True, arrowsize=20)
    nx.draw_networkx_labels(original_tree, pos1, ax=ax1, 
                           font_size=9, font_weight='bold', font_color='white')
    
    # 在下层绘制所有切分后的子树
    # 计算每个子树的位置，让它们水平排列
    subtree_positions = []
    x_start = 0
    y_base = 0
    
    for idx, subtree in enumerate(tree_list):
        # 为每个子树计算位置（水平排列）
        subtree_pos = {}
        x_offset = x_start
        
        # 使用层次布局来排列子树
        try:
            pos_subtree = nx.spring_layout(subtree, seed=42+idx, k=1.5, iterations=30)
            # 调整x坐标，让子树水平排列
            for node, (x, y) in pos_subtree.items():
                subtree_pos[node] = (x + x_offset, y)
        except:
            # 如果布局失败，使用简单布局
            nodes = list(subtree.nodes())
            for i, node in enumerate(nodes):
                subtree_pos[node] = (x_offset + i * 0.5, 0)
        
        # 绘制子树
        color = colors[idx % len(colors)]
        
        # 绘制节点
        nx.draw_networkx_nodes(subtree, subtree_pos, ax=ax2,
                              node_color=color, node_size=600, alpha=0.9,
                              edgecolors='black', linewidths=2)
        # 绘制边
        nx.draw_networkx_edges(subtree, subtree_pos, ax=ax2,
                              edge_color=color, width=2, alpha=0.8, arrows=True, arrowsize=15)
        # 绘制标签
        nx.draw_networkx_labels(subtree, subtree_pos, ax=ax2,
                               font_size=8, font_weight='bold', font_color='white')
        
        # 记录子树的位置信息，用于绘制对应关系
        subtree_positions.append({
            'subtree': subtree,
            'pos': subtree_pos,
            'color': color,
            'idx': idx
        })
        
        # 更新下一个子树的起始位置
        if subtree_pos:
            max_x = max(x for x, y in subtree_pos.values())
            x_start = max_x + 2
    
    # 绘制对应关系：用虚线连接原始树中的节点和切分后子树中对应的同名节点
    # 规则：原始树中的节点X应该连接到子树中相同的节点X（如DP1->DP1, PP1->PP1）
    for subtree_info in subtree_positions:
        subtree = subtree_info['subtree']
        subtree_pos = subtree_info['pos']
        color = subtree_info['color']
        
        # 找到子树中所有在原始树中存在的节点（排除Root，因为Root是后加的）
        common_nodes = [n for n in subtree.nodes() if n != 'Root' and n in original_tree.nodes()]
        
        # 对于每个共同的节点，绘制连接线
        for node_name in common_nodes:
            if node_name not in pos1 or node_name not in subtree_pos:
                continue
            
            # 获取节点在各自坐标系中的坐标
            x1, y1 = pos1[node_name]  # 原始树中的节点坐标（ax1坐标系）
            x2, y2 = subtree_pos[node_name]  # 子树中相同节点的坐标（ax2坐标系）
            
            # 将节点坐标转换为figure坐标系
            # 原始树节点坐标转换
            ax1_point = ax1.transData.transform([x1, y1])
            fig_point1 = fig.transFigure.inverted().transform(ax1_point)
            
            # 子树节点坐标转换
            ax2_point = ax2.transData.transform([x2, y2])
            fig_point2 = fig.transFigure.inverted().transform(ax2_point)
            
            # 绘制连接线：从原始树节点中心 -> 子树中相同节点的中心
            line = mpatches.FancyArrowPatch(
                (fig_point1[0], fig_point1[1]),  # 起点：原始树节点中心
                (fig_point2[0], fig_point2[1]),  # 终点：子树节点中心
                transform=fig.transFigure,
                arrowstyle='->', 
                linestyle='--',
                color=color,
                alpha=0.6,
                linewidth=2,
                connectionstyle="arc3,rad=0.15"
            )
            fig.patches.append(line)
    
    # 添加图例
    legend_elements = [
        mpatches.Patch(facecolor='black', label='Original Tree'),
    ]
    for idx, subtree_info in enumerate(subtree_positions):
        color = subtree_info['color']
        legend_elements.append(
            mpatches.Patch(facecolor=color, label=f'Subtree {idx+1}')
        )
    
    ax1.legend(handles=legend_elements, loc='upper right', fontsize=10)
    
    # 调整布局
    plt.tight_layout()
    
    # 保存图片
    plt.savefig(output_path, dpi=300, bbox_inches='tight', facecolor='white')
    plt.close()
    
    return output_path

 # 主要的拓扑切分函数
def performTreeCut(tree_data=None, output_dir="TreeGroup", show_graphs=False, generate_3d_viz=False):
    """
    执行拓扑切分的主要函数
    
    Args:
        tree_data: 外部通信树数据，如果为None则使用默认构建方式
        output_dir: 输出目录，默认为"TreeGroup"
        show_graphs: 是否显示图形，默认为False
        generate_3d_viz: 是否生成3D分层可视化图片，默认为False
    
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
    
    # 保存原始树的副本用于可视化
    original_tree_for_viz = copy.deepcopy(T)
    
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
    
    # 生成3D分层可视化（HTML版本，更精确）
    viz_path = None
    if generate_3d_viz:
        try:
            os.makedirs(output_dir, exist_ok=True)
            # 使用HTML版本，连接更精确
            viz_path = os.path.join(output_dir, "tree_split_3d.html")
            visualize3DSplitTreeHTML(original_tree_for_viz, Tree_list, viz_path)
            print(f"✅ 3D分层可视化HTML已保存: {viz_path}")
        except Exception as e:
            print(f"⚠️ 生成3D可视化HTML时出错: {e}")
            import traceback
            traceback.print_exc()
            viz_path = None
    
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
        "out_dependence_list": out_dependence_list,
        "visualization_path": viz_path
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