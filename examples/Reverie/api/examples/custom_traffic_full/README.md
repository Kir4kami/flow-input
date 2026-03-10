# 自定义流量完整格式说明

## 完整流量 = 一个 task 的完整数据

用户上传的是**完整流量**（未切分），包含多个 rdma_operate 文件和一个 dependence 文件。
**多个 task**（task1、task2、task3、task4）由后续**切分**产生，不是上传格式。

## 本示例：DP/PP/TP 通信树结构（可完全切分）

本示例模拟分布式训练中的通信树，结构如下：

```
Root
├── operate0: DP AR L#n           (Data Parallel AllReduce，层 n)
└── operate1: PP Snd/Rcv L#n+1   (Pipeline Parallel Send/Receive)
    └── operate2: TP Attn AR L#n+1
        └── operate3: TP MLP AR L#n+1
            └── operate4: DP AR L#n+1
```

- Root 有两个子节点，tree-cut 可识别为两个独立子树，**可完全切分**
- 分支1：operate0 独立
- 分支2：operate1→2→3→4 为顺序依赖链

## 目录结构（ZIP 根目录）

```
custom_traffic_full.zip
├── rdma_operate0.txt
├── rdma_operate1.txt
├── rdma_operate2.txt
├── rdma_operate3.txt
├── rdma_operate4.txt
└── dependence.txt         # 可选，缺失时所有 operate 视为 Root 的直接子节点
```

## 文件格式

**rdma_operate*.txt**（与 trafficGen 一致）：
```
stat rdma operate:
phase:3000
Type rdma_send src_node 0 src_port 1000 dst_node 1 dst_port 1000 priority 0 msg_len 32768
...
```

**dependence.txt**（operate 索引依赖，格式 `子起-子止:父起-父止`）：
```
2-2:1-1
3-3:2-2
4-4:3-3
```
表示：operate 2 依赖 operate 1；operate 3 依赖 operate 2；operate 4 依赖 operate 3。
operate 0、1 无依赖（直接连 Root）。

## 打包方式

```bash
cd examples/Reverie/api/examples/custom_traffic_full
zip custom_traffic_full.zip rdma_operate*.txt dependence.txt
```

## 处理流程

- **task_num=1**：完整流量直接作为 task1 使用
- **task_num=4**：需执行切分逻辑，将完整流量分配到 task1..4（类似 merge_rdma）

## 与简单格式的对比

| 模式 | 输入 | 输出 |
|------|------|------|
| 简单 | 单 txt（src dst 或 rdma 格式） | 1 个 operate0 + 空 dependence |
| 完整 | ZIP（多 operate + dependence） | 完整流量 → task1 或切分到 task1..4 |
