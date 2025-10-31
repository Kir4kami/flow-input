# JSON文件URL使用示例

## 快速开始

### 1. 准备JSON文件

将通信树数据保存为JSON文件：

**tree_input.json**:
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
        "nodes_passed": ["Host1", "Host2"],
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
  }
}
```

### 2. 提供JSON文件访问

**方法A: 本地文件服务器**
```bash
# 在JSON文件所在目录启动HTTP服务器
python -m http.server 8888

# JSON文件URL: http://localhost:8888/tree_input.json
```

**方法B: 上传到Web服务器**
- 上传到Nginx/Apache服务器
- 上传到云存储（如OSS）
- 上传到文件托管服务

### 3. 调用API

**使用curl**:
```bash
curl -X POST http://localhost:8002/tree-cut \
  -H "Content-Type: application/json" \
  -d '{
    "tree_data_url": "http://localhost:8888/tree_input.json",
    "output_dir": "my_output"
  }'
```

**使用Python**:
```python
import requests

response = requests.post("http://localhost:8002/tree-cut", json={
    "tree_data_url": "http://localhost:8888/tree_input.json",
    "output_dir": "my_output",
    "show_graphs": False
})

if response.status_code == 200:
    result = response.json()
    print(f"切分成功！生成了{result['tree_groups']}个树组")
else:
    print(f"失败：{response.text}")
```

**使用Apifox**:
1. 新建POST请求: `http://localhost:8002/tree-cut`
2. Body选择JSON格式
3. 输入：
   ```json
   {
     "tree_data_url": "http://localhost:8888/tree_input.json",
     "output_dir": "apifox_output"
   }
   ```
4. 发送请求

## 完整示例

### 场景：使用远程JSON文件

**步骤1**: 将JSON文件上传到服务器
```bash
# 假设上传到 http://yourserver.com/data/tree.json
```

**步骤2**: 调用API
```python
import requests

response = requests.post("http://localhost:8002/tree-cut", json={
    "tree_data_url": "http://yourserver.com/data/tree.json",
    "output_dir": "remote_output"
})

result = response.json()
print(f"切分结果: {result['tree_groups']}个树组")

# 查看各组信息
for group in result['json_overview']['groups']:
    print(f"组{group['group_id']}: {group['node_count']}节点, {group['edge_count']}边")
```

## JSON文件格式要求

### 格式1: 包含tree_data字段（推荐）
```json
{
  "tree_data": {
    "nodes": [...],
    "edges": [...]
  }
}
```

### 格式2: 直接是tree_data内容
```json
{
  "nodes": [...],
  "edges": [...]
}
```

两种格式都支持！

## 完整测试流程

### 终端1: 启动文件服务器
```bash
cd /home/sakura/桌面/flow-input-zyh/examples/Reverie/api/test
python -m http.server 8888

# 保持运行
```

### 终端2: 启动API服务
```bash
cd /home/sakura/桌面/flow-input-zyh/examples/Reverie/api
python start_tree_cut_api.py

# 保持运行
```

### 终端3: 执行测试
```bash
cd /home/sakura/桌面/flow-input-zyh/examples/Reverie/api

# 方法1: 运行自动测试
python test/test_with_url.py

# 方法2: 手动测试
curl -X POST http://localhost:8002/tree-cut \
  -H "Content-Type: application/json" \
  -d '{
    "tree_data_url": "http://localhost:8888/sample_tree_data.json",
    "output_dir": "url_output"
  }'
```

## 测试用例

### 测试1: 简单树（sample_tree_data.json）
```bash
curl -X POST http://localhost:8002/tree-cut \
  -H "Content-Type: application/json" \
  -d '{
    "tree_data_url": "http://localhost:8888/sample_tree_data.json",
    "output_dir": "test1_output"
  }'
```

**预期结果**: 切分成2个树组

### 测试2: 复杂树（complex_tree_data.json）
```bash
curl -X POST http://localhost:8002/tree-cut \
  -H "Content-Type: application/json" \
  -d '{
    "tree_data_url": "http://localhost:8888/complex_tree_data.json",
    "output_dir": "test2_output"
  }'
```

**预期结果**: 切分成3个树组

### 测试3: 错误处理 - 同时提供两种输入
```bash
curl -X POST http://localhost:8002/tree-cut \
  -H "Content-Type: application/json" \
  -d '{
    "tree_data": {"nodes": [], "edges": []},
    "tree_data_url": "http://localhost:8888/sample_tree_data.json",
    "output_dir": "error_test"
  }'
```

**预期结果**: 400错误

### 测试4: 错误处理 - 无效URL
```bash
curl -X POST http://localhost:8002/tree-cut \
  -H "Content-Type: application/json" \
  -d '{
    "tree_data_url": "http://invalid-url.com/data.json",
    "output_dir": "error_test"
  }'
```

**预期结果**: 400错误

## 注意事项

1. **URL可访问性**
   - API服务器必须能访问该URL
   - 检查防火墙和网络配置
   - 本地测试使用localhost

2. **JSON文件大小**
   - 默认超时30秒
   - 大文件可能需要调整超时设置
   - 建议文件大小 < 10MB

3. **JSON格式**
   - 必须是有效的JSON格式
   - 使用UTF-8编码
   - 包含必需字段（nodes和edges）

4. **安全性**
   - 验证URL来源
   - 避免使用不可信的URL
   - 生产环境建议添加URL白名单

## 对比两种方式

| 特性 | 直接数据 | JSON URL |
|------|---------|---------|
| 请求大小 | 可能很大 | 很小 |
| 网络请求 | 1次 | 2次 |
| 数据复用 | 困难 | 容易 |
| 版本管理 | 困难 | 容易 |
| 调试 | 容易 | 需要文件服务器 |
| 适用场景 | 小数据/一次性 | 大数据/复用 |

## 推荐使用场景

### 使用直接数据
- 数据量小（<100个节点）
- 一次性测试
- 快速原型开发
- 数据动态生成

### 使用JSON URL
- 数据量大（>100个节点）
- 需要复用相同数据
- 数据文件独立管理
- 多个系统共享数据

## 总结

现在拓扑切分API支持两种灵活的输入方式：

1. **tree_data** - 直接在请求中提供数据
2. **tree_data_url** - 通过URL引用JSON文件

根据您的实际需求选择合适的方式！🎉
