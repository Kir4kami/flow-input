#!/usr/bin/env python3
import networkx as nx
from lxml import etree
import argparse
from copy import deepcopy
import time
import os
import numpy as np
from tqdm import tqdm, trange
import netisim_utils
import math

STATIC_COMP_COST = 8*1024*1024
STATIC_SYNC_COST = 8*1024*1024

class NetiSimGraph(nx.Graph):
    node_type = [
        'host',
        'node'
    ]

    def __init__(self):
        super().__init__()
        
        self.output_dir = "./output/" + time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime()) + "/"
        self.host_ids = [] # 拓扑中的host节点id
        self.node_ids = [] # 拓扑中的node(即交换机)节点id 
        self.leaf_ids = []  # 新增：叶子交换机ID
        self.spine_ids = []  # 新增：脊柱交换机ID   
        self.next_hop_port = [] # 下一跳端口表: next_hop_port[src][dst] = port, 可用get_link_port(src, dst)获取, 同时可用get_next_hop(src, port)获取下一跳节点
        self.route_table_2port = None # 路由表: route_table_2port[node_id][dst_id] = {port1, port2, ...} 与2node对应
        self.route_table_2node = None # 路由表: route_table_2node[node_id][dst_id] = {node1, node2, ...} 与2port对应
        self.topo_ele_xml = None # 生成的拓扑xml文件
        self.node_ele_xml = None # 生成的节点xml文件
        self.route_ele_xml = None # 生成的路由表xml文件

        # 给定xml文件生成graph,根据仿真激励修剪graph相关的变量
        self.comm = {} # 用户指定的通信域
        self.avtive_comm_id = set() # 根据用户指定的仿真激励, 激活的通信域id
        self.avtive_ids = set() # 根据激活的通信域id, 基于路由表生成的激活节点id. 用于修剪拓扑

        self.path_finding_algo = nx.all_shortest_paths
        
    # 增加host节点, 通常表示netisim中的交换机
    def add_netisim_host(self, node_id, **attr):
        self.host_ids.append(node_id)
        return super().add_node(node_id, type='host', comp_cost=STATIC_COMP_COST, **attr)
    
    # 增加node节点, 通常表示netisim中的交换机
    
    def add_netisim_node(self, node_id, comp_delay=1300, node_subtype='leaf', **attr):
        self.node_ids.append(node_id)
        if node_subtype == 'leaf':
            self.leaf_ids.append(node_id)
        elif node_subtype == 'spine':
            self.spine_ids.append(node_id)
        else:
            raise ValueError("node_subtype must be 'leaf' or 'spine'")
        return super().add_node(node_id, type='node', comp_delay=comp_delay, comp_cost=STATIC_COMP_COST, **attr)
    
    #def add_netisim_node(self, node_id, comp_delay=1300, **attr):
    #    self.node_ids.append(node_id)
    #    return super().add_node(node_id, type='node', comp_delay=comp_delay, comp_cost=STATIC_COMP_COST, **attr)
    
    # graph.add_edge(host_id, int(host_id/6) * 2 + HOST_NUM, weight='1', bandwidth='200', delay='20')
    def add_netisim_edge(self, u, v, bandwidth='200', delay='20', edge_count=1, **attr):
        return super().add_edge(u, v, bandwidth=bandwidth, delay=delay, edge_count=edge_count, sync_cost=STATIC_SYNC_COST, **attr)
    
    def check_graph_index_valid(self):
        for i in tqdm(range(len(self.nodes))):
            assert self.has_node(i), "编号{}:必须从0开始顺序编号!".format(i)
            assert self.nodes[i]["type"] in self.node_type, "编号{}节点类型{},必须是host(代表NPU卡)或node(代表交换机)!".format(i, self.nodes[i]["type"])

        assert max(self.host_ids) == min(self.node_ids) - 1, "编号由小到大,host在前,node在后,且顺序编号!"
        assert len(self.host_ids) + len(self.node_ids) == len(self.nodes), "host和node节点数目之和应等于总节点数目!"
        return True
    
    def get_host_num(self):
        return len(self.host_ids)
    
    def get_node_num(self):
        return len(self.node_ids)
    
    def get_total_num(self):
        return len(self.host_ids) + len(self.node_ids)
    
    def node_is_switch(self, node_id):
        return self.nodes[node_id]['type'] == 'node'
    
    def node_is_host(self, node_id):
        return self.nodes[node_id]['type'] == 'host'
    
    def build_graph_config(self, template_xml = "./dcn2.0_config_rdma_template.xml", write_flag=True, output_name=None,  rdma_log_num= "1"):
        # graph到xml文件的转换
        assert self.check_graph_index_valid()
        try:
            root_config = etree.parse(template_xml).getroot()
        except:
            print("Woops.")
            exit()
        else:
            pass


        old_node_ele = root_config.xpath('/dcn/dcn_network/node')[0]
        new_node_ele = etree.Element("node")
        
        
        host_num = self.get_host_num()
        total_node_num = self.get_total_num()
        
        # host_ele = etree.SubElement(new_node_ele, "grp", type=HOST_TYPE, node_id="0..{}".format(host_num - 1), port_num="2", config_template="0")

        port_num_id_dict = {}
        for node_id in self.nodes:
            # if not self.node_is_switch(node_id):
            #     continue
            t_node = self.nodes[node_id]
            # t_port_num = self.degree[node_id]
            t_port_num = 0
            for edge in self.edges(node_id):
                t_port_num += int(self.get_edge_data(edge[0], edge[1])["edge_count"])
            if t_port_num not in port_num_id_dict:
                port_num_id_dict[t_port_num] = [node_id]
            else:
                port_num_id_dict[t_port_num].append(node_id)

        t_template_host = 0
        t_template_node = 0
        for port_num, node_id in port_num_id_dict.items():
            if 'comp_delay' in self.nodes[node_id[0]]:
                comp_delay = self.nodes[node_id[0]]['comp_delay']
            else:
                comp_delay = 1300
            # print(comp_delay)
            if self.node_is_host(node_id[0]):
                node_ele = etree.SubElement(new_node_ele, "grp", type=NETISIM_MOD + self.nodes[node_id[0]]['type'], node_id=" ".join(str(id) for id in node_id), port_num=str(port_num + 1), config_template=str(t_template_host), comp_delay=str(comp_delay))
                t_template_host += 1
            else:
                node_ele = etree.SubElement(new_node_ele, "grp", type=NETISIM_MOD + self.nodes[node_id[0]]['type'], node_id=" ".join(str(id) for id in node_id), port_num=str(port_num), config_template=str(t_template_node), comp_delay=str(comp_delay))
                t_template_node += 1
        old_node_ele.getparent().replace(old_node_ele, new_node_ele)


        old_topo_ele = root_config.xpath('/dcn/dcn_network/topology')[0]
        new_topo_ele = etree.Element("topology")
        node_ele = etree.SubElement(new_topo_ele, "grp", link_type="bi_direct", src_node="0..{}".format(host_num - 1), src_port="0", dst_node="-1", dst_port="0..{}".format(host_num - 1), bandwidth="200", delay="10")
        port_conn_count = [0] * total_node_num
        for node_id in self.nodes:
            t_node = self.nodes[node_id]
            if self.node_is_host(node_id):
                port_conn_count[node_id] += 1

        for u, v in tqdm(self.edges, desc="生成拓扑连线"):
            edge_count = self.edges[u, v]["edge_count"]
            for e in range(int(edge_count)):
                u_port_cnt = str(port_conn_count[u])
                v_port_cnt = str(port_conn_count[v])
                bw = self.edges[u, v]["bandwidth"]
                dl = self.edges[u, v]["delay"]
                topo_ele = etree.SubElement(new_topo_ele, "grp", link_type="bi_direct", src_node=str(u), src_port=u_port_cnt, dst_node=str(v), dst_port=v_port_cnt, bandwidth=str(bw), delay=str(dl))
                port_conn_count[u] += 1
                port_conn_count[v] += 1
        old_topo_ele.getparent().replace(old_topo_ele, new_topo_ele)


        # <dcn_common_node_config>修改
        config_ele = etree.Element("common_node")
        old_config_ele = root_config.xpath('/dcn/dcn_common_node_config/common_node')[0]
        template_ele = root_config.xpath('/dcn/dcn_common_node_config/common_node/template')[0]

        t_template_id = 0
        for port_num, node_id in port_num_id_dict.items():
            if not self.node_is_switch(node_id[0]):
                continue
            template_ele.set("index", str(t_template_id))
            t_port_att_eles = template_ele.xpath('.//*[@port]')
            for ele in t_port_att_eles:
                # print(ele.get("port"))
                ele.set("port", "0.." + str(port_num - 1))
            config_ele.append(deepcopy(template_ele))
            t_template_id += 1
        old_config_ele.getparent().replace(old_config_ele, config_ele)
        
        config_ele = etree.Element("common_host")
        old_config_ele = root_config.xpath('/dcn/dcn_common_node_config/common_host')[0]
        template_ele = root_config.xpath('/dcn/dcn_common_node_config/common_host/template')[0]

        t_template_id = 0
        for port_num, node_id in port_num_id_dict.items():
            if not self.node_is_host(node_id[0]):
                continue
            template_ele.set("index", str(t_template_id))
            t_port_att_eles = template_ele.xpath('.//*[@port]')
            for ele in t_port_att_eles:
                # print(ele.get("port"))
                if ele.get("port") == "0..0":
                    continue
                ele.set("port", "1.." + str(port_num - 1 + 1))
            config_ele.append(deepcopy(template_ele))
            t_template_id += 1
        old_config_ele.getparent().replace(old_config_ele, config_ele)

        # 按照现有配置, 更改一些xml中的字段
        # ft_ele = root_config.xpath('/dcn/dcn_common_node_config/ft_node/node_config')[0]
        # ft_ele.set("host_num", str(list(self.host_ids)))
        # ft_ele.set("leaf_num", str(list(self.node_ids)))

        # 新增：动态修改 ft_node 和 ft_host 中的参数
        host_num_str = str(len(self.host_ids))
        leaf_num_str = str(len(self.leaf_ids))
        spine_num_str = str(len(self.spine_ids))

        # 修改 ft_node 的每个 template
        ft_node_templates = root_config.xpath('/dcn/dcn_common_node_config/ft_node/template')
        for template in ft_node_templates:
            node_config_ele = template.xpath('node_config')[0]
            node_config_ele.set("host_num", host_num_str)
            node_config_ele.set("leaf_num", leaf_num_str)
            node_config_ele.set("spine_num", spine_num_str)

        # 修改 ft_host
        ft_host = root_config.xpath('/dcn/dcn_common_node_config/ft_host')[0]
        ft_host_node_config = ft_host.xpath('node_config')[0]
        ft_host_node_config.set("host_num", host_num_str)
        ft_host_node_config.set("leaf_num", leaf_num_str)
        ft_host_node_config.set("spine_num", spine_num_str)

        ft_host_host_config = ft_host.xpath('host_config')[0]
        ft_host_host_config.set("host_num", host_num_str)

        # 新增：动态修改 sim/cli 中的 rdma_log_num
        cli_ele = root_config.xpath('/dcn/sim/cli')[0]
        cli_ele.set("rdma_log_num", str(rdma_log_num))

        etree.indent(root_config, space="    ")
        # print(etree.tostring(root_config, pretty_print=True).decode(), end="")
        if output_name is None:
            output_name = "dcn2.0_config.xml"
        if write_flag:
            if not os.path.exists(self.output_dir):
                os.mkdir(self.output_dir)
            with open(self.output_dir + output_name, "w") as output_xml:
                output_xml.write(etree.tostring(root_config, pretty_print=True).decode())
            print("配置文件已写入：", self.output_dir + output_name)
        
        self.topo_ele_xml = new_topo_ele
        self.node_ele_xml = new_node_ele
        
        # 构建下一跳端口表
        next_hop_port = []
        for i in range(total_node_num):
            next_hop_port.append([])
            for j in range(total_node_num):
                next_hop_port[i].append(-1)
        for link_ele in self.topo_ele_xml:
            if link_ele.get("dst_node") == "-1":
                continue
            # 为简化代码,脚本仅支持一对一的topo配置,不支持使用空格或".."分割的配置
            sn = int(link_ele.get("src_node"))
            sp = int(link_ele.get("src_port"))
            dn = int(link_ele.get("dst_node"))
            dp = int(link_ele.get("dst_port"))
            next_hop_port[sn][dn] = sp
            next_hop_port[dn][sn] = dp
            # print(next_hop_port)
        self.next_hop_port = next_hop_port
        
        return new_node_ele, new_topo_ele
    
    def set_route_table(self, curr_node, dst, next_hop_node, metric):
        """如果你想直接写入路由表项, 请使用本方法. 
        如果你想使用寻路算法寻找每一对host节点间的可用路径, 并基于可用路径生成路由表, 请使用gen_route_table方法. 
        
        Parameters
        ----------
        self : 定义好的NetiSimGraph图
        curr_node : 表项会被写入到的当前节点id
        dst : 目的节点id
        next_hop_node : 从当前节点到目的节点的下一跳节点id
        metric : 当前路径到目的节点的跳数, 或者其它用于量化该路径长度/开销的值
        """
        self.route_table_2port[curr_node][dst].add((self.next_hop_port[curr_node][next_hop_node], metric))
        self.route_table_2node[curr_node][dst].add((next_hop_node, metric))
    
    def all_shortest_paths(self, src, dst):
        return nx.all_shortest_paths(self, src, dst, weight=None, method="dijkstra")

    def set_path_finding_algo(self, func):
        """设置需要的路径发现算法.
            Parameters
            ----------
            func : 算法定义

            Notes
            -----
            func只允许三个变量输入,分别是图`graph`, 源节点`src`以及目的节点`dst`.
            `src`以及`dst`皆为`host`节点.
            输出算法发现的从`src`到`dst`所有路径, 路径以有序的节点编号表示, 以`src`为开头, `dst`为结尾.
        """
        self.path_finding_algo = func
        
    def get_path_finding_algo(self):
        return self.path_finding_algo.__name__
    
    def init_routing_tables(self):
        # 初始化路由表
        if self.topo_ele_xml is None or self.node_ele_xml is None:
            self.build_graph_config()
        total_node_num = self.get_total_num()
        self.route_table_2port = []
        self.route_table_2node = []
        for i in range(total_node_num):
            self.route_table_2port.append([])
            self.route_table_2node.append([])
            for j in range(total_node_num):
                self.route_table_2port[i].append(set())
                self.route_table_2node[i].append(set())
    
    def gen_route_table(self, path_finding_algo=nx.all_shortest_paths, write_file=True):
        """
        如果你想使用寻路算法寻找每一对host节点间的可用路径, 并基于可用路径生成路由表, 请使用本方法. 
        
        如果你想直接写入路由表项, 请使用`set_route_table`方法. 
        Parameters
        ----------
        path_finding_algo : 你可以自定义寻路方法. 该方法定义为`path_finding_algo(NetiSimGraph, src, dst)`.
            只允许三个变量输入, 分别是图`NetiSimGraph`, 源节点`src`以及目的节点`dst`. `src`以及`dst`皆为`host`节点.
            输出算法发现的从`src`到`dst`所有路径, 路径以有序的节点编号列表表示, 以`src`为开头, `dst`为结尾.

        """


        self.init_routing_tables()

        # 对每一对host间的路径进行路由表项的建立
        paths = []
        for m in trange(len(self.host_ids), desc="算法{}寻找所有可用路径".format(path_finding_algo.__name__)):
            src = self.host_ids[m]
            ts1 = time.time()
            for n in range(m, len(self.host_ids)):
                dst = self.host_ids[n]
                try:
                    paths += path_finding_algo(self, src, dst)
                except nx.exception.NetworkXNoPath:
                    # print("networkx.exception.NetworkXNoPath: {} {}".format(src, dst))
                    pass
                
        for path in tqdm(paths, desc="填写路由表项"):
            # print(path)
            src = path[0]
            dst = path[-1]
            for i in range(0, len(path)):
                node_id = path[i]
                if self.node_is_host(node_id):
                    pass

                if i >= 1:
                    metric = i
                    self.set_route_table(node_id, src, path[i-1], metric)
                if i < len(path) - 1:
                    metric = len(path) - i - 1
                    self.set_route_table(node_id, dst, path[i+1], metric)

        if write_file:
            self.write_route_table_to_xml(algo=path_finding_algo)
    
    def write_route_table_to_xml(self, algo=None):
        # 路由表写入xml文件中
        route_ele = etree.Element("router")
        route_table = self.route_table_2port
        for node_id in tqdm(self.nodes, desc="写入路由表"):
            # print(self.nodes[node_id]["type"])
            if self.node_is_host(node_id):
                # continue
                pass
            route_grp_ele = etree.SubElement(route_ele, "grp", node_id=str(node_id), node_type=self.nodes[node_id]["type"])
            route_grp_ele.set("node_id", str(node_id))
            for dst_id in range(len(route_table[node_id])):
                next_ports_metric_sets = sorted(route_table[node_id][dst_id])
                if len(next_ports_metric_sets) == 0:
                    continue
                ports = ""
                metrics = ""
                for p_m in next_ports_metric_sets:
                    ports += str(p_m[0]) + " "
                    metrics += str(p_m[1]) + " "
                target_ele = etree.SubElement(route_grp_ele, "target", node_id=str(dst_id), port_id=ports.strip(), metric=metrics.strip())
        
        self.route_ele_xml = route_ele
        
        if not os.path.exists(self.output_dir):
            os.mkdir(self.output_dir)
        etree.indent(route_ele, space="    ")
        # print(etree.tostring(route_ele, pretty_print=True).decode(), end="")
        with open(self.output_dir + "router_mine.xml", "w") as output_xml:
            if algo:
                output_xml.write("<!-- create with [{}] algorithm at module[{}] -->\n".format(algo.__name__, algo.__module__))
            output_xml.write(etree.tostring(route_ele, pretty_print=True).decode())
        print("路由文件已写入：", self.output_dir + "router_mine.xml")

    def get_link_port(self, src, dst): # 给定src, dst,输出src绑定的对应port
        return self.next_hop_port[src][dst]
    
    def get_next_hop(self, src, port): # 给定src, port,输出下一跳节点
        return self.next_hop_port[src].index(port)
    
    def find_all_paths_with_router(self, src, dst):
        if self.route_table_2port == None or self.route_table_2node == None:
            print("先生成NetiSimGraph图以及路由信息再调用此方法！")
            return None
        result_paths = []
        
        current_idx = 0
        current_path = [src]
        current_node = current_path[current_idx]
        
        possible_next_hops = []
        next_hops = self.route_table_2node[current_node][dst]
        possible_next_hops.append(list(next_hops))
        next_hop = possible_next_hops[current_idx].pop()[0]
        current_path.append(next_hop)
        current_idx += 1
        current_node = current_path[current_idx]
        while current_idx != 0:
            if current_node == dst:
                result_paths.append(current_path.copy())
                current_idx -= 1
                current_path = current_path[:-1]
                current_node = current_path[current_idx]
                continue
            if current_idx >= len(possible_next_hops):
                # 第一次进入当前跳数的节点，下一跳节点还未更新
                next_hops = self.route_table_2node[current_node][dst]
                possible_next_hops.append(list(next_hops))
            if len(possible_next_hops[current_idx]) == 0:
                # 当前跳数的下一跳可能节点已经全部遍历完毕，则返回上一层
                possible_next_hops = possible_next_hops[:-1]
                current_path = current_path[:-1]
                current_idx -= 1
                current_node = current_path[current_idx]
                continue
            next_hop = possible_next_hops[current_idx].pop()[0]
            current_path.append(next_hop)
            current_idx += 1
            current_node = current_path[current_idx]
        
        return result_paths

    def find_all_paths_host2host(self, src, dst, method = "shortest"):
        if self.node_is_switch(src) or self.node_is_switch(dst):
            print("src和dst必须是host节点!任意节点间最短路径使用networkx内置函数nx.shortest_path()计算!")
            return None
        if method == "shortest":
            return nx.all_shortest_paths(self, src, dst)
        if method == "router":
            return self.find_all_paths_with_router(src, dst)

