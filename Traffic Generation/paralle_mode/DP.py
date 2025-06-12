#!/usr/bin/env python3
import numpy as np
import sys
import random
import os

def get_neighbor(index, num, iter):#当前主机的索引，主机总数，当前迭代次数
    span = 2 ** (iter -1)
    left_nei = index - span
    right_nei = index + span
    if left_nei < 0:
        return right_nei
    if right_nei > num - 1:
        return left_nei
    if left_nei // 2 ** iter == index // 2 ** iter:
        return left_nei
    if right_nei // 2 ** iter == index // 2 ** iter:
        return right_nei
    else:
        raise

def write_file(result, file_name):#包含所有 RDMA 操作的嵌套列表、输出文件名
    os.makedirs(os.path.dirname(file_name), exist_ok=True)  # 自动创建目录
    with open(file_name, 'w') as fd:
        fd.write("stat rdma operate:\n")
        for phase in result:
            fd.write("phase:3000\n")
            for line in phase:
                fd.write(line)

def SetHD(host_list, msg_len, file_name=''):
    host_num = len(host_list)
    iter_times =0
    for i in range(15):
        standard_hd_num =2**i
        if standard_hd_num > host_num:
            raise
        if standard_hd_num == host_num:
            iter_times =i
            break

    result = []
    for iter in range(1,iter_times+1):
        res = []
        res1 = []
        res2 = []
        msg = msg_len // 2 ** iter
        for idx, host in enumerate(host_list):
            nei_idx = get_neighbor(idx, host_num, iter)
            res1.append("Type:rdma_send, src_node:" + str(host) + ", src_port:0, dest_node:" + str(host_list[nei_idx]) + ", dst_port:0, priority:0, msg_len:" + '64'+ '\n')
        result.append(res1)
        for idx, host in enumerate(host_list):
            nei_idx = get_neighbor(idx, host_num, iter)
            res.append("Type:rdma_send, src_node:" + str(host) + ", src_port:0, dest_node:" + str(host_list[nei_idx]) + ", dst_port:0, priority:0, msg_len:" + str(msg) + '\n')
        result.append(res)
        for idx, host in enumerate(host_list):
            nei_idx = get_neighbor(idx, host_num, iter)
            res2.append("Type:rdma_send, src_node:" + str(host) + ", src_port:0, dest_node:" + str(host_list[nei_idx]) + ", dst_port:0, priority:0, msg_len:" + '64' + '\n')
        result.append(res2)
    result += result[::-1]

    if file_name:
        write_file(result, file_name)

def get_host_list(host_num, dp):
    assert host_num % dp == 0
    span = host_num // dp
    host_list = []
    for start in range(span):
        host_ids = []
        for host_id in range(start,host_num,span):
            host_ids.append(host_id)
        host_list.append(host_ids)
    return host_list

if __name__ == '__main__':
    topo = 'topo_dp'
    pod_num = 8
    sub_pod_num_per_pod = 32
    host_num_per_sub_pod = 32
    host_num_per_pod = sub_pod_num_per_pod * host_num_per_sub_pod
    host_num = pod_num * host_num_per_pod
    host_num = 1024*4*4

    dp_list = [16, 64, 256, 512]
    for dp in dp_list:
        host_list = get_host_list(host_num, dp)
        for index, host_ids in enumerate(host_list):
            index = '' if index == 0 else str(index)
            # Modified file path to include host_num{host_num}
            file_name = f"rdma_result/{topo}/host_num{host_num}/dp{dp}/rdma_operate{index}.txt"
            SetHD(host_ids, 128 * 1024 * 1024, file_name)