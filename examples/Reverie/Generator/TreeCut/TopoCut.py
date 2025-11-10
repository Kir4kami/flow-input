#!/usr/bin/env python3
import datetime
import re
from ecmp_path import UnionFind, load_file, find_ecmp_path, get_rdma_files
from collections import defaultdict
from tqdm import tqdm
import multiprocessing, time
import pandas as pd
import os
import mmap
import netisim_graph
import networkx as nx
import json
from shutil import copyfile

graph = netisim_graph.NetiSimGraph()

host_num = 4096
leaf_num = 64
spine_num = 16
node_in_set = 64
msg_len = 67108864
# 集合为所有用到的节点
used_nodes = set()
Total_Flow_Path = []
Total_Flow_Info_List = []
Total_Link_Info_List = []
Total_Paths_Port = []

def process_flow_path(flow_path):
    processed_flow_path = []
    phase_tuples = []
    uf = UnionFind()  # 创建一个 UnionFind 实例，跨阶段使用

    for item in flow_path:
        if item == 'phase':
            # 处理前一个 phase 的数据
            if phase_tuples:
                element_to_indices = defaultdict(set)

                # 对每个阶段内的元素进行索引映射
                for idx, lst in phase_tuples:
                    for elem in lst:
                        element_to_indices[elem].add(idx)

                # 合并所有有交集的数组
                for indices in element_to_indices.values():
                    indices = list(indices)
                    for i in range(len(indices) - 1):
                        uf.union(indices[i], indices[i + 1])

                # 按并查集合并结果进行合并
                clusters = defaultdict(list)
                for idx, lst in phase_tuples:
                    root = uf.find(idx)
                    clusters[root].append((idx, lst))

                # 合并每个 cluster 中的列表，并将相应的索引合并
                new_phase = []
                for cluster in clusters.values():
                    combined_list = set()
                    combined_indices = set()
                    for idx, lst in cluster:
                        combined_list.update(lst)
                        combined_indices.add(idx)
                    new_phase.append(
                        (combined_indices, list(combined_list)))  # 保留合并后的索引集

                # 将处理后的 phase 添加到结果中
                processed_flow_path.append('phase')
                processed_flow_path.extend(new_phase)
                phase_tuples = []  # 重置当前阶段的数据
            else:
                processed_flow_path.append('phase')
        else:
            phase_tuples.append(item)
    # 处理最后一个阶段
    if phase_tuples:
        element_to_indices = defaultdict(set)
        for idx, lst in phase_tuples:
            for elem in lst:
                element_to_indices[elem].add(idx)
        for indices in element_to_indices.values():
            indices = list(indices)
            for i in range(len(indices) - 1):
                uf.union(indices[i], indices[i + 1])
        clusters = defaultdict(list)
        for idx, lst in phase_tuples:
            root = uf.find(idx)
            clusters[root].append((idx, lst))
        new_phase = []
        for cluster in clusters.values():
            combined_list = set()
            combined_indices = set()
            for idx, lst in cluster:
                combined_list.update(lst)
                combined_indices.add(idx)
            new_phase.append(
                (combined_indices, list(combined_list)))  # 保留合并后的索引集
        processed_flow_path.append('phase')
        processed_flow_path.extend(new_phase)
    print("process_flow_path success")
    return processed_flow_path


