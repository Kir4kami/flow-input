## 🎯 使用自动化脚本

### 方法1: 使用默认配置

**默认配置**：
- 128 主机
- 16 Leaf
- 8 Spine
- Qwen 模型
- 2 设备, 2 迭代

---

### 方法2: 自定义配置

```bash
python3 run_all.py \
  --hosts 256 \
  --leafs 32 \
  --spines 16 \
  --model qwen \
  --max-devices 2 \
  --max-iterations 2
```

---

### 方法3: 使用自定义流量输入

```bash
python3 run_all.py \
  --hosts 128 \
  --leafs 16 \
  --spines 8 \
  --traffic-input ./my_custom_traffic.txt
```

---

## 📂 输出目录结构

执行后会在 `workflow_output/时间戳/` 下生成：

```
workflow_output/2025-11-05_10-30-00/
├── 1_topology/
│   ├── dcn2.0_config.xml       # 拓扑配置
│   └── router_mine.xml          # 路由表
├── 2_traffic/
│   └── rdma_result/             # 流量文件
│       ├── 1_TP1/
│       ├── 2_EP1/
│       └── ...
├── 3_paths/
│   └── ecmp_outputs/            # ECMP路径
│       ├── 1_TP1.txt
│       ├── 2_EP1.txt
│       └── ...
├── 4_treecut/                   # 树分割结果(可选)
│   └── TreeGroup/
└── SUMMARY.txt                  # 执行摘要
```

---

## 🔍 验证步骤

### 1. 检查拓扑生成

```bash
ls -lh workflow_output/*/1_topology/
```

应该看到 `dcn2.0_config.xml` 和 `router_mine.xml`

### 2. 检查流量生成

```bash
ls -R workflow_output/*/2_traffic/rdma_result/
```

应该看到多个子目录（如 1_TP1, 2_EP2 等）

### 3. 检查路径生成

```bash
ls -lh workflow_output/*/3_paths/ecmp_outputs/
```

应该看到对应的 .txt 文件

---

## ⚙️ 高级配置

### 只执行部分步骤

```bash
# 跳过拓扑生成（使用已有拓扑）
python3 run_all.py --skip-topo

# 跳过流量生成（使用已有流量）
python3 run_all.py --skip-traffic
```

### 启用TreeCut分割

```bash
python3 run_all.py --enable-treecut
```

⚠️ **注意**：TreeCut功能需要先修改硬编码路径

---

## 🐛 常见问题

### Q1: 提示找不到模块

**A**: 确保在 Generator 目录下运行
```bash
cd /home/kira/flow-input-test2/Generator
python3 run_all.py
```

### Q2: 流量生成参数不匹配

**A**: 确保 `--hosts` 参数与流量输入文件中的 `--host_num` 一致
- 脚本会自动修改，但如果使用自定义文件，请手动检查

### Q3: ECMP路径生成失败

**A**: 检查拓扑文件是否正确复制到 rdma_result 子目录
- 脚本会自动复制，但如果中断可能不完整

### Q4: TreeCut执行失败

**A**: TreeCut 功能暂未完全集成，需要先修改硬编码路径
- 建议先不启用 `--enable-treecut`

---

## 📝 待完善项

1. **TreeCut 完全集成**
   - 需要修改 TreeCut.py 中的硬编码路径
   - 添加参数化支持

2. **TopoCut 集成**
   - 需要修改固定参数
   - 添加到自动化流程

3. **错误恢复**
   - 中断后继续执行
   - 支持检查点

4. **并行执行**
   - 多个配置并行生成
   - 加速处理

---

## 🎉 快速测试

最简单的测试命令：

```bash
cd /home/kira/flow-input-test2/Generator
python3 run_all.py --hosts 64 --leafs 8 --spines 4
```

这会生成一个小规模的测试环境，快速验证流程是否正常。

---

## 📚 参考

- 拓扑生成文档: `TopoGenerator/clos/auto_gen_topo.py --help`
- 流量生成文档: `TrafficGenerator/trafficGen_add.py --help`
- 主脚本帮助: `python3 run_all.py --help`

