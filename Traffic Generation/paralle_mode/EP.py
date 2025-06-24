#!/usr/bin/env python3
import os

def write_file(result, file_name):
    os.makedirs(os.path.dirname(file_name), exist_ok=True)  # 自动创建目录
    with open(file_name, 'w') as fd:
        fd.write("stat rdma operate:\n")
        for phase in result:
            fd.write("phase:3000\n")
            for line in phase:
                fd.write(line)

def SetA2A(host_list, msg_len, file_name=''):
    host_num = len(host_list)
    result = []
    for step in range(1, host_num):
        res = []
        for idx, host_id_a in enumerate(host_list):
            idy = (step + idx) % host_num
            host_id_b = host_list[idy]
            res.append(
                "Type:rdma_send, src_node:" + str(host_id_a) +
                ", src_port:0, dest_node:" + str(host_id_b) +
                ", dst_port:0, priority:0, msg_len:" + str(msg_len) + '\n'
            )
        result.append(res)

    if file_name:
        write_file(result, file_name)

def get_host_list(host_num, dp):
    assert host_num % dp == 0
    span = host_num // dp
    host_list = []
    for start in range(0,span):
        host_ids = []
        for host_id in range(start, host_num, span):
            host_ids.append(host_id)
        host_list.append(host_ids)
    return host_list

if __name__ == "__main__":
    topo = 'topo_a2a'
    pod_num = 4
    sub_pod_num_per_pod = 32
    host_num_per_sub_pod = 32
    host_num_per_pod = sub_pod_num_per_pod * host_num_per_sub_pod
    host_num = host_num_per_pod * pod_num
    host_num = 64
    dp_list = [8,16]

    for dp in dp_list:
        host_list = get_host_list(host_num, dp)
        for index, host_ids in enumerate(host_list):
            index_str = '' if index == 0 else str(index)
            # Modified file path to include host_num{host_num}
            file_name = f"rdma_result/{topo}/host_num{host_num}/dp{dp}/rdma_operate{index_str}.txt"
            SetA2A(host_ids, 32 * 1024 * 1024, file_name)