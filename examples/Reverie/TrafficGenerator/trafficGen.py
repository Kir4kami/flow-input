#!/usr/bin/env python3
import networkx as nx
import random
import os
import math
import argparse
import shutil
import re

# Root node
root_node = 'Root'

# Global variables
model_identifier = None
max_devices = None
max_iterations = None
global_node_counter = 1  # 从1开始计数
first_tp_args = None  # 存储第一行 TP 节点的参数

# Define node addition method
def addCommunicationEdge(G, layer, comm_type, parent_node, node_args):
    global global_node_counter
    node_name = f"{global_node_counter}_{comm_type}{layer}"
    nodes_passed = [random.choice(['A', 'B', 'C', 'D', 'E']) for _ in range(random.randint(1, 3))]
    G.add_node(node_name, name=node_name, type=comm_type, layer=layer, nodes_passed=nodes_passed, children=[], isBurr=False, args=node_args)
    G.add_edge(parent_node, node_name)
    G.nodes[parent_node]['children'].append(node_name)
    global_node_counter += 1
    return node_name

def constructTree(G, input_file, iteration=0, prev_dp_node=None, prev_dp_args=None):
    global model_identifier, max_devices, max_iterations, first_tp_args
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Input file {input_file} does not exist")
    
    valid_modes = {'EP', 'TP', 'PP', 'DP'}
    node_name_mapping = {}
    tp_multi_parent_nodes = {}
    mode_counters = {'TP': 0, 'EP': 0, 'PP': 0, 'DP': 0}

    # 如果有prev_dp_node，添加到当前图
    if prev_dp_node and iteration > 0:
        layer = str(17 + (iteration - 1) * 17)  # 前一迭代的DP层级
        G.add_node(prev_dp_node, name=prev_dp_node, type='DP', layer=layer, nodes_passed=[], children=[], isBurr=False, args=prev_dp_args)

    with open(input_file, 'r') as f:
        lines = f.readlines()
        if not lines:
            raise ValueError("Input file is empty")
        
        # 解析第一行：model devices iterations
        first_line = lines[0].strip()
        first_line_parts = re.split(r'\s+', first_line)
        if len(first_line_parts) != 3:
            raise ValueError(f"First line must specify model, devices, and iterations, got '{first_line}'")
        model, devices, iterations = first_line_parts
        if model.lower() not in {'qwen', 'deepseek'}:
            raise ValueError(f"First line model must be 'Qwen' or 'DeepSeek', got '{model}'")
        try:
            max_devices = int(devices)
            if max_devices <= 0:
                raise ValueError("Devices must be a positive integer")
            max_iterations = int(iterations)
            if max_iterations <= 0:
                raise ValueError("Iterations must be a positive integer")
        except ValueError:
            raise ValueError(f"Invalid devices or iterations value: '{devices}', '{iterations}', must be positive integers")
        model_identifier = model.lower()
        
        print(f"Iteration {iteration}: Parsed model={model_identifier}, devices={max_devices}, iterations={max_iterations}")
        
        # Process remaining lines
        for line_num, line in enumerate(lines[1:], 2):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            parts = re.split(r'\s+', line)
            if len(parts) < 3:
                raise ValueError(f"Line {line_num}: Invalid format, expected at least layer, mode, parent_node")
            
            try:
                layer = str(int(parts[0]) + iteration * 17)  # 调整层级
                mode = parts[1]
                parent_nodes = parts[2].split('/')
            except ValueError:
                raise ValueError(f"Line {line_num}: Layer must be provided")
            
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
                'host_num': 128,
                'num_nodes': 8,
                'dp': 1,
                'msg_len': 32*1024*1024,
                'num_phases': 7,
                'num_iterations': 1,
                'device': 0,
                'forward': 1
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
                        elif key in {'device', 'forward'}:
                            node_args[key] = int(parts[i])
                            if key == 'device' and (node_args[key] < 0 or node_args[key] >= max_devices):
                                raise ValueError(f"Line {line_num}: Device must be in [0, {max_devices-1}], got {parts[i]}")
                            if key == 'forward' and node_args[key] not in [0, 1]:
                                raise ValueError(f"Line {line_num}: Forward must be 0 or 1, got {parts[i]}")
                        else:
                            node_args[key] = int(parts[i])
                    except (ValueError, argparse.ArgumentTypeError) as e:
                        raise ValueError(f"Line {line_num}: Invalid value for {parts[i-1]}: {e}")
                i += 1
            
            # 存储第一行 TP 节点的参数
            if line_num == 2 and mode == 'TP' and iteration == 0:
                first_tp_args = node_args.copy()
                print(f"Iteration {iteration}: Stored first TP args: {first_tp_args}")
            
            # Handle TP nodes with multiple parents
            generated_node_name = None
            if mode == 'TP' and len(parent_nodes) > 1:
                parent_key = (layer, tuple(sorted(parent_nodes)))
                if parent_key in tp_multi_parent_nodes:
                    generated_node_name = tp_multi_parent_nodes[parent_key]
                    for parent_node in mapped_parent_nodes:
                        if not G.has_edge(parent_node, generated_node_name):
                            G.add_edge(parent_node, generated_node_name)
                            G.nodes[parent_node]['children'].append(generated_node_name)
                else:
                    generated_node_name = addCommunicationEdge(G, layer, mode, mapped_parent_nodes[0], node_args)
                    tp_multi_parent_nodes[parent_key] = generated_node_name
                    for parent_node in mapped_parent_nodes[1:]:
                        if not G.has_edge(parent_node, generated_node_name):
                            G.add_edge(parent_node, generated_node_name)
                            G.nodes[parent_node]['children'].append(generated_node_name)
            else:
                for parent_node in mapped_parent_nodes:
                    generated_node_name = addCommunicationEdge(G, layer, mode, parent_node, node_args)
            
            mode_counters[mode] += 1
            expected_node_name = f"{mode}{mode_counters[mode]}"
            node_name_mapping[expected_node_name] = generated_node_name

        # 添加额外的TP节点
        if prev_dp_node and iteration > 0:
            if first_tp_args is None:
                raise ValueError(f"Iteration {iteration}: first_tp_args is None, cannot create extra TP node")
            layer = str(17 + iteration * 17)
            mode = 'TP'
            node_args = first_tp_args.copy()  # 使用第一行 TP 节点的参数
            print(f"Iteration {iteration}: Adding extra TP node with args: {node_args}")
            generated_node_name = addCommunicationEdge(G, layer, mode, prev_dp_node, node_args)
            mode_counters['TP'] += 1
            expected_node_name = f"TP{mode_counters['TP']}"
            node_name_mapping[expected_node_name] = generated_node_name

    dp_node = node_name_mapping.get('DP1', None)
    dp_args = G.nodes[dp_node]['args'] if dp_node else None
    return dp_node, dp_args

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

