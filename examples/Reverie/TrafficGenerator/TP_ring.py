#!/usr/bin/env python3
import argparse
import os


def write_ring_traffic(total_nodes, msg_len, output_file, output_dir, topo):
    if output_file:
        target_file = output_file
    else:
        target_file = f"{output_dir}/{topo}/host_num{total_nodes}/rdma_operate0.txt"
    os.makedirs(os.path.dirname(target_file) or ".", exist_ok=True)
    with open(target_file, "w") as fd:
        fd.write("stat rdma operate:\n")
        fd.write("phase:3000\n")
        for src in range(total_nodes):
            dst = (src + 1) % total_nodes
            line = (
                f"Type rdma_send src_node {src} src_port 0 "
                f"dst_node {dst} dst_port 0 priority 0 "
                f"msg_len {msg_len}\n"
            )
            fd.write(line)


def parse_args():
    parser = argparse.ArgumentParser(description="Generate ring RDMA traffic.")
    parser.add_argument("--total_nodes", type=int, default=64, help="Total number of nodes.")
    parser.add_argument("--msg_len", type=int, default=4096000, help="Message size in bytes.")
    parser.add_argument(
        "--output_file",
        type=str,
        default="",
        help="Output file path.",
    )
    parser.add_argument("--output_dir", type=str, default="result")
    parser.add_argument("--topo", type=str, default="topo_tp")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.total_nodes <= 1:
        raise SystemExit("total_nodes must be >= 2")
    write_ring_traffic(
        args.total_nodes,
        args.msg_len,
        args.output_file,
        args.output_dir,
        args.topo,
    )


if __name__ == "__main__":
    main()
