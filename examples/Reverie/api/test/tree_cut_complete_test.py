#!/usr/bin/env python3
# 完整的拓扑切分API测试

import requests
import json
import os
import time
from pathlib import Path

# API基础URL
BASE_URL = "http://localhost:8002"

def test_health_check():
    """测试健康检查接口"""
    print("=== 测试健康检查接口 ===")
    try:
        response = requests.get(f"{BASE_URL}/health")
        print(f"状态码: {response.status_code}")
        print(f"响应: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"健康检查失败: {e}")
        return False

def test_get_example_tree():
    """测试获取示例通信树"""
    print("\n=== 测试获取示例通信树 ===")
    try:
        response = requests.get(f"{BASE_URL}/example-tree")
        print(f"状态码: {response.status_code}")
        data = response.json()
        print(f"示例树节点数: {len(data['tree_data']['nodes'])}")
        print(f"示例树边数: {len(data['tree_data']['edges'])}")
        print("示例树结构:")
        print(json.dumps(data['tree_data'], indent=2, ensure_ascii=False))
        return response.status_code == 200
    except Exception as e:
        print(f"获取示例树失败: {e}")
        return False

def test_tree_cut_with_example():
    """使用示例数据测试拓扑切分"""
    print("\n=== 测试拓扑切分（使用示例数据） ===")
    try:
        # 先获取示例数据
        example_response = requests.get(f"{BASE_URL}/example-tree")
        if example_response.status_code != 200:
            print("获取示例数据失败")
            return False
        
        example_data = example_response.json()["tree_data"]
        
        # 构建请求数据
        request_data = {
            "tree_data": {
                "nodes": example_data["nodes"],
                "edges": example_data["edges"]
            },
            "output_dir": "test_output",
            "show_graphs": False
        }
        
        print("发送的请求数据:")
        print(json.dumps(request_data, indent=2, ensure_ascii=False))
        
        # 发送切分请求
        response = requests.post(f"{BASE_URL}/tree-cut", json=request_data)
        print(f"\n响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 切分成功!")
            print(f"消息: {result['message']}")
            print(f"树组数量: {result['tree_groups']}")
            print(f"输出目录: {result['output_directory']}")
            print(f"生成文件: {len(result['result_files'])}个")
            
            # 检查JSON概览信息
            if 'json_overview' in result:
                overview = result['json_overview']
                print(f"\nJSON概览信息:")
                print(f"总组数: {overview['total_groups']}")
                print(f"输出目录: {overview['output_directory']}")
                print("各组信息:")
                for group in overview['groups']:
                    print(f"  组 {group['group_id']}: {group['filename']} "
                          f"(节点: {group['node_count']}, 边: {group['edge_count']})")
            
            # 检查输出文件是否存在
            if os.path.exists(result['output_directory']):
                print(f"\n输出目录已创建: {result['output_directory']}")
                
                # 检查JSON文件
                overview_file = os.path.join(result['output_directory'], "tree_group_overview.json")
                if os.path.exists(overview_file):
                    print(f"✅ 概览文件存在: {overview_file}")
                    with open(overview_file, 'r', encoding='utf-8') as f:
                        overview_data = json.load(f)
                        print("概览文件内容:")
                        print(json.dumps(overview_data, indent=2, ensure_ascii=False))
                
                # 检查各个Tree文件
                for group in result.get('json_overview', {}).get('groups', []):
                    if os.path.exists(group['filepath']):
                        print(f"✅ Tree文件存在: {group['filepath']}")
                        with open(group['filepath'], 'r', encoding='utf-8') as f:
                            tree_data = json.load(f)
                            print(f"Tree {group['group_id']} 内容:")
                            print(json.dumps(tree_data, indent=2, ensure_ascii=False))
                    else:
                        print(f"❌ Tree文件不存在: {group['filepath']}")
            else:
                print("❌ 输出目录未创建")
            
            return True
        else:
            print(f"❌ 切分失败: {response.text}")
            return False
            
    except Exception as e:
        print(f"测试拓扑切分失败: {e}")
        return False

def test_tree_cut_with_custom_data():
    """使用自定义数据测试拓扑切分"""
    print("\n=== 测试拓扑切分（使用自定义数据） ===")
    try:
        # 构建更复杂的通信树
        custom_tree = {
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
                },
                {
                    "name": "PP1_1",
                    "type": "PP",
                    "layer": 1,
                    "nodes_passed": ["D", "E"],
                    "children": [],
                    "isBurr": False
                },
                {
                    "name": "TP2_2",
                    "type": "TP",
                    "layer": 2,
                    "nodes_passed": ["F", "G", "H"],
                    "children": [],
                    "isBurr": False
                }
            ],
            "edges": [
                {"from_node": "Root", "to_node": "DP1_0"},
                {"from_node": "Root", "to_node": "PP1_1"},
                {"from_node": "PP1_1", "to_node": "TP2_2"}
            ]
        }
        
        request_data = {
            "tree_data": custom_tree,
            "output_dir": "custom_test_output",
            "show_graphs": False
        }
        
        print("发送的自定义数据:")
        print(json.dumps(request_data, indent=2, ensure_ascii=False))
        
        response = requests.post(f"{BASE_URL}/tree-cut", json=request_data)
        print(f"\n响应状态码: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 切分成功!")
            print(f"消息: {result['message']}")
            print(f"树组数量: {result['tree_groups']}")
            print(f"输出目录: {result['output_directory']}")
            
            # 检查JSON概览信息
            if 'json_overview' in result:
                overview = result['json_overview']
                print(f"\nJSON概览信息:")
                print(f"总组数: {overview['total_groups']}")
                print("各组信息:")
                for group in overview['groups']:
                    print(f"  组 {group['group_id']}: {group['filename']} "
                          f"(节点: {group['node_count']}, 边: {group['edge_count']})")
            
            return True
        else:
            print(f"❌ 切分失败: {response.text}")
            return False
            
    except Exception as e:
        print(f"测试自定义拓扑切分失败: {e}")
        return False

