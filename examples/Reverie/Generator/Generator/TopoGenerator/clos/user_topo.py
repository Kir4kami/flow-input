#!/usr/bin/env python3
import netisim_graph
import networkx as nx

graph = netisim_graph.NetiSimGraph()

host_num = 4 * 32
leaf_sw_num = 4 * 2
spine_sw_num = 4 * 2

total_node_num = host_num + leaf_sw_num + spine_sw_num
host_ids = []
leaf_ids = []
spine_ids = []
# step1: 生成节点,要求host在前,node在后,且顺序编号,不符合要求会报错
for host_id in range(host_num):
    graph.add_netisim_host(host_id)
    host_ids.append(host_id)

for leaf_sw_id in range(leaf_sw_num):
    graph.add_netisim_node(leaf_sw_id + host_num, comp_delay=1300)
    leaf_ids.append(leaf_sw_id + host_num)

for spine_sw_id in range(spine_sw_num):
    graph.add_netisim_node(spine_sw_id + host_num + leaf_sw_num, comp_delay=1300)
    spine_ids.append(spine_sw_id + host_num + leaf_sw_num)

# step2: 生成拓扑连线,按照自定义拓扑,将指定id的节点(host或node皆可)进行连线并指定带宽和时延(发包器会自动连接)
for host_id in range(host_num):
    graph.add_netisim_edge(host_id, host_id // 16 + host_num, bandwidth='400', delay='20', edge_count=1)

for sw_index in range(0, len(leaf_ids), 2):
    graph.add_netisim_edge(leaf_ids[sw_index], spine_ids[sw_index], bandwidth='400', delay='20', edge_count=8)
    graph.add_netisim_edge(leaf_ids[sw_index + 1], spine_ids[sw_index], bandwidth='400', delay='20', edge_count=8)
    graph.add_netisim_edge(leaf_ids[sw_index], spine_ids[sw_index + 1], bandwidth='400', delay='20', edge_count=8)
    graph.add_netisim_edge(leaf_ids[sw_index + 1], spine_ids[sw_index + 1], bandwidth='400', delay='20', edge_count=8)

for group_id in range(4):
    spine_in_group = []
    for sw_id in spine_ids:
        if sw_id % 2 == group_id:
            spine_in_group.append(sw_id)
    for i in range(len(spine_in_group)):
        for j in range(i + 1, len(spine_in_group)):
            graph.add_netisim_edge(spine_in_group[i], spine_in_group[j], bandwidth='400', delay='20', edge_count=4)
# step3: 生成配置文件,build_graph_config会生成一系列中间数据,最终生成dcn2.0_config.xml文件
graph.build_graph_config(node_gen_bandwidth='400', template_xml="dcn2.0_config_flowar_template.xml", output_name="dcn2.0_config.xml")


# step4: 生成路由表

def all_simple_paths(G, source, target):
    try:
        paths = nx.all_simple_paths(G, source, target, cutoff=6)
    except nx.exception.NetworkXNoPath:
        paths = []
    final_paths = []

    return paths


graph.gen_route_table(path_finding_algo=all_simple_paths, host_router=False)