def get_host_list_dp(host_num, dp):
    if host_num % dp != 0:
        raise ValueError(f"host_num {host_num} 无法被 dp {dp} 整除")
    span = host_num // dp
    host_list = []
    for start in range(0, span):
        host_ids = [host_id for host_id in range(start, host_num, span)]
        host_list.append(host_ids)
    return host_list

def get_host_list_ep(host_num, dp, device):
    if host_num % dp != 0:
        raise ValueError(f"host_num {host_num} 无法被 dp {dp} 整除")
    span = host_num // max_devices // dp
    host_list = []
    for start in range(0 + device * span, span + device * span):
        host_ids = [host_id for host_id in range(start, host_num, 2 * span)]
        host_list.append(host_ids)
    return host_list

def set_all2all(host_list, msg_len, port, forward, file_name=""):
    host_num = len(host_list)
    result = []
    for step in range(1, host_num):
        phase = []
        for idx, host_id_a in enumerate(host_list):
            idy = (step + idx) % host_num
            host_id_b = host_list[idy]
            src_node, dst_node = (host_id_a, host_id_b) if forward else (host_id_b, host_id_a)
            src_port, dst_port = (port, port) if forward else (port, port)
            phase.append(
                f"Type rdma_send src_node {src_node} src_port {src_port} "
                f"dst_node {dst_node} dst_port {dst_port} priority 0 "
                f"msg_len {msg_len}\n"
            )
        result.append(phase)
    if file_name:
        write_file(result, file_name)
    return result

