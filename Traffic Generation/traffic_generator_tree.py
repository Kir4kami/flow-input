#!/usr/bin/env python3
import networkx as nx
import random
import matplotlib.pyplot as plt
import os
import math
import argparse
import shutil

# Root node
root_node = 'Root'

# Define node addition method
def addCommunicationEdge(G, layer, comm_type, pre_node):
    node_name = f"{len(G.nodes)}_{comm_type}{layer}"
    nodes_passed = [random.choice(['A', 'B', 'C', 'D', 'E']) for _ in range(random.randint(1, 3))]
    G.add_node(node_name, name=node_name, type=comm_type, layer=layer, nodes_passed=nodes_passed, children=[], isBurr=False)
    G.add_edge(pre_node, node_name)
    G.nodes[pre_node]['children'].append(node_name)
    return node_name

# Construct communication tree
def constructTree(G, root_node):
    A2A1 = addCommunicationEdge(G, 1, "A2A", root_node)
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

# Traffic generator functions
def evaluate_expression(value):
    try:
        return int(eval(value))
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

def set_all2all(host_list, msg_len, file_name=""):
    host_num = len(host_list)
    result = []
    for step in range(1, host_num):
        phase = []
        for idx, host_id_a in enumerate(host_list):
            idy = (step + idx) % host_num
            host_id_b = host_list[idy]
            phase.append(
                f"Type:rdma_send, src_node:{host_id_a}, src_port:0, "
                f"dst_node:{host_id_b}, dst_port:0, priority:0, "
                f"msg_len:{msg_len}\n"
            )
        result.append(phase)
    if file_name:
        write_file(result, file_name)
    return result

def set_hypercube(host_list, msg_len, file_name=""):
    host_num = len(host_list)
    iter_times = math.log2(host_num)
    if not iter_times.is_integer():
        raise ValueError(f"主机数 {host_num} 必须是 2 的幂")
    iter_times = int(iter_times)
    result = []
    for iter in range(1, iter_times + 1):
        res1, res, res2 = [], [], []
        msg = msg_len // (2 ** iter)
        for idx, host in enumerate(host_list):
            nei_idx = get_neighbor(idx, host_num, iter)
            res1.append(
                f"Type:rdma_send, src_node:{host}, src_port:0, "
                f"dst_node:{host_list[nei_idx]}, dst_port:0, priority:0, "
                f"msg_len:64\n"
            )
            res.append(
                f"Type:rdma_send, src_node:{host}, src_port:0, "
                f"dst_node:{host_list[nei_idx]}, dst_port:0, priority:0, "
                f"msg_len:{msg}\n"
            )
            res2.append(
                f"Type:rdma_send, src_node:{host}, src_port:0, "
                f"dst_node:{host_list[nei_idx]}, dst_port:0, priority:0, "
                f"msg_len:64\n"
            )
        result.extend([res1, res, res2])
    result += result[::-1]
    if file_name:
        write_file(result, file_name)
    return result

def set_tensor_parallel(m, num_nodes, msg_len, num_phases, file_name="", append=False):
    if num_nodes <= 0 or num_phases <= 0:
        raise ValueError(f"num_nodes {num_nodes} 和 num_phases {num_phases} 必须大于 0")
    result = []
    for _ in range(num_phases):
        phase = []
        for i in range(m * num_nodes, (m + 1) * num_nodes):
            dst_node = i + 1 if i < (m + 1) * num_nodes - 1 else m * num_nodes
            phase.append(
                f"Type:rdma_send, src_node:{i}, src_port:0, "
                f"dst_node:{dst_node}, dst_port:0, priority:0, "
                f"msg_len:{msg_len}\n"
            )
        result.append(phase)
    if file_name:
        write_file(result, file_name, append)
    return result

def set_pipeline_parallel(node_pairs, msg_len, file_name=""):
    result = [[]]
    for src_node, dst_node in node_pairs:
        result[0].append(
            f"Type:rdma_send, src_node:{src_node}, src_port:0, "
            f"dst_node:{dst_node}, dst_port:0, priority:0, "
            f"msg_len:{msg_len}\n"
        )
    if file_name:
        write_file(result, file_name)
    return result

