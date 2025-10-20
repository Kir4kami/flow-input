# Apifox拓扑切分API测试方案

## 📋 测试概述

**测试目标**: 验证拓扑切分API的所有功能
**测试工具**: Apifox
**API地址**: http://localhost:8002
**测试用例数**: 12个
**预期结果**: 100%通过

---

## 🚀 准备工作（5分钟）

### 步骤1: 启动必要的服务

**终端1 - 启动API服务**:
```bash
cd /home/sakura/桌面/flow-input-zyh/examples/Reverie/api
python start_tree_cut_api.py
```

**终端2 - 启动文件服务器（用于URL测试）**:
```bash
cd /home/sakura/桌面/flow-input-zyh/examples/Reverie/api/test
python -m http.server 8888
```

验证服务启动：
- API服务: http://localhost:8002/health
- 文件服务器: http://localhost:8888/sample_tree_data.json

### 步骤2: 配置Apifox

1. 打开Apifox应用
2. 创建新项目：`拓扑切分API测试`
3. 导入API文档：
   - 方式1: 访问 http://localhost:8002/openapi.json
   - 方式2: 在Apifox中选择"导入" → "URL导入" → 输入OpenAPI URL

4. 配置环境变量：
   - `base_url`: `http://localhost:8002`
   - `file_server_url`: `http://localhost:8888`

---

## 📝 测试用例清单

### 基础功能测试（3个）

| # | 测试用例 | 方法 | URL | 预期状态码 |
|---|---------|------|-----|-----------|
| 1 | 健康检查 | GET | /health | 200 |
| 2 | 获取示例树 | GET | /example-tree | 200 |
| 3 | API根路径 | GET | / | 200 |

### 直接数据测试（3个）

| # | 测试用例 | 预期树组数 | 说明 |
|---|---------|-----------|------|
| 4 | 简单树切分 | 1 | 2节点，1条边 |
| 5 | 标准树切分 | 2 | 3节点，2条边 |
| 6 | 复杂树切分 | 3 | 4节点，3条边 |

### URL输入测试（2个）

| # | 测试用例 | 预期树组数 | 说明 |
|---|---------|-----------|------|
| 7 | URL方式-简单 | 2 | 使用sample_tree_data.json |
| 8 | URL方式-复杂 | 3 | 使用complex_tree_data.json |

### 错误处理测试（4个）

| # | 测试用例 | 预期状态码 | 说明 |
|---|---------|-----------|------|
| 9 | 空节点错误 | 400 | nodes为空 |
| 10 | 空边错误 | 400 | edges为空 |
| 11 | 同时提供两种输入 | 400 | tree_data和tree_data_url都提供 |
| 12 | 都不提供输入 | 400 | 两者都不提供 |

---

## 🔧 详细测试配置

### 测试1: 健康检查 ✅

**基本信息**:
- 接口名称: 健康检查
- 请求方式: GET
- 接口路径: `{{base_url}}/health`

**断言**:
```javascript
pm.test("状态码为200", function() {
    pm.response.to.have.status(200);
});

pm.test("响应包含status字段", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.status).to.equal("healthy");
});
```

**预期响应**:
```json
{
  "status": "healthy",
  "message": "Tree Cut API服务正常运行"
}
```

---

### 测试2: 获取示例树 ✅

**基本信息**:
- 接口名称: 获取示例通信树
- 请求方式: GET
- 接口路径: `{{base_url}}/example-tree`

**断言**:
```javascript
pm.test("状态码为200", function() {
    pm.response.to.have.status(200);
});

pm.test("响应包含tree_data", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData).to.have.property('tree_data');
    pm.expect(jsonData.tree_data).to.have.property('nodes');
    pm.expect(jsonData.tree_data).to.have.property('edges');
});

pm.test("节点数量正确", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.tree_data.nodes.length).to.equal(3);
});
```

---

### 测试3: API根路径 ✅

**基本信息**:
- 接口名称: API根路径
- 请求方式: GET
- 接口路径: `{{base_url}}/`

**断言**:
```javascript
pm.test("状态码为200", function() {
    pm.response.to.have.status(200);
});

pm.test("响应包含message", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.message).to.equal("Tree Cut API");
});
```

---

### 测试4: 简单树切分 ✅

**基本信息**:
- 接口名称: 拓扑切分-简单树
- 请求方式: POST
- 接口路径: `{{base_url}}/tree-cut`
- Content-Type: application/json

