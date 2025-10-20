#!/usr/bin/env python3
# 测试使用JSON文件URL的拓扑切分接口

import requests
import json
import time
import subprocess
import os
import signal

BASE_URL = "http://localhost:8002"
FILE_SERVER_PORT = 8888

def start_file_server():
    """启动简单的HTTP文件服务器"""
    print("启动文件服务器（端口8888）...")
    
    # 在test目录启动HTTP服务器
    process = subprocess.Popen(
        ["python", "-m", "http.server", str(FILE_SERVER_PORT)],
        cwd="/home/sakura/桌面/flow-input-zyh/examples/Reverie/api/test",
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # 等待服务器启动
    time.sleep(2)
    
    print(f"✅ 文件服务器已启动，PID: {process.pid}")
    print(f"文件URL: http://localhost:{FILE_SERVER_PORT}/sample_tree_data.json")
    
    return process

def stop_file_server(process):
    """停止文件服务器"""
    print("\n停止文件服务器...")
    process.terminate()
    process.wait()
    print("✅ 文件服务器已停止")

def test_tree_cut_with_url():
    """测试使用URL的拓扑切分"""
    print("\n=== 测试1: 使用JSON文件URL ===")
    
    file_url = f"http://localhost:{FILE_SERVER_PORT}/sample_tree_data.json"
    
    # 先验证文件URL可访问
    try:
        response = requests.get(file_url)
        if response.status_code == 200:
            print(f"✅ JSON文件可访问: {file_url}")
            print("文件内容预览:")
            print(json.dumps(response.json(), indent=2, ensure_ascii=False)[:500] + "...")
        else:
            print(f"❌ JSON文件不可访问")
            return False
    except Exception as e:
        print(f"❌ 无法访问JSON文件: {e}")
        return False
    
    # 发送拓扑切分请求
    request_data = {
        "tree_data_url": file_url,
        "output_dir": "url_test_output",
        "show_graphs": False
    }
    
    print("\n发送拓扑切分请求（使用URL）...")
    print(f"请求数据: {json.dumps(request_data, indent=2, ensure_ascii=False)}")
    
    try:
        response = requests.post(f"{BASE_URL}/tree-cut", json=request_data)
        print(f"\n响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 切分成功!")
            print(f"消息: {result['message']}")
            print(f"树组数量: {result['tree_groups']}")
            print(f"输出目录: {result['output_directory']}")
            
            # 检查JSON概览
            if 'json_overview' in result:
                print(f"\nJSON概览:")
                print(f"总组数: {result['json_overview']['total_groups']}")
                for g in result['json_overview']['groups']:
                    print(f"  - 组{g['group_id']}: {g['filename']} "
                          f"({g['node_count']}节点, {g['edge_count']}边)")
            
            return True
        else:
            print(f"❌ 切分失败: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

def test_tree_cut_with_direct_data():
    """测试直接使用tree_data（对比测试）"""
    print("\n=== 测试2: 使用直接数据（对比） ===")
    
    request_data = {
        "tree_data": {
            "nodes": [
                {"name": "Root", "type": "Root", "layer": 0, "nodes_passed": [], "children": [], "isBurr": False},
                {"name": "DP1_0", "type": "DP", "layer": 1, "nodes_passed": ["A", "B"], "children": [], "isBurr": False}
            ],
            "edges": [
                {"from_node": "Root", "to_node": "DP1_0"}
            ]
        },
        "output_dir": "direct_test_output",
        "show_graphs": False
    }
    
    try:
        response = requests.post(f"{BASE_URL}/tree-cut", json=request_data)
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 直接数据切分成功!")
            print(f"树组数量: {result['tree_groups']}")
            return True
        else:
            print(f"❌ 切分失败: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

def test_both_provided_error():
    """测试同时提供tree_data和tree_data_url的错误处理"""
    print("\n=== 测试3: 同时提供两种输入（应该报错）===")
    
    request_data = {
        "tree_data": {
            "nodes": [{"name": "Root", "type": "Root", "layer": 0, "nodes_passed": [], "children": [], "isBurr": False}],
            "edges": []
        },
        "tree_data_url": "http://localhost:8888/sample_tree_data.json",
        "output_dir": "error_test"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/tree-cut", json=request_data)
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code == 400:
            print("✅ 正确返回400错误")
            print(f"错误信息: {response.json()['detail']}")
            return True
        else:
            print(f"❌ 应该返回400错误")
            return False
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

def test_neither_provided_error():
    """测试两种输入都不提供的错误处理"""
    print("\n=== 测试4: 都不提供（应该报错）===")
    
    request_data = {
        "output_dir": "error_test"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/tree-cut", json=request_data)
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code == 400:
            print("✅ 正确返回400错误")
            print(f"错误信息: {response.json()['detail']}")
            return True
        else:
            print(f"❌ 应该返回400错误")
            return False
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

def test_invalid_url():
    """测试无效URL的错误处理"""
    print("\n=== 测试5: 无效URL（应该报错）===")
    
    request_data = {
        "tree_data_url": "http://invalid-url-12345.com/data.json",
        "output_dir": "error_test"
    }
    
    try:
        response = requests.post(f"{BASE_URL}/tree-cut", json=request_data)
        print(f"响应状态码: {response.status_code}")
        
        if response.status_code == 400:
            print("✅ 正确返回400错误")
            print(f"错误信息: {response.json()['detail']}")
            return True
        else:
            print(f"❌ 应该返回400错误")
            return False
            
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False

def cleanup_test_files():
    """清理测试文件"""
    print("\n=== 清理测试文件 ===")
    import shutil
    
    test_dirs = ["url_test_output", "direct_test_output", "error_test"]
    
    for test_dir in test_dirs:
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
            print(f"已删除目录: {test_dir}")

def main():
    """主测试函数"""
    print("="*60)
    print("测试拓扑切分API - JSON文件URL功能")
    print("="*60)
    
    # 启动文件服务器
    file_server = start_file_server()
    
    try:
        # 等待服务器完全启动
        time.sleep(2)
        
        # 执行测试
        tests = [
            ("使用JSON文件URL", test_tree_cut_with_url),
            ("使用直接数据（对比）", test_tree_cut_with_direct_data),
            ("同时提供两种输入", test_both_provided_error),
            ("都不提供输入", test_neither_provided_error),
            ("无效URL", test_invalid_url)
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n{'='*60}")
            print(f"执行测试: {test_name}")
            print('='*60)
            
            try:
                if test_func():
                    print(f"✅ {test_name} 通过")
                    passed += 1
                else:
                    print(f"❌ {test_name} 失败")
            except Exception as e:
                print(f"❌ {test_name} 异常: {e}")
        
        # 清理测试文件
        cleanup_test_files()
        
        # 输出测试结果
        print(f"\n{'='*60}")
        print(f"测试完成: {passed}/{total} 通过")
        print('='*60)
        
        if passed == total:
            print("🎉 所有测试通过！")
        else:
            print(f"⚠️  {total - passed}个测试失败")
    
    finally:
        # 停止文件服务器
        stop_file_server(file_server)

if __name__ == "__main__":
    main()