"""
def merge_flow_paths(flow_path_port):
    processed_flow_path = []
    phase_tuples = []
    uf = UnionFind()  # 创建一个 UnionFind 实例，跨阶段使用

    for item in flow_path_port:
        if item == 'phase':
            # 处理前一个 phase 的数据
            if phase_tuples:
                element_to_indices = defaultdict(set)

                # 对每个阶段内的元素进行索引映射
                for idx, lst in phase_tuples:
                    for elem in lst:
                        element_to_indices[elem].add(idx)

                # 合并所有有交集的数组
                for indices in element_to_indices.values():
                    indices = list(indices)
                    for i in range(len(indices) - 1):
                        uf.union(indices[i], indices[i + 1])

                # 按并查集合并结果进行合并
                clusters = defaultdict(list)
                for idx, lst in phase_tuples:
                    root = uf.find(idx)
                    clusters[root].append((idx, lst))

                # 合并每个 cluster 中的列表，并将相应的索引合并
                new_phase = []
                for cluster in clusters.values():
                    combined_list = set()
                    combined_indices = set()
                    for idx, lst in cluster:
                        combined_list.update(lst)
                        combined_indices.add(idx)
                    new_phase.append((combined_indices, list(combined_list)))  # 保留合并后的索引集

                # 将处理后的 phase 添加到结果中
                processed_flow_path.append('phase')
                processed_flow_path.extend(new_phase)
                phase_tuples = []  # 重置当前阶段的数据
            else:
                processed_flow_path.append('phase')
        else:
            phase_tuples.append(item)

        # 处理最后一个阶段
    if phase_tuples:
        element_to_indices = defaultdict(set)

        # 对每个阶段内的元素进行索引映射
        for idx, lst in phase_tuples:
            for elem in lst:
                element_to_indices[elem].add(idx)

        # 合并所有有交集的数组
        for indices in element_to_indices.values():
            indices = list(indices)
            for i in range(len(indices) - 1):
                uf.union(indices[i], indices[i + 1])

        # 按并查集合并结果进行合并
        clusters = defaultdict(list)
        for idx, lst in phase_tuples:
            root = uf.find(idx)
            clusters[root].append((idx, lst))

        # 合并每个 cluster 中的列表，并将相应的索引合并
        new_phase = []
        for cluster in clusters.values():
            combined_list = set()
            combined_indices = set()
            for idx, lst in cluster:
                combined_list.update(lst)
                combined_indices.add(idx)
            new_phase.append((combined_indices, list(combined_list)))  # 保留合并后的索引集

        # 将处理后的 phase 添加到结果中
        processed_flow_path.append('phase')
        processed_flow_path.extend(new_phase)

    return processed_flow_path
   """


def merge_flow_paths(flow_paths_port):
    processed_flow_path = []
    phase_tuples = []
    uf = UnionFind()  # 创建一个 UnionFind 实例，跨阶段使用

    for item in flow_paths_port:
        if item == 'phase':
            # 处理前一个 phase 的数据
            if phase_tuples:
                element_to_indices = defaultdict(set)

                # 对每个阶段内的元素进行索引映射（忽略首尾元素）
                for idx, lst in phase_tuples:
                    trimmed_lst = lst[1:-1] if len(lst) > 2 else []  # 去掉首尾
                    for elem in trimmed_lst:
                        element_to_indices[elem].add(idx)

                # 合并所有有交集的数组
                for indices in element_to_indices.values():
                    indices = list(indices)
                    for i in range(len(indices) - 1):
                        uf.union(indices[i], indices[i + 1])

                # 按并查集合并结果进行合并
                clusters = defaultdict(list)
                for idx, lst in phase_tuples:
                    root = uf.find(idx)
                    clusters[root].append((idx, lst))

                # 合并每个 cluster 中的列表，并将相应的索引合并
                new_phase = []
                for cluster in clusters.values():
                    combined_list = set()
                    combined_indices = set()
                    for idx, lst in cluster:
                        combined_list.update(lst)
                        combined_indices.add(idx)
                    new_phase.append(
                        (combined_indices, list(combined_list)))  # 保留合并后的索引集

                # 将处理后的 phase 添加到结果中
                processed_flow_path.append('phase')
                processed_flow_path.extend(new_phase)
                phase_tuples = []  # 重置当前阶段的数据
            else:
                processed_flow_path.append('phase')
        else:
            phase_tuples.append(item)
        # 处理最后一个阶段
    if phase_tuples:
        element_to_indices = defaultdict(set)

        # 对每个阶段内的元素进行索引映射（忽略首尾元素）
        for idx, lst in phase_tuples:
            trimmed_lst = lst[1:-1] if len(lst) > 2 else []  # 去掉首尾
            for elem in trimmed_lst:
                element_to_indices[elem].add(idx)

        # 合并所有有交集的数组
        for indices in element_to_indices.values():
            indices = list(indices)
            for i in range(len(indices) - 1):
                uf.union(indices[i], indices[i + 1])

        # 按并查集合并结果进行合并
        clusters = defaultdict(list)
        for idx, lst in phase_tuples:
            root = uf.find(idx)
            clusters[root].append((idx, lst))

        # 合并每个 cluster 中的列表，并将相应的索引合并
        new_phase = []
        for cluster in clusters.values():
            combined_list = set()
            combined_indices = set()
            for idx, lst in cluster:
                combined_list.update(lst)
                combined_indices.add(idx)
            new_phase.append(
                (combined_indices, list(combined_list)))  # 保留合并后的索引集

        # 将处理后的 phase 添加到结果中
        processed_flow_path.append('phase')
        processed_flow_path.extend(new_phase)

    return processed_flow_path


