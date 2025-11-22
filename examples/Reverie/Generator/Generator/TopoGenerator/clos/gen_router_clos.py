#!/usr/bin/env python3
import datetime
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

host_num = 128
leaf_num = 16
# 一个leaf最少要连接64个host
spine_num = 8

node_in_set=(int)(host_num/leaf_num)
# 64*2==128

def judge_type(id,hostnum,leafnum,flag):
    if flag:
        if (0 <= id < hostnum):
            return "host"
        elif (hostnum<=id<hostnum+leafnum):
            return "leaf"
        else: return "spine"
    else:
        if (0 <= id < hostnum):
            return "host"
        else:
            return "node"
def get_port_in_leaf(node_id):
   if node_id%2==0: return f'{node_id%(node_in_set*2)//2}'
   else :return f'{(node_id%(node_in_set*2)-1)//2}'

def get_port_in_spine(node_id,leafnum):
    return f'{node_id%leafnum}'

def get_leaf_id(id,hostnum):
    if id >= hostnum:
        return id-hostnum
    group = id // (node_in_set*2)
    offset =id%(node_in_set*2)
    leaf_in_grp=0 if offset %2 ==0 else 1
    leaf_id=group*2+leaf_in_grp
    return leaf_id

def cal_port(src_node, dst_host,hostnum,leafnum,spinenum):
    if dst_host >= hostnum:
        raise ValueError("目标节点必须是主机")

    if src_node == dst_host:
        return

    dst_leaf = get_leaf_id(dst_host,hostnum)  # 获取目标主机所属的leaf ID
    src_leaf = get_leaf_id(src_node,hostnum)  # 获取源主机所属的leaf ID

    src_type = judge_type(src_node,hostnum,leafnum,0)

    if src_type == "host":
        if dst_leaf == src_leaf:
            return "1"
        else:
            return "1"
    elif src_type == "node" and hostnum <= src_node < hostnum+leafnum:
        if dst_leaf == src_leaf:
            return get_port_in_leaf(dst_host)
        else:
            # 从node_in_set开始，spine有几个就写几个
            return f' '.join(str(node_in_set + i) for i in range(spinenum))
    elif src_type == "node" and hostnum+leafnum <= src_node < hostnum+leafnum+spinenum:
        return get_port_in_spine(get_leaf_id(dst_host,hostnum),leafnum)


def cal_metric(src, dst,hostnum,leafnum,spinenum):
    if (src == dst):
        return "0"
    src_leaf = get_leaf_id(src,hostnum)

    dst_leaf = get_leaf_id(dst,hostnum)

    node_type = judge_type(src,hostnum,leafnum,0)
    if node_type == "node" and hostnum+leafnum <= src < hostnum+leafnum+spinenum:
        return "2"
    elif node_type == "node" and hostnum <= src < hostnum+leafnum:
        if src_leaf == dst_leaf:
            return "1"
        else:
            return " ".join(["3"]*spinenum)
    else:
        if src_leaf == dst_leaf:
            return "2"
        else:
            return " ".join(["4"]*spinenum)

def write_route_table_to_xml(host,leaf,spine):
    host_num=host
    leaf_num=leaf
    spine_num=spine

    file_path = "./router_output/"
    os.makedirs(file_path, exist_ok=True)

    file_path=file_path+f"/router_mine.xml"
    node_num = host_num+leaf_num+spine_num
    progress_bar = tqdm(total=node_num * host_num, desc="写入进度", unit="项")
    with open(file_path, "w") as output_xml:
        output_xml.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        output_xml.write('<router>\n')
        for node_id in range(host_num,host_num+leaf_num+spine_num,1):
                output_xml.write(
            f'  <grp node_id="{node_id}" node_type="{judge_type(node_id,host_num,leaf_num,0)}">\n')
                for dst_id in range(host_num):
                    if dst_id != node_id:
                        output_xml.write(f'     <target node_id="{dst_id}" '
                                     f'port_id="{cal_port(node_id,dst_id,host_num,leaf_num,spine_num)}" '
                                     f'metric="{cal_metric(node_id,dst_id,host_num,leaf_num,spine_num)}"/>\n')
                        progress_bar.update(1)


                output_xml.write('  </grp>\n')
                output_xml.flush()
        output_xml.write('</router>')
    progress_bar.close()
    print("路由文件已写入")

if __name__ == '__main__':
    write_route_table_to_xml(host_num,leaf_num,spine_num)