**请求Body**:
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
  "output_dir": "apifox_simple_test",
  "show_graphs": false
}
```

**断言**:
```javascript
pm.test("状态码为200", function() {
    pm.response.to.have.status(200);
});

pm.test("切分成功", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.success).to.equal(true);
});

pm.test("生成树组", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.tree_groups).to.be.above(0);
});

pm.test("包含json_overview", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.json_overview).to.have.property('total_groups');
    pm.expect(jsonData.json_overview.groups).to.be.an('array');
});

pm.test("响应时间小于5秒", function() {
    pm.expect(pm.response.responseTime).to.be.below(5000);
});
```

---

### 测试5: 标准树切分 ✅

**请求Body**:
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
      },
      {
        "name": "PP1_1",
        "type": "PP",
        "layer": 1,
        "nodes_passed": ["C", "D"],
        "children": [],
        "isBurr": false
      }
    ],
    "edges": [
      {
        "from_node": "Root",
        "to_node": "DP1_0"
      },
      {
        "from_node": "Root",
        "to_node": "PP1_1"
      }
    ]
  },
  "output_dir": "apifox_standard_test",
  "show_graphs": false
}
```

**断言**: 同测试4，额外添加：
```javascript
pm.test("树组数量为2", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.tree_groups).to.equal(2);
});
```

---

### 测试6: 复杂树切分 ✅

**请求Body**:
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
        "nodes_passed": ["A", "B", "C"],
        "children": [],
        "isBurr": false
      },
      {
        "name": "PP1_1",
        "type": "PP",
        "layer": 1,
        "nodes_passed": ["D", "E"],
        "children": [],
        "isBurr": false
      },
      {
        "name": "TP2_2",
        "type": "TP",
        "layer": 2,
        "nodes_passed": ["F", "G", "H"],
        "children": [],
        "isBurr": false
      }
    ],
    "edges": [
      {
        "from_node": "Root",
        "to_node": "DP1_0"
      },
      {
        "from_node": "Root",
        "to_node": "PP1_1"
      },
      {
        "from_node": "PP1_1",
        "to_node": "TP2_2"
      }
    ]
  },
  "output_dir": "apifox_complex_test",
  "show_graphs": false
}
```

**断言**: 同测试4，额外添加：
```javascript
pm.test("树组数量为3", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.tree_groups).to.equal(3);
});
```

---

### 测试7: URL方式-简单 ✅（重点）

**基本信息**:
- 接口名称: 拓扑切分-URL方式（简单）
- 请求方式: POST
- 接口路径: `{{base_url}}/tree-cut`

**前置条件**: 确保文件服务器在8888端口运行

**请求Body**:
```json
{
  "tree_data_url": "http://localhost:8888/sample_tree_data.json",
  "output_dir": "apifox_url_simple",
  "show_graphs": false
}
```

**断言**:
```javascript
pm.test("状态码为200", function() {
    pm.response.to.have.status(200);
});

pm.test("URL方式切分成功", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.success).to.equal(true);
});

pm.test("树组数量为2", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.tree_groups).to.equal(2);
});

pm.test("包含JSON概览", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.json_overview.total_groups).to.equal(2);
});
```

---

### 测试8: URL方式-复杂 ✅（重点）

**请求Body**:
```json
{
  "tree_data_url": "http://localhost:8888/complex_tree_data.json",
  "output_dir": "apifox_url_complex",
  "show_graphs": false
}
```

**断言**: 同测试7，修改树组数量：
```javascript
pm.test("树组数量为3", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.tree_groups).to.equal(3);
});
```

---

### 测试9: 空节点错误 ✅

**请求Body**:
```json
{
  "tree_data": {
    "nodes": [],
    "edges": []
  },
  "output_dir": "apifox_error_test"
}
```

**断言**:
```javascript
pm.test("状态码为400", function() {
    pm.response.to.have.status(400);
});

pm.test("错误信息包含'节点'", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.detail).to.include("节点");
});
```

**预期响应**:
```json
{
  "detail": "通信树必须包含至少一个节点"
}
```

---

### 测试10: 空边错误 ✅

**请求Body**:
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
      }
    ],
    "edges": []
  },
  "output_dir": "apifox_error_test"
}
```

**断言**:
```javascript
pm.test("状态码为400", function() {
    pm.response.to.have.status(400);
});

pm.test("错误信息包含'边'", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.detail).to.include("边");
});
```

---

### 测试11: 同时提供两种输入 ✅

