#!/usr/bin/env python3
import argparse
import os


def get_neighbor(index, num, it):
    span = 2 ** (it - 1)
    left_nei = index - span
    right_nei = index + span
    if left_nei < 0:
        return right_nei
    if right_nei > num - 1:
        return left_nei
    if left_nei // 2 ** it == index // 2 ** it:
        return left_nei
    if right_nei // 2 ** it == index // 2 ** it:
        return right_nei
    raise ValueError("neighbor not found")


def write_file(lines, file_name):
    os.makedirs(os.path.dirname(file_name), exist_ok=True)
    with open(file_name, "w") as fd:
        fd.write("stat rdma operate:\n")
        fd.write("phase:3000\n")
        for line in lines:
            fd.write(line)


def get_host_list(host_num, dp):
    if host_num % dp != 0:
        raise ValueError("host_num must be divisible by dp")
    span = host_num // dp
    host_list = []
    for start in range(span):
        host_ids = []
        for host_id in range(start, host_num, span):
            host_ids.append(host_id)
        host_list.append(host_ids)
    return host_list


def build_lines_for_host_list(host_list, msg_len):
    host_num = len(host_list)
    iter_times = 0
    for i in range(15):
        standard_hd_num = 2 ** i
        if standard_hd_num > host_num:
            raise ValueError("host_num not power of two")
        if standard_hd_num == host_num:
            iter_times = i
            break

    lines = []
    for it in range(1, iter_times + 1):
        msg = msg_len // (2 ** it)
        for idx, host in enumerate(host_list):
            nei_idx = get_neighbor(idx, host_num, it)
            lines.append(
                "Type rdma_send src_node " + str(host) + " src_port 0 "
                "dst_node " + str(host_list[nei_idx]) + " dst_port 0 "
                "priority 0 msg_len 64\n"
            )
        for idx, host in enumerate(host_list):
            nei_idx = get_neighbor(idx, host_num, it)
            lines.append(
                "Type rdma_send src_node " + str(host) + " src_port 0 "
                "dst_node " + str(host_list[nei_idx]) + " dst_port 0 "
                "priority 0 msg_len " + str(msg) + "\n"
            )
        for idx, host in enumerate(host_list):
            nei_idx = get_neighbor(idx, host_num, it)
            lines.append(
                "Type rdma_send src_node " + str(host) + " src_port 0 "
                "dst_node " + str(host_list[nei_idx]) + " dst_port 0 "
                "priority 0 msg_len 64\n"
            )
    lines += list(reversed(lines))
    return lines


def parse_args():
    parser = argparse.ArgumentParser(description="Generate DP traffic with a single phase.")
    parser.add_argument("--topo", type=str, default="topo_dp")
    parser.add_argument("--host_num", type=int, default=64)
    parser.add_argument("--dp_list", type=str, default="8")
    parser.add_argument("--msg_len", type=int, default=4096000)
    parser.add_argument("--output_dir", type=str, default="result")
    return parser.parse_args()


def main():
    args = parse_args()
    dp_list = [int(x) for x in args.dp_list.split(",") if x.strip()]
    for dp in dp_list:
        host_groups = get_host_list(args.host_num, dp)
        for index, host_ids in enumerate(host_groups):
            suffix = str(index)
            file_name = (
                f"{args.output_dir}/{args.topo}/host_num{args.host_num}/dp{dp}/"
                f"rdma_operate{suffix}.txt"
            )
            lines = build_lines_for_host_list(host_ids, args.msg_len)
            write_file(lines, file_name)


if __name__ == "__main__":
    main()
