#!/usr/bin/env python3
import argparse
import sys
import os


def main():
    parser = argparse.ArgumentParser(description="Generate leaf-spine topology file.")
    parser.add_argument("--servers_per_tor", type=int)
    parser.add_argument("--tor_switches", type=int)
    parser.add_argument("--spine_switches", type=int)
    parser.add_argument("--server_tor_delay", type=str)
    parser.add_argument("--tor_spine_delay", type=str)
    parser.add_argument("--server_data_rate", type=int)
    parser.add_argument("--other_data_rate", type=int)
    parser.add_argument("--error_rate", type=float)
    parser.add_argument("--output_file", type=str)
    args = parser.parse_args()

    # 如果未传参数，读取 topology_list.txt 的默认配置
    if (
        args.servers_per_tor is None
        or args.tor_switches is None
        or args.spine_switches is None
        or args.server_tor_delay is None
        or args.tor_spine_delay is None
        or args.server_data_rate is None
        or args.other_data_rate is None
        or args.error_rate is None
    ):
        topo_list = "topology_list.txt"
        if not os.path.isfile(topo_list):
            raise SystemExit(f"topology_list.txt not found in {os.getcwd()}")
        with open(topo_list, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split()
                if len(parts) < 10:
                    raise SystemExit("topology_list.txt format invalid")
                # topology_list.txt:
                # label serversPerTor torSwitches spineSwitches serverTorDelay torSpineDelay serverDataRate otherDataRate errorRate msgLen [trafficMode]
                servers_per_tor = parts[1]
                tor_switches = parts[2]
                spine_switches = parts[3]
                server_tor_delay = parts[4]
                tor_spine_delay = parts[5]
                server_data_rate = parts[6]
                other_data_rate = parts[7]
                error_rate = parts[8]
                args.servers_per_tor = args.servers_per_tor or int(servers_per_tor)
                args.tor_switches = args.tor_switches or int(tor_switches)
                args.spine_switches = args.spine_switches or int(spine_switches)
                args.server_tor_delay = args.server_tor_delay or server_tor_delay
                args.tor_spine_delay = args.tor_spine_delay or tor_spine_delay
                args.server_data_rate = args.server_data_rate or int(server_data_rate)
                args.other_data_rate = args.other_data_rate or int(other_data_rate)
                args.error_rate = args.error_rate or float(error_rate)
                break

    servers_per_tor = args.servers_per_tor
    tor_switches = args.tor_switches
    spine_switches = args.spine_switches
    server_tor_delay = args.server_tor_delay or "2us"
    tor_spine_delay = args.tor_spine_delay or "2us"
    server_data_rate = args.server_data_rate or 25
    other_data_rate = args.other_data_rate or 25
    error_rate = args.error_rate if args.error_rate is not None else 0.0

    switch_num = tor_switches + spine_switches
    node_num = servers_per_tor * tor_switches + switch_num
    link_num = servers_per_tor * tor_switches + tor_switches * spine_switches

    output_file = args.output_file or "leaf-spine.txt"
    with open(output_file, "w") as f:
        f.write(
            f"{node_num} {switch_num} {tor_switches} {link_num} "
            f"{int(server_data_rate * 1e9)} {int(other_data_rate * 1e9)}\n"
        )
        for i in range(switch_num):
            f.write(f"{int(servers_per_tor * tor_switches + i)} ")
        f.write("\n")

        for i in range(tor_switches):
            for j in range(servers_per_tor):
                f.write(
                    f"{j + servers_per_tor * i} "
                    f"{servers_per_tor * tor_switches + i} "
                    f"{int(server_data_rate * 1e9)} "
                    f"{server_tor_delay} {error_rate}\n"
                )

        tor_index_begin = servers_per_tor * tor_switches
        spine_index_begin = servers_per_tor * tor_switches + tor_switches
        for i in range(tor_switches):
            for j in range(spine_switches):
                f.write(
                    f"{tor_index_begin + i} {spine_index_begin + j} "
                    f"{int(other_data_rate * 1e9)} {tor_spine_delay} {error_rate}\n"
                )


if __name__ == "__main__":
    sys.exit(main())
