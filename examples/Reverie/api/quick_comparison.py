#!/usr/bin/env python3
"""
快速对比脚本
快速运行四种配置并生成简洁的对比表格
"""

import requests
import json
import time
from datetime import datetime
from pathlib import Path

API_URL = "http://localhost:8000"

# 配置列表
CONFIGS = [
    {"name": "基准配置", "cut": False, "mixed": False},
    {"name": "仅切分", "cut": True, "mixed": False},
    {"name": "仅混合粒度", "cut": False, "mixed": True},
    {"name": "完整优化", "cut": True, "mixed": True},
]

def run_single_test(config, msg_len="32*(1024*1024)", sim_time=15.0):
    """运行单个测试"""
    print(f"\n{'='*70}")
    print(f"运行: {config['name']}")
    print(f"  切分: {'✓' if config['cut'] else '✗'}  |  混合粒度: {'✓' if config['mixed'] else '✗'}")
    print(f"{'='*70}")
    
    # 1. 生成拓扑
    print("→ 生成拓扑...", end="", flush=True)
    r = requests.post(f"{API_URL}/generate-topology", json={"torSwitches": 8, "spineSwitches": 4})
    host_num = r.json().get("num_hosts", 64)
    print(f" ✓ ({host_num}主机)")
    
    # 2. 生成负载
    print(f"→ 生成负载 (msg_len={msg_len})...", end="", flush=True)
    r = requests.post(f"{API_URL}/generate-load", json={
        "host_num": host_num,
        "msg_len": msg_len,
        "dp": 8,
        "device": 0,
        "forward": 1
    })
    print(" ✓")
    
    # 3. 启动监控
    requests.post(f"{API_URL}/start-steady-state-monitor")
    
    # 4. 运行仿真
    print(f"→ 运行仿真 ({sim_time}秒)...", end="", flush=True)
    r = requests.post(f"{API_URL}/run-simulation", json={
        "task_num": 4 if config['cut'] else 1,
        "llm_model": "qwen",
        "enable_mixed_granularity": config['mixed'],
        "simulation_time": sim_time
    })
    
    # 等待完成
    for i in range(int(sim_time + 10)):
        time.sleep(1)
        print(".", end="", flush=True)
    print(" ✓")
    
    # 5. 获取稳态信息
    print("→ 收集稳态信息...", end="", flush=True)
    r = requests.get(f"{API_URL}/steady-state-monitor")
    steady = r.json()
    print(" ✓")
    
    # 6. 分析结果
    print("→ 分析结果...", end="", flush=True)
    r = requests.post(f"{API_URL}/analyze-results", json={"analysis_type": "all"})
    analysis = r.json().get("results", {}) if r.json().get("success") else {}
    print(" ✓")
    
    # 停止监控
    requests.post(f"{API_URL}/stop-steady-state-monitor")
    
    return {
        "config": config,
        "steady_count": steady.get("steady_state_count", 0),
        "transition_count": steady.get("transition_count", 0),
        "is_steady": steady.get("is_steady", False),
        "analysis": analysis
    }

def print_comparison_table(results):
    """打印对比表格"""
    print("\n\n")
    print("╔" + "="*98 + "╗")
    print("║" + " "*35 + "四配置对比结果" + " "*49 + "║")
    print("╠" + "="*98 + "╣")
    
    # 表头
    header = f"║ {'配置':<14} │ {'切分':<4} │ {'混合粒度':<8} │ {'稳态次数':<8} │ {'跃迁次数':<8} │ {'是否稳态':<8} │ {'性能评估':<16} ║"
    print(header)
    print("╠" + "-"*98 + "╣")
    
    # 数据行
    for result in results:
        cfg = result['config']
        name = cfg['name'][:12]
        cut = "✓" if cfg['cut'] else "✗"
        mixed = "✓" if cfg['mixed'] else "✗"
        steady_cnt = result['steady_count']
        trans_cnt = result['transition_count']
        is_steady = "是" if result['is_steady'] else "否"
        
        # 性能评估（简化）
        perf = "数据不足"
        analysis = result.get('analysis', {})
        if analysis:
            perf = "已收集"
            
        row = f"║ {name:<14} │ {cut:<4} │ {mixed:<8} │ {steady_cnt:<8} │ {trans_cnt:<8} │ {is_steady:<8} │ {perf:<16} ║"
        print(row)
        
    print("╚" + "="*98 + "╝")
    
    # 详细分析
    print("\n详细分析:")
    print("-" * 100)
    
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['config']['name']}")
        print(f"   稳态: {result['steady_count']}次 | 跃迁: {result['transition_count']}次 | 状态: {'已稳定' if result['is_steady'] else '未稳定'}")
        
        analysis = result.get('analysis', {})
        if analysis:
            print(f"   分析: {json.dumps(analysis, ensure_ascii=False)[:100]}...")

def main():
    print("""
╔════════════════════════════════════════════════════════════════╗
║                    快速四配置对比实验                            ║
╚════════════════════════════════════════════════════════════════╝
""")
    
    # 检查API
    try:
        r = requests.get(f"{API_URL}/")
        print("✓ API 已连接\n")
    except:
        print("✗ 无法连接到 API (http://localhost:8000)")
        print("  请先启动 API: python3 complete_api.py")
        return
        
    # 参数设置
    msg_len = input("消息大小 [默认: 32*(1024*1024) = 32MB]: ").strip() or "32*(1024*1024)"
    sim_time = float(input("仿真时间(秒) [默认: 15]: ").strip() or "15")
    
    print(f"\n实验配置:")
    print(f"  消息大小: {msg_len} = {eval(msg_len):,} 字节")
    print(f"  仿真时间: {sim_time} 秒")
    print(f"  配置数量: {len(CONFIGS)}")
    
    confirm = input("\n开始实验? (y/n): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        return
        
    # 运行所有配置
    results = []
    start_time = datetime.now()
    
    for i, config in enumerate(CONFIGS, 1):
        print(f"\n\n进度: [{i}/{len(CONFIGS)}]")
        try:
            result = run_single_test(config, msg_len, sim_time)
            results.append(result)
            print(f"✓ {config['name']} 完成")
        except Exception as e:
            print(f"✗ {config['name']} 失败: {e}")
            results.append({
                "config": config,
                "steady_count": 0,
                "transition_count": 0,
                "is_steady": False,
                "analysis": {"error": str(e)}
            })
            
        # 配置间隔
        if i < len(CONFIGS):
            time.sleep(3)
            
    # 显示结果
    print_comparison_table(results)
    
    # 保存结果
    output_dir = Path(__file__).parent.parent / "experiment_results"
    output_dir.mkdir(exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"quick_comparison_{timestamp}.json"
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "timestamp": timestamp,
            "msg_len": msg_len,
            "sim_time": sim_time,
            "results": results
        }, f, indent=2, ensure_ascii=False)
        
    elapsed = (datetime.now() - start_time).total_seconds()
    
    print(f"\n✓ 实验完成!")
    print(f"  总耗时: {elapsed:.1f} 秒")
    print(f"  结果已保存: {output_file}")

if __name__ == "__main__":
    main()
































