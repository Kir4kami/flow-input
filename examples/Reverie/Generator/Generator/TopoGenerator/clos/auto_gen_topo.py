#!/usr/bin/env python3
"""
自动化生成 Clos 拓扑配置和路由表
支持参数化配置，便于后续集成流量生成
"""

import os
import sys
import argparse
import time
from pathlib import Path
import netisim_graph


class ClosTopoGenerator:
    """Clos 拓扑生成器"""
    
    def __init__(self, host_num, leaf_num, spine_num, 
                 host_bw=200, leaf_spine_bw=400,
                 host_delay=5, leaf_spine_delay=10,
                 comp_delay=1600, rdma_log_num=None,
                 output_dir=None):
        """
        初始化拓扑生成器
        
        参数:
            host_num: 主机数量
            leaf_num: Leaf交换机数量
            spine_num: Spine交换机数量
            host_bw: 主机到Leaf带宽 (Gbps)
            leaf_spine_bw: Leaf到Spine带宽 (Gbps)
            host_delay: 主机到Leaf延迟 (ns)
            leaf_spine_delay: Leaf到Spine延迟 (ns)
            comp_delay: 交换机计算延迟 (ns)
            rdma_log_num: RDMA日志数量
            output_dir: 输出目录
        """
        self.host_num = host_num
        self.leaf_num = leaf_num
        self.spine_num = spine_num
        self.host_bw = host_bw
        self.leaf_spine_bw = leaf_spine_bw
        self.host_delay = host_delay
        self.leaf_spine_delay = leaf_spine_delay
        self.comp_delay = comp_delay
        self.rdma_log_num = rdma_log_num if rdma_log_num else host_num + leaf_num + spine_num
        
        # 输出目录
        if output_dir is None:
            timestamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
            self.output_dir = f"./auto_output/{timestamp}"
        else:
            self.output_dir = output_dir
        
        # 创建输出目录
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 验证参数
        self._validate_params()
        
        # 初始化图
        self.graph = netisim_graph.NetiSimGraph()
        # 覆盖默认输出目录
        self.graph.output_dir = self.output_dir + "/"
        
        print(f"初始化 Clos 拓扑生成器")
        print(f"   主机数: {self.host_num}")
        print(f"   Leaf数: {self.leaf_num} (每个连接 {self.host_num//self.leaf_num} 台主机)")
        print(f"   Spine数: {self.spine_num}")
        print(f"   超额订阅比: {self.leaf_num/self.spine_num:.1f}:1")
        print(f"   输出目录: {self.output_dir}")
        print()
    
    def _validate_params(self):
        """验证参数合法性"""
        if self.host_num <= 0 or self.leaf_num <= 0 or self.spine_num <= 0:
            raise ValueError("主机数、Leaf数、Spine数必须大于0")
        
        if self.host_num % self.leaf_num != 0:
            raise ValueError(f"主机数({self.host_num})必须能被Leaf数({self.leaf_num})整除")
        
        hosts_per_leaf = self.host_num // self.leaf_num
        print(f"参数验证通过: 每个Leaf将连接 {hosts_per_leaf} 台主机")
    
    def generate_topology(self, connection_mode="sequential"):
        """
        生成拓扑
        
        参数:
            connection_mode: 连接模式
                - "interleaved": 交错模式 (默认)
                - "sequential": 顺序模式
        """
        print(f"开始生成拓扑 (连接模式: {connection_mode})...")
        
        # Step 1: 添加节点
        print(f"   添加 {self.host_num} 个主机节点...")
        for host_id in range(self.host_num):
            self.graph.add_netisim_host(host_id)
        
        print(f"   添加 {self.leaf_num} 个Leaf交换机...")
        for leaf_sw_id in range(self.leaf_num):
            self.graph.add_netisim_node(
                leaf_sw_id + self.host_num, 
                comp_delay=self.comp_delay, 
                node_subtype='leaf'
            )
        
        print(f"   添加 {self.spine_num} 个Spine交换机...")
        for spine_sw_id in range(self.spine_num):
            self.graph.add_netisim_node(
                spine_sw_id + self.host_num + self.leaf_num, 
                comp_delay=self.comp_delay, 
                node_subtype='spine'
            )
        
        # Step 2: Spine-Leaf 全连接
        print(f"   连接 Spine-Leaf (全连接)...")
        for spine_sw_id in range(self.spine_num):
            for leaf_sw_id in range(self.leaf_num):
                self.graph.add_netisim_edge(
                    spine_sw_id + self.host_num + self.leaf_num,
                    leaf_sw_id + self.host_num, 
                    bandwidth=str(self.leaf_spine_bw), 
                    delay=str(self.leaf_spine_delay)
                )
        
        # Step 3: Host-Leaf 连接
        print(f"   连接 Host-Leaf ({connection_mode}模式)...")
        if connection_mode == "interleaved":
            self._connect_interleaved()
        elif connection_mode == "sequential":
            self._connect_sequential()
        else:
            raise ValueError(f"未知的连接模式: {connection_mode}")
        
        print("拓扑生成完成\n")
    
    def _connect_interleaved(self):
        """交错连接模式 (与 gen_config_clos.py 一致)"""
        hosts_per_leaf = self.host_num // self.leaf_num
        for leaf_sw_id in range(self.leaf_num):
            base = (leaf_sw_id // 2) * (hosts_per_leaf * 2)
            start = base + (leaf_sw_id % 2)
            for i in range(hosts_per_leaf):
                host_id = start + i * 2
                if host_id < self.host_num:
                    self.graph.add_netisim_edge(
                        leaf_sw_id + self.host_num, 
                        host_id,
                        bandwidth=str(self.host_bw), 
                        delay=str(self.host_delay)
                    )
    
    def _connect_sequential(self):
        """顺序连接模式"""
        hosts_per_leaf = self.host_num // self.leaf_num
        for leaf_sw_id in range(self.leaf_num):
            start = leaf_sw_id * hosts_per_leaf
            for i in range(hosts_per_leaf):
                host_id = start + i
                if host_id < self.host_num:
                    self.graph.add_netisim_edge(
                        leaf_sw_id + self.host_num, 
                        host_id,
                        bandwidth=str(self.host_bw), 
                        delay=str(self.host_delay)
                    )
    
    def generate_config(self, template_xml="dcn2.0_config_rdma_template.xml", 
                       output_name="dcn2.0_config.xml"):
        """生成配置文件"""
        print(f"生成配置文件...")
        
        # 检查模板文件
        if not os.path.exists(template_xml):
            print(f"警告: 模板文件 {template_xml} 不存在，尝试使用绝对路径...")
            script_dir = os.path.dirname(os.path.abspath(__file__))
            template_xml = os.path.join(script_dir, template_xml)
            if not os.path.exists(template_xml):
                raise FileNotFoundError(f"找不到模板文件: {template_xml}")
        
        self.graph.build_graph_config(
            template_xml=template_xml,
            output_name=output_name,
            rdma_log_num=self.rdma_log_num
        )
        
        self.config_file = self.output_dir + "/" + output_name
        print(f"配置文件已生成: {self.config_file}\n")
        return self.config_file
    
    def generate_routing(self, algorithm="shortest"):
        """
        生成路由表
        
        参数:
            algorithm: 路由算法
                - "shortest": 最短路径 (默认)
                - "custom": 自定义算法
        """
        print(f"生成路由表 (算法: {algorithm})...")
        
        if algorithm == "shortest":
            import networkx as nx
            self.graph.gen_route_table(
                path_finding_algo=nx.all_shortest_paths,
                write_file=True
            )
        else:
            # 预留自定义算法接口
            raise NotImplementedError(f"算法 {algorithm} 尚未实现")
        
        self.router_file = self.output_dir + "/router_mine.xml"
        print(f"路由表已生成: {self.router_file}\n")
        return self.router_file
    
    def generate_traffic(self, pattern="all_to_all", **kwargs):
        """
        生成流量模式 (预留接口)
        
        参数:
            pattern: 流量模式
                - "all_to_all": 全对全通信
                - "random": 随机通信
                - "incast": 多对一通信
                - "custom": 自定义流量
            **kwargs: 其他参数
        """
        print(f"生成流量模式 (模式: {pattern})...")
        print("量生成功能待实现")
        # TODO: 实现流量生成逻辑
        return None
    
    def summary(self):
        """打印生成摘要"""
        print("=" * 70)
        print("拓扑生成摘要")
        print("=" * 70)
        print(f"网络规模:")
        print(f"  - 主机数:         {self.host_num}")
        print(f"  - Leaf交换机:     {self.leaf_num}")
        print(f"  - Spine交换机:    {self.spine_num}")
        print(f"  - 总节点数:       {self.host_num + self.leaf_num + self.spine_num}")
        print()
        print(f"网络参数:")
        print(f"  - 每Leaf主机数:   {self.host_num // self.leaf_num}")
        print(f"  - 超额订阅比:     {self.leaf_num/self.spine_num:.1f}:1")
        print(f"  - Host带宽:       {self.host_bw} Gbps")
        print(f"  - Leaf-Spine带宽: {self.leaf_spine_bw} Gbps")
        print()
        print(f"生成文件:")
        if hasattr(self, 'config_file'):
            print(f"  - 配置文件:       {self.config_file}")
        if hasattr(self, 'router_file'):
            print(f"  - 路由表:         {self.router_file}")
        print()
        print(f"输出目录: {self.output_dir}")
        print("=" * 70)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='自动化生成 Clos 拓扑配置和路由表',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # 网络规模参数
    parser.add_argument('--hosts', type=int, default=128,
                       help='主机数量')
    parser.add_argument('--leafs', type=int, default=16,
                       help='Leaf交换机数量')
    parser.add_argument('--spines', type=int, default=8,
                       help='Spine交换机数量')
    
    # 带宽和延迟参数
    parser.add_argument('--host-bw', type=int, default=200,
                       help='主机到Leaf带宽 (Gbps)')
    parser.add_argument('--leaf-spine-bw', type=int, default=400,
                       help='Leaf到Spine带宽 (Gbps)')
    parser.add_argument('--host-delay', type=int, default=5,
                       help='主机到Leaf延迟 (ns)')
    parser.add_argument('--leaf-spine-delay', type=int, default=10,
                       help='Leaf到Spine延迟 (ns)')
    parser.add_argument('--comp-delay', type=int, default=1600,
                       help='交换机计算延迟 (ns)')
    
    # 连接模式
    parser.add_argument('--connection-mode', 
                       choices=['interleaved', 'sequential'],
                       default='sequential',
                       help='主机到Leaf的连接模式')
    
    # 路由算法
    parser.add_argument('--routing-algo',
                       choices=['shortest'],
                       default='shortest',
                       help='路由算法')
    
    # 输出选项
    parser.add_argument('--output-dir', type=str, default=None,
                       help='输出目录 (默认: ./auto_output/时间戳)')
    parser.add_argument('--template', type=str,
                       default='dcn2.0_config_rdma_template.xml',
                       help='配置模板文件')
    
    # 功能开关
    parser.add_argument('--no-routing', action='store_true',
                       help='不生成路由表')
    parser.add_argument('--traffic-pattern', type=str, default=None,
                       help='流量模式 (待实现)')
    
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()
    
    print()
    print("=" * 70)
    print("  Clos 拓扑自动化生成工具")
    print("=" * 70)
    print()
    
    try:
        # 创建生成器
        generator = ClosTopoGenerator(
            host_num=args.hosts,
            leaf_num=args.leafs,
            spine_num=args.spines,
            host_bw=args.host_bw,
            leaf_spine_bw=args.leaf_spine_bw,
            host_delay=args.host_delay,
            leaf_spine_delay=args.leaf_spine_delay,
            comp_delay=args.comp_delay,
            output_dir=args.output_dir
        )
        
        # 生成拓扑
        generator.generate_topology(connection_mode=args.connection_mode)
        
        # 生成配置文件
        generator.generate_config(template_xml=args.template)
        
        # 生成路由表
        if not args.no_routing:
            generator.generate_routing(algorithm=args.routing_algo)
        
        # 生成流量 (可选)
        if args.traffic_pattern:
            generator.generate_traffic(pattern=args.traffic_pattern)
        
        # 打印摘要
        generator.summary()
        
        print("全部完成！\n")
        return 0
        
    except Exception as e:
        print(f"\n错误: {e}\n", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())

