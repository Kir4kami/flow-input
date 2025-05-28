#!/usr/bin/env python3
import os
import math
import argparse

def evaluate_expression(value):
    """
    将输入字符串评估为整数表达式。
    """
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

def main(args):
    mode = args.mode.lower()
    if mode not in ["a2a", "dp", "tp", "pp"]:
        print(f"不支持的通信模式: {mode}")
        return 1

    # 验证参数
    if args.host_num <= 0:
        print(f"host_num 必须大于 0，当前值: {args.host_num}")
        return 1
    if args.num_nodes <= 0 and mode in ["tp", "pp"]:
        print(f"num_nodes 必须大于 0，当前值: {args.num_nodes}")
        return 1
    if args.dp <= 0:
        print(f"dp 必须大于 0，当前值: {args.dp}")
        return 1
    if args.msg_len <= 0:
        print(f"msg_len 必须大于 0，当前值: {args.msg_len}")
        return 1
    if args.num_phases <= 0 and mode == "tp":
        print(f"num_phases 必须大于 0，当前值: {args.num_phases}")
        return 1
    if args.num_iterations <= 0 and mode == "tp":
        print(f"num_iterations 必须大于 0，当前值: {args.num_iterations}")
        return 1

    # 计算分组
    dp = max(1, args.dp)
    host_list = []
    node_pairs = []
    if mode in ["a2a", "dp"]:
        try:
            host_list = get_host_list(args.host_num, dp)
            num_groups = len(host_list)  # Number of groups is span, not dp
        except ValueError as e:
            print(e)
            return 1
        if not host_list:
            print(f"get_host_list 返回空列表: host_num={args.host_num}, dp={dp}")
            return 1
    elif mode == "tp":
        if args.host_num % args.num_nodes != 0:
            print(f"host_num {args.host_num} 无法被 num_nodes {args.num_nodes} 整除")
            return 1
        num_groups = args.host_num // args.num_nodes
        dp=num_groups
    elif mode == "pp":
        nodes_per_group = max(1, args.host_num // dp)
        node_pairs = generate_pipeline_pairs(args.host_num)
        num_groups = dp

    # 生成配置
    for group_idx in range(num_groups):
        index_str = "" if group_idx == 0 else str(group_idx)
        file_name = f"rdma_result/{args.topo}/dp{dp}/rdma_operate{index_str}.txt"

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

    print(f"{mode} 模式 RDMA 配置生成成功")
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="RDMA 流量生成器，支持多种通信模式（All-to-All、Hypercube、Tensor Parallel、Pipeline Parallel）。"
    )
    parser.add_argument(
        "--mode",
        type=str,
        default="a2a",
        choices=["a2a", "dp", "tp", "pp"],
        help="通信模式（默认: a2a）"
    )
    parser.add_argument(
        "--topo",
        type=str,
        default="topo_traffic",
        help="拓扑名称（默认: topo_traffic）"
    )
    parser.add_argument(
        "--host_num",
        type=int,
        default=2048,
        help="总节点数（默认: 2048）"
    )
    parser.add_argument(
        "--num_nodes",
        type=int,
        default=16,
        help="每组节点数（对 tp  有效，默认: 16）"
    )
    parser.add_argument(
        "--dp",
        type=int,
        default=1,
        help="分组数（默认: 1）"
    )
    parser.add_argument(
        "--msg_len",
        type=evaluate_expression,
        default=32*1024*1024,
        help="消息长度（字节，支持表达式，如 32*1024*1024，默认: 32MB）"
    )
    parser.add_argument(
        "--num_phases",
        type=int,
        default=15,
        help="通信阶段数（对 tp 有效，默认: 15）"
    )
    parser.add_argument(
        "--num_iterations",
        type=int,
        default=1,
        help="每组生成次数（对 tp 有效，默认: 1）"
    )

    args = parser.parse_args()
    exit_code = main(args)
    if exit_code != 0:
        print(f"{args.mode} 模式生成失败")