**请求Body**:
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
      }
    ],
    "edges": []
  },
  "tree_data_url": "http://localhost:8888/sample_tree_data.json",
  "output_dir": "apifox_error_test"
}
```

**断言**:
```javascript
pm.test("状态码为400", function() {
    pm.response.to.have.status(400);
});

pm.test("错误信息正确", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.detail).to.include("不能同时提供");
});
```

**预期响应**:
```json
{
  "detail": "tree_data和tree_data_url不能同时提供，请只提供其中一个"
}
```

---

### 测试12: 都不提供输入 ✅

**请求Body**:
```json
{
  "output_dir": "apifox_error_test",
  "show_graphs": false
}
```

**断言**:
```javascript
pm.test("状态码为400", function() {
    pm.response.to.have.status(400);
});

pm.test("错误信息正确", function() {
    var jsonData = pm.response.json();
    pm.expect(jsonData.detail).to.include("必须提供");
});
```

**预期响应**:
```json
{
  "detail": "必须提供tree_data或tree_data_url其中之一"
}
```

---

## 🎬 执行步骤

### 方法1: 手动逐个测试（推荐新手）

1. 在Apifox左侧选择第一个测试用例
2. 点击"发送"按钮
3. 查看响应结果和断言状态
4. 所有断言都显示✅表示通过
5. 重复步骤1-4，完成所有12个测试

### 方法2: 批量执行测试（推荐）

1. 在Apifox中点击"测试管理"
2. 创建测试集合："拓扑切分API完整测试"
3. 将12个测试用例添加到集合
4. 点击"运行"按钮
5. 选择环境："本地开发环境"
6. 点击"开始测试"
7. 等待所有测试执行完成
8. 查看测试报告

### 方法3: 导入测试集合

1. 在Apifox中点击"导入"
2. 选择"导入测试用例"
3. 选择文件: `test/apifox_test_collection.json`
4. 导入完成后，点击"运行测试集合"

---

## 📊 测试报告模板

### 测试执行记录

**基本信息**:
- 测试时间: ___________
- 测试人员: ___________
- API版本: 1.0.0
- 测试环境: 本地开发环境

**测试结果统计**:
- 总测试数: 12
- 通过: ___ / 12
- 失败: ___ / 12
- 成功率: ___%

**详细结果**:

| # | 测试用例 | 状态 | 响应时间 | 备注 |
|---|---------|------|---------|------|
| 1 | 健康检查 | ✅/❌ | ___ ms | |
| 2 | 获取示例树 | ✅/❌ | ___ ms | |
| 3 | API根路径 | ✅/❌ | ___ ms | |
| 4 | 简单树切分 | ✅/❌ | ___ ms | |
| 5 | 标准树切分 | ✅/❌ | ___ ms | |
| 6 | 复杂树切分 | ✅/❌ | ___ ms | |
| 7 | URL方式-简单 | ✅/❌ | ___ ms | |
| 8 | URL方式-复杂 | ✅/❌ | ___ ms | |
| 9 | 空节点错误 | ✅/❌ | ___ ms | |
| 10 | 空边错误 | ✅/❌ | ___ ms | |
| 11 | 同时提供两种输入 | ✅/❌ | ___ ms | |
| 12 | 都不提供输入 | ✅/❌ | ___ ms | |

**性能指标**:
- 平均响应时间: ___ ms
- 最大响应时间: ___ ms
- 最小响应时间: ___ ms

---

## ✅ 验证要点

### 功能验证
- [ ] 所有接口返回正确的状态码
- [ ] 成功请求返回完整的响应数据
- [ ] 错误请求返回清晰的错误信息
- [ ] JSON格式正确，可解析
- [ ] 生成的文件存在且格式正确

### 数据验证
- [ ] tree_groups数量正确
- [ ] json_overview结构完整
- [ ] 每组的node_count和edge_count正确
- [ ] result_files列表包含所有生成的文件

### 错误处理验证
- [ ] 空节点返回400错误
- [ ] 空边返回400错误
- [ ] 两种输入同时提供返回400错误
- [ ] 两种输入都不提供返回400错误
- [ ] 错误信息清晰明确

### URL功能验证
- [ ] 可以从URL读取JSON文件
- [ ] 支持带tree_data字段的JSON
- [ ] 支持直接是tree_data的JSON
- [ ] URL错误返回400错误
- [ ] JSON格式错误返回400错误

---

## 📸 测试截图要求

每个测试用例需要截图以下内容：

1. **请求配置** - 显示URL、方法、Headers、Body
2. **响应结果** - 显示状态码、响应时间、响应Body
3. **断言结果** - 显示所有断言的通过状态
4. **测试报告** - 整体测试统计

---

## 🎯 预期测试结果

### 成功测试（8个）
所有断言应该通过：
- 测试1-8: 状态码200，success=true，tree_groups>0

### 错误测试（4个）
正确返回错误：
- 测试9-12: 状态码400，包含清晰的错误信息

### 整体结果
```
测试集合: 拓扑切分API完整测试
总测试数: 12
通过: 12
失败: 0
成功率: 100%
平均响应时间: < 1000ms
```

---

## 🔍 故障排查

### 问题1: 连接失败
**症状**: Connection refused
**解决**: 
```bash
# 检查API服务
curl http://localhost:8002/health