def set_hypercube(host_list, msg_len, port, file_name=""):
    host_num = len(host_list)
    iter_times = math.log2(host_num)
    if not iter_times.is_integer():
        target_num = 2 ** math.ceil(math.log2(host_num))
        while len(host_list) < target_num:
            host_list.append(random.randint(0, host_num - 1))
        host_num = len(host_list)
        iter_times = math.log2(host_num)
    iter_times = int(iter_times)
    result = []
    for iter in range(1, iter_times + 1):
        res = []
        msg = msg_len // (2 ** iter)
        for idx, host in enumerate(host_list):
            nei_idx = get_neighbor(idx, host_num, iter)
            res.append(
                f"Type rdma_send src_node {host} src_port {port} "
                f"dst_node {host_list[nei_idx]} dst_port {port} priority 0 "
                f"msg_len {msg}\n"
            )
        result.extend([res])
    result += result[::-1]
    if file_name:
        write_file(result, file_name)
    return result

def set_tensor_parallel(m, num_nodes, msg_len, num_phases, device, port, forward, file_name="", append=False):
    if num_nodes <= 0 or num_phases <= 0:
        raise ValueError(f"num_nodes {num_nodes} 和 num_phases {num_phases} 必须大于 0")
    result = []
    for _ in range(num_phases):
        phase = []
        start = math.floor((m + 0.5 * device) * 2 * num_nodes)
        end = math.floor(((m + 0.5 * device) * 2 + 1) * num_nodes)
        for i in range(start, end):
            dst_node = i + 1 if i < end - 1 else start
            src_node, dst_node = (i, dst_node) if forward else (dst_node, i)
            src_port, dst_port = (port, port) if forward else (port, port)
            phase.append(
                f"Type rdma_send src_node {src_node} src_port {src_port} "
                f"dst_node {dst_node} dst_port {dst_port} priority 0 "
                f"msg_len {msg_len}\n"
            )
        result.append(phase)
    if file_name:
        write_file(result, file_name, append)
    return result

def set_pipeline_parallel(node_pairs, msg_len, port, forward, file_name=""):
    result = [[]]
    for src_node, dst_node in node_pairs:
        src_node, dst_node = (src_node, dst_node) if forward else (dst_node, src_node)
        src_port, dst_port = (port, port) if forward else (port, port)
        result[0].append(
            f"Type rdma_send src_node {src_node} src_port {src_port} "
            f"dst_node {dst_node} dst_port {dst_port} priority 0 "
            f"msg_len {msg_len}\n"
        )
    if file_name:
        write_file(result, file_name)
    return result

