#!/usr/bin/env python3
import os

def write_rdma_operate(node_pairs, msg_len, file_name):
    """
    生成 RDMA 操作配置并写入文件。

    Args:
        node_pairs (list of tuples): 源节点和目标节点的配对列表 [(src, dst), ...]。
        msg_len (int): 消息长度（字节）。
        file_name (str): 输出文件路径。
    """
    os.makedirs(os.path.dirname(file_name), exist_ok=True)
    try:
        with open(file_name, "w") as ofs:
            ofs.write("stat rdma operate:\n")
            ofs.write("phase:3000\n")
            for src_node, dst_node in node_pairs:
                ofs.write(
                    f"Type:rdma_send, src_node:{src_node}, src_port:0, "
                    f"dst_node:{dst_node}, dst_port:0, priority:1, "
                    f"msg_len:{msg_len}\n"
                )
    except IOError:
        print(f"无法写入文件: {file_name}")
        return 1
    return 0

def generate_pipeline_pairs(num_nodes, dp):
    """
    生成流水线并行的节点配对（按组分块，源节点到目标节点加 dp）。

    Args:
        num_nodes (int): 每组节点数（总节点数为 2 * num_nodes）。
        dp (int): 数据并行度（分组数）。

    Returns:
        list of tuples: 节点配对 [(src, dst), ...]。
    """
    node_pairs = []
    num_groups = max(1, (2 * num_nodes) // (2 * dp))  # 总组数
    for k in range(num_groups):
        for i in range(dp):
            src_node = k * 2 * dp + i
            dst_node = src_node + dp
            # 确保目标节点不超过总节点数
            if src_node < num_nodes and dst_node < 2 * num_nodes:
                node_pairs.append((src_node, dst_node))
    return node_pairs

def main(topo="topo_pp", num_nodes=128, msg_len=128*1024*1024, dp=8):
    """
    生成 RDMA 操作配置的主函数。

    Args:
        topo (str): 拓扑名称。
        num_nodes (int): 总节点数（必须为偶数）。
        msg_len (int): 消息长度（字节）。
        dp (int): 数据并行度。
        

    Returns:
        int: 0 表示成功，1 表示失败。
    """
    # 参数验证
    if num_nodes % 2 != 0:
        print("错误：num_nodes 必须为偶数")
        return 1
    if dp <= 0:
        print("错误：dp 必须为正整数")
        return 1

    # 生成节点配对
    node_pairs = generate_pipeline_pairs(num_nodes , dp)

    # 计算分组
    nodes_per_group = max(1, (num_nodes // 2) // dp)

    # 为每个分组生成文件
    for group_idx in range(dp):
        start_idx = group_idx * nodes_per_group
        end_idx = min((group_idx + 1) * nodes_per_group, num_nodes // 2)
        group_pairs = node_pairs[start_idx:end_idx]

        group_idx_str = '' if group_idx == 0 else str(group_idx)
        file_name = f"rdma_result/{topo}/host_num{num_nodes}/dp{dp}/rdma_operate{group_idx_str}.txt"

        # 检查文件是否存在
        if os.path.exists(file_name):
            print(f"警告：文件 {file_name} 已存在，将被覆盖")

        # 写入配置
        if write_rdma_operate(group_pairs, msg_len, file_name) != 0:
            return 1

    print("所有配置文件生成成功")
    return 0

if __name__ == "__main__":
    # 默认参数
    topo = "topo_pp"
    num_nodes = 128
    msg_len = 128 * 1024 * 1024  # 128MB
    dp = 8
    

    # 执行主函数
    main(topo, num_nodes, msg_len, dp)