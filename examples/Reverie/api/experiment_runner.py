#!/usr/bin/env python3
"""
自动化实验运行器
比较四种配置组合：
1. 关闭切分 + 关闭混合粒度
2. 开启切分 + 关闭混合粒度
3. 关闭切分 + 开启混合粒度
4. 开启切分 + 开启混合粒度
"""

import requests
import json
import time
import os
from pathlib import Path
from datetime import datetime

API_BASE_URL = "http://localhost:8000"

class ExperimentRunner:
    def __init__(self):
        self.results = []
        self.experiment_dir = Path(__file__).parent.parent / "experiment_results"
        self.experiment_dir.mkdir(exist_ok=True)
        
    def print_header(self, text):
        print("\n" + "="*80)
        print(f"  {text}")
        print("="*80)
        
    def print_step(self, step_num, total_steps, text):
        print(f"\n[步骤 {step_num}/{total_steps}] {text}")
        
    def wait_with_progress(self, seconds, message="等待中"):
        """带进度的等待"""
        print(f"{message}...", end="", flush=True)
        for i in range(seconds):
            time.sleep(1)
            print(".", end="", flush=True)
        print(" 完成!")
        
    def generate_topology(self, tor_switches=8, spine_switches=4):
        """生成拓扑"""
        self.print_step(1, 6, f"生成拓扑 ({tor_switches} TOR, {spine_switches} Spine)")
        
        response = requests.post(
            f"{API_BASE_URL}/generate-topology",
            json={
                "torSwitches": tor_switches,
                "spineSwitches": spine_switches
            }
        )
        result = response.json()
        
        if result.get("success"):
            print(f"✓ 拓扑生成成功: {result.get('num_hosts', 0)} 个主机")
            return result.get('num_hosts', 64)
        else:
            print(f"✗ 拓扑生成失败")
            return 64
            
    def generate_load(self, host_num=64, msg_len="32*(1024*1024)", dp=8):
        """生成负载"""
        self.print_step(2, 6, f"生成负载 (消息大小: {msg_len})")
        
        response = requests.post(
            f"{API_BASE_URL}/generate-load",
            json={
                "host_num": host_num,
                "msg_len": msg_len,
                "dp": dp,
                "device": 0,
                "forward": 1
            }
        )
        result = response.json()
        
        if result.get("success"):
            print(f"✓ 负载生成成功")
            return True
        else:
            print(f"✗ 负载生成失败")
            return False
            
    def run_simulation(self, config_name, enable_cut=False, enable_mixed_granularity=False, 
                      simulation_time=20.0):
        """运行仿真"""
        self.print_step(3, 6, f"运行仿真: {config_name}")
        print(f"  配置:")
        print(f"    - 切分: {'✓ 开启' if enable_cut else '✗ 关闭'}")
        print(f"    - 混合粒度: {'✓ 开启' if enable_mixed_granularity else '✗ 关闭'}")
        print(f"    - 仿真时间: {simulation_time}s")
        
        # 启动稳态监控
        requests.post(f"{API_BASE_URL}/start-steady-state-monitor")
        
        # 运行仿真
        response = requests.post(
            f"{API_BASE_URL}/run-simulation",
            json={
                "task_num": 4 if enable_cut else 1,
                "llm_model": "qwen",
                "enable_mixed_granularity": enable_mixed_granularity,
                "simulation_time": simulation_time
            }
        )
        result = response.json()
        
        if not result.get("success"):
            print(f"✗ 仿真启动失败")
            return False
            
        print(f"✓ 仿真已启动 (ID: {result.get('simulation_id', 'N/A')})")
        
        # 等待仿真完成（增加缓冲时间）
        wait_time = int(simulation_time + 30)
        self.wait_with_progress(wait_time, f"仿真运行中 ({wait_time}秒)")
        
        # 停止稳态监控
        requests.post(f"{API_BASE_URL}/stop-steady-state-monitor")
        
        return True
        
    def collect_steady_state_info(self):
        """收集稳态信息"""
        self.print_step(4, 6, "收集稳态信息")
        
        response = requests.get(f"{API_BASE_URL}/steady-state-monitor")
        result = response.json()
        
        steady_info = {
            "is_steady": result.get("is_steady", False),
            "steady_state_count": result.get("steady_state_count", 0),
            "transition_count": result.get("transition_count", 0),
            "details": result.get("details", [])
        }
        
        print(f"  稳态状态: {'✓ 已进入稳态' if steady_info['is_steady'] else '✗ 未进入稳态'}")
        print(f"  稳态次数: {steady_info['steady_state_count']}")
        print(f"  跃迁次数: {steady_info['transition_count']}")
        
        return steady_info
        
    def analyze_results(self):
        """分析结果"""
        self.print_step(5, 6, "分析结果")
        
        response = requests.post(
            f"{API_BASE_URL}/analyze-results",
            json={"analysis_type": "all"}
        )
        result = response.json()
        
        if result.get("success"):
            print(f"✓ 分析完成")
            return result.get("results", {})
        else:
            print(f"✗ 分析失败")
            return {}
            
    def save_results(self, config_name, results):
        """保存结果"""
        self.print_step(6, 6, "保存结果")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{config_name}_{timestamp}.json"
        filepath = self.experiment_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
            
        print(f"✓ 结果已保存: {filepath}")
        
        # 同时保存到results列表用于最终对比
        self.results.append({
            "config": config_name,
            "timestamp": timestamp,
            "data": results
        })
        
    def run_experiment(self, config_name, enable_cut, enable_mixed_granularity, 
                      msg_len="32*(1024*1024)", simulation_time=20.0):
        """运行单个实验"""
        self.print_header(f"实验配置: {config_name}")
        
        print(f"\n配置详情:")
        print(f"  - 切分: {'开启' if enable_cut else '关闭'}")
        print(f"  - 混合粒度: {'开启' if enable_mixed_granularity else '关闭'}")
        print(f"  - 消息大小: {msg_len}")
        print(f"  - 仿真时间: {simulation_time}s")
        
        try:
            # 1. 生成拓扑
            host_num = self.generate_topology()
            
            # 2. 生成负载
            if not self.generate_load(host_num, msg_len):
                return False
                
            # 3. 运行仿真
            if not self.run_simulation(config_name, enable_cut, 
                                      enable_mixed_granularity, simulation_time):
                return False
                
            # 4. 收集稳态信息
            steady_info = self.collect_steady_state_info()
            
            # 5. 分析结果
            analysis = self.analyze_results()
            
            # 6. 保存结果
            results = {
                "config": {
                    "name": config_name,
                    "enable_cut": enable_cut,
                    "enable_mixed_granularity": enable_mixed_granularity,
                    "msg_len": msg_len,
                    "simulation_time": simulation_time
                },
                "steady_state": steady_info,
                "analysis": analysis
            }
            
            self.save_results(config_name, results)
            
            print(f"\n✓ 实验 '{config_name}' 完成!")
            return True
            
        except Exception as e:
            print(f"\n✗ 实验失败: {e}")
            return False
            
    def run_all_experiments(self, msg_len="32*(1024*1024)", simulation_time=20.0):
        """运行所有四种配置的实验"""
        self.print_header("开始四配置对比实验")
        
        print(f"\n实验参数:")
        print(f"  - 消息大小: {msg_len} = {eval(msg_len)} 字节")
        print(f"  - 仿真时间: {simulation_time} 秒")
        print(f"  - 实验数量: 4")
        
        experiments = [
            {
                "name": "配置1_关闭切分_关闭混合粒度",
                "enable_cut": False,
                "enable_mixed_granularity": False
            },
            {
                "name": "配置2_开启切分_关闭混合粒度",
                "enable_cut": True,
                "enable_mixed_granularity": False
            },
            {
                "name": "配置3_关闭切分_开启混合粒度",
                "enable_cut": False,
                "enable_mixed_granularity": True
            },
            {
                "name": "配置4_开启切分_开启混合粒度",
                "enable_cut": True,
                "enable_mixed_granularity": True
            }
        ]
        
        success_count = 0
        
        for i, exp in enumerate(experiments, 1):
            print(f"\n\n{'='*80}")
            print(f"实验 {i}/4")
            print(f"{'='*80}")
            
            if self.run_experiment(
                exp["name"],
                exp["enable_cut"],
                exp["enable_mixed_granularity"],
                msg_len,
                simulation_time
            ):
                success_count += 1
                
            # 实验间隔
            if i < len(experiments):
                print(f"\n等待5秒后开始下一个实验...")
                time.sleep(5)
                
        # 生成对比报告
        self.generate_comparison_report()
        
        self.print_header(f"所有实验完成 ({success_count}/{len(experiments)} 成功)")
        
    def generate_comparison_report(self):
        """生成对比报告"""
        self.print_header("生成对比报告")
        
        if not self.results:
            print("没有实验结果可供对比")
            return
            
        report_lines = []
        report_lines.append("="*100)
        report_lines.append("四配置对比报告")
        report_lines.append("="*100)
        report_lines.append("")
        
        # 表格头
        report_lines.append(f"{'配置':<30} | {'切分':<6} | {'混合粒度':<8} | {'稳态次数':<8} | {'跃迁次数':<8} | {'平均FCT':<10}")
        report_lines.append("-"*100)
        
        # 每个配置的结果
        for result in self.results:
            config = result["data"]["config"]
            steady = result["data"]["steady_state"]
            analysis = result["data"]["analysis"]
            
            name = config["name"][:28]
            cut = "✓" if config["enable_cut"] else "✗"
            mixed = "✓" if config["enable_mixed_granularity"] else "✗"
            steady_count = steady.get("steady_state_count", 0)
            trans_count = steady.get("transition_count", 0)
            
            # 尝试从分析中获取平均FCT
            avg_fct = "N/A"
            if "fct" in analysis and "average" in str(analysis.get("fct", {})):
                try:
                    avg_fct = f"{analysis['fct'].get('average', 'N/A'):.2f}ms"
                except:
                    pass
                    
            report_lines.append(f"{name:<30} | {cut:<6} | {mixed:<8} | {steady_count:<8} | {trans_count:<8} | {avg_fct:<10}")
            
        report_lines.append("="*100)
        report_lines.append("")
        report_lines.append("详细分析:")
        report_lines.append("")
        
        for result in self.results:
            report_lines.append(f"\n### {result['data']['config']['name']}")
            report_lines.append(f"时间戳: {result['timestamp']}")
            
            # 稳态信息
            steady = result["data"]["steady_state"]
            report_lines.append(f"\n**稳态信息:**")
            report_lines.append(f"  - 是否进入稳态: {'是' if steady.get('is_steady') else '否'}")
            report_lines.append(f"  - 稳态次数: {steady.get('steady_state_count', 0)}")
            report_lines.append(f"  - 跃迁次数: {steady.get('transition_count', 0)}")
            
            # 分析结果
            analysis = result["data"]["analysis"]
            report_lines.append(f"\n**性能分析:**")
            report_lines.append(f"  {json.dumps(analysis, indent=4, ensure_ascii=False)}")
            report_lines.append("")
            
        report = "\n".join(report_lines)
        
        # 保存报告
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = self.experiment_dir / f"comparison_report_{timestamp}.txt"
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
            
        print(report)
        print(f"\n✓ 对比报告已保存: {report_file}")


