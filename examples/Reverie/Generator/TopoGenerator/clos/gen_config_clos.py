#!/usr/bin/env python3
import netisim_graph
import networkx as nx

graph = netisim_graph.NetiSimGraph()

host_num = 768
leaf_sw_num = 768
spine_sw_num = 64
rdma_log_num =176


total_node_num = host_num + leaf_sw_num + spine_sw_num

# step1: 生成节点,要求host在前,node在后,且顺序编号,不符合要求会报错
for host_id in range(host_num):
    graph.add_netisim_host(host_id)

for leaf_sw_id in range(leaf_sw_num):
    graph.add_netisim_node(leaf_sw_id + host_num, comp_delay=1600, node_subtype='leaf')#新增参数node_subtype

for spine_sw_id in range(spine_sw_num):
    graph.add_netisim_node(spine_sw_id + host_num + leaf_sw_num, comp_delay=1600, node_subtype='spine')

# step2: 生成拓扑连线,按照自定义拓扑,将指定id的节点(host或node皆可)进行连线并指定带宽和时延(发包器会自动连接)

for spine_sw_id in range(spine_sw_num):
    for leaf_sw_id in range(leaf_sw_num):
        graph.add_netisim_edge(spine_sw_id + host_num + leaf_sw_num,
                                   leaf_sw_id + host_num, bandwidth='400', delay='10')

# 主机与叶子交换机之间的连接，确保每个叶子交换机连接到64个主机，且这些连接是交错的
for leaf_sw_id in range(leaf_sw_num):
    base = (leaf_sw_id//2)*(host_num//leaf_sw_num*2)
    start = base+(leaf_sw_id%2)
    for i in range(host_num//leaf_sw_num):
        host_id = start+i*2
        if(host_id <host_num):
            graph.add_netisim_edge(leaf_sw_id+host_num, host_id,bandwidth="200",delay="5")

## 主机与叶子交换机之间的连接，确保每个叶子交换机连接到连续的8个主机（顺序模式）
#for leaf_sw_id in range(leaf_sw_num):
#    start = leaf_sw_id * (host_num // leaf_sw_num)  # 每个叶子分配连续的8个主机
#    for i in range(host_num // leaf_sw_num):
#        host_id = start + i
#        if host_id < host_num:
#            graph.add_netisim_edge(leaf_sw_id + host_num, host_id, bandwidth="200", delay="5")

# step3: 生成配置文件,build_graph_config会生成一系列中间数据,最终生成dcn2.0_config.xml文件
graph.build_graph_config(template_xml="dcn2.0_config_rdma_template.xml", output_name=f"dcn2.0_config.xml", rdma_log_num=rdma_log_num)