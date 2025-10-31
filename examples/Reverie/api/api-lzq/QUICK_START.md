# 拓扑切分API快速开始指南

## 快速测试（3步）

### 1. 停止并重启API服务

**方法A：手动重启**
```bash
# 停止现有服务
kill -9 $(lsof -ti:8002)

# 启动API服务
cd /home/sakura/桌面/flow-input-zyh/examples/Reverie/api
python start_tree_cut_api.py
```

**方法B：使用自动测试脚本**
```bash
cd /home/sakura/桌面/flow-input-zyh/examples/Reverie/api
python run_all_tests.py
```

### 2. 运行测试

```bash
cd /home/sakura/桌面/flow-input-zyh/examples/Reverie/api

# 运行完整测试（6个测试用例）
python test/tree_cut_complete_test.py

# 运行扩展测试（7个测试用例）
python test/tree_cut_extended_test.py
```

### 3. 查看结果

测试通过后，检查生成的JSON文件：

```bash
# 查看概览文件
cat test_output/tree_group_overview.json

# 查看各个树文件
cat test_output/tree_group_1.json
cat test_output/tree_group_2.json
```

## 测试用例说明

### 基础测试（tree_cut_complete_test.py）

1. **健康检查** - 验证API服务状态
2. **获取示例树** - 验证示例数据获取
3. **拓扑切分（示例数据）** - 2个节点，2条边
4. **拓扑切分（自定义数据）** - 4个节点，3条边，包含层级结构
5. **无效数据测试** - 验证错误处理
6. **JSON文件格式验证** - 验证输出文件格式

### 扩展测试（tree_cut_extended_test.py）

1. **单节点树** - 只有Root节点（应返回错误）
2. **线性树** - Root -> A -> B -> C 线性结构
3. **二叉树** - 多分支结构
4. **冲突节点** - nodes_passed有交集的节点
5. **大型树** - 10个节点的复杂树
6. **混合类型树** - DP、PP、TP混合
7. **空nodes_passed** - 节点没有经过任何host

## 输入输出示例

### 输入格式（两种方式）

#### 方式1：直接提供tree_data
```json
{
  "tree_data": {
    "nodes": [
      {
        "name": "Root",
        "type": "Root",
        "layer": 0,
        "nodes_passed": [],
        "children": [],
        "isBurr": false
      },
      {
        "name": "DP1_0",
        "type": "DP",
        "layer": 1,
        "nodes_passed": ["A", "B"],
        "children": [],
        "isBurr": false
      }
    ],
    "edges": [
      {
        "from_node": "Root",
        "to_node": "DP1_0"
      }
    ]
  },
  "output_dir": "my_output",
  "show_graphs": false
}
```

#### 方式2：提供JSON文件URL
```json
{
  "tree_data_url": "http://localhost:8888/sample_tree_data.json",
  "output_dir": "my_output",
  "show_graphs": false
}
```

**注意**: tree_data和tree_data_url二选一，不能同时提供。

### 输出格式（JSON文件）

**tree_group_overview.json** - 总览信息
```json
{
  "total_groups": 2,
  "groups": [
    {
      "group_id": 1,
      "filename": "tree_group_1.json",
      "filepath": "my_output/tree_group_1.json",
      "node_count": 2,
      "edge_count": 1
    },
    {
      "group_id": 2,
      "filename": "tree_group_2.json",
      "filepath": "my_output/tree_group_2.json",
      "node_count": 2,
      "edge_count": 1
    }
  ],
  "output_directory": "my_output"
}
```

**tree_group_1.json** - 单个树组
```json
{
  "nodes": [
    {
      "name": "root"
    },
    {
      "name": "DP1_0",
      "range": "0-127",
      "group": "group2"
    }
  ],
  "edges": [
    {
      "from_node": "Root",
      "to_node": "DP1_0"
    }
  ]
}
```

## API接口

### 1. 健康检查
```bash
curl http://localhost:8002/health
```

### 2. 获取示例树
```bash
curl http://localhost:8002/example-tree
```

### 3. 执行拓扑切分
```bash
curl -X POST http://localhost:8002/tree-cut \
  -H "Content-Type: application/json" \
  -d @test_data.json
```

## 测试结果说明

### 完整测试预期结果
```
测试完成: 6/6 通过
🎉 所有测试通过！
```

### 扩展测试预期结果
```
扩展测试完成: 7/7 通过
🎉 所有扩展测试通过！
```

## 常见问题

### Q1: 为什么需要重启API服务？
A: uvicorn的reload功能可能不会重新加载TreeCut模块（在不同目录），需要手动重启。

### Q2: 如何停止API服务？
A: 使用命令 `kill -9 $(lsof -ti:8002)`

### Q3: 如何查看API日志？
A: 查看文件 `api_server.log`

### Q4: 如何验证JSON文件格式？
A: 使用命令 `python -m json.tool output_file.json`

## 下一步

1. ✅ 基础测试全部通过
2. ✅ 扩展测试全部通过
3. 📝 使用Apifox进行接口测试
4. 📝 集成到实际应用中

## 文档参考

- `README.md` - API使用说明
- `TEST_EXECUTION_GUIDE.md` - 完整测试指南
- `test/apifox_complete_test_guide.md` - Apifox测试方案
- `FINAL_SUMMARY.md` - 项目总结

