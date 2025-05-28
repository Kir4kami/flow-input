#!/usr/bin/env python3
import os

def write_file(result, file_name, append=False):
    os.makedirs(os.path.dirname(file_name), exist_ok=True)
    mode = 'a' if append else 'w'
    with open(file_name, mode) as fd:
        if not append:
            fd.write("stat rdma operate:\n")
        for phase in result:
            fd.write("phase:3000\n")
            for line in phase:
                fd.write(line)

    
def write_rdma_stat_to_file(m, num_nodes, msg_len, num_phases, file_name, append=False):
    result = []
    # 生成 num_phases 个阶段
    for _ in range(num_phases):
        phase = []
        # 节点范围：m * num_nodes 到 (m + 1) * num_nodes - 1
        for i in range(m * num_nodes, (m + 1) * num_nodes):
            # 环形通信：i 发送到 i+1，最后一个节点发送到组内第一个节点
            dst_node = i + 1 if i < (m + 1) * num_nodes - 1 else m * num_nodes
            line = (
                f"Type:rdma_send, src_node:{i}, src_port:0, "
                f"dst_node:{dst_node}, dst_port:0, priority:0, "
                f"msg_len:{msg_len}\n"
            )
            phase.append(line)
        result.append(phase)

    write_file(result, file_name, append)

def write_multiple_times(m, num_nodes, msg_len, num_phases, file_name, num_iterations):
    
    for iteration in range(num_iterations):
        append = iteration > 0
        write_rdma_stat_to_file(m, num_nodes, msg_len, num_phases, file_name, append)
        

def main(topo="topo_tp", host_num=2048, num_nodes=16, msg_len=128*1024*1024, num_phases=15, num_iterations=1):
    
    if host_num % num_nodes != 0:
        print(f"总节点数 {host_num} 无法被每组节点数 {num_nodes} 整除")
        return 1

    dp = host_num // num_nodes  # 分组数
    for m in range(dp):
        m_str = '' if m==0 else str(m)
        file_name = f"rdma_result/{topo}/dp{dp}/rdma_operate{m_str}.txt"
        write_multiple_times(m, num_nodes, msg_len, num_phases, file_name, num_iterations)


if __name__ == "__main__":
    # 默认参数
    topo = "topo_tp"
    host_num = 2048
    num_nodes = 16
    msg_len = 128 * 1024 * 1024  # 128MB
    num_phases = 15
    num_iterations = 1

    # 执行主函数
    main(topo, host_num, num_nodes, msg_len, num_phases, num_iterations)
