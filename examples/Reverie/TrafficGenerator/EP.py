#!/usr/bin/env python3
import argparse
import os


def write_file(phases, file_name):
    os.makedirs(os.path.dirname(file_name), exist_ok=True)
    with open(file_name, "w") as fd:
        fd.write("stat rdma operate:\n")
        for phase_lines in phases:
            fd.write("phase:3000\n")
            for line in phase_lines:
                fd.write(line)


def get_host_list(host_num, dp):
    if host_num % dp != 0:
        raise ValueError(f"host_num({host_num}) must be divisible by dp({dp})")
    span = host_num // dp
    host_list = []
    for start in range(span):
        host_ids = []
        for host_id in range(start, host_num, span):
            host_ids.append(host_id)
        host_list.append(host_ids)
    return host_list


def build_a2a_phases(host_ids, msg_len):
    host_num = len(host_ids)
    if host_num <= 1:
        return []
    phases = []
    for step in range(1, host_num):
        phase_lines = []
        for idx, src_node in enumerate(host_ids):
            dst_node = host_ids[(idx + step) % host_num]
            phase_lines.append(
                "Type rdma_send src_node " + str(src_node) + " src_port 0 "
                "dst_node " + str(dst_node) + " dst_port 0 "
                "priority 0 msg_len " + str(msg_len) + "\n"
            )
        phases.append(phase_lines)
    return phases


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate EP(all-to-all) traffic in the same format/path style as DP/TP/PP."
    )
    parser.add_argument("--topo", type=str, default="topo_ep")
    parser.add_argument("--host_num", type=int, default=64)
    parser.add_argument("--dp_list", type=str, default="8")
    parser.add_argument("--msg_len", type=int, default=4096000)
    parser.add_argument("--output_dir", type=str, default="result")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.host_num <= 1:
        raise SystemExit("host_num must be >= 2")

    dp_list = [int(x) for x in args.dp_list.split(",") if x.strip()]
    if not dp_list:
        raise SystemExit("dp_list is empty")

    for dp in dp_list:
        if dp <= 0:
            raise SystemExit("dp must be a positive integer")
        host_groups = get_host_list(args.host_num, dp)
        for group_idx, host_ids in enumerate(host_groups):
            file_name = (
                f"{args.output_dir}/{args.topo}/host_num{args.host_num}/dp{dp}/"
                f"rdma_operate{group_idx}.txt"
            )
            phases = build_a2a_phases(host_ids, args.msg_len)
            write_file(phases, file_name)


if __name__ == "__main__":
    main()

