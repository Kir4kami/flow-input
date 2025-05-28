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
    # 确保输出目录存在
    os.makedirs(os.path.dirname(file_name), exist_ok=True)

    try:
        with open(file_name, "w") as ofs:
            # 写入头信息
            ofs.write("stat rdma operate:\n")
            ofs.write("phase:3000\n")

            # 写入 RDMA 操作
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

def generate_pipeline_pairs(num_nodes):
    """
    生成流水线并行的节点配对（一对一通信）。

    Args:
        num_nodes (int): 每组节点数（总节点数为 2 * num_nodes）。

    Returns:
        list of tuples: 节点配对 [(src, dst), ...]。
    """
    node_pairs = []
    for i in range(num_nodes):
        src_node = num_nodes + i  # 源节点: num_nodes 到 2*num_nodes-1
        dst_node = i              # 目标节点: 0 到 num_nodes-1
        node_pairs.append((src_node, dst_node))
    return node_pairs

def main(topo="topo_pp", num_nodes=2048, msg_len=32*1024*1024, dp=1):
    
    # 生成节点配对
    node_pairs = generate_pipeline_pairs(num_nodes)

    # 计算分组
    if dp <= 0:
        dp = 1
    nodes_per_group = max(1, num_nodes // dp)

    # 为每个分组生成文件
    for group_idx in range(dp):
        # 确定当前分组的节点配对
        start_idx = group_idx * nodes_per_group
        end_idx = min((group_idx + 1) * nodes_per_group, num_nodes)
        group_pairs = node_pairs[start_idx:end_idx]

        group_idx_str = '' if group_idx==0 else str(group_idx)
        # 构造输出文件路径
        file_name = f"rdma_result/{topo}/dp{dp}/rdma_operate{group_idx_str}.txt"

        # 写入配置
        write_rdma_operate(group_pairs, msg_len, file_name)


if __name__ == "__main__":
    # 默认参数
    topo = "topo_pp"
    num_nodes = 2048
    msg_len = 32 * 1024 * 1024  # 32MB
    dp = 1  # 单文件输出，兼容多分组

    # 执行主函数
    main(topo, num_nodes, msg_len, dp)