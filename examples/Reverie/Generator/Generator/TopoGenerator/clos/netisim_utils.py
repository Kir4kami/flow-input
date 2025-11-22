#!/usr/bin/env python3
import re
from tqdm import tqdm, trange
import networkx as nx
import numpy as np

EMPTY_NODE_WEIGHT = 4*1024*1024

def get_range_int(s: str) -> iter:
    """
    获取字符串中的数字范围
    :param s: 字符串, 例如: "1..10 11 25 39"
    :return: 数字范围生成器int
    """
    spaced_strs = s.split()
    for item in spaced_strs:
        if '..' in item:
            groups = re.match(r'(\d+)..(\d+)', item)
            if groups:
                start, end = groups.groups()
                for i in range(int(start), int(end) + 1):
                    yield i
        else:
            yield int(item)
    
    return None

def gen_comm_line(comm: list, index):
    return "<item index=\"{}\" rank=\"{}\"/>".format(index, " ".join([str(x) for x in comm]))

if __name__ == '__main__':

    exit()