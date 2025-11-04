#!/usr/bin/env python3
"""
改进的稳态监测测试脚本
测试新的日志解析和稳态监测功能
"""

import requests
import time
import json
from pathlib import Path

API_BASE_URL = "http://localhost:8000"

def print_section(title):
    """打印分节标题"""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

def test_file_status():
    """测试文件状态检测"""
    print_section("1. 检查关键文件状态")
    
    files_to_check = [
        Path(__file__).parent.parent / "dump" / "evaluation.out",
        Path(__file__).parent.parent.parent / "flow_stats.txt",  # 上两级目录
        Path(__file__).parent / "logs"
    ]
    
    for file_path in files_to_check:
        if file_path.is_dir():
            print(f"\n📁 目录: {file_path}")
            print(f"   存在: {file_path.exists()}")
            if file_path.exists():
                log_files = list(file_path.glob("*.log"))
                print(f"   日志文件数: {len(log_files)}")
                if log_files:
                    latest = max(log_files, key=lambda p: p.stat().st_mtime)
                    print(f"   最新日志: {latest.name}")
        else:
            print(f"\n📄 文件: {file_path}")
            print(f"   存在: {file_path.exists()}")
            if file_path.exists():
                size = file_path.stat().st_size
                print(f"   大小: {size:,} bytes")
                print(f"   修改时间: {time.ctime(file_path.stat().st_mtime)}")

def test_start_monitor():
    """测试启动稳态监控"""
    print_section("2. 启动稳态监控")
    
    try:
        response = requests.post(f"{API_BASE_URL}/start-steady-state-monitor", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 监控启动成功")
            print(f"   响应: {json.dumps(data, indent=2, ensure_ascii=False)}")
            return True
        else:
            print(f"❌ 启动失败: {response.status_code}")
            print(f"   响应: {response.text}")
            return False
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

def test_monitor_status(iterations=5, interval=2):
    """测试监控状态"""
    print_section(f"3. 监控状态检测 (查询{iterations}次,间隔{interval}秒)")
    
    for i in range(iterations):
        try:
            response = requests.get(f"{API_BASE_URL}/steady-state-monitor", timeout=5)
            if response.status_code == 200:
                data = response.json()
                print(f"\n⏱️  查询 #{i+1}:")
                print(f"   监控状态: {'✅ 运行中' if data.get('is_monitoring') else '❌ 未运行'}")
                print(f"   稳态状态: {'🟢 稳态' if data.get('is_steady') else '🔴 非稳态'}")
                print(f"   稳态计数: {data.get('steady_state_count', 0)}")
                print(f"   跃迁计数: {data.get('transition_count', 0)}")
                print(f"   消息: {data.get('message', 'N/A')}")
                
                # 显示文件信息
                file_info = data.get('file_info', {})
                if file_info:
                    print(f"   文件状态:")
                    print(f"     evaluation.out: {'✅' if file_info.get('evaluation_out_exists') else '❌'}")
                    print(f"     flow_stats.txt: {'✅' if file_info.get('flow_stats_exists') else '❌'}")
                
                # 显示历史记录
                history = data.get('history', [])
                if history:
                    print(f"   历史记录: {len(history)} 条")
                    for h in history[-3:]:  # 显示最近3条
                        status = h.get('status', 'unknown')
                        enter_time = h.get('enter_time_ns', 0) / 1e9  # 转换为秒
                        trans_count = h.get('transition_count', 0)
                        print(f"     - 第{h.get('count')}次 | {status} | 时间:{enter_time:.6f}s | 跃迁:{trans_count}")
            else:
                print(f"❌ 查询失败 #{i+1}: {response.status_code}")
                
        except Exception as e:
            print(f"❌ 请求失败 #{i+1}: {e}")
        
        if i < iterations - 1:
            time.sleep(interval)

def test_read_log_files():
    """测试读取日志文件内容"""
    print_section("4. 读取日志文件内容(最后10行)")
    
    files = [
        ("evaluation.out", Path(__file__).parent.parent / "dump" / "evaluation.out"),
        ("flow_stats.txt", Path(__file__).parent.parent.parent / "flow_stats.txt")  # 上两级目录
    ]
    
    for name, file_path in files:
        print(f"\n📖 {name}:")
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                    print(f"   总行数: {len(lines)}")
                    print(f"   最后10行:")
                    for line in lines[-10:]:
                        print(f"      {line.rstrip()}")
            except Exception as e:
                print(f"   ❌ 读取失败: {e}")
        else:
            print(f"   ❌ 文件不存在")

def test_stop_monitor():
    """测试停止稳态监控"""
    print_section("5. 停止稳态监控")
    
    try:
        response = requests.post(f"{API_BASE_URL}/stop-steady-state-monitor", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ 监控停止成功")
            print(f"   响应: {json.dumps(data, indent=2, ensure_ascii=False)}")
            return True
        else:
            print(f"❌ 停止失败: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

def main():
    """主测试流程"""
    print("\n🚀 开始测试改进的稳态监测功能")
    print(f"   API 地址: {API_BASE_URL}")
    print(f"   时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 测试1: 检查文件状态
    test_file_status()
    
    # 测试2: 启动监控
    if not test_start_monitor():
        print("\n⚠️  无法启动监控,后续测试可能失败")
    
    # 等待一下
    time.sleep(1)
    
    # 测试3: 监控状态
    test_monitor_status(iterations=5, interval=2)
    
    # 测试4: 读取日志文件
    test_read_log_files()
    
    # 测试5: 停止监控
    test_stop_monitor()
    
    print_section("测试完成")
    print("\n💡 提示:")
    print("   1. 如果监测不到稳态,请检查:")
    print("      - evaluation.out 或 flow_stats.txt 是否存在")
    print("      - 文件中是否包含稳态标记")
    print("      - 仿真是否正在运行")
    print("   2. 查看 logs/ 目录下的日志文件获取详细调试信息")
    print("   3. API 会优先读取 evaluation.out,备选 flow_stats.txt")
    print()

if __name__ == "__main__":
    main()

