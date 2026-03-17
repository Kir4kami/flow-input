#!/usr/bin/env python3
import argparse
import os


def write_file(lines, file_name):
    os.makedirs(os.path.dirname(file_name), exist_ok=True)
    with open(file_name, "w") as fd:
        fd.write("stat rdma operate:\n")
        fd.write("phase:3000\n")
        for line in lines:
            fd.write(line)


def build_lines_for_lane(host_num, dp, msg_len, lane_idx):
    if lane_idx < 0 or lane_idx >= dp:
        raise ValueError("lane_idx out of range")

    lines = []
    # 每个 block 含 2*dp 个主机：前 dp 为 src，后 dp 为对应 dst
    block = 2 * dp
    for base in range(0, host_num, block):
        src = base + lane_idx
        dst = src + dp
        if dst >= host_num:
            continue
        lines.append(
            "Type rdma_send src_node " + str(src) + " src_port 0 "
            "dst_node " + str(dst) + " dst_port 0 "
            "priority 0 msg_len " + str(msg_len) + "\n"
        )
    return lines


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate PP traffic in the same format/path style as DP_onephase/TP_ring."
    )
    parser.add_argument("--topo", type=str, default="topo_pp")
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
    for dp in dp_list:
        if dp <= 0:
            raise SystemExit("dp must be a positive integer")
        if args.host_num < 2 * dp:
            raise SystemExit(f"host_num({args.host_num}) must be >= 2*dp({2*dp})")

        for lane_idx in range(dp):
            file_name = (
                f"{args.output_dir}/{args.topo}/host_num{args.host_num}/dp{dp}/"
                f"rdma_operate{lane_idx}.txt"
            )
            lines = build_lines_for_lane(args.host_num, dp, args.msg_len, lane_idx)
            write_file(lines, file_name)


if __name__ == "__main__":
    main()

