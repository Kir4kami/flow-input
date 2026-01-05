#!/usr/bin/env python3
import os
import re
from collections import defaultdict
import xml.etree.ElementTree as ET
import json

node_in_set = 16


class FlowInfo:
    def __init__(self, flow_id, src_node, dst_node, src_port=1016, dst_port=1016, protocol=6):
        """
        流信息类
        Args:
            flow_id: 流ID
            src_node: 源节点ID
            dst_node: 目标节点ID
            src_port: 源端口（默认1016）
            dst_port: 目标端口（默认1016）
            protocol: 协议类型（6=TCP, 17=UDP，默认6）
        """
        self.flow_id = flow_id
        self.src_node = src_node
        self.dst_node = dst_node
        self.src_port = src_port
        self.dst_port = dst_port
        self.protocol = protocol

    def __repr__(self):
        return f"{self.flow_id} (src_node={self.src_node}, dst_node={self.dst_node}, src_port={self.src_port}, dst_port={self.dst_port}, protocol={self.protocol})"


class LinkInfo:
    def __init__(self, link_id, src_node, src_port, dst_node, dst_port):
        self.link_id = link_id
        self.src_node = src_node
        self.src_port = src_port
        self.dst_node = dst_node
        self.dst_port = dst_port

    def __repr__(self):
        return f"{self.link_id} (src_node={self.src_node}, src_port={self.src_port}, dst_node={self.dst_node}, dst_port={self.dst_port})"


class UnionFind:
    def __init__(self):
        self.parent = dict()

    def find(self, x):
        self.parent.setdefault(x, x)
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]

    def union(self, x, y):
        self.parent[self.find(y)] = self.find(x)


class RouteEntry:
    def __init__(self, node_id, target_node_id, port_ids, metrics):
        self.node_id = node_id
        self.target_node_id = target_node_id
        self.port_ids = port_ids
        self.metrics = metrics

    def __repr__(self):
        return f"RouteEntry(node_id={self.node_id}, target_node_id={self.target_node_id}, port_ids={self.port_ids}, metrics={self.metrics})"


def parse_rdma_operate(file_path):
    """
    解析rdma_operate文件，提取流信息（包括端口号）
    """
    flow_list = []
    flow_id_count = 1
    default_src_port = 1016
    default_dst_port = 1016
    default_protocol = 6  # TCP
    
    with open(file_path, 'r') as file:
        lines = file.readlines()

    for line in lines:
        if "rdma_send" in line:
            # 解析: Type rdma_send src_node X src_port Y dst_node Z dst_port W priority 0 msg_len SIZE
            # 先尝试匹配完整格式（包含端口）
            match_full = re.search(
                r'src_node[:\s]+(\d+).*?src_port[:\s]+(\d+).*?dst_node[:\s]+(\d+).*?dst_port[:\s]+(\d+)',
                line
            )
            if match_full:
                src_node = int(match_full.group(1))
                src_port = int(match_full.group(2))
                dst_node = int(match_full.group(3))
                dst_port = int(match_full.group(4))
            else:
                # 回退到只匹配节点（兼容旧格式）
                match = re.search(r'src_node[:\s]+(\d+)[,\s].*dst_node[:\s]+(\d+)', line)
                if match:
                    src_node = int(match.group(1))
                    dst_node = int(match.group(2))
                    src_port = default_src_port
                    dst_port = default_dst_port
                else:
                    continue
            
            flow = FlowInfo(flow_id_count, src_node, dst_node, src_port, dst_port, default_protocol)
            flow_list.append(flow)
            flow_id_count += 1
        if "phase" in line:
            continue
    return flow_list