def find2(file_name):
    ele = []
    with open(file_name, 'r') as file:
        for line in file:
            matches = re.findall(r'\[(.+?)\]', line)
            ele.append(matches)
    return ele

def fun(task):
    print(f"fun：{task} is running")

    Working_Directory = "Topo_Operate"
    # 路径信息
    Flow_Info_List, Link_Info_List, Route_Info_Table, Link_Map, Reverse_Link_Map = load_file(Working_Directory, task)

    Flow_Path, Flow_Paths_Port, path_port_dic = find_ecmp_path(Flow_Info_List, Link_Info_List, Route_Info_Table,
                                                               Link_Map,
                                                               Reverse_Link_Map)

    # cutting_path = process_flow_path(Flow_Path)

    # result = merge_flow_paths(Flow_Paths_Port)

    """with open(f"result{task}", 'w') as file:
        for item in tqdm(result, desc="Writing result"):
            file.write(' '.join(map(str, item)) + '\n')  """
    with open(f"Flow_Path{task}", 'w') as file:
        for path in tqdm(Flow_Path, desc="Writing Flow_Path"):
            file.write(' '.join(map(str, path)) + " ")
    """file.write("----------------------------------------\n")"""
    with open(f"Flow_Paths_Port{task}", 'w') as file:
        for path in tqdm(Flow_Paths_Port, desc="Writing Flow_Paths_Port"):
            file.write(' '.join(map(str, path)) + " ")
    """ for item in tqdm(cutting_path, desc="Writing cutting_path"):
            if item == 'phase':
                file.write('phase\n')
            else:
                file.write(f"({item[0]}, {item[1]})\n")
        file.write("----------------------------------------\n")   """
    with open(f'data{task}', 'w') as file:
        # 路径信息写入datasplit
        count = len(path_port_dic)
        for item in path_port_dic:
            count = len(item)
            for key in item:
                count -= 1
                val = item.get(key, [])
                if (len(val) > 1):
                    file.write(f"{val[0]}->{key}->{val[-1]}\n")
                elif (count == 0):
                    file.write(f"{val[0]}->{key}\n")
                else:
                    file.write(f"{key}->{val[0]}\n")

# 使用正则表达式匹配 src_node 和 dst_node 后面的数字
def replace_nodes(line, host_dict):
    # 替换 src_node
    line = re.sub(r'src_node:(\d+)', lambda match: f'src_node:{host_dict.get(int(match.group(1)), match.group(1))}', line)
    # 替换 dst_node
    line = re.sub(r'dst_node:(\d+)', lambda match: f'dst_node:{host_dict.get(int(match.group(1)), match.group(1))}', line)
    return line

def change_rdma(path_list, file_path_list, host_dic, leaf_dic, spine_dic):
    # 指定目标文件夹
    target_folder = './rdma_operate_output'
    # 遍历文件路径列表，将文件复制到目标文件夹
    for file_path in file_path_list:
        # 获取文件名
        file_name = os.path.basename(file_path)
        # 构建目标文件路径
        target_path = os.path.join(target_folder, file_name)
        # 复制文件
        copyfile(file_path, target_path)
    file_path_list_copy = get_rdma_files(target_folder)

    for file_path in file_path_list_copy:
        with open(file_path, 'r') as file:
            lines = file.readlines()
        with open(file_path, 'w') as file:
            for line in lines:
                if "Type:rdma_send" in line:
                    match = re.search(r'src_node:(\d+),.*dst_node:(\d+)', line)
                    if match:
                        # 替换 src_node 为 "src_node"
                        line = replace_nodes(line, host_dic)
                        file.write(line)
                    else:
                        file.write(line)
                elif "phase" in line:
                    file.write(line)
                    continue
                else:
                    file.write(line)

