#!/usr/bin/env python3
# 拓扑切分接口，接收通信树数据，返回切分后的TreeGroup

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import os
import sys
import json
import requests
from pathlib import Path

# 添加TreeCut目录到路径，以便导入TreeCut模块
sys.path.append(str(Path(__file__).parent.parent / "TreeCut"))

from TreeCut import performTreeCut, graphToDict, dictToGraph

app = FastAPI(
    title="Tree Cut API",
    description="通信树拓扑切分 API 接口",
    version="1.0.0"
)

class TreeNode(BaseModel):
    """通信树节点模型"""
    name: str
    type: str  # DP, PP, TP
    layer: int
    nodes_passed: List[str] = []
    children: List[str] = []
    isBurr: bool = False

class TreeEdge(BaseModel):
    """通信树边模型"""
    from_node: str
    to_node: str

class TreeData(BaseModel):
    """通信树数据模型"""
    nodes: List[TreeNode]
    edges: List[TreeEdge]

class TreeCutRequest(BaseModel):
    """拓扑切分请求模型"""
    tree_data: Optional[TreeData] = None
    tree_data_url: Optional[str] = None  # JSON文件的URL
    output_dir: str = "TreeGroup"
    show_graphs: bool = False

class TreeGroupInfo(BaseModel):
    """树组信息模型"""
    group_id: int
    filename: str
    filepath: str
    node_count: int
    edge_count: int

class TreeCutResponse(BaseModel):
    """拓扑切分响应模型"""
    success: bool
    message: str
    tree_groups: int
    output_directory: str
    json_overview: Dict[str, Any]
    result_files: List[str]

@app.get("/")
async def root():
    """根路径，返回API信息"""
    return {
        "message": "Tree Cut API",
        "version": "1.0.0",
        "endpoints": {
            "POST /tree-cut": "执行拓扑切分",
            "GET /docs": "API文档"
        }
    }

@app.post("/tree-cut", response_model=TreeCutResponse)
async def tree_cut(request: TreeCutRequest):
    """
    执行通信树拓扑切分
    
    - **tree_data**: 通信树数据，包含节点和边信息（与tree_data_url二选一）
    - **tree_data_url**: JSON文件的URL地址（与tree_data二选一）
    - **output_dir**: 输出目录，默认为"TreeGroup"
    - **show_graphs**: 是否显示图形，默认为False
    """
    # 验证输入参数：tree_data和tree_data_url必须提供其中一个
    if not request.tree_data and not request.tree_data_url:
        raise HTTPException(status_code=400, detail="必须提供tree_data或tree_data_url其中之一")
    
    if request.tree_data and request.tree_data_url:
        raise HTTPException(status_code=400, detail="tree_data和tree_data_url不能同时提供，请只提供其中一个")
    
    # 如果提供了URL，从URL读取数据
    if request.tree_data_url:
        try:
            # 从URL获取JSON数据
            response = requests.get(request.tree_data_url, timeout=30)
            response.raise_for_status()
            
            # 解析JSON数据
            json_data = response.json()
            
            # 验证JSON数据格式
            if "tree_data" in json_data:
                # 如果JSON文件包含tree_data字段
                tree_data_raw = json_data["tree_data"]
            else:
                # 否则假设整个JSON就是tree_data
                tree_data_raw = json_data
            
            # 转换为TreeData对象
            request.tree_data = TreeData(
                nodes=[TreeNode(**node) for node in tree_data_raw.get("nodes", [])],
                edges=[TreeEdge(from_node=edge.get("from_node"), to_node=edge.get("to_node")) 
                       for edge in tree_data_raw.get("edges", [])]
            )
            
        except requests.RequestException as e:
            raise HTTPException(status_code=400, detail=f"无法从URL获取数据: {str(e)}")
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"JSON格式错误: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"解析JSON数据失败: {str(e)}")
    
    try:
        
        # 验证tree_data
        if not request.tree_data.nodes:
            raise HTTPException(status_code=400, detail="通信树必须包含至少一个节点")
        
        if not request.tree_data.edges:
            raise HTTPException(status_code=400, detail="通信树必须包含至少一条边")
        
        # 转换数据格式
        tree_data_dict = {
            "nodes": [node.dict() for node in request.tree_data.nodes],
            "edges": [{"from": edge.from_node, "to": edge.to_node} for edge in request.tree_data.edges]
        }
        
        # 执行拓扑切分
        result = performTreeCut(
            tree_data=tree_data_dict,
            output_dir=request.output_dir,
            show_graphs=request.show_graphs
        )
        
        # 获取生成的文件列表
        result_files = []
        if os.path.exists(request.output_dir):
            for root, dirs, files in os.walk(request.output_dir):
                for file in files:
                    result_files.append(os.path.join(root, file))
        
        return TreeCutResponse(
            success=True,
            message=f"成功切分通信树，生成了{result['tree_groups']}个树组",
            tree_groups=result['tree_groups'],
            output_directory=result['output_directory'],
            json_overview=result['json_overview'],
            result_files=result_files
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"拓扑切分时出错: {str(e)}")

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy", "message": "Tree Cut API服务正常运行"}

@app.get("/example-tree")
async def get_example_tree():
    """获取示例通信树数据"""
    example_tree = {
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
            },
            {
                "name": "PP1_1",
                "type": "PP",
                "layer": 1,
                "nodes_passed": ["C", "D"],
                "children": [],
                "isBurr": False
            }
        ],
        "edges": [
            {"from_node": "Root", "to_node": "DP1_0"},
            {"from_node": "Root", "to_node": "PP1_1"}
        ]
    }
    
    return {
        "message": "示例通信树数据",
        "tree_data": example_tree
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