def gen_netisim_graph_with_xml(config_xml, router_xml) -> NetiSimGraph:
        root = etree.parse(config_xml).getroot()
        graph = NetiSimGraph()
        # 从xml文件中读取节点信息
        for node in root.xpath('/dcn/dcn_network/node/grp'):
            if "host" in node.get('type'):
                for host_id in netisim_utils.get_range_int(node.get('node_id')):
                    graph.add_netisim_host(host_id)
            elif "node" in node.get('type'):
                for node_id in netisim_utils.get_range_int(node.get('node_id')):
                    graph.add_netisim_node(node_id)
                    
        # 从xml文件中读取链路信息
        total_node_num = graph.get_total_num()
        graph.next_hop_port = []
        for i in range(total_node_num):
            graph.next_hop_port.append([])
            for j in range(total_node_num):
                graph.next_hop_port[i].append(-1)
                
        for link in root.xpath('/dcn/dcn_network/topology/grp'):
            if link.get('dst_node') == '-1':
                continue
            # 为简化代码,脚本仅支持一对一的topo配置,不支持使用空格或".."分割的配置
            src_node = int(link.get('src_node'))
            dst_node = int(link.get('dst_node'))
            bandwidth = int(link.get('bandwidth'))
            delay = int(link.get('delay'))
            graph.add_netisim_edge(src_node, dst_node, bandwidth, delay)
            graph.next_hop_port[src_node][dst_node] = int(link.get('src_port'))
            graph.next_hop_port[dst_node][src_node] = int(link.get('dst_port'))
            
        graph.node_ele_xml = root.xpath('/dcn/dcn_network/node')[0]
        graph.topo_ele_xml = root.xpath('/dcn/dcn_network/topology')[0]
        # show node_ele_xml and topo_ele_xml
        # print(etree.tostring(self.node_ele_xml, pretty_print=True).decode(), end="")
        # print(etree.tostring(self.topo_ele_xml, pretty_print=True).decode(), end="")
        
        if router_xml == None:
            return graph
        
        # 构建路由表
        root = etree.parse(router_xml).getroot()
        
        graph.init_routing_tables()
        # route_table_2port = []
        # route_table_2node = []
        # for i in range(total_node_num):
        #     route_table_2port.append([])
        #     route_table_2node.append([])
        #     for j in range(total_node_num):
        #         route_table_2port[i].append(set())
        #         route_table_2node[i].append(set())
                
        for node_route in root.xpath('/router/grp'):
            node_id = int(node_route.get('node_id'))
            for route in node_route:
                dst_node = int(route.get('node_id'))
                port_ids = list(netisim_utils.get_range_int(route.get('port_id')))
                metrics = list(netisim_utils.get_range_int(route.get('metric')))
                for id in range(len(port_ids)):
                    port_id = port_ids[id]
                    metric = metrics[id]
                    next_hop = graph.get_next_hop(node_id, port_id)
                    graph.set_route_table(node_id, dst_node, next_hop, metric)
                    # route_table_2port[node_id][dst_node].add((port_id, metric))
                    # # print("{}->{} next_hop:{}".format(node_id, dst_node, next_hop))
                    # route_table_2node[node_id][dst_node].add(next_hop)
                    
        # graph.route_table_2port = route_table_2port
        # graph.route_table_2node = route_table_2node
        graph.route_ele_xml = root
        return graph