# 重启服务
python start_tree_cut_api.py
```

### 问题2: URL测试失败
**症状**: 无法从URL获取数据
**解决**:
```bash
# 检查文件服务器
curl http://localhost:8888/sample_tree_data.json

# 重启文件服务器
cd test
python -m http.server 8888
```

### 问题3: 测试超时
**症状**: 响应时间过长
**解决**: 
- 检查数据大小
- 调整超时时间
- 优化网络连接

---

## 📋 测试检查清单

### 准备阶段
- [ ] API服务已启动（端口8002）
- [ ] 文件服务器已启动（端口8888）
- [ ] Apifox已安装并打开
- [ ] 已创建测试项目
- [ ] 已配置环境变量
- [ ] 已导入API文档

### 执行阶段
- [ ] 测试1: 健康检查 ✅
- [ ] 测试2: 获取示例树 ✅
- [ ] 测试3: API根路径 ✅
- [ ] 测试4: 简单树切分 ✅
- [ ] 测试5: 标准树切分 ✅
- [ ] 测试6: 复杂树切分 ✅
- [ ] 测试7: URL方式-简单 ✅
- [ ] 测试8: URL方式-复杂 ✅
- [ ] 测试9: 空节点错误 ✅
- [ ] 测试10: 空边错误 ✅
- [ ] 测试11: 同时提供两种输入 ✅
- [ ] 测试12: 都不提供输入 ✅

### 验证阶段
- [ ] 所有断言通过
- [ ] 响应时间合理
- [ ] 生成文件存在
- [ ] JSON格式正确
- [ ] 错误处理正确

### 报告阶段
- [ ] 导出测试报告
- [ ] 记录测试结果
- [ ] 截图保存
- [ ] 问题记录（如有）

---

## 💡 高级测试（可选）

### 性能测试
1. 在Apifox中配置"性能测试"
2. 设置参数：
   - 并发数: 10
   - 持续时间: 60秒
3. 执行性能测试
4. 查看性能报告

### 数据驱动测试
1. 创建测试数据集
2. 配置数据变量
3. 批量执行测试
4. 对比不同数据的结果

---

## 📄 导出测试报告

### 步骤
1. 测试完成后，点击"测试报告"
2. 选择导出格式：HTML/PDF/Excel
3. 选择导出内容：
   - ✅ 测试统计
   - ✅ 详细结果
   - ✅ 断言信息
   - ✅ 响应数据
4. 点击"导出"
5. 保存测试报告

---

## 🎉 测试完成标准

所有12个测试用例都应该通过，具体验证：

### 功能测试（8个）
- ✅ 基础功能正常（3个）
- ✅ 直接数据切分正常（3个）
- ✅ URL方式切分正常（2个）

### 错误测试（4个）
- ✅ 参数验证正确（2个）
- ✅ 输入验证正确（2个）

### 综合评价
- ✅ 成功率: 100%
- ✅ 响应时间: < 5秒
- ✅ 错误处理: 完善
- ✅ 文档: 完整

**测试通过即可投入使用！** 🚀

---

## 📚 相关资源

### 测试文件
- `test/sample_tree_data.json` - 简单示例数据
- `test/complex_tree_data.json` - 复杂示例数据
- `test/apifox_test_collection.json` - 可导入的测试集合

### 文档
- `APIFOX_STEP_BY_STEP.md` - 详细步骤指南
- `URL_INPUT_GUIDE.md` - URL输入使用指南
- `URL_USAGE_EXAMPLE.md` - URL使用示例

### 自动化脚本
- `test/test_with_url.py` - Python自动测试脚本

---

## 📞 技术支持

如遇问题，请检查：
1. API服务是否正常启动
2. 文件服务器是否运行（URL测试）
3. JSON文件格式是否正确
4. 网络连接是否正常
5. Apifox版本是否最新

---

**开始测试，祝测试顺利！** ✨