def main():
    """主函数"""
    print("""
╔════════════════════════════════════════════════════════════════╗
║                    自动化实验运行器                              ║
║                    四配置对比实验                                ║
╚════════════════════════════════════════════════════════════════╝
    """)
    
    # 检查API连接
    try:
        response = requests.get(f"{API_BASE_URL}/")
        if response.status_code != 200:
            print("✗ 无法连接到API，请确保API服务运行在 http://localhost:8000")
            return
    except:
        print("✗ 无法连接到API，请确保API服务运行在 http://localhost:8000")
        return
        
    print("✓ API连接成功\n")
    
    # 获取用户输入
    print("请配置实验参数:")
    print("-" * 60)
    
    msg_len = input("消息大小表达式 [默认: 32*(1024*1024)]: ").strip() or "32*(1024*1024)"
    
    try:
        msg_bytes = eval(msg_len)
        msg_mb = msg_bytes / (1024 * 1024)
        print(f"  → 计算结果: {msg_bytes:,} 字节 ({msg_mb:.2f} MB)")
    except:
        print(f"  → 表达式无效，使用默认值: 32*(1024*1024)")
        msg_len = "32*(1024*1024)"
        
    sim_time_input = input("仿真时间(秒) [默认: 20]: ").strip()
    simulation_time = float(sim_time_input) if sim_time_input else 20.0
    
    print(f"\n开始实验...")
    print(f"  消息大小: {msg_len}")
    print(f"  仿真时间: {simulation_time}s")
    print(f"  配置数量: 4")
    
    confirm = input("\n确认开始? (y/n): ").strip().lower()
    if confirm != 'y':
        print("实验已取消")
        return
        
    # 运行实验
    runner = ExperimentRunner()
    runner.run_all_experiments(msg_len, simulation_time)


if __name__ == "__main__":
    main()





















