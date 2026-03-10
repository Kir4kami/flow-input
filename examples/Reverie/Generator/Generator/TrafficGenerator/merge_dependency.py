#!/usr/bin/env python3

import sys
import os
import re
from typing import Dict, List, Tuple, Any

INPUT_FILE = "deepseek.txt"
OUTPUT_FILE = "dependence.txt"

def parse_params(args_str: str) -> Dict[str, Any]:
    """Parse command-line style arguments into a dict."""
    params = {
        "host_num": 4096,
        "num_nodes": 8,
        "dp": 1,
        "msg_len": 32 * 1024 * 1024,  # default
        "num_phases": 7,
        "device": "",
        "forward": ""
    }

    tokens = args_str.split()
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("--"):
            key = token[2:].replace("-", "_")
            i += 1
            if i >= len(tokens):
                raise ValueError(f"Missing value for {token}")
            value = tokens[i]

            if key == "msg_len":
                try:
                    # 用 Python eval 解析表达式，支持 // 等（bc 不支持 //）
                    params[key] = int(eval(value))
                except Exception as e:
                    raise ValueError(f"Failed to evaluate msg_len expression: {value}") from e
            else:
                params[key] = value
        i += 1

    return params

def get_file_count(mode: str, host_num: int, dp: int, num_nodes: int, max_devices: int) -> int:
    """Calculate number of files for a given mode."""
    if mode == "EP":
        if host_num % max_devices != 0 or (host_num // max_devices) % dp != 0:
            raise ValueError(f"host_num/max_devices ({host_num}/{max_devices}) not divisible by dp {dp}")
        return host_num // max_devices // dp
    elif mode == "DP":
        if host_num % dp != 0:
            raise ValueError(f"host_num {host_num} not divisible by dp {dp}")
        return host_num // dp
    elif mode == "TP":
        if host_num % max_devices != 0 or (host_num // max_devices) % num_nodes != 0:
            raise ValueError(f"host_num/max_devices ({host_num}/{max_devices}) not divisible by num_nodes {num_nodes}")
        return host_num // max_devices // num_nodes
    elif mode == "PP":
        return dp
    else:
        return 0

def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else INPUT_FILE
    if not os.path.isfile(input_file):
        print(f"Error: Input file {input_file} does not exist.", file=sys.stderr)
        sys.exit(1)
    if os.path.getsize(input_file) == 0:
        print(f"Error: Input file {input_file} is empty.", file=sys.stderr)
        sys.exit(1)

    with open(input_file, 'r') as f:
        lines = [line.strip() for line in f.readlines()]

    if not lines or not lines[0]:
        print("Error: Header line is empty", file=sys.stderr)
        sys.exit(1)

    header_parts = lines[0].split()
    if len(header_parts) != 3:
        print(f"Error: Invalid header format: {lines[0]}. Expected '<header_word> <max_devices> <num_iterations>'", file=sys.stderr)
        sys.exit(1)

    header_word, max_devices_str, num_iterations_str = header_parts
    try:
        max_devices = int(max_devices_str)
        num_iterations = int(num_iterations_str)
    except ValueError:
        print(f"Error: Invalid header format: {lines[0]}. Expected numbers for max_devices and num_iterations", file=sys.stderr)
        sys.exit(1)

    print(f"Header line: {lines[0]}, header_word: {header_word}, max_devices: {max_devices}, num_iterations: {num_iterations}", file=sys.stderr)

    node_files: Dict[str, Tuple[int, int]] = {}
    node_parents: Dict[str, List[str]] = {}
    node_name_map: Dict[str, str] = {}
    iteration_dp_nodes: Dict[int, str] = {}
    dependencies: List[Tuple[int, int, int, int]] = []

    current_file_index = 0
    node_count = 0
    first_tp_args = None

    for iter_num in range(1, num_iterations + 1):
        print(f"Processing iteration {iter_num} of {num_iterations}", file=sys.stderr)
        mode_counters = {"TP": 0, "EP": 0, "PP": 0, "DP": 0}
        last_dp_node = ""

        for line_num, line in enumerate(lines[1:], start=2):
            if not line or line.startswith("#"):
                continue

            parts = line.split(maxsplit=3)
            if len(parts) < 3:
                print(f"Error: Invalid line format at line {line_num}: {line}", file=sys.stderr)
                sys.exit(1)

            layer, mode, parents_str = parts[:3]
            args = parts[3] if len(parts) > 3 else ""

            if mode not in ("TP", "EP", "PP", "DP"):
                print(f"Error: Invalid mode {mode} at line {line_num}: {line}", file=sys.stderr)
                sys.exit(1)

            if mode == "TP" and first_tp_args is None:
                first_tp_args = args
                print(f"Saved first TP args: {first_tp_args}", file=sys.stderr)

            params = parse_params(args)
            host_num = int(params.get("host_num", 4096))
            dp = int(params.get("dp", 1))
            num_nodes = int(params.get("num_nodes", 8))
            device = params.get("device", "")
            forward = params.get("forward", "")

            if device:
                if not re.fullmatch(r'\d+(/\d+)*', device):
                    print(f"Error: Invalid device format '{device}' at line {line_num}: {line}", file=sys.stderr)
                    sys.exit(1)
                for dev in device.split('/'):
                    if int(dev) >= max_devices:
                        print(f"Error: Device {dev} exceeds max_devices ({max_devices}) at line {line_num}: {line}", file=sys.stderr)
                        sys.exit(1)

            mode_counters[mode] += 1
            expected_node_name = f"{mode}{mode_counters[mode]}_iter{iter_num}"
            actual_node_name = f"{node_count}_{mode}{layer}_iter{iter_num}"
            node_count += 1

            node_name_map[expected_node_name] = actual_node_name
            print(f"Mapping: {expected_node_name} -> {actual_node_name}", file=sys.stderr)

            parent_list = []
            if parents_str == "Root" and iter_num > 1:
                prev_dp = iteration_dp_nodes.get(iter_num - 1)
                if not prev_dp:
                    print(f"Error: No DP node found for iteration {iter_num - 1}", file=sys.stderr)
                    sys.exit(1)
                parent_list = [prev_dp]
            else:
                for parent in parents_str.split('/'):
                    parent = parent.strip()
                    if parent == "Root":
                        continue
                    parent_iter = f"{parent}_iter{iter_num}"
                    if parent_iter not in node_name_map:
                        print(f"Error: Parent node {parent_iter} does not exist at line {line_num}: {line}", file=sys.stderr)
                        sys.exit(1)
                    parent_list.append(node_name_map[parent_iter])

            node_parents[actual_node_name] = parent_list
            print(f"Node {actual_node_name} parents: {' '.join(parent_list)}", file=sys.stderr)

            file_count = get_file_count(mode, host_num, dp, num_nodes, max_devices)
            if file_count <= 0:
                print(f"Error: Invalid file count for mode {mode} at line {line_num}: {line}", file=sys.stderr)
                sys.exit(1)

            start_index = current_file_index
            end_index = current_file_index + file_count - 1
            node_files[actual_node_name] = (start_index, end_index)
            current_file_index = end_index + 1
            print(f"Node {actual_node_name} files: {start_index}-{end_index} ({file_count} files)", file=sys.stderr)

            if mode == "DP":
                iteration_dp_nodes[iter_num] = actual_node_name
                last_dp_node = actual_node_name
                print(f"Stored DP node for iter={iter_num}: {last_dp_node}", file=sys.stderr)

        # Add extra TP node after DP if not last iteration
        if iter_num < num_iterations and last_dp_node and first_tp_args is not None:
            mode = "TP"
            mode_counters[mode] += 1
            expected_node_name = f"{mode}{mode_counters[mode]}_iter{iter_num}"
            actual_node_name = f"{node_count}_{mode}18_iter{iter_num}"
            node_count += 1

            node_name_map[expected_node_name] = actual_node_name
            print(f"Mapping: {expected_node_name} -> {actual_node_name}", file=sys.stderr)

            node_parents[actual_node_name] = [last_dp_node]
            print(f"Node {actual_node_name} parents: {last_dp_node}", file=sys.stderr)

            params = parse_params(first_tp_args)
            host_num = int(params.get("host_num", 128))
            dp = int(params.get("dp", 8))
            num_nodes = int(params.get("num_nodes", 8))

            file_count = get_file_count(mode, host_num, dp, num_nodes, max_devices)
            start_index = current_file_index
            end_index = current_file_index + file_count - 1
            node_files[actual_node_name] = (start_index, end_index)
            current_file_index = end_index + 1
            print(f"Node {actual_node_name} files: {start_index}-{end_index} ({file_count} files)", file=sys.stderr)

    # Build dependencies
    for node, (start, end) in node_files.items():
        for parent in node_parents.get(node, []):
            if parent == "Root":
                continue
            if parent not in node_files:
                print(f"Error: No file range found for parent {parent} of node {node}", file=sys.stderr)
                sys.exit(1)
            p_start, p_end = node_files[parent]
            dependencies.append((start, end, p_start, p_end))

    # Sort and write
    dependencies.sort(key=lambda x: x[0])
    with open(OUTPUT_FILE, 'w') as f:
        for start, end, p_start, p_end in dependencies:
            f.write(f"{start}-{end}:{p_start}-{p_end}\n")

    print(f"Generated {OUTPUT_FILE} with dependencies for {current_file_index} files.")

if __name__ == "__main__":
    main()
