#!/usr/bin/env python3
import networkx as nx
import random
import matplotlib.pyplot as plt
import copy
from collections import defaultdict
#from DocProcess import process_file


# 根节点
root_node = 'Root'

# 切割后树的列表集合
Tree_list = []

# 定义添加节点的方法
def addCommunicationEdge(G, layer, comm_type, pre_node):
    node_name = f"{comm_type}{layer}_{len(G.nodes)}"
    file_path = f"{node_name}.txt"
    # huawei主机
    # nodes_passed = process_file(file_path)
    nodes_passed = [random.choice(['A', 'B', 'C', 'D', 'E']) for _ in range(random.randint(1, 3))]
    G.add_node(node_name, name=node_name, type=comm_type, layer=layer, nodes_passed=nodes_passed, children=[]
               , isBurr=False)
    G.add_edge(pre_node, node_name)
    return node_name

# 构建通信树
def constructTree(G, root_node):
    TP1 = addCommunicationEdge(G, 1, "TP", root_node)
    PP1 = addCommunicationEdge(G, 1, "PP", root_node)
    PP2 = addCommunicationEdge(G, 2, "PP", TP1)
    DP1 = addCommunicationEdge(G, 2, "DP", TP1)
    TP2 = addCommunicationEdge(G, 2, "TP", PP1)
    TP3 = addCommunicationEdge(G, 3, "TP", PP2)
    TP4 = addCommunicationEdge(G, 3, "TP", TP2)
    TP5 = addCommunicationEdge(G, 4, "TP", TP3)
    PP3 = addCommunicationEdge(G, 4, "PP", TP4)
    DP2 = addCommunicationEdge(G, 4, "DP", TP4)
    DP3 = addCommunicationEdge(G, 5, "DP", TP5)
    TP6 = addCommunicationEdge(G, 5, "TP", PP3)
    TP7 = addCommunicationEdge(G, 6, "TP", TP6)
    DP4 = addCommunicationEdge(G, 7, "DP", TP7)
    PP4 = addCommunicationEdge(G, 7, "PP", TP7)
    TP8 = addCommunicationEdge(G, 8, "TP", PP4)
    TP9 = addCommunicationEdge(G, 9, "TP", TP8)
    DP5 = addCommunicationEdge(G, 10, "DP", TP9)
    nodes_list = list(G.nodes())

if __name__ == '__main__':
    # 创建一个有向图
    T = nx.DiGraph()
    # 添加根节点
    T.add_node(root_node, name='Root', nodes_passed=[], children=[])
    # 构建通信树
    constructTree(T, root_node)