#!/usr/bin/env python3
"""
完整的拓扑生成、流量生成、路径分析自动化脚本
将 TopoGenerator -> TrafficGenerator -> TreeCut 整合为一键执行
"""

import os
import sys
import argparse
import time
import shutil
import subprocess
import copy
import logging
from pathlib import Path


class WorkflowAutomation:
    """工作流自动化管理器"""
    
    def __init__(self, config):
        """
        初始化自动化管理器
        
        参数:
            config: 配置字典，包含所有必要参数
        """
        self.config = config
        
        # 设置基础目录
        self.base_dir = Path(__file__).parent
        self.topo_dir = self.base_dir / "TopoGenerator" / "clos"
        self.traffic_dir = self.base_dir / "TrafficGenerator"
        self.treecut_dir = self.base_dir / "TreeCut"
        
        # 创建统一输出目录
        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
        self.output_root = self.base_dir / "workflow_output" / timestamp
        self.output_root.mkdir(parents=True, exist_ok=True)
        
        # 子目录
        self.topo_output = self.output_root / "1_topology"
        self.traffic_output = self.output_root / "2_traffic"
        self.paths_output = self.output_root / "3_paths"
        self.treecut_output = self.output_root / "4_treecut"
        
        # 设置日志
        self._setup_logging()
        
        self.logger.info(f"📂 统一输出目录: {self.output_root}")
        print(f"📂 统一输出目录: {self.output_root}")
        print()
    
    def _setup_logging(self):
        """设置日志系统"""
        # 创建日志文件
        log_file = self.output_root / "workflow.log"
        
        # 创建logger
        self.logger = logging.getLogger('WorkflowAutomation')
        self.logger.setLevel(logging.DEBUG)
        
        # 清除已有的handlers
        self.logger.handlers.clear()
        
        # 创建文件handler（详细日志）
        file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        
        # 创建控制台handler（简化输出，仅INFO及以上）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(message)s')
        console_handler.setFormatter(console_formatter)
        
        # 添加handlers
        self.logger.addHandler(file_handler)
        # 注意：不添加console_handler，因为我们用print输出到控制台
        
        self.logger.info("=" * 70)
        self.logger.info("工作流自动化日志")
        self.logger.info("=" * 70)
        self.logger.info(f"日志文件: {log_file}")
        self.logger.info(f"开始时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        self.logger.info("")
        self.logger.info("配置参数:")
        for key, value in self.config.items():
            self.logger.info(f"  {key}: {value}")
        self.logger.info("")
    
    def _log_and_print(self, message, level='info'):
        """同时记录日志和打印到控制台"""
        print(message)
        if level == 'info':
            self.logger.info(message)
        elif level == 'warning':
            self.logger.warning(message)
        elif level == 'error':
            self.logger.error(message)
        elif level == 'debug':
            self.logger.debug(message)
    
    def step1_generate_topology(self):
        """步骤1: 生成网络拓扑"""
        sep = "=" * 70
        self._log_and_print(sep)
        self._log_and_print("步骤 1/4: 生成网络拓扑")
        self._log_and_print(sep)
        
        self.logger.info(f"创建拓扑输出目录: {self.topo_output}")
        self.topo_output.mkdir(parents=True, exist_ok=True)
        
        # 调用 auto_gen_topo.py
        cmd = [
            sys.executable,
            str(self.topo_dir / "auto_gen_topo.py"),
            "--hosts", str(self.config['host_num']),
            "--leafs", str(self.config['leaf_num']),
            "--spines", str(self.config['spine_num']),
            "--host-bw", str(self.config.get('host_bw', 200)),
            "--leaf-spine-bw", str(self.config.get('leaf_spine_bw', 400)),
            "--output-dir", str(self.topo_output)
        ]
        
        cmd_str = ' '.join(cmd)
        self._log_and_print(f"执行命令: {cmd_str}")
        
        # 执行命令并捕获输出
        result = subprocess.run(cmd, cwd=str(self.topo_dir), 
                               capture_output=True, text=True)
        
        # 记录子进程的输出到日志
        if result.stdout:
            self.logger.info("--- 拓扑生成输出 ---")
            for line in result.stdout.splitlines():
                self.logger.info(line)
        if result.stderr:
            self.logger.error("--- 拓扑生成错误 ---")
            for line in result.stderr.splitlines():
                self.logger.error(line)
        
        if result.returncode != 0:
            self.logger.error(f"拓扑生成失败，返回码: {result.returncode}")
            raise RuntimeError("拓扑生成失败")
        
        # 验证输出
        config_file = self.topo_output / "dcn2.0_config.xml"
        router_file = self.topo_output / "router_mine.xml"
        
        if not config_file.exists() or not router_file.exists():
            self.logger.error("拓扑文件生成不完整")
            raise RuntimeError("拓扑文件生成不完整")
        
        self._log_and_print(f"✅ 拓扑生成完成")
        self._log_and_print(f"   - 配置文件: {config_file}")
        self._log_and_print(f"   - 路由表: {router_file}")
        print()
        
        return config_file, router_file
    
    def step2_generate_traffic(self):
        """步骤2: 生成流量"""
        sep = "=" * 70
        self._log_and_print(sep)
        self._log_and_print("步骤 2/4: 生成流量模式")
        self._log_and_print(sep)
        
        self.traffic_output.mkdir(parents=True, exist_ok=True)
        
        # 准备输入文件
        input_file = self.config.get('traffic_input')
        if not input_file:
            # 使用默认的 qwen.txt 或 deepseek.txt
            model = self.config.get('model', 'qwen').lower()
            input_file = self.traffic_dir / f"{model}.txt"
        else:
            input_file = Path(input_file)
        
        if not input_file.exists():
            raise FileNotFoundError(f"流量输入文件不存在: {input_file}")
        
        # 修改输入文件中的参数（如果需要）
        temp_input = self.traffic_output / "traffic_input.txt"
        self._prepare_traffic_input(input_file, temp_input)
        
        # 切换到 traffic_dir 执行（因为脚本中有硬编码的相对路径）
        original_dir = os.getcwd()
        os.chdir(self.traffic_dir)
        
        try:
            # 创建临时链接到输出目录
            rdma_result_link = Path("rdma_result")
            if rdma_result_link.exists():
                if rdma_result_link.is_symlink():
                    rdma_result_link.unlink()
                else:
                    shutil.rmtree(rdma_result_link)
            
            # 运行流量生成
            cmd = [
                sys.executable,
                "trafficGen_add.py",
                "--input_file", str(temp_input)
            ]
            
            cmd_str = ' '.join(cmd)
            self._log_and_print(f"执行命令: {cmd_str}")
            
            # 捕获输出
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            # 记录输出到日志
            if result.stdout:
                self.logger.info("--- 流量生成输出 ---")
                for line in result.stdout.splitlines():
                    self.logger.info(line)
            if result.stderr:
                self.logger.error("--- 流量生成错误 ---")
                for line in result.stderr.splitlines():
                    self.logger.error(line)
            
            if result.returncode != 0:
                self.logger.error(f"流量生成失败，返回码: {result.returncode}")
                raise RuntimeError("流量生成失败")
            
            # 移动结果到输出目录
            if Path("rdma_result").exists():
                shutil.move("rdma_result", str(self.traffic_output / "rdma_result"))
            
        finally:
            os.chdir(original_dir)
        
        rdma_result_dir = self.traffic_output / "rdma_result"
        if not rdma_result_dir.exists():
            self.logger.error("流量文件生成失败")
            raise RuntimeError("流量文件生成失败")
        
        self._log_and_print(f"✅ 流量生成完成")
        self._log_and_print(f"   - 输出目录: {rdma_result_dir}")
        print()
        
        return rdma_result_dir
    
    def step3_generate_paths(self, rdma_result_dir):
        """步骤3: 生成ECMP路径"""
        sep = "=" * 70
        self._log_and_print(sep)
        self._log_and_print("步骤 3/4: 生成ECMP路径")
        self._log_and_print(sep)
        
        self.paths_output.mkdir(parents=True, exist_ok=True)
        
        # 复制配置文件到每个 rdma_result 子目录
        config_file = self.topo_output / "dcn2.0_config.xml"
        router_file = self.topo_output / "router_mine.xml"
        
        self.logger.info(f"复制配置文件到流量目录...")
        copied_count = 0
        for subdir in rdma_result_dir.iterdir():
            if subdir.is_dir():
                shutil.copy(config_file, subdir / "dcn2.0_config.xml")
                shutil.copy(router_file, subdir / "router_mine.xml")
                copied_count += 1
        self.logger.info(f"已复制到 {copied_count} 个子目录")
        
        # 修改 paths_port_gen.py 使用我们的路径
        original_dir = os.getcwd()
        os.chdir(self.treecut_dir)
        
        try:
            # 创建临时修改的脚本
            self._run_paths_generation(rdma_result_dir, self.paths_output)
            
        finally:
            os.chdir(original_dir)
        
        ecmp_outputs = self.paths_output / "ecmp_outputs"
        if not ecmp_outputs.exists() or len(list(ecmp_outputs.iterdir())) == 0:
            self.logger.error("路径生成失败")
            raise RuntimeError("路径生成失败")
        
        path_count = len(list(ecmp_outputs.glob("*.txt")))
        self._log_and_print(f"✅ ECMP路径生成完成")
        self._log_and_print(f"   - 输出目录: {ecmp_outputs}")
        self._log_and_print(f"   - 生成路径文件: {path_count} 个")
        print()
        
        return ecmp_outputs
    
    def step4_tree_cut(self, ecmp_outputs):
        """步骤4: 通信树分割"""
        sep = "=" * 70
        self._log_and_print(sep)
        self._log_and_print("步骤 4/4: 通信树分割")
        self._log_and_print(sep)
        
        if not self.config.get('enable_treecut', False):
            self._log_and_print("⚠️  通信树分割未启用，跳过此步骤", level='warning')
            self._log_and_print("   (使用 --enable-treecut 启用)")
            print()
            return None
        
        self.treecut_output.mkdir(parents=True, exist_ok=True)
        
        # 设置环境变量，让 TreeCut.py 使用正确的路径
        env = os.environ.copy()
        env['ECMP_OUTPUTS_DIR'] = str(ecmp_outputs)
        env['TREE_GROUP_DIR'] = str(self.treecut_output / 'TreeGroup')
        
        # 切换到 TreeCut 目录执行
        original_dir = os.getcwd()
        os.chdir(self.treecut_dir)
        
        try:
            # 导入并执行 TreeCut
            sys.path.insert(0, str(self.treecut_dir))
            
            # 动态导入 TreeCut 模块
            import importlib.util
            spec = importlib.util.spec_from_file_location("TreeCut", "TreeCut.py")
            treecut_module = importlib.util.module_from_spec(spec)
            
            # 设置环境变量
            os.environ['ECMP_OUTPUTS_DIR'] = env['ECMP_OUTPUTS_DIR']
            os.environ['TREE_GROUP_DIR'] = env['TREE_GROUP_DIR']
            
            spec.loader.exec_module(treecut_module)
            
            # 执行主流程
            self._log_and_print("   构建通信树...")
            T = treecut_module.nx.DiGraph()
            T.add_node(treecut_module.root_node, name='Root', nodes_passed=[], children=[])
            
            # 传递流量输入文件，使用动态构建
            traffic_input = self.traffic_output / "traffic_input.txt"
            self.logger.info(f"使用流量输入文件: {traffic_input}")
            treecut_module.constructTree(T, treecut_module.root_node, str(traffic_input))
            
            self._log_and_print("   预处理毛刺节点...")
            T = treecut_module.preTreatment(T)
            
            self._log_and_print("   深拷贝树结构...")
            treecut_module.Tree_copy = copy.deepcopy(T)
            
            self._log_and_print("   分割通信树...")
            treecut_module.splitCommunicationTree(T)
            
            self._log_and_print("   生成依赖信息...")
            treecut_module.makeInDependenceInfo(treecut_module.Tree_list)
            treecut_module.makeOutDependenceInfo(treecut_module.out_dependence_list, treecut_module.Tree_list)
            
            subtree_count = len(treecut_module.Tree_list)
            self._log_and_print(f"   分割完成: 共生成 {subtree_count} 个子树")
            
            tree_group_dir = Path(env['TREE_GROUP_DIR'])
            if tree_group_dir.exists():
                self._log_and_print(f"✅ TreeCut分割完成")
                self._log_and_print(f"   - 输出目录: {tree_group_dir}")
                self._log_and_print(f"   - 子树数量: {len(treecut_module.Tree_list)}")
                print()
            else:
                self.logger.error("TreeGroup目录未生成")
                raise RuntimeError("TreeGroup目录未生成")
            
        except FileNotFoundError as e:
            self._log_and_print(f"❌ 错误: 找不到必要的文件", level='error')
            self._log_and_print(f"   {e}", level='error')
            self._log_and_print(f"   请确保所有 ecmp_outputs 文件都已生成", level='error')
            print()
            return None
        except Exception as e:
            self._log_and_print(f"❌ TreeCut执行失败: {e}", level='error')
            import traceback
            error_trace = traceback.format_exc()
            self.logger.error(error_trace)
            traceback.print_exc()
            print()
            return None
        finally:
            os.chdir(original_dir)
        
        return tree_group_dir
    
    def _prepare_traffic_input(self, source_file, target_file):
        """准备流量输入文件，替换参数"""
        with open(source_file, 'r') as f:
            lines = f.readlines()
        
        # 修改第一行的参数
        first_line_parts = lines[0].strip().split()
        if len(first_line_parts) >= 3:
            model = first_line_parts[0]
            # 保持 devices 和 iterations 不变，或使用配置中的值
            devices = self.config.get('max_devices', first_line_parts[1])
            iterations = self.config.get('max_iterations', first_line_parts[2])
            lines[0] = f"{model} {devices} {iterations}\n"
        
        # 替换所有 --host_num 参数
        host_num = self.config['host_num']
        modified_lines = []
        for line in lines:
            if '--host_num' in line:
                # 简单替换（可能需要更复杂的逻辑）
                import re
                line = re.sub(r'--host_num\s+\d+', f'--host_num {host_num}', line)
            modified_lines.append(line)
        
        with open(target_file, 'w') as f:
            f.writelines(modified_lines)
    
    def _run_paths_generation(self, rdma_result_dir, output_dir):
        """运行路径生成，使用修改后的路径"""
        # 导入需要的模块
        sys.path.insert(0, str(self.treecut_dir))
        from ecmp_path import get_rdma_files, load_file, find_ecmp_path
        
        # 导入 tqdm
        from tqdm import tqdm
        
        ecmp_output = output_dir / "ecmp_outputs"
        ecmp_output.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"开始生成ECMP路径，输出到: {ecmp_output}")
        
        # 收集所有需要处理的目录
        dirs_to_process = [item for item in rdma_result_dir.iterdir() if item.is_dir()]
        
        # 遍历所有子目录，使用 tqdm 显示进度
        # 使用 file=sys.stdout 和 dynamic_ncols=True 确保进度条正确显示
        # 显式设置 disable=False 确保进度条显示
        # 使用 leave=True 保留进度条
        import contextlib
        import io
        
        with tqdm(dirs_to_process, desc="生成ECMP路径", unit="目录", file=sys.stdout, 
                  dynamic_ncols=True, disable=False, mininterval=0.1, leave=True) as pbar:
            for item in pbar:
                # 更新进度条描述
                pbar.set_postfix_str(f"处理: {item.name}")
                self.logger.info(f"处理目录: {item.name}")
                
                try:
                    file_path_list = get_rdma_files(str(item))
                    if not file_path_list:
                        msg = f"未找到RDMA文件，跳过"
                        self.logger.warning(f"  {item.name}: {msg}")
                        continue
                    
                    self.logger.debug(f"  加载 {len(file_path_list)} 个RDMA文件")
                    
                    # 临时重定向 print 输出，避免打断 tqdm 进度条
                    with io.StringIO() as buf, contextlib.redirect_stdout(buf):
                        Flow_Info_List, Link_Info_List, Route_Info_Table, Link_Map, Reverse_Link_Map, host_num, leaf_num, spine_num = load_file(
                            str(item), file_path_list
                        )
                    
                    self.logger.debug(f"  查找ECMP路径，流数量: {len(Flow_Info_List)}")
                    
                    _, Flow_Paths_Port = find_ecmp_path(
                        Flow_Info_List, Link_Info_List, Route_Info_Table, Link_Map, Reverse_Link_Map
                    )
                    
                    # 保存结果
                    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in item.name)
                    output_file = ecmp_output / f"{safe_name}.txt"
                    
                    path_count = 0
                    with open(output_file, 'w') as f:
                        for tup in Flow_Paths_Port:
                            if len(tup) > 1 and isinstance(tup[1], list):
                                for path_item in tup[1]:
                                    f.write(f"{path_item}\n")
                                    path_count += 1
                    
                    self.logger.info(f"  {item.name}: 保存 {path_count} 条路径到 {output_file.name}")
                    
                except Exception as e:
                    error_msg = f"错误: {e}"
                    self.logger.error(f"  {item.name}: {error_msg}")
    
    def run_all(self):
        """运行完整流程"""
        print("\n")
        print("╔" + "=" * 68 + "╗")
        print("║" + " " * 20 + "自动化工作流程" + " " * 33 + "║")
        print("╚" + "=" * 68 + "╝")
        print()
        
        self.logger.info("")
        self.logger.info("╔" + "=" * 68 + "╗")
        self.logger.info("║" + " " * 20 + "自动化工作流程" + " " * 33 + "║")
        self.logger.info("╚" + "=" * 68 + "╝")
        self.logger.info("")
        
        start_time = time.time()
        
        try:
            # 步骤1: 拓扑生成
            self.logger.info("开始步骤1: 拓扑生成")
            config_file, router_file = self.step1_generate_topology()
            
            # 步骤2: 流量生成
            self.logger.info("开始步骤2: 流量生成")
            rdma_result_dir = self.step2_generate_traffic()
            
            # 步骤3: 路径生成
            self.logger.info("开始步骤3: ECMP路径生成")
            ecmp_outputs = self.step3_generate_paths(rdma_result_dir)
            
            # 步骤4: 树分割（可选）
            self.logger.info("开始步骤4: 通信树分割")
            self.step4_tree_cut(ecmp_outputs)
            
            elapsed = time.time() - start_time
            
            sep = "=" * 70
            self._log_and_print(sep)
            self._log_and_print(f"✅ 全部完成！总耗时: {elapsed:.2f} 秒")
            self._log_and_print(f"📂 输出目录: {self.output_root}")
            self._log_and_print(sep)
            print()
            
            # 生成摘要
            self._generate_summary()
            
            self.logger.info(f"工作流完成，总耗时: {elapsed:.2f} 秒")
            self.logger.info(f"日志已保存到: {self.output_root}/workflow.log")
            
            return 0
            
        except Exception as e:
            error_msg = f"\n❌ 错误: {e}\n"
            print(error_msg)
            self.logger.error(error_msg)
            
            import traceback
            error_trace = traceback.format_exc()
            self.logger.error("完整错误堆栈:")
            self.logger.error(error_trace)
            traceback.print_exc()
            
            return 1
    
    def _generate_summary(self):
        """生成执行摘要"""
        summary_file = self.output_root / "SUMMARY.txt"
        
        with open(summary_file, 'w') as f:
            f.write("=" * 70 + "\n")
            f.write("工作流执行摘要\n")
            f.write("=" * 70 + "\n\n")
            
            f.write("配置参数:\n")
            for key, value in self.config.items():
                f.write(f"  {key}: {value}\n")
            f.write("\n")
            
            f.write("生成的文件:\n")
            f.write(f"  1. 拓扑配置: {self.topo_output}/dcn2.0_config.xml\n")
            f.write(f"  2. 路由表: {self.topo_output}/router_mine.xml\n")
            f.write(f"  3. 流量文件: {self.traffic_output}/rdma_result/\n")
            f.write(f"  4. ECMP路径: {self.paths_output}/ecmp_outputs/\n")
            
            if self.config.get('enable_treecut'):
                treecut_result = self.treecut_output / 'TreeGroup'
                if treecut_result.exists():
                    f.write(f"  5. 通信树分割: {treecut_result}/\n")
            f.write("\n")
            
            f.write(f"执行时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("\n")
            f.write("日志文件:\n")
            f.write(f"  详细日志: workflow.log\n")
        
        self._log_and_print(f"📄 摘要已保存: {summary_file}")
        self._log_and_print(f"📋 详细日志: {self.output_root}/workflow.log")


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='自动化执行拓扑生成、流量生成、路径分析完整流程',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    # 网络拓扑参数
    parser.add_argument('--hosts', type=int, default=128,
                       help='主机数量')
    parser.add_argument('--leafs', type=int, default=16,
                       help='Leaf交换机数量')
    parser.add_argument('--spines', type=int, default=8,
                       help='Spine交换机数量')
    
    # 带宽参数
    parser.add_argument('--host-bw', type=int, default=200,
                       help='主机到Leaf带宽 (Gbps)')
    parser.add_argument('--leaf-spine-bw', type=int, default=400,
                       help='Leaf到Spine带宽 (Gbps)')
    
    # 流量生成参数
    parser.add_argument('--model', type=str, default='qwen',
                       choices=['qwen', 'deepseek'],
                       help='大模型类型')
    parser.add_argument('--traffic-input', type=str, default=None,
                       help='自定义流量输入文件路径')
    parser.add_argument('--max-devices', type=int, default=2,
                       help='最大设备数')
    parser.add_argument('--max-iterations', type=int, default=2,
                       help='迭代次数')
    
    # 功能开关
    parser.add_argument('--enable-treecut', action='store_true',default=True,
                       help='启用通信树分割（TreeCut）')
    
    # 步骤控制
    parser.add_argument('--skip-topo', action='store_true',
                       help='跳过拓扑生成（使用已有拓扑）')
    parser.add_argument('--skip-traffic', action='store_true',
                       help='跳过流量生成（使用已有流量）')
    
    return parser.parse_args()


def main():
    """主函数"""
    args = parse_args()
    
    # 构建配置字典
    config = {
        'host_num': args.hosts,
        'leaf_num': args.leafs,
        'spine_num': args.spines,
        'host_bw': args.host_bw,
        'leaf_spine_bw': args.leaf_spine_bw,
        'model': args.model,
        'traffic_input': args.traffic_input,
        'max_devices': args.max_devices,
        'max_iterations': args.max_iterations,
        'enable_treecut': args.enable_treecut,
    }
    
    # 创建并运行工作流
    workflow = WorkflowAutomation(config)
    return workflow.run_all()


if __name__ == '__main__':
    sys.exit(main())

