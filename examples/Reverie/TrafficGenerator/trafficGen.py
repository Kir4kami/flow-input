#!/usr/bin/env python3
import networkx as nx
import random
import matplotlib.pyplot as plt
import os
import math
import argparse
import shutil
import re

# Root node
root_node = 'Root'

# Define node addition method
def addCommunicationEdge(G, layer, comm_type, parent_node, node_args):
    node_name = f"{len(G.nodes)}_{comm_type}{layer}"
    nodes_passed = [random.choice(['A', 'B', 'C', 'D', 'E']) for _ in range(random.randint(1, 3))]
    G.add_node(node_name, name=node_name, type=comm_type, layer=layer, nodes_passed=nodes_passed, children=[], isBurr=False, args=node_args)
    G.add_edge(parent_node, node_name)
    G.nodes[parent_node]['children'].append(node_name)
    return node_name

# Parse input file to construct tree
def constructTree(G, input_file):
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file {input_file} does not exist")
    
    valid_modes = {'EP', 'TP', 'PP', 'DP'}
    node_name_mapping = {}
    tp_multi_parent_nodes = {}  # {(layer, parent_nodes): generated_node_name}
    mode_counters = {'TP': 0, 'EP': 0, 'PP': 0, 'DP': 0}  # Track mode-specific counters for naming

    with open(input_file, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = re.split(r'\s+', line)
            if len(parts) < 3:
                raise ValueError(f"Line {line_num}: Invalid format, expected at least layer, mode, parent_node")
            
            try:
                layer = (parts[0])
                mode = parts[1]
                parent_nodes = parts[2].split('/')
            except ValueError:
                raise ValueError(f"Line {line_num}: Layer must be an integer")
            
            if mode not in valid_modes:
                raise ValueError(f"Line {line_num}: Invalid mode {mode}, must be one of {valid_modes}")
            
            # Validate and map parent nodes
            mapped_parent_nodes = []
            for parent_node in parent_nodes:
                if parent_node != root_node:
                    if parent_node not in node_name_mapping:
                        raise ValueError(f"Line {line_num}: Parent node {parent_node} does not exist")
                    parent_node = node_name_mapping[parent_node]
                if parent_node != root_node and parent_node not in G.nodes:
                    raise ValueError(f"Line {line_num}: Parent node {parent_node} does not exist")
                mapped_parent_nodes.append(parent_node)
            
            node_args = {
                'host_num': 4096,
                'num_nodes': 16,
                'dp': 1,
                'msg_len': 32*1024*1024,
                'num_phases': 15,
                'num_iterations': 1,
            }
            i = 3
            while i < len(parts):
                if parts[i].startswith('--'):
                    key = parts[i][2:].replace('-', '_')
                    if key not in node_args:
                        raise ValueError(f"Line {line_num}: Unknown argument {parts[i]}")
                    i += 1
                    if i >= len(parts):
                        raise ValueError(f"Line {line_num}: Missing value for {parts[i-1]}")
                    try:
                        if key == 'msg_len':
                            node_args[key] = evaluate_expression(parts[i])
                        else:
                            node_args[key] = int(parts[i])
                    except (ValueError, argparse.ArgumentTypeError) as e:
                        raise ValueError(f"Line {line_num}: Invalid value for {parts[i-1]}: {e}")
                i += 1
            
            # Handle TP nodes with multiple parents or same layer/parent
            generated_node_name = None
            if mode == 'TP' and len(parent_nodes) > 1:  # Multi-parent TP nodes
                parent_key = (layer, tuple(sorted(parent_nodes)))
                if parent_key in tp_multi_parent_nodes:
                    generated_node_name = tp_multi_parent_nodes[parent_key]
                    # Add edges for additional parents
                    for parent_node in mapped_parent_nodes:
                        if not G.has_edge(parent_node, generated_node_name):
                            G.add_edge(parent_node, generated_node_name)
                            G.nodes[parent_node]['children'].append(generated_node_name)
                else:
                    # Create new node for the first parent
                    generated_node_name = addCommunicationEdge(G, layer, mode, mapped_parent_nodes[0], node_args)
                    tp_multi_parent_nodes[parent_key] = generated_node_name
                    # Add edges for remaining parents
                    for parent_node in mapped_parent_nodes[1:]:
                        if not G.has_edge(parent_node, generated_node_name):
                            G.add_edge(parent_node, generated_node_name)
                            G.nodes[parent_node]['children'].append(generated_node_name)
            else:
                # Non-TP or single-parent TP nodes
                for parent_node in mapped_parent_nodes:
                    generated_node_name = addCommunicationEdge(G, layer, mode, parent_node, node_args)
            
            # Map expected node name
            mode_counters[mode] += 1
            expected_node_name = f"{mode}{mode_counters[mode]}"
            node_name_mapping[expected_node_name] = generated_node_name

# Traffic generator functions
def evaluate_expression(value):
    try:
        return int(eval(value, {"__builtins__": {}}, {}))
    except Exception as e:
        raise argparse.ArgumentTypeError(f"Invalid expression: {value}. Error: {e}")

def get_neighbor(index, num, iter):
    span = 2 ** (iter - 1)
    left_nei = index - span
    right_nei = index + span
    if left_nei < 0:
        return right_nei
    if right_nei > num - 1:
        return left_nei
    if left_nei // 2 ** iter == index // 2 ** iter:
        return left_nei
    if right_nei // 2 ** iter == index // 2 ** iter:
        return right_nei
    raise ValueError(f"No valid neighbor for index {index}, num {num}, iter {iter}")

def write_file(result, file_name, append=False):
    os.makedirs(os.path.dirname(file_name), exist_ok=True)
    mode = 'a' if append else 'w'
    try:
        with open(file_name, mode) as fd:
            if not append:
                fd.write("stat rdma operate:\n")
            for phase in result:
                fd.write("phase:3000\n")
                for line in phase:
                    fd.write(line)
    except IOError:
        print(f"无法写入文件: {file_name}")
        return 1
    return 0

def get_host_list(host_num, dp):
    if host_num % dp != 0:
        raise ValueError(f"host_num {host_num} 无法被 dp {dp} 整除")
    span = host_num // dp
    host_list = []
    for start in range(span):
        host_ids = [host_id for host_id in range(start, host_num, span)]
        host_list.append(host_ids)
    return host_list

# 修改后的 set_all2all 函数，增加了端口参数
def set_all2all(host_list, msg_len, port, file_name=""):
    host_num = len(host_list)
    result = []
    for step in range(1, host_num):
        phase = []
        for idx, host_id_a in enumerate(host_list):
            idy = (step + idx) % host_num
            host_id_b = host_list[idy]
            phase.append(
                f"Type rdma_send src_node {host_id_a} src_port {port} "
                f"dst_node {host_id_b} dst_port {port} priority 0 "  # 修改了端口号
                f"msg_len {msg_len}\n"
            )
        result.append(phase)
    if file_name:
        write_file(result, file_name)
    return result

# 修改后的 set_hypercube 函数，增加了端口参数
def set_hypercube(host_list, msg_len, port, file_name=""):
    host_num = len(host_list)
    iter_times = math.log2(host_num)
    if not iter_times.is_integer():
        # Pad host_list to the next power of 2
        target_num = 2 ** math.ceil(math.log2(host_num))
        while len(host_list) < target_num:
            host_list.append(random.randint(0, host_num - 1))
        host_num = len(host_list)
        iter_t = math.log2(host_num)
    iter_times = int(iter_times)
    result = []
    for iter in range(1, iter_times + 1):
        res1, res, res2 = [], [], []
        msg = msg_len // (2 ** iter)
        for idx, host in enumerate(host_list):
            nei_idx = get_neighbor(idx, host_num, iter)
            res1.append(
                f"Type rdma_send src_node {host} src_port {port} "
                f"dst_node {host_list[nei_idx]} dst_port {port} priority 0 "  # 修改了端口号
                f"msg_len 64\n"
            )
            res.append(
                f"Type rdma_send src_node {host} src_port {port} "
                f"dst_node {host_list[nei_idx]} dst_port {port} priority 0 "  # 修改了端口号
                f"msg_len {msg}\n"
            )
            res2.append(
                f"Type rdma_send src_node {host} src_port {port} "
                f"dst_node {host_list[nei_idx]} dst_port {port} priority 0 "  # 修改了端口号
                f"msg_len 64\n"
            )
        result.extend([res1, res, res2])
    result += result[::-1]
    if file_name:
        write_file(result, file_name)
    return result

# 修改后的 set_tensor_parallel 函数，增加了端口参数
def set_tensor_parallel(m, num_nodes, msg_len, num_phases, port, file_name="", append=False):
    if num_nodes <= 0 or num_phases <= 0:
        raise ValueError(f"num_nodes {num_nodes} 和 num_phases {num_phases} 必须大于 0")
    result = []
    for _ in range(num_phases):
        phase = []
        for i in range(m * num_nodes, (m + 1) * num_nodes):
            dst_node = i + 1 if i < (m + 1) * num_nodes - 1 else m * num_nodes
            phase.append(
                f"Type rdma_send src_node {i} src_port {port} "
                f"dst_node {dst_node} dst_port {port} priority 0 "  # 修改了端口号
                f"msg_len {msg_len}\n"
            )
        result.append(phase)
    if file_name:
        write_file(result, file_name, append)
    return result

# 修改后的 set_pipeline_parallel 函数，增加了端口参数
def set_pipeline_parallel(node_pairs, msg_len, port, file_name=""):
    result = [[]]
    for src_node, dst_node in node_pairs:
        result[0].append(
            f"Type rdma_send src_node {src_node} src_port {port} "
            f"dst_node {dst_node} dst_port {port} priority 0 "  # 修改了端口号
            f"msg_len {msg_len}\n"
        )
    if file_name:
        write_file(result, file_name)
    return result

def generate_pipeline_pairs(host_num):
    return [(host_num + i, i) for i in range(host_num)]

# Generate traffic based on tree
def generate_traffic_from_tree(T):
    # 添加端口号计数器，从1000开始
    port_counter = 1000
    
    # Map node types to traffic modes
    type_to_mode = {
        'EP': 'ep',
        'TP': 'tp',
        'PP': 'pp',
        'DP': 'dp'
    }

    # Map letters to host IDs for validation
    letter_to_id = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5}

    # Traverse tree in topological order
    for node in nx.topological_sort(T):
        if node == root_node:
            continue
        node_data = T.nodes[node]
        comm_type = node_data['type']
        node_name = node_data['name']
        nodes_passed = node_data['nodes_passed']
        node_args = node_data['args']

        if comm_type not in type_to_mode:
            print(f"Skipping node {node}: Unknown type {comm_type}")
            continue

        mode = type_to_mode[comm_type]

        # Validate nodes_passed (used for validation only, not traffic generation)
        host_list_validation = [letter_to_id[host] for host in nodes_passed if host in letter_to_id]
        host_list_validation = [h for h in host_list_validation if h < node_args['host_num']]
        if not host_list_validation:
            print(f"Node {node}: No valid hosts in nodes_passed {nodes_passed}")
            continue

        # Initialize grouping variables
        dp = max(1, node_args['dp'])
        host_list = []
        node_pairs = []
        num_groups = 1

        # Compute groups based on mode
        try:
            if mode in ["ep", "dp"]:
                host_list = get_host_list(node_args['host_num'], dp)
                num_groups = len(host_list)
                if not host_list:
                    print(f"Node {node}: get_host_list returned empty list: host_num={node_args['host_num']}, dp={dp}")
                    continue
            elif mode == "tp":
                if node_args['host_num'] % node_args['num_nodes'] != 0:
                    print(f"Node {node}: host_num {node_args['host_num']} not divisible by num_nodes {node_args['num_nodes']}")
                    continue
                num_groups = node_args['host_num'] // node_args['num_nodes']
                dp = num_groups
            elif mode == "pp":
                nodes_per_group = max(1, node_args['host_num'] // dp)
                node_pairs = generate_pipeline_pairs(node_args['host_num'])
                num_groups = dp
        except ValueError as e:
            print(f"Node {node}: {e}")
            continue

        # Limit num_groups to prevent excessive file generation
        if num_groups > 1000:
            print(f"Node {node}: num_groups={num_groups} is too large, limiting to 1000")
            num_groups = 1000

        # Generate configuration for each group
        for group_idx in range(num_groups):
            # 为当前组分配端口号并递增
            current_port = port_counter
            port_counter += 1
            
            index_str = "" if group_idx == 0 else str(group_idx)
            file_name = f"rdma_result/{node_name}/rdma_operate{index_str}.txt"

            try:
                if mode == "ep":
                    set_all2all(host_list[group_idx], node_args['msg_len'], current_port, file_name)
                elif mode == "dp":
                    set_hypercube(host_list[group_idx], node_args['msg_len'], current_port, file_name)
                elif mode == "tp":
                    for iteration in range(node_args['num_iterations']):
                        append = iteration > 0
                        set_tensor_parallel(
                            group_idx, node_args['num_nodes'], node_args['msg_len'], 
                            node_args['num_phases'], current_port, file_name, append
                        )
                elif mode == "pp":
                    start_idx = group_idx * nodes_per_group
                    end_idx = min((group_idx + 1) * nodes_per_group, node_args['host_num'])
                    group_pairs = node_pairs[start_idx:end_idx]
                    set_pipeline_parallel(group_pairs, node_args['msg_len'], current_port, file_name)
                print(f"Generated traffic for node {node}, group {group_idx} (mode: {mode}) with port {current_port}")
            except ValueError as e:
                print(f"Error generating traffic for node {node}, group {group_idx}: {e}")
def main(args):
    # Clear previous rdma_result directory
    result_dir = "rdma_result"
    try:
        if os.path.exists(result_dir):
            shutil.rmtree(result_dir)
            print(f"Removed existing {result_dir} directory")
    except Exception as e:
        print(f"Error removing {result_dir}: {e}")
        return 1

    # Create directed graph
    T = nx.DiGraph()
    T.add_node(root_node, name='Root', nodes_passed=[], children=[])

    # Construct tree from input file
    try:
        constructTree(T, args.input_file)
    except Exception as e:
        print(f"Error constructing tree from {args.input_file}: {e}")
        return 1

    # Generate traffic
    generate_traffic_from_tree(T)

    # Optional: Visualize tree (uncomment to enable)
    """
    try:
        pos = nx.nx_agraph.graphviz_layout(T, prog='dot')
    except ImportError:
        pos = nx.spring_layout(T)
    nx.draw(T, pos, with_labels=True, node_color='lightblue', arrows=True)
    plt.show()
    """

    print("Traffic generation completed")
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Traffic generator based on communication tree from file input."
    )
    parser.add_argument(
        "--input_file",
        type=str,
        required=True,
        help="Path to input file defining the communication tree"
    )
    args = parser.parse_args()
    exit_code = main(args)
    if exit_code != 0:
        print("Traffic generation failed")