#!/usr/bin/env python3
"""
测试修复后的ECMP算法
验证：
1. ECMP hash函数是否正确
2. 不同流的hash值是否不同
3. 路径计算是否正确
"""

import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ecmp_path import (
    FlowInfo, 
    node_id_to_ip, 
    ecmp_hash, 
    compute_ecmp_hash_for_flow,
    parse_rdma_operate
)

def test_node_id_to_ip():
    """测试节点ID到IP地址的转换"""
    print("=" * 60)
    print("测试1: 节点ID到IP地址转换")
    print("=" * 60)
    
    test_cases = [
        (0, 0x0b000001),
        (1, 0x0b000101),
        (14, 0x0b000e01),
        (64, 0x0b004001),
        (65, 0x0b004101),
    ]
    
    all_passed = True
    for node_id, expected_ip in test_cases:
        actual_ip = node_id_to_ip(node_id)
        passed = actual_ip == expected_ip
        status = "✓" if passed else "✗"
        print(f"{status} 节点 {node_id:3d} -> IP 0x{actual_ip:08x} (期望: 0x{expected_ip:08x})")
        if not passed:
            all_passed = False
    
    print(f"\n结果: {'全部通过' if all_passed else '部分失败'}\n")
    return all_passed


def test_ecmp_hash_consistency():
    """测试ECMP hash的一致性"""
    print("=" * 60)
    print("测试2: ECMP Hash一致性")
    print("=" * 60)
    
    # 测试相同的输入应该产生相同的hash
    key_bytes = bytearray([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0c])
    seed = 65
    
    hash1 = ecmp_hash(key_bytes, seed)
    hash2 = ecmp_hash(key_bytes, seed)
    
    passed = hash1 == hash2
    status = "✓" if passed else "✗"
    print(f"{status} 相同输入产生相同hash: {hash1} == {hash2}")
    
    # 测试不同的seed产生不同的hash
    hash3 = ecmp_hash(key_bytes, 66)
    passed2 = hash1 != hash3
    status2 = "✓" if passed2 else "✗"
    print(f"{status2} 不同seed产生不同hash: {hash1} != {hash3}")
    
    # 测试不同的key产生不同的hash
    key_bytes2 = bytearray([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0a, 0x0b, 0x0d])
    hash4 = ecmp_hash(key_bytes2, seed)
    passed3 = hash1 != hash4
    status3 = "✓" if passed3 else "✗"
    print(f"{status3} 不同key产生不同hash: {hash1} != {hash4}")
    
    all_passed = passed and passed2 and passed3
    print(f"\n结果: {'全部通过' if all_passed else '部分失败'}\n")
    return all_passed


def test_flow_hash_differentiation():
    """测试不同流的hash值是否不同"""
    print("=" * 60)
    print("测试3: 不同流的Hash值区分")
    print("=" * 60)
    
    # 模拟之前提取的14条流的情况
    # 所有流都从TOR65出发，但目标不同
    current_node = 65  # TOR65
    src_node = 14  # H14
    src_port = 1016
    dst_port = 1016
    
    # 不同的目标节点
    dst_nodes = [6, 62, 54, 46, 38, 30, 22, 2]
    
    hashes = []
    print(f"源节点: H{src_node}, 当前节点: TOR{current_node}")
    print(f"不同目标节点的hash值:")
    
    for dst_node in dst_nodes:
        hash_value = compute_ecmp_hash_for_flow(
            src_node, dst_node, src_port, dst_port, current_node
        )
        hashes.append((dst_node, hash_value))
        print(f"  H{src_node} -> H{dst_node:2d}: hash = {hash_value:10d} (0x{hash_value:08x})")
    
    # 检查是否有重复的hash值
    hash_values = [h[1] for h in hashes]
    unique_hashes = len(set(hash_values))
    total_hashes = len(hash_values)
    
    print(f"\n唯一hash值数量: {unique_hashes}/{total_hashes}")
    
    if unique_hashes == total_hashes:
        print("✓ 所有流的hash值都不同（符合预期）")
        passed = True
    else:
        print(f"✗ 有 {total_hashes - unique_hashes} 个重复的hash值")
        # 找出重复的
        from collections import Counter
        counter = Counter(hash_values)
        duplicates = {h: count for h, count in counter.items() if count > 1}
        print(f"  重复的hash值: {duplicates}")
        passed = False
    
    print(f"\n结果: {'通过' if passed else '失败'}\n")
    return passed