# 根据拓扑修改
def gen_router(host_dic, leaf_dic, spine_dic):
    host = len(host_dic)
    leaf = len(leaf_dic)
    spine = len(spine_dic)
    write_route_table_to_xml(host, leaf, spine)

def get_port_in_leaf(node_id):
   if node_id%2==0: return f'{node_id%(node_in_set*2)//2}'
   else :return f'{(node_id%(node_in_set*2)-1)//2}'


def get_port_in_spine(node_id, leafnum):
    return f'{node_id % leafnum}'


def get_leaf_id(id, hostnum):
    if id >= hostnum:
        return id - hostnum
    group = id // (node_in_set * 2)
    offset = id % (node_in_set * 2)
    leaf_in_grp = 0 if offset % 2 == 0 else 1
    leaf_id = group * 2 + leaf_in_grp
    return leaf_id


def cal_port(src_node, dst_host, hostnum, leafnum, spinenum):
    if dst_host >= hostnum:
        raise ValueError("目标节点必须是主机")

    if src_node == dst_host:
        return

    dst_leaf = get_leaf_id(dst_host, hostnum)  # 获取目标主机所属的leaf ID
    src_leaf = get_leaf_id(src_node, hostnum)  # 获取源主机所属的leaf ID

    src_type = judge_type(src_node, hostnum, leafnum, 0)

    if src_type == "host":
        if dst_leaf == src_leaf:
            return "1"
        else:
            return "1"
    elif src_type == "node" and hostnum <= src_node < hostnum + leafnum:
        if dst_leaf == src_leaf:
            return get_port_in_leaf(dst_host)
        else:
            return f' '.join(str(node_in_set + i) for i in range(spinenum))
    elif src_type == "node" and hostnum + leafnum <= src_node < hostnum + leafnum + spinenum:
        return get_port_in_spine(get_leaf_id(dst_host, hostnum), leafnum)


def cal_metric(src, dst, hostnum, leafnum, spinenum):
    if (src == dst):
        return "0"
    src_leaf = get_leaf_id(src, hostnum)

    dst_leaf = get_leaf_id(dst, hostnum)

    node_type = judge_type(src, hostnum, leafnum, 0)
    if node_type == "node" and hostnum + leafnum <= src < hostnum + leafnum + spinenum:
        return "2"
    elif node_type == "node" and hostnum <= src < hostnum + leafnum:
        if src_leaf == dst_leaf:
            return "1"
        else:
            return " ".join(["3"] * spinenum)
    else:
        if src_leaf == dst_leaf:
            return "2"
        else:
            return " ".join(["4"] * spinenum)


def write_route_table_to_xml(host, leaf, spine):
    host_num = host
    leaf_num = leaf
    spine_num = spine

    file_path = "./router_output/"
    os.makedirs(file_path, exist_ok=True)

    file_path = file_path + f"/router_mine.xml"
    node_num = host_num + leaf_num + spine_num
    progress_bar = tqdm(total=node_num * host_num, desc="写入进度", unit="项")
    with open(file_path, "w") as output_xml:
        output_xml.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        output_xml.write('<router>\n')
        for node_id in range(host_num, host_num + leaf_num + spine_num, 1):
            output_xml.write(
                f'  <grp node_id="{node_id}" node_type="{judge_type(node_id, host_num, leaf_num, 0)}">\n')
            for dst_id in range(host_num):
                if dst_id != node_id:
                    output_xml.write(f'     <target node_id="{dst_id}" '
                                     f'port_id="{cal_port(node_id, dst_id, host_num, leaf_num, spine_num)}" '
                                     f'metric="{cal_metric(node_id, dst_id, host_num, leaf_num, spine_num)}"/>\n')
                    progress_bar.update(1)
            output_xml.write('  </grp>\n')
            output_xml.flush()
        output_xml.write('</router>')
    progress_bar.close()
    print("路由文件已写入")


