#!/usr/bin/env python3
import os
from tqdm import tqdm

# ========================
# 网络拓扑参数（可修改）
# ========================
HOST_NUM = 128
LEAF_NUM = 16
SPINE_NUM = 8

# 每个 Leaf 连接的主机数（必须整除）
assert HOST_NUM % LEAF_NUM == 0, "主机数必须能被 Leaf 数整除"
HOSTS_PER_LEAF = HOST_NUM // LEAF_NUM  # 例如：8


def judge_type(node_id, host_num, leaf_num):
    """判断节点类型（host / leaf / spine）"""
    if 0 <= node_id < host_num:
        return "host"
    elif host_num <= node_id < host_num + leaf_num:
        return "leaf"
    elif host_num + leaf_num <= node_id < host_num + leaf_num + SPINE_NUM:
        return "spine"
    else:
        raise ValueError(f"无效节点 ID: {node_id}")


def get_leaf_id(node_id, host_num, leaf_num):
    """获取节点所属的 Leaf ID（连续分配）"""
    if node_id >= host_num:
        # Leaf 或 Spine 节点：Leaf ID = node_id - host_num
        return node_id - host_num
    else:
        # Host 节点：按连续分组计算 Leaf ID
        return node_id // HOSTS_PER_LEAF


def get_port_to_host(host_id):
    """Leaf 交换机连接该主机所用的端口号（0 ~ HOSTS_PER_LEAF-1）"""
    return str(host_id % HOSTS_PER_LEAF)


def cal_port(src_node, dst_host, host_num, leaf_num, spine_num):
    """计算 src_node 到 dst_host 的出端口（dst_host 必须是主机）"""
    if dst_host >= host_num:
        raise ValueError("目标必须是主机")

    src_type = judge_type(src_node, host_num, leaf_num)
    dst_leaf = get_leaf_id(dst_host, host_num, leaf_num)
    src_leaf = get_leaf_id(src_node, host_num, leaf_num)

    if src_type == "host":
        # 主机只有一个上行端口（通常为 "1"）
        return "1"

    elif src_type == "leaf":
        if src_leaf == dst_leaf:
            # 同 Leaf：直连主机
            return get_port_to_host(dst_host)
        else:
            # 跨 Leaf：ECMP 到所有 Spine
            # 假设 Leaf 的上行端口从 HOSTS_PER_LEAF 开始编号（0~7 给 host，8~15 给 spine）
            spine_ports = [str(HOSTS_PER_LEAF + i) for i in range(spine_num)]
            return " ".join(spine_ports)

    elif src_type == "spine":
        # Spine 到目标 Leaf 的端口 = Leaf ID
        return str(dst_leaf)

    else:
        raise RuntimeError("未知节点类型")


def cal_metric(src_node, dst_host, host_num, leaf_num, spine_num):
    """计算路由度量（metric）"""
    if src_node == dst_host:
        return "0"

    src_type = judge_type(src_node, host_num, leaf_num)
    dst_leaf = get_leaf_id(dst_host, host_num, leaf_num)
    src_leaf = get_leaf_id(src_node, host_num, leaf_num)

    if src_type == "host":
        return "2" if src_leaf == dst_leaf else " ".join(["4"] * spine_num)

    elif src_type == "leaf":
        if src_leaf == dst_leaf:
            return "1"
        else:
            return " ".join(["3"] * spine_num)

    elif src_type == "spine":
        return "2"

    else:
        raise RuntimeError("未知节点类型")


def write_route_table_to_xml(host_num, leaf_num, spine_num):
    output_dir = "./router_output/"
    os.makedirs(output_dir, exist_ok=True)
    file_path = os.path.join(output_dir, "router_mine.xml")

    total_entries = (leaf_num + spine_num) * host_num
    progress_bar = tqdm(total=total_entries, desc="写入路由表", unit="条")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        f.write('<router>\n')

        # 只为 Leaf 和 Spine 生成路由组（Host 不转发）
        for node_id in range(host_num, host_num + leaf_num + spine_num):
            node_type = judge_type(node_id, host_num, leaf_num)
            f.write(f'  <grp node_id="{node_id}" node_type="{node_type}">\n')

            for dst_id in range(host_num):  # 所有主机为目标
                if node_id == dst_id:
                    continue  # 不应发生，但安全起见
                port = cal_port(node_id, dst_id, host_num, leaf_num, spine_num)
                metric = cal_metric(node_id, dst_id, host_num, leaf_num, spine_num)
                f.write(f'    <target node_id="{dst_id}" port_id="{port}" metric="{metric}"/>\n')
                progress_bar.update(1)

            f.write('  </grp>\n')
            f.flush()

        f.write('</router>\n')

    progress_bar.close()
    print(f"路由表已写入: {file_path}")


if __name__ == '__main__':
    write_route_table_to_xml(HOST_NUM, LEAF_NUM, SPINE_NUM)