NETISIM_MOD = "ft2_"
HOST_TYPE = NETISIM_MOD + "host"
NODE_TYPE = NETISIM_MOD + "node"

COMP_DELAY = 1300
TO_DIR = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime()) + "/"

# 用例1:用户自定义拓扑,并生成xml文件以及通过最短路径算法生成路由文件
def user_topo():

    graph = NetiSimGraph()
    host_num = 8
    leaf_sw_num = 4
    spine_sw_num = 4
    total_node_num = host_num + leaf_sw_num + spine_sw_num
    
    # step1: 生成节点,要求host在前,node在后,且顺序编号,不符合要求会报错
    for host_id in range(host_num):
        graph.add_netisim_host(host_id)

    for leaf_sw_id in range(leaf_sw_num):
        graph.add_netisim_node(leaf_sw_id + host_num, comp_delay=COMP_DELAY)

    for spine_sw_id in range(spine_sw_num):
        graph.add_netisim_node(spine_sw_id + host_num + leaf_sw_num, comp_delay=COMP_DELAY)
    

    # step2: 生成拓扑连线,按照自定义拓扑,将指定id的节点(host或node皆可)进行连线并指定带宽和时延(发包器会自动连接)
    for host_id in range(host_num):
        graph.add_netisim_edge(host_id, host_num + int(host_id/2), bandwidth='200', delay='20')
                
    for lsw_id in range(host_num, host_num + leaf_sw_num):
        for ssw_id in range(host_num + leaf_sw_num, host_num + leaf_sw_num + spine_sw_num):
            graph.add_netisim_edge(lsw_id, ssw_id, bandwidth='200', delay='20')

    # 生成配置文件,build_graph_config会生成一系列中间数据,最终生成dcn2.0_config.xml文件
    graph.build_graph_config(output_name="dcn2.0_config.xml", write_flag=False)
    # 生成路由表,gen_route_table会依赖build_graph_config产生的中间数据,最终生成router_mine.xml文件
    graph.gen_route_table(write_file=False)
    return graph

if __name__ == '__main__':
    user_topo()