def gen_config(host_dic, leaf_dic, spine_dic):
    host_num = len(host_dic)
    leaf_sw_num = len(leaf_dic)
    spine_sw_num = len(spine_dic)

    # step1: 生成节点,要求host在前,node在后,且顺序编号,不符合要求会报错
    for host_id in range(host_num):
        graph.add_netisim_host(host_id)

    for leaf_sw_id in range(leaf_sw_num):
        graph.add_netisim_node(leaf_sw_id + host_num, comp_delay=1600)

    for spine_sw_id in range(spine_sw_num):
        graph.add_netisim_node(spine_sw_id + host_num + leaf_sw_num, comp_delay=1600)

    # step2: 生成拓扑连线,按照自定义拓扑,将指定id的节点(host或node皆可)进行连线并指定带宽和时延(发包器会自动连接)

    for spine_sw_id in range(spine_sw_num):
        for leaf_sw_id in range(leaf_sw_num):
            graph.add_netisim_edge(spine_sw_id + host_num + leaf_sw_num, leaf_sw_id + host_num, bandwidth='400',
                                   delay='10')

    # 主机与叶子交换机之间的连接，确保每个叶子交换机连接到64个主机，且这些连接是交错的
    for leaf_sw_id in range(leaf_sw_num):
        base = (leaf_sw_id // 2) * (host_num // leaf_sw_num * 2)
        start = base + (leaf_sw_id % 2)
        for i in range(host_num // leaf_sw_num):
            host_id = start + i * 2
            if (host_id < host_num):
                graph.add_netisim_edge(leaf_sw_id + host_num, host_id, bandwidth="200", delay="5")

    # step3: 生成配置文件,build_graph_config会生成一系列中间数据,最终生成dcn2.0_config.xml文件
    graph.build_graph_config(template_xml="dcn2.0_config_rdma_template.xml", output_name=f"dcn2.0_config.xml")


# 判断节点类型
def judge_type(id, hostnum, leafnum, flag):
    if flag:
        if (0 <= id < hostnum):
            return "host"
        elif (hostnum <= id < hostnum + leafnum):
            return "leaf"
        else:
            return "spine"
    else:
        if (0 <= id < hostnum):
            return "host"
        else:
            return "node"


def judge_type_new(id):
    if (0 <= id < host_num):
        return "host"
    elif (host_num <= id < host_num + leaf_num):
        return "leaf"
    else:
        return "spine"


def find2(file_name):
    ele = []
    with open(file_name, 'r') as file:
        for line in file:
            matches = re.findall(r'\[(.+?)\]', line)
            ele.append(matches)
    return ele


def TopoCut(path, file_path_list):
    spine = set()
    leaf = set()
    host = set()
    for ele in path:
        for i in ele[1]:
            if judge_type_new(i) == "spine":
                spine.add(i)
            elif judge_type_new(i) == "leaf":
                leaf.add(i)
            else:
                host.add(i)
    spine = sorted(set(spine))
    leaf = sorted(set(leaf))
    host = sorted(set(host))
    # dic={old,new}
    host_dic = {x: 0 + i for i, x in enumerate(host)}
    leaf_dic = {x: len(host) + i for i, x in enumerate(leaf)}
    spine_dic = {x: len(host) + len(leaf) + i for i, x in enumerate(spine)}

    gen_config(host_dic, leaf_dic, spine_dic)
    gen_router(host_dic, leaf_dic, spine_dic)
    change_rdma(path, file_path_list, host_dic, leaf_dic, spine_dic)



if __name__ == "__main__":
    # 在此处更改工作目录
    Working_Directory = "topo_ready/4K-1flow"
    file_path_list = get_rdma_files(Working_Directory)
    Flow_Info_List, Link_Info_List, Route_Info_Table, Link_Map, Reverse_Link_Map, host_num, leaf_num, spine_num = load_file(Working_Directory, file_path_list)
    node_in_set = int(host_num / leaf_num)
    Total_Flow_Path, Flow_Paths_Port = find_ecmp_path(Flow_Info_List, Link_Info_List, Route_Info_Table, Link_Map, Reverse_Link_Map)
    for item in Total_Flow_Path:
        # 获取元组的第二个位置的列表
        inner_list = item[1]
        # 遍历列表中的每个元素
        for element in inner_list:
            used_nodes.add(element)
    TopoCut(Total_Flow_Path, file_path_list)
    print(used_nodes)