def generate_pipeline_pairs(host_num):
    return [(host_num + i, i) for i in range(host_num)]

# Generate traffic based on tree
def generate_traffic_from_tree(T, args):
    # Map node types to traffic modes
    type_to_mode = {
        'A2A': 'a2a',
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

        if comm_type not in type_to_mode:
            print(f"Skipping node {node}: Unknown type {comm_type}")
            continue

        mode = type_to_mode[comm_type]

        # Validate nodes_passed
        host_list_validation = [letter_to_id[host] for host in nodes_passed if host in letter_to_id]
        host_list_validation = [h for h in host_list_validation if h < args.host_num]
        if not host_list_validation:
            print(f"Node {node}: No valid hosts in nodes_passed {nodes_passed}")
            continue

        # Initialize grouping variables
        dp = max(1, args.dp)
        host_list = []
        node_pairs = []
        num_groups = 1

        # Compute groups based on mode
        try:
            if mode in ["a2a", "dp"]:
                host_list = get_host_list(args.host_num, dp)
                num_groups = len(host_list)
                if not host_list:
                    print(f"Node {node}: get_host_list returned empty list: host_num={args.host_num}, dp={dp}")
                    continue
            elif mode == "tp":
                if args.host_num % args.num_nodes != 0:
                    print(f"Node {node}: host_num {args.host_num} not divisible by num_nodes {args.num_nodes}")
                    continue
                num_groups = args.host_num // args.num_nodes
                dp = num_groups
            elif mode == "pp":
                nodes_per_group = max(1, args.host_num // dp)
                node_pairs = generate_pipeline_pairs(args.host_num)
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
            index_str = "" if group_idx == 0 else str(group_idx)
            file_name = f"rdma_result/{node_name}/rdma_operate{index_str}.txt"#f"rdma_result/{node_name}/dp{dp}/rdma_operate{index_str}.txt"

            try:
                if mode == "a2a":
                    set_all2all(host_list[group_idx], args.msg_len, file_name)
                elif mode == "dp":
                    set_hypercube(host_list[group_idx], args.msg_len, file_name)
                elif mode == "tp":
                    for iteration in range(args.num_iterations):
                        append = iteration > 0
                        set_tensor_parallel(
                            group_idx, args.num_nodes, args.msg_len, args.num_phases,
                            file_name, append
                        )
                elif mode == "pp":
                    start_idx = group_idx * nodes_per_group
                    end_idx = min((group_idx + 1) * nodes_per_group, args.host_num)
                    group_pairs = node_pairs[start_idx:end_idx]
                    set_pipeline_parallel(group_pairs, args.msg_len, file_name)
                print(f"Generated traffic for node {node}, group {group_idx} (mode: {mode})")
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

    # Construct tree
    constructTree(T, root_node)

    # Generate traffic
    generate_traffic_from_tree(T, args)

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
        description="Traffic generator based on communication tree."
    )
    parser.add_argument(
        "--host_num",
        type=int,
        default=4096,
        help="Total number of nodes (default: 4096)"
    )
    parser.add_argument(
        "--num_nodes",
        type=int,
        default=16,
        help="Number of nodes per group for TP (default: 16)"
    )
    parser.add_argument(
        "--dp",
        type=int,
        default=1,
        help="Number of groups (default: 1)"
    )
    parser.add_argument(
        "--msg_len",
        type=evaluate_expression,
        default=32*1024*1024,
        help="Message length in bytes (default: 32MB)"
    )
    parser.add_argument(
        "--num_phases",
        type=int,
        default=15,
        help="Number of phases for TP (default: 15)"
    )
    parser.add_argument(
        "--num_iterations",
        type=int,
        default=1,
        help="Number of iterations for TP (default: 1)"
    )

    args = parser.parse_args()
    exit_code = main(args)
    if exit_code != 0:
        print("Traffic generation failed")