def parse_topology_xml(file_path):
    link_list = []
    link_map = defaultdict(list)
    reverse_link_map = defaultdict(list)
    link_id_count = 1

    tree = ET.parse(file_path)
    root = tree.getroot()

    for grp in root.findall(".//topology//grp"):
        link_type = grp.get('link_type')
        src_nodes = grp.get('src_node')
        src_port = grp.get('src_port')
        dst_node = grp.get('dst_node')
        dst_port = grp.get('dst_port')
        bandwidth = grp.get('bandwidth')
        delay = grp.get('delay')

        if dst_node == "-1":
            continue

        if '..' in src_nodes:
            continue

        try:
            src_node = int(src_nodes)
        except ValueError:
            continue

        link = LinkInfo(link_id_count, src_node, int(src_port), int(dst_node), int(dst_port))
        link_list.append(link)
        link_map[(src_node, int(src_port))].append(link)
        reverse_link_map[(int(dst_node), int(dst_port))].append(link)
        link_id_count += 1

    node_config = root.find('.//dcn_common_node_config/ft_host/node_config')
    hostnum = node_config.get('host_num')
    leafnum = node_config.get('leaf_num')
    spinenum = node_config.get('spine_num')

    return link_list, link_map, reverse_link_map, int(hostnum), int(leafnum), int(spinenum)


def parse_route_xml(file_path):
    route_table = []
    tree = ET.parse(file_path)
    root = tree.getroot()

    for grp in root.findall(".//grp"):
        node_id = grp.get('node_id')
        node_type = grp.get('node_type')

        """ if node_type != "node":
            continue """

        for target in grp.findall('target'):
            target_node_id = target.get('node_id')
            port_id_str = target.get('port_id')
            metric_str = target.get('metric')
            port_ids = list(map(int, port_id_str.split()))
            metrics = list(map(int, metric_str.split()))
            route_entry = RouteEntry(node_id=int(node_id), target_node_id=int(target_node_id), port_ids=port_ids,
                                     metrics=metrics)
            route_table.append(route_entry)
    return route_table


