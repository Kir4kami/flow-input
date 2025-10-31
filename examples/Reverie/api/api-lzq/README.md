# 拓扑切分API接口

本目录包含了通信树拓扑切分的API接口实现和测试文件。

## 文件结构

```
api/
├── tree_cut_api.py          # 拓扑切分API接口
├── topology_api.py          # 网络拓扑生成API接口
├── start_tree_cut_api.py    # 启动拓扑切分API服务
├── test/
│   ├── tree_cut_test.py     # Python测试文件
│   ├── topology.py          # 拓扑API测试文件
│   └── apifox_test_guide.md # Apifox测试方案
└── README.md               # 本文件
```

## 功能说明

### 拓扑切分API (tree_cut_api.py)

提供通信树拓扑切分功能，将复杂的通信树切分为多个独立的树组。

**主要接口：**
- `POST /tree-cut`: 执行拓扑切分
- `GET /example-tree`: 获取示例通信树数据
- `GET /health`: 健康检查

**输入格式（两种方式）：**

方式1：直接提供tree_data
```json
{
  "tree_data": {
    "nodes": [
      {
        "name": "节点名称",
        "type": "节点类型",
        "layer": 层级,
        "nodes_passed": ["经过的节点列表"],
        "children": ["子节点列表"],
        "isBurr": false
      }
    ],
    "edges": [
      {
        "from_node": "起始节点",
        "to_node": "目标节点"
      }
    ]
  },
  "output_dir": "输出目录",
  "show_graphs": false
}
```

方式2：提供JSON文件URL
```json
{
  "tree_data_url": "http://example.com/tree_data.json",
  "output_dir": "输出目录",
  "show_graphs": false
}
```

**输出：**
- 切分后的树组文件保存在指定目录
- 每个树组包含依赖关系信息文件
- 返回切分结果统计信息

## 使用方法

### 1. 启动API服务

```bash
# 启动拓扑切分API
python start_tree_cut_api.py

# 或者直接启动
python tree_cut_api.py
```

服务启动后访问：
- API文档: http://localhost:8001/docs
- 健康检查: http://localhost:8001/health

### 2. Python测试

```bash
# 运行Python测试
python test/tree_cut_test.py
```

### 3. Apifox测试

参考 `test/apifox_test_guide.md` 文件中的详细测试方案。

## 依赖要求

- Python 3.7+
- FastAPI
- NetworkX
- Pydantic
- Uvicorn
- Requests (测试用)

## 安装依赖

```bash
pip install fastapi networkx pydantic uvicorn requests
```

## 示例用法

### 基本使用

```python
import requests

# 获取示例数据
response = requests.get("http://localhost:8001/example-tree")
example_data = response.json()["tree_data"]

# 执行拓扑切分
cut_response = requests.post("http://localhost:8001/tree-cut", json={
    "tree_data": example_data,
    "output_dir": "my_output",
    "show_graphs": False
})

print(cut_response.json())
```

### 自定义通信树

```python
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
            "nodes_passed": ["A", "B"],
            "children": [],
            "isBurr": False
        }
    ],
    "edges": [
        {"from": "Root", "to": "DP1_0"}
    ]
}

response = requests.post("http://localhost:8001/tree-cut", json={
    "tree_data": custom_tree,
    "output_dir": "custom_output"
})
```

## 输出文件说明

拓扑切分完成后，会在输出目录中生成以下文件：

```
output_dir/
├── group1/
│   └── In_dependence_Info.txt    # 组内依赖关系
├── group2/
│   └── In_dependence_Info.txt
├── ...
└── Out_Dependence_Info.txt       # 组间依赖关系
```

### 文件格式说明

**In_dependence_Info.txt:**
- 包含组内节点间的依赖关系
- 格式: `(目标范围,源范围)`
- 节点信息: `(节点名):(范围)`

**Out_Dependence_Info.txt:**
- 包含组间依赖关系
- 格式: `源组:目标组->范围`

## 错误处理

API会返回适当的HTTP状态码和错误信息：

- `400`: 请求参数错误
- `500`: 服务器内部错误

常见错误：
- 通信树必须包含至少一个节点
- 通信树必须包含至少一条边
- 节点类型必须是DP、PP或TP

## 注意事项

1. 确保TreeCut目录下有必要的operate文件
2. 输出目录需要有写入权限
3. 大型通信树可能需要较长的处理时间
4. 建议在生产环境中设置适当的超时时间

## 技术支持

如有问题，请检查：
1. API服务是否正常启动
2. 输入数据格式是否正确
3. 输出目录权限是否足够
4. 相关依赖是否正确安装