def test_port_parsing():
    """测试端口解析功能"""
    print("=" * 60)
    print("测试4: 端口解析功能")
    print("=" * 60)
    
    # 创建临时测试文件
    import tempfile
    test_content = """stat rdma operate:
phase:3000
Type rdma_send src_node 14 src_port 1016 dst_node 6 dst_port 1016 priority 0 msg_len 33554432
Type rdma_send src_node 14 src_port 1016 dst_node 62 dst_port 1016 priority 0 msg_len 33554432
Type rdma_send src_node 10 src_port 2020 dst_node 2 dst_port 3030 priority 0 msg_len 33554432
"""
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(test_content)
        temp_file = f.name
    
    try:
        flows = parse_rdma_operate(temp_file)
        
        print(f"解析到 {len(flows)} 条流:")
        all_passed = True
        
        expected_flows = [
            (14, 6, 1016, 1016),
            (14, 62, 1016, 1016),
            (10, 2, 2020, 3030),
        ]
        
        for i, (flow, expected) in enumerate(zip(flows, expected_flows), 1):
            exp_src, exp_dst, exp_sport, exp_dport = expected
            passed = (flow.src_node == exp_src and 
                     flow.dst_node == exp_dst and
                     flow.src_port == exp_sport and
                     flow.dst_port == exp_dport)
            status = "✓" if passed else "✗"
            print(f"{status} 流{i}: {flow}")
            if not passed:
                all_passed = False
                print(f"    期望: src={exp_src}, dst={exp_dst}, sport={exp_sport}, dport={exp_dport}")
        
        print(f"\n结果: {'全部通过' if all_passed else '部分失败'}\n")
        return all_passed
    finally:
        os.unlink(temp_file)


def test_ecmp_port_selection():
    """测试ECMP端口选择"""
    print("=" * 60)
    print("测试5: ECMP端口选择")
    print("=" * 60)
    
    # 模拟TOR65有多个到Spine的端口
    current_node = 65
    port_ids = [0, 1, 2, 3, 4, 5, 6, 7]  # 8个Spine
    
    # 测试不同流的端口选择
    flows = [
        (14, 6, 1016, 1016),
        (14, 62, 1016, 1016),
        (14, 54, 1016, 1016),
        (10, 2, 1016, 1016),
    ]
    
    print(f"当前节点: TOR{current_node}, 可用端口: {port_ids}")
    print(f"不同流的端口选择:")
    
    port_selections = []
    for src_node, dst_node, src_port, dst_port in flows:
        hash_value = compute_ecmp_hash_for_flow(
            src_node, dst_node, src_port, dst_port, current_node
        )
        port_index = hash_value % len(port_ids)
        selected_port = port_ids[port_index]
        port_selections.append(selected_port)
        print(f"  H{src_node} -> H{dst_node:2d}: hash={hash_value:10d}, 选择端口 {selected_port}")
    
    # 检查端口分布
    from collections import Counter
    port_dist = Counter(port_selections)
    print(f"\n端口分布: {dict(port_dist)}")
    
    # 如果所有流都选择同一个端口，说明可能有问题
    unique_ports = len(set(port_selections))
    if unique_ports == 1:
        print("⚠ 警告: 所有流都选择了同一个端口（可能hash分布不均匀）")
        passed = False
    else:
        print(f"✓ 流被分配到 {unique_ports} 个不同的端口（符合ECMP负载均衡）")
        passed = True
    
    print(f"\n结果: {'通过' if passed else '需要检查'}\n")
    return passed


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("ECMP算法修复测试")
    print("=" * 60 + "\n")
    
    results = []
    
    # 运行所有测试
    results.append(("节点ID到IP转换", test_node_id_to_ip()))
    results.append(("ECMP Hash一致性", test_ecmp_hash_consistency()))
    results.append(("流Hash值区分", test_flow_hash_differentiation()))
    results.append(("端口解析", test_port_parsing()))
    results.append(("ECMP端口选择", test_ecmp_port_selection()))
    
    # 汇总结果
    print("=" * 60)
    print("测试汇总")
    print("=" * 60)
    
    passed_count = sum(1 for _, result in results if result)
    total_count = len(results)
    
    for test_name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"{status}: {test_name}")
    
    print(f"\n总计: {passed_count}/{total_count} 测试通过")
    
    if passed_count == total_count:
        print("\n🎉 所有测试通过！ECMP算法修复成功！")
        return 0
    else:
        print(f"\n⚠️  有 {total_count - passed_count} 个测试失败，请检查")
        return 1


if __name__ == "__main__":
    sys.exit(main())