def generate_pipeline_pairs(host_num, dp):
    node_pairs = []
    num_groups = max(1, (max_devices * host_num) // (max_devices * dp))
    for k in range(num_groups):
        for i in range(dp):
            src_node = k * max_devices * dp + i
            dst_node = src_node + dp
            if src_node < host_num and dst_node < max_devices * host_num:
                node_pairs.append((src_node, dst_node))
    return node_pairs

def generate_traffic_from_tree(T, iteration=0):
    global model_identifier, max_devices
    port_counter = 1000 + iteration * 1000
    type_to_mode = {'EP': 'ep', 'TP': 'tp', 'PP': 'pp', 'DP': 'dp'}
    letter_to_id = {'A': 0, 'B': 1, 'C': 2, 'D': 3, 'E': 4, 'F': 5}

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
        if model_identifier == 'deepseek' and comm_type == 'EP':
            mode = 'tp'

        host_list_validation = [letter_to_id[host] for host in nodes_passed if host in letter_to_id]
        host_list_validation = [h for h in host_list_validation if h < node_args['host_num']]
        if not host_list_validation:
            print(f"Node {node}: No valid hosts in nodes_passed {nodes_passed}")
            continue

        dp = max(1, node_args['dp'])
        host_list = []
        node_pairs = []
        num_groups = 1

        try:
            if mode == "dp":
                host_list = get_host_list_dp(node_args['host_num'], dp)
                num_groups = len(host_list)
                if not host_list:
                    print(f"Node {node}: get_host_list returned empty list: host_num={node_args['host_num']}, dp={dp}")
                    continue
            elif mode == "ep":
                host_list = get_host_list_ep(node_args['host_num'], dp, node_args['device'])
                num_groups = len(host_list)
                if not host_list:
                    print(f"Node {node}: get_host_list returned empty list: host_num={node_args['host_num']}, dp={dp}")
                    continue
            elif mode == "tp":
                if node_args['host_num'] % node_args['num_nodes'] != 0:
                    print(f"Node {node}: host_num {node_args['host_num']} not divisible by num_nodes {node_args['num_nodes']}")
                    continue
                num_groups = node_args['host_num'] // max_devices // node_args['num_nodes']
                dp = num_groups
            elif mode == "pp":
                nodes_per_group = max(1, node_args['host_num'] // max_devices // dp)
                node_pairs = generate_pipeline_pairs(node_args['host_num'], dp)
                num_groups = dp
        except ValueError as e:
            print(f"Node {node}: {e}")
            continue

        if num_groups > 1000:
            print(f"Node {node}: num_groups={num_groups} is too large, limiting to 1000")
            num_groups = 1000

        for group_idx in range(num_groups):
            current_port = port_counter
            port_counter += 1
            index_str = "" if group_idx == 0 else str(group_idx)
            file_name = f"rdma_result/{node_name}/rdma_operate{index_str}.txt"

            try:
                if mode == "ep" and model_identifier != 'deepseek':
                    set_all2all(host_list[group_idx], node_args['msg_len'], current_port, node_args['forward'], file_name)
                elif mode == "dp":
                    set_hypercube(host_list[group_idx], node_args['msg_len'], current_port, file_name)
                elif mode == "tp":
                    for iter_idx in range(node_args['num_iterations']):
                        append = iter_idx > 0
                        set_tensor_parallel(
                            group_idx, node_args['num_nodes'], node_args['msg_len'], 
                            node_args['num_phases'], node_args['device'], current_port, node_args['forward'], file_name, append
                        )
                elif mode == "pp":
                    start_idx = group_idx * nodes_per_group
                    end_idx = min((group_idx + 1) * nodes_per_group, node_args['host_num'] // max_devices)
                    group_pairs = node_pairs[start_idx:end_idx]
                    set_pipeline_parallel(group_pairs, node_args['msg_len'], current_port, node_args['forward'], file_name)
                print(f"Generated traffic for node {node}, group {group_idx} (mode: {mode}, iteration: {iteration}) with port {current_port}")
            except ValueError as e:
                print(f"Error generating traffic for node {node}, group {group_idx}: {e}")

def main(args):
    global model_identifier, max_devices, max_iterations, global_node_counter, first_tp_args
    model_identifier = None
    max_devices = None
    max_iterations = None
    global_node_counter = 1
    first_tp_args = None
    result_dir = "rdma_result"
    try:
        if os.path.exists(result_dir):
            shutil.rmtree(result_dir)
            print(f"Removed existing {result_dir} directory")
    except Exception as e:
        print(f"Error removing {result_dir}: {e}")
        return 1

    # 先解析输入文件以获取max_iterations
    T = nx.DiGraph()
    T.add_node(root_node, name='Root', nodes_passed=[], children=[])
    try:
        constructTree(T, args.input_file)  # 第一次调用仅用于设置max_iterations和first_tp_args
        print(f"max_iterations after initial parse: {max_iterations}")
    except Exception as e:
        print(f"Error parsing input file {args.input_file}: {e}")
        return 1

    # 重置计数器并开始迭代
    global_node_counter = 1
    prev_dp_node = None
    prev_dp_args = None
    for iteration in range(max_iterations):
        print(f"Starting iteration {iteration}")
        T = nx.DiGraph()
        T.add_node(root_node, name='Root', nodes_passed=[], children=[])
        try:
            dp_node, dp_args = constructTree(T, args.input_file, iteration, prev_dp_node, prev_dp_args)
            if dp_node is None:
                print(f"Iteration {iteration}: No DP node found")
                return 1
            generate_traffic_from_tree(T, iteration)
            prev_dp_node = dp_node
            prev_dp_args = dp_args
        except Exception as e:
            print(f"Error in iteration {iteration} with file {args.input_file}: {e}")
            return 1

    print(f"Traffic generation completed for model {model_identifier} with {max_devices} devices and {max_iterations} iterations")
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