def node_id_to_ip(node_id):
    """
    将节点ID转换为IP地址格式（与NS-3一致）
    参考: kira_functions.cc 第59-60行
    IP格式: 0x0b000001 + ((node_id / 256) * 0x00010000) + ((node_id % 256) * 0x00000100)
    即: 11.0.0.1 + (node_id的高8位 << 16) + (node_id的低8位 << 8)
    """
    return 0x0b000001 + ((node_id // 256) * 0x00010000) + ((node_id % 256) * 0x00000100)


def ecmp_hash(key_bytes, seed):
    """
    ECMP Hash函数，与NS-3的SwitchNode::EcmpHash完全一致
    参考: switch-node.cc 第182-218行
    
    Args:
        key_bytes: 字节数组（12字节：src_ip 4字节 + dst_ip 4字节 + ports 4字节）
        seed: 种子值（通常是节点ID）
    
    Returns:
        hash值（uint32）
    """
    h = seed & 0xFFFFFFFF  # 确保是32位无符号整数
    key_len = len(key_bytes)
    
    # 处理4字节对齐的部分
    if key_len > 3:
        i = key_len >> 2  # 除以4
        key_idx = 0
        while i > 0:
            # 读取4字节（小端序）
            k = (key_bytes[key_idx] |
                 (key_bytes[key_idx + 1] << 8) |
                 (key_bytes[key_idx + 2] << 16) |
                 (key_bytes[key_idx + 3] << 24))
            k = k & 0xFFFFFFFF  # 确保是32位
            
            # MurmurHash3的混合步骤
            k *= 0xcc9e2d51
            k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
            k *= 0x1b873593
            k = k & 0xFFFFFFFF
            
            h ^= k
            h = h & 0xFFFFFFFF
            h = ((h << 13) | (h >> 19)) & 0xFFFFFFFF
            h = (h + ((h << 2) + 0xe6546b64)) & 0xFFFFFFFF
            
            key_idx += 4
            i -= 1
    
    # 处理剩余的字节（1-3字节）
    if key_len & 3:
        i = key_len & 3
        k = 0
        key_idx = key_len - 1
        while i > 0:
            k = ((k << 8) | key_bytes[key_idx]) & 0xFFFFFFFF
            key_idx -= 1
            i -= 1
        
        k *= 0xcc9e2d51
        k = ((k << 15) | (k >> 17)) & 0xFFFFFFFF
        k *= 0x1b873593
        k = k & 0xFFFFFFFF
        h ^= k
        h = h & 0xFFFFFFFF
    
    # 最终混合
    h ^= key_len
    h = h & 0xFFFFFFFF
    h ^= (h >> 16)
    h = h & 0xFFFFFFFF
    h = (h * 0x85ebca6b) & 0xFFFFFFFF
    h ^= (h >> 13)
    h = h & 0xFFFFFFFF
    h = (h * 0xc2b2ae35) & 0xFFFFFFFF
    h ^= (h >> 16)
    h = h & 0xFFFFFFFF
    
    return h


def compute_ecmp_hash_for_flow(src_node, dst_node, src_port, dst_port, current_node_id):
    """
    为流计算ECMP hash值（与NS-3的GetOutDev函数一致）
    参考: switch-node.cc 第90-107行, kira_functions.cc 第54-63行
    
    Args:
        src_node: 源节点ID
        dst_node: 目标节点ID
        src_port: 源端口
        dst_port: 目标端口
        current_node_id: 当前节点ID（作为seed）
    
    Returns:
        hash值
    """
    # 将节点ID转换为IP地址格式
    src_ip = node_id_to_ip(src_node)
    dst_ip = node_id_to_ip(dst_node)
    
    # 构建12字节的key（与NS-3一致）
    # buf.u32[0] = src_ip (4字节)
    # buf.u32[1] = dst_ip (4字节)
    # buf.u32[2] = src_port | (dst_port << 16) (4字节)
    key_bytes = bytearray(12)
    
    # src_ip (小端序)
    key_bytes[0] = src_ip & 0xFF
    key_bytes[1] = (src_ip >> 8) & 0xFF
    key_bytes[2] = (src_ip >> 16) & 0xFF
    key_bytes[3] = (src_ip >> 24) & 0xFF
    
    # dst_ip (小端序)
    key_bytes[4] = dst_ip & 0xFF
    key_bytes[5] = (dst_ip >> 8) & 0xFF
    key_bytes[6] = (dst_ip >> 16) & 0xFF
    key_bytes[7] = (dst_ip >> 24) & 0xFF
    
    # ports: src_port | (dst_port << 16) (小端序)
    ports = src_port | (dst_port << 16)
    key_bytes[8] = ports & 0xFF
    key_bytes[9] = (ports >> 8) & 0xFF
    key_bytes[10] = (ports >> 16) & 0xFF
    key_bytes[11] = (ports >> 24) & 0xFF
    
    # 使用当前节点ID作为seed（与NS-3一致：m_ecmpSeed = m_id）
    return ecmp_hash(key_bytes, current_node_id)


#def find_ecmp_path(flow_info_list, link_info_list, route_info_table, link_map, reverse_link_map):
#   flow_paths = []
#   flow_paths_port = []
#   first_node_to_links = defaultdict(list)
#   for link in link_info_list:
#       first_node_to_links[link.src_node].append(link)
#
#   nodes_to_route = defaultdict(list)
#   for entry in route_info_table:
#       nodes_to_route[entry.node_id].append(entry)
#
#   # 遍历所有rdma_operate
#   for flow in flow_info_list:
#       src_node = flow.src_node
#       dst_node = flow.dst_node
#       paths = [src_node]
#       current_node = src_node
#
#       # 找到host —— sw_node的第一跳
#       for link in link_info_list:
#           if current_node == link.src_node:
#               current_node = link.dst_node
#               paths_port = [str(link.src_node) + "->" + str(link.src_port),
#                             str(link.dst_port) + "->" + str(link.dst_node)]
#               paths.append(current_node)
#               break
#
#       # 找到2跳 —— 最后一跳
#       while current_node != dst_node:
#           next_in_port = link.dst_port
#           for entry in nodes_to_route[current_node]:
#               if entry.node_id == current_node and entry.target_node_id == dst_node:
#                   # 找到下一跳的路由条目entry，入端口号%路由中端口号个数 = 出端口
#                   current_out_port = entry.port_ids[next_in_port % len(entry.port_ids)]
#                   # 通过出端口和现节点找到link,并找到下一跳。
#                   if link_map[(current_node, current_out_port)]:
#                       link = link_map[(current_node, current_out_port)][0]
#                       current_node = link.dst_node
#                       reverse = False
#                   else:
#                       link = reverse_link_map[(current_node, current_out_port)][0]
#                       current_node = link.src_node
#                       reverse = True
#                   if reverse:
#                       paths_port[-1] = paths_port[-1] + "->" + str(link.dst_port)
#                       paths_port.append(str(link.src_port) + "->" + str(link.src_node))
#                   else:
#                       paths_port[-1] = paths_port[-1] + "->" + str(link.src_port)
#                       paths_port.append(str(link.dst_port) + "->" + str(link.dst_node))
#                   paths.append(current_node)
#                   break
#
#       # for route_entry in nodes_to_route[current_node]:
#       #     if route_entry.target_node_id == dst_node:
#       flow_paths.append((flow.flow_id, paths))
#       flow_paths_port.append((flow.flow_id, paths_port))
#   return flow_paths, flow_paths_port

def find_ecmp_path(flow_info_list, link_info_list, route_info_table, link_map, reverse_link_map):
    flow_paths = []
    flow_paths_port = []

    # 构建节点到路由条目的映射
    nodes_to_route = defaultdict(list)
    for entry in route_info_table:
        nodes_to_route[entry.node_id].append(entry)

    MAX_HOPS = 100  # 防止死循环

    for flow in flow_info_list:
        src_node = flow.src_node
        dst_node = flow.dst_node

        if src_node == dst_node:
            flow_paths.append((flow.flow_id, [src_node]))
            flow_paths_port.append((flow.flow_id, []))
            continue

        paths = [src_node]
        paths_port = []

        # === 第一跳：从 host 到 leaf switch ===
        first_link = None
        in_port = None  # 到达当前节点的入端口（对第一跳，host 无入端口，但交换机需要知道从哪个端口进来的）
        current_node = src_node

        # 找从 src_node 出发的链路（host -> switch）
        for link in link_info_list:
            if link.src_node == src_node:
                first_link = link
                break
        else:
            raise RuntimeError(f"未找到从源节点 {src_node} 出发的链路")

                # 第一跳：host -> switch
        next_node = first_link.dst_node
        paths.append(next_node)
        # 记录端口路径: host -> out_port -> in_port -> switch
        # 添加类型标记：N表示节点，P表示端口
        paths_port.append(f"N{first_link.src_node}->P{first_link.src_port}")
        paths_port.append(f"P{first_link.dst_port}->N{first_link.dst_node}")

        current_node = next_node
        in_port = first_link.dst_port  # 到达 current_node 的入端口

        # === 后续跳：在交换机之间转发，直到到达 dst_node 所在的 leaf ===
        hop_count = 1
        while current_node != dst_node and hop_count < MAX_HOPS:
            # 查找当前节点到 dst_node 的路由条目
            route_entry = None
            for entry in nodes_to_route[current_node]:
                if entry.target_node_id == dst_node:
                    route_entry = entry
                    break
            if not route_entry:
                raise RuntimeError(f"路由表缺失：节点 {current_node} 无到 {dst_node} 的路由")

            # 使用正确的ECMP hash算法选择出端口（与NS-3一致）
            if len(route_entry.port_ids) == 0:
                raise RuntimeError(f"路由条目无可用端口：节点 {current_node} 到 {dst_node}")
            elif len(route_entry.port_ids) == 1:
                # 只有一个端口，直接使用
                out_port = route_entry.port_ids[0]
            else:
                # 多个端口，使用ECMP hash选择
                # 使用5元组hash: (src_node, dst_node, src_port, dst_port, current_node)
                hash_value = compute_ecmp_hash_for_flow(
                    flow.src_node, flow.dst_node,
                    flow.src_port, flow.dst_port,
                    current_node
                )
                port_index = hash_value % len(route_entry.port_ids)
                out_port = route_entry.port_ids[port_index]

            # 查找对应的链路
            link = None
            reverse = False
            if (current_node, out_port) in link_map and link_map[(current_node, out_port)]:
                link = link_map[(current_node, out_port)][0]
                next_node = link.dst_node
                reverse = False
            elif (current_node, out_port) in reverse_link_map and reverse_link_map[(current_node, out_port)]:
                link = reverse_link_map[(current_node, out_port)][0]
                next_node = link.src_node
                reverse = True
            else:
                raise RuntimeError(f"找不到节点 {current_node} 端口 {out_port} 对应的链路")

            # 更新路径
            paths.append(next_node)
            if reverse:
                # 反向链路：追加目标端口，然后添加 端口->节点
                paths_port[-1] += f"->P{link.dst_port}"
                paths_port.append(f"P{link.src_port}->N{link.src_node}")
            else:
                # 正向链路：追加源端口，然后添加 端口->节点
                paths_port[-1] += f"->P{link.src_port}"
                paths_port.append(f"P{link.dst_port}->N{link.dst_node}")

            # 更新状态
            current_node = next_node
            in_port = link.src_port if reverse else link.dst_port
            hop_count += 1

        if hop_count >= MAX_HOPS:
            raise RuntimeError(f"ECMP 路径查找超限（>{MAX_HOPS}跳），可能有环路：flow {flow.flow_id}, {src_node} -> {dst_node}")

        flow_paths.append((flow.flow_id, paths))
        flow_paths_port.append((flow.flow_id, paths_port))

    return flow_paths, flow_paths_port

def load_file(working_directory, file_addr):
    rdma_file_path = file_addr
    topology_file_path = working_directory + "/dcn2.0_config.xml"
    route_file_path = working_directory + "/router_mine.xml"

    link_info_list, link_map, reverse_link_map, hostnum, leafnum, spinenum = parse_topology_xml(topology_file_path)
    route_info_table = parse_route_xml(route_file_path)
    flow_info_list = []
    for rdma_file in rdma_file_path:
        flow_info_list.extend(parse_rdma_operate(rdma_file))
        # 注释掉 print，避免打断 tqdm 进度条（可以通过 logger 记录）
        # print(f"{rdma_file} load file success")
    return flow_info_list, link_info_list, route_info_table, link_map, reverse_link_map, hostnum, leafnum, spinenum

def get_rdma_files(file_dir):
    file_path_list = []
    for root, dirs, files in os.walk(file_dir):
        for file in files:
            if file.startswith('rdma_operate'):
                file_path = os.path.join(root, file)
                file_path_list.append(file_path)
    return file_path_list

# 主函數入口
if __name__ == "__main__":
    # 在此处更改工作目录
    Working_Directory = "./64-4-1_DP2"
    file_path_list = get_rdma_files(Working_Directory)
    Flow_Info_List, Link_Info_List, Route_Info_Table, Link_Map, Reverse_Link_Map, host_num, leaf_num, spine_num = load_file(
        Working_Directory, file_path_list)
    Total_Flow_Path, Flow_Paths_Port = find_ecmp_path(Flow_Info_List, Link_Info_List, Route_Info_Table, Link_Map,
                                                      Reverse_Link_Map)
    temp = "debug"