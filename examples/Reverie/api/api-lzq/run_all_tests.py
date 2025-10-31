#!/usr/bin/env python3
# 自动重启API服务并运行所有测试

import subprocess
import time
import os
import sys
import signal

API_PORT = 8002
BASE_URL = f"http://localhost:{API_PORT}"

def find_and_kill_process():
    """查找并终止占用端口的进程"""
    try:
        result = subprocess.run(
            f"lsof -ti:{API_PORT}",
            shell=True,
            capture_output=True,
            text=True
        )
        
        if result.stdout.strip():
            pid = result.stdout.strip()
            print(f"发现运行中的服务，PID: {pid}")
            os.kill(int(pid), signal.SIGKILL)
            print("已停止服务")
            time.sleep(2)
            return True
        else:
            print("没有运行中的服务")
            return False
    except Exception as e:
        print(f"检查进程时出错: {e}")
        return False

def start_api_server():
    """启动API服务"""
    print("\n启动API服务...")
    
    try:
        # 启动API服务（后台运行）
        with open("api_server.log", "w") as log_file:
            process = subprocess.Popen(
                ["python", "start_tree_cut_api.py"],
                stdout=log_file,
                stderr=log_file,
                cwd="/home/sakura/桌面/flow-input-zyh/examples/Reverie/api"
            )
        
        print(f"API服务已启动，PID: {process.pid}")
        
        # 等待服务启动
        print("等待服务启动...")
        for i in range(10):
            time.sleep(1)
            try:
                import requests
                response = requests.get(f"{BASE_URL}/health", timeout=2)
                if response.status_code == 200:
                    print(f"✅ API服务启动成功！")
                    return True
            except:
                print(f"等待中... ({i+1}/10)")
        
        print("❌ API服务启动超时")
        return False
        
    except Exception as e:
        print(f"启动API服务时出错: {e}")
        return False

def run_tests():
    """运行所有测试"""
    print("\n" + "="*60)
    print("运行完整测试...")
    print("="*60)
    
    # 运行完整测试
    result1 = subprocess.run(
        ["python", "test/tree_cut_complete_test.py"],
        cwd="/home/sakura/桌面/flow-input-zyh/examples/Reverie/api"
    )
    
    print("\n" + "="*60)
    print("运行扩展测试...")
    print("="*60)
    
    # 运行扩展测试
    result2 = subprocess.run(
        ["python", "test/tree_cut_extended_test.py"],
        cwd="/home/sakura/桌面/flow-input-zyh/examples/Reverie/api"
    )
    
    return result1.returncode == 0 and result2.returncode == 0

def main():
    print("="*60)
    print("拓扑切分API自动测试脚本")
    print("="*60)
    
    # 1. 停止现有服务
    print("\n1. 检查并停止现有API服务...")
    find_and_kill_process()
    
    # 2. 启动API服务
    print("\n2. 启动API服务...")
    if not start_api_server():
        print("❌ API服务启动失败，退出测试")
        sys.exit(1)
    
    # 3. 运行测试
    print("\n3. 运行测试...")
    success = run_tests()
    
    # 4. 输出结果
    print("\n" + "="*60)
    if success:
        print("🎉 所有测试完成！")
    else:
        print("⚠️  部分测试失败")
    print("="*60)
    
    print(f"\nAPI服务日志: {os.path.abspath('api_server.log')}")
    print(f"要停止API服务，运行: kill -9 $(lsof -ti:{API_PORT})")

if __name__ == "__main__":
    main()