def test_invalid_data():
    """测试无效数据"""
    print("\n=== 测试无效数据 ===")
    try:
        # 测试空节点
        empty_nodes_data = {
            "tree_data": {
                "nodes": [],
                "edges": []
            },
            "output_dir": "invalid_test"
        }
        
        response = requests.post(f"{BASE_URL}/tree-cut", json=empty_nodes_data)
        print(f"空节点测试 - 状态码: {response.status_code}")
        if response.status_code == 400:
            print("✅ 正确捕获了空节点错误")
        else:
            print("❌ 未正确捕获空节点错误")
            print(f"响应: {response.text}")
        
        # 测试空边
        empty_edges_data = {
            "tree_data": {
                "nodes": [{"name": "Root", "type": "Root", "layer": 0, "nodes_passed": [], "children": [], "isBurr": False}],
                "edges": []
            },
            "output_dir": "invalid_test"
        }
        
        response = requests.post(f"{BASE_URL}/tree-cut", json=empty_edges_data)
        print(f"空边测试 - 状态码: {response.status_code}")
        if response.status_code == 400:
            print("✅ 正确捕获了空边错误")
        else:
            print("❌ 未正确捕获空边错误")
            print(f"响应: {response.text}")
        
        return True
        
    except Exception as e:
        print(f"测试无效数据失败: {e}")
        return False

def test_json_file_validation():
    """测试JSON文件格式验证"""
    print("\n=== 测试JSON文件格式验证 ===")
    try:
        # 测试示例数据切分
        example_response = requests.get(f"{BASE_URL}/example-tree")
        if example_response.status_code != 200:
            print("获取示例数据失败")
            return False
        
        example_data = example_response.json()["tree_data"]
        
        request_data = {
            "tree_data": example_data,
            "output_dir": "json_validation_test",
            "show_graphs": False
        }
        
        response = requests.post(f"{BASE_URL}/tree-cut", json=request_data)
        if response.status_code != 200:
            print(f"切分失败: {response.text}")
            return False
        
        result = response.json()
        output_dir = result['output_directory']
        
        # 验证概览文件
        overview_file = os.path.join(output_dir, "tree_group_overview.json")
        if os.path.exists(overview_file):
            with open(overview_file, 'r', encoding='utf-8') as f:
                overview_data = json.load(f)
                print("✅ 概览文件格式正确")
                print(f"概览文件内容: {json.dumps(overview_data, indent=2, ensure_ascii=False)}")
        
        # 验证各个Tree文件
        for group in result.get('json_overview', {}).get('groups', []):
            if os.path.exists(group['filepath']):
                with open(group['filepath'], 'r', encoding='utf-8') as f:
                    tree_data = json.load(f)
                    print(f"✅ Tree {group['group_id']} 文件格式正确")
                    print(f"Tree {group['group_id']} 内容: {json.dumps(tree_data, indent=2, ensure_ascii=False)}")
        
        return True
        
    except Exception as e:
        print(f"JSON文件验证失败: {e}")
        return False

def cleanup_test_files():
    """清理测试文件"""
    print("\n=== 清理测试文件 ===")
    test_dirs = ["test_output", "custom_test_output", "invalid_test", "json_validation_test"]
    
    for test_dir in test_dirs:
        if os.path.exists(test_dir):
            import shutil
            shutil.rmtree(test_dir)
            print(f"已删除目录: {test_dir}")

def main():
    """主测试函数"""
    print("开始完整测试拓扑切分API...")
    
    # 等待API服务启动
    print("等待API服务启动...")
    time.sleep(2)
    
    # 执行测试
    tests = [
        ("健康检查", test_health_check),
        ("获取示例树", test_get_example_tree),
        ("拓扑切分（示例数据）", test_tree_cut_with_example),
        ("拓扑切分（自定义数据）", test_tree_cut_with_custom_data),
        ("无效数据测试", test_invalid_data),
        ("JSON文件格式验证", test_json_file_validation)
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
        print("⚠️  部分测试失败，请检查API服务状态")

if __name__ == "__main__":
    main()
