#!/usr/bin/env python3
# 测试完整六功能API的所有接口

import requests
import json
import time
import os
from pathlib import Path

# API基础URL
BASE_URL = "http://localhost:8001"

def test_tree_cut():
    """测试拓扑切分接口"""
    print("\n" + "="*60)
    print("测试拓扑切分接口 /tree-cut")
    print("="*60)
    
    url = f"{BASE_URL}/tree-cut"
    data = {
        "tree_data": {
            "nodes": [
                {
                    "name": "Root",
                    "type": "Root",
                    "layer": 0,
                    "nodes_passed": [],
                    "children": [],
                    "isBurr": False
                },
                {
                    "name": "DP1_0",
                    "type": "DP",
                    "layer": 1,
                    "nodes_passed": ["A", "B", "C"],
                    "children": [],
                    "isBurr": False
                }
            ],
            "edges": [
                {
                    "from_node": "Root",
                    "to_node": "DP1_0"
                }
            ]
        },
        "output_dir": "test_complete_tree_cut",
        "show_graphs": False
    }
    
    try:
        print("正在发送请求...")
        response = requests.post(url, json=data)
        print(f"响应状态码: {response.status_code}")
        print("响应内容:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        return response.json().get("success", False)
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_generate_load():
    """测试负载生成接口"""
    print("\n" + "="*60)
    print("测试负载生成接口 /generate-load")
    print("="*60)
    
    url = f"{BASE_URL}/generate-load"
    data = {
        "host_num": 64,
        "msg_len": "32*(1024)",
        "dp": 8,
        "device": 0,
        "forward": 1
    }
    
    try:
        print("正在发送请求...")
        response = requests.post(url, json=data)
        print(f"响应状态码: {response.status_code}")
        print("响应内容:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        return response.json().get("success", False)
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_generate_topology():
    """测试拓扑生成接口"""
    print("\n" + "="*60)
    print("测试拓扑生成接口 /generate-topology")
    print("="*60)
    
    url = f"{BASE_URL}/generate-topology"
    data = {
        "torSwitches": 8,
        "spineSwitches": 4
    }
    
    try:
        print("正在发送请求...")
        response = requests.post(url, json=data)
        print(f"响应状态码: {response.status_code}")
        print("响应内容:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        return response.json().get("success", False)
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_modify_load_file():
    """测试负载文件修改接口"""
    print("\n" + "="*60)
    print("测试负载文件修改接口 /modify-load-file")
    print("="*60)
    
    url = f"{BASE_URL}/modify-load-file"
    data = {
        "filename": "deepseek.txt",
        "old_value": "128",
        "new_value": "64"
    }
    
    try:
        print("正在发送请求...")
        response = requests.post(url, json=data)
        print(f"响应状态码: {response.status_code}")
        print("响应内容:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        return response.json().get("success", False)
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_run_simulation_no_cut_no_granularity():
    """测试仿真：不开启切分 + 不开启流粒度"""
    print("\n" + "="*60)
    print("【按钮测试1】仿真运行：不开启切分 + 不开启流粒度")
    print("="*60)
    
    url = f"{BASE_URL}/run-simulation"
    data = {
        "task_num": 1,                      # 按钮1: 不开启切分
        "enable_mixed_granularity": False,  # 按钮2: 不开启流粒度
        "llm_model": "deepseek",
        "simulation_time": 5.0
    }
    
    try:
        print("正在发送请求...")
        print(f"  - 切分开关: 关闭 (task_num=1)")
        print(f"  - 流粒度开关: 关闭 (enable_mixed_granularity=False)")
        response = requests.post(url, json=data)
        print(f"响应状态码: {response.status_code}")
        print("响应内容:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        
        if response.json().get("success", False):
            print("仿真已启动（不开启切分 + 不开启流粒度）")
            return True
        return False
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_run_simulation_with_cut_no_granularity():
    """测试仿真：开启切分 + 不开启流粒度"""
    print("\n" + "="*60)
    print("【按钮测试2】仿真运行：开启切分 + 不开启流粒度")
    print("="*60)
    
    url = f"{BASE_URL}/run-simulation"
    data = {
        "task_num": 4,                      # 按钮1: 开启切分
        "enable_mixed_granularity": False,  # 按钮2: 不开启流粒度
        "llm_model": "deepseek",
        "simulation_time": 5.0
    }
    
    try:
        print("正在发送请求...")
        print(f"  - 切分开关: 开启 (task_num=4)")
        print(f"  - 流粒度开关: 关闭 (enable_mixed_granularity=False)")
        response = requests.post(url, json=data)
        print(f"响应状态码: {response.status_code}")
        print("响应内容:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        
        if response.json().get("success", False):
            print("仿真已启动（开启切分 + 不开启流粒度）")
            return True
        return False
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_run_simulation_no_cut_with_granularity():
    """测试仿真：不开启切分 + 开启流粒度"""
    print("\n" + "="*60)
    print("【按钮测试3】仿真运行：不开启切分 + 开启流粒度")
    print("="*60)
    
    url = f"{BASE_URL}/run-simulation"
    data = {
        "task_num": 1,                     # 按钮1: 不开启切分
        "enable_mixed_granularity": True,  # 按钮2: 开启流粒度
        "llm_model": "deepseek",
        "simulation_time": 5.0
    }
    
    try:
        print("正在发送请求...")
        print(f"  - 切分开关: 关闭 (task_num=1)")
        print(f"  - 流粒度开关: 开启 (enable_mixed_granularity=True)")
        response = requests.post(url, json=data)
        print(f"响应状态码: {response.status_code}")
        print("响应内容:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        
        if response.json().get("success", False):
            print("仿真已启动（不开启切分 + 开启流粒度）")
            return True
        return False
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_run_simulation_full_features():
    """测试仿真：开启切分 + 开启流粒度"""
    print("\n" + "="*60)
    print("【按钮测试4】仿真运行：开启切分 + 开启流粒度")
    print("="*60)
    
    url = f"{BASE_URL}/run-simulation"
    data = {
        "task_num": 4,                     # 按钮1: 开启切分
        "enable_mixed_granularity": True,  # 按钮2: 开启流粒度
        "llm_model": "deepseek",
        "simulation_time": 5.0
    }
    
    try:
        print("正在发送请求...")
        print(f"  - 切分开关: 开启 (task_num=4)")
        print(f"  - 流粒度开关: 开启 (enable_mixed_granularity=True)")
        response = requests.post(url, json=data)
        print(f"响应状态码: {response.status_code}")
        print("响应内容:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        
        if response.json().get("success", False):
            simulation_id = response.json().get("simulation_id")
            print(f"仿真已启动，ID: {simulation_id}")
            
            # 监控仿真状态
            print("监控仿真状态...")
            for i in range(10):  # 监控10次
                time.sleep(2)
                status_response = requests.get(f"{BASE_URL}/simulation-status")
                status = status_response.json()
                print(f"状态检查 {i+1}: 运行中={status['is_running']}, 稳态={status['steady_state']}")
                
                if not status['is_running']:
                    print("仿真已完成")
                    break
            
            return True
        return False
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_simulation_control_demo():
    """演示三个按钮的完整控制流程"""
    print("\n" + "="*80)
    print("【核心功能演示】三个按钮的完整控制流程")
    print("="*80)
    print("\n你的需求：")
    print("  1. 按钮1：控制是否开启切分 (TASKNUM=1 或 4)")
    print("  2. 按钮2：控制是否开启流粒度 (ENABLE_JUMP_TRANSITION)")
    print("  3. 按钮3：执行仿真 (运行整个仿真程序)")
    print("\n当前API实现：")
    print("  接口: POST /run-simulation")
    print("  参数: task_num, enable_mixed_granularity")
    print("  功能: 一个接口控制所有三个按钮！")
    print("="*80)
    
    # 测试四种组合
    results = []
    
    print("\n测试场景1: 两个开关都关闭")
    results.append(("关闭切分+关闭流粒度", test_run_simulation_no_cut_no_granularity()))
    
    time.sleep(1)
    print("\n测试场景2: 只开启切分")
    results.append(("开启切分+关闭流粒度", test_run_simulation_with_cut_no_granularity()))
    
    time.sleep(1)
    print("\n测试场景3: 只开启流粒度")
    results.append(("关闭切分+开启流粒度", test_run_simulation_no_cut_with_granularity()))
    
    time.sleep(1)
    print("\n测试场景4: 两个开关都开启（完整加速）")
    results.append(("开启切分+开启流粒度", test_run_simulation_full_features()))
    
    print("\n" + "="*80)
    print("三个按钮控制测试结果汇总:")
    print("="*80)
    for scenario, result in results:
        status = "成功" if result else "失败"
        print(f"  {scenario:25} : {status}")
    print("="*80)
    
    return all(r for _, r in results)

def test_simulation_status():
    """测试仿真状态接口"""
    print("\n" + "="*60)
    print("测试仿真状态接口 /simulation-status")
    print("="*60)
    
    url = f"{BASE_URL}/simulation-status"
    
    try:
        print("正在发送请求...")
        response = requests.get(url)
        print(f"响应状态码: {response.status_code}")
        print("响应内容:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        return True
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_steady_state_monitor():
    """测试稳态监控接口"""
    print("\n" + "="*60)
    print("测试稳态监控接口 /steady-state-monitor")
    print("="*60)
    
    url = f"{BASE_URL}/steady-state-monitor"
    
    try:
        print("正在发送请求...")
        response = requests.get(url)
        print(f"响应状态码: {response.status_code}")
        print("响应内容:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        return True
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_analyze_results():
    """测试结果分析接口"""
    print("\n" + "="*60)
    print("测试结果分析接口 /analyze-results")
    print("="*60)
    
    url = f"{BASE_URL}/analyze-results"
    data = {
        "analysis_type": "all"
    }
    
    try:
        print("正在发送请求...")
        response = requests.post(url, json=data)
        print(f"响应状态码: {response.status_code}")
        print("响应内容:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        return response.json().get("success", False)
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_health():
    """测试健康检查接口"""
    print("\n" + "="*60)
    print("测试健康检查接口 /health")
    print("="*60)
    
    url = f"{BASE_URL}/health"
    
    try:
        print("正在发送请求...")
        response = requests.get(url)
        print(f"响应状态码: {response.status_code}")
        print("响应内容:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        return True
    except Exception as e:
        print(f"错误: {e}")
        return False

def test_root():
    """测试根路径接口"""
    print("\n" + "="*60)
    print("测试根路径接口 /")
    print("="*60)
    
    url = f"{BASE_URL}/"
    
    try:
        print("正在发送请求...")
        response = requests.get(url)
        print(f"响应状态码: {response.status_code}")
        print("响应内容:")
        print(json.dumps(response.json(), indent=2, ensure_ascii=False))
        return True
    except Exception as e:
        print(f"错误: {e}")
        return False

def run_complete_test():
    """运行完整测试"""
    print("\n" + "="*80)
    print("完整六功能API测试 - 包含三个核心按钮控制")
    print("="*80)
    
    test_results = {}
    
    # 第一部分：基础接口测试
    print("\n【第一部分】基础接口测试")
    print("-"*80)
    test_results["root"] = test_root()
    test_results["health"] = test_health()
    
    # 第二部分：辅助功能测试
    print("\n【第二部分】辅助功能测试")
    print("-"*80)
    test_results["tree_cut"] = test_tree_cut()
    test_results["generate_load"] = test_generate_load()
    test_results["generate_topology"] = test_generate_topology()
    test_results["modify_load_file"] = test_modify_load_file()
    
    # 第三部分：核心按钮控制测试（你的主要需求）
    print("\n【第三部分】核心按钮控制测试 - 你的主要需求！")
    print("-"*80)
    test_results["simulation_control"] = test_simulation_control_demo()
    
    # 第四部分：监控和分析功能测试
    print("\n【第四部分】监控和分析功能测试")
    print("-"*80)
    test_results["simulation_status"] = test_simulation_status()
    test_results["steady_state_monitor"] = test_steady_state_monitor()
    test_results["analyze_results"] = test_analyze_results()
    
    # 输出测试结果
    print("\n" + "="*80)
    print("测试结果汇总:")
    print("="*80)
    
    success_count = 0
    total_count = len(test_results)
    
    for test_name, result in test_results.items():
        status = "成功" if result else "失败"
        print(f"{test_name:25} : {status}")
        if result:
            success_count += 1
    
    print("="*80)
    print(f"总计: {success_count}/{total_count} 个测试通过")
    print(f"成功率: {success_count/total_count*100:.1f}%")
    print("="*80)
    
    print("\n" + "="*80)
    print("核心功能确认：")
    print("="*80)
    print("按钮1（切分控制）：通过 task_num 参数实现")
    print("按钮2（流粒度控制）：通过 enable_mixed_granularity 参数实现")
    print("按钮3（执行仿真）：通过 POST /run-simulation 接口实现")
    print("="*80)
    
    return test_results

if __name__ == "__main__":
    run_complete_test()
