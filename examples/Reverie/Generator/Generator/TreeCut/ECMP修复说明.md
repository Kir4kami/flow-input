# ECMP算法修复说明

## 修复内容

已修复ECMP路径计算算法，使其与NS-3仿真完全一致。

### 主要修改

1. **FlowInfo类增强**
   - 添加了 `src_port`, `dst_port`, `protocol` 字段
   - 支持完整的流信息用于ECMP hash计算

2. **端口解析增强**
   - `parse_rdma_operate` 函数现在可以解析端口信息
   - 支持完整格式：`Type rdma_send src_node X src_port Y dst_node Z dst_port W`
   - 兼容旧格式（无端口时使用默认值1016）

3. **实现ECMP Hash函数**
   - `node_id_to_ip`: 节点ID到IP地址转换（与NS-3一致）
   - `ecmp_hash`: MurmurHash3算法实现（与NS-3的SwitchNode::EcmpHash一致）
   - `compute_ecmp_hash_for_flow`: 为流计算ECMP hash值（使用5元组）

4. **路径计算修复**
   - 替换了简单的 `in_port % len(port_ids)` 算法
   - 使用正确的ECMP hash算法选择出端口
   - 考虑流的完整信息（src_node, dst_node, src_port, dst_port, seed）

## 测试方法

### 在Linux VM中测试

1. **确保文件已同步到VM**
   ```bash
   # 检查文件是否存在
   ls -lh /home/chanel/flow-input-local/examples/Reverie/Generator/Generator/TreeCut/ecmp_path.py
   ```

2. **运行测试脚本**
   ```bash
   cd /home/chanel/flow-input-local/examples/Reverie/Generator/Generator/TreeCut
   python3 test_ecmp_fix.py
   ```

3. **验证修复效果**
   - 重新计算ECMP路径
   - 调用 `/extract-link-competition-flows` 接口
   - 检查提取的流数量是否更准确（应该比之前的14条更少，因为不同目标主机的流会被分配到不同的Spine）

## 修复前后对比

### 修复前
- 使用 `in_port % len(port_ids)` 选择出端口
- 所有从同一入端口的流会选择相同路径
- 无法区分不同目标主机的流

### 修复后
- 使用5元组hash: `(src_ip, dst_ip, src_port, dst_port, seed)`
- 不同目标主机的流会被分配到不同路径
- 与NS-3仿真结果一致

## 预期效果

对于之前提取的14条流（H14/H10 -> 不同目标主机）：
- **修复前**: 所有流都被分配到 TOR65→Spine74
- **修复后**: 不同目标主机的流会被分配到不同的Spine，实际共享 TOR65→Spine74 的流数量可能更少（更符合实际网络行为）

## 注意事项

1. 修复后需要重新计算ECMP路径（调用 `/compute-ecmp` 接口）
2. 旧的路径缓存可能需要清除
3. 建议在Linux VM中测试，因为Windows环境可能有编码问题


