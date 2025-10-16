#!/usr/bin/env python3
# 拓扑接口，接收torSwitches和spineSwitches，返回leaf_spine.txt文件内容

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import sys
import subprocess
from pathlib import Path

# 添加父目录到路径，以便导入原始脚本
sys.path.append(str(Path(__file__).parent.parent))

app = FastAPI(
    title="Network Topology API",
    description="生成 Leaf-Spine 网络拓扑的 API 接口",
    version="1.0.0"
)

class TopologyRequest(BaseModel):
    """
    Leaf-Spine 网络拓扑生成请求模型
    
    用于定义生成 Leaf-Spine 网络拓扑所需的参数
    """
    torSwitches: int  # TOR（Top of Rack）交换机数量，必需参数
    spineSwitches: int  # Spine 核心交换机数量，必需参数
    serversPerTor: int = 8  # 每个 TOR 下连接的服务器数量，默认 8 台
    serverTorDelay: str = "2us"  # 服务器到 TOR 交换机的网络延迟，默认 2 微秒
    torSpineDelay: str = "2us"  # TOR 到 Spine 交换机的网络延迟，默认 2 微秒
    serverDataRate: int = 25  # 服务器链路数据率（Gbps），默认 25 Gbps
    allOtherDataRate: int = 25  # 交换机间链路数据率（Gbps），默认 25 Gbps
    errorRate: float = 0  # 链路传输错误率，默认 0（无错误）

class TopologyResponse(BaseModel):
    success: bool
    content: str
    filename: str
    message: str

def generate_topology_leafspine(torSwitches, spineSwitches, serversPerTor=8, 
                               serverTorDelay="2us", torSpineDelay="2us",
                               serverDataRate=25, allOtherDataRate=25, errorRate=0):
    """生成 Leaf-Spine 拓扑的核心函数"""
    import numpy as np
    
    output_file = "leaf-spine.txt"
    
    # 计算拓扑参数
    switch_num = torSwitches + spineSwitches
    node_num = serversPerTor * torSwitches + switch_num
    link_num = serversPerTor * torSwitches + (torSwitches) * spineSwitches
    
    # 生成拓扑内容
    content_lines = []
    
    # 第一行：节点数 交换机数 TOR数 链路数 服务器数据率 其他数据率
    content_lines.append(f"{node_num} {switch_num} {torSwitches} {link_num} {int(serverDataRate*1e9)} {int(allOtherDataRate*1e9)}")
    
    # 第二行：交换机节点ID
    switch_ids = []
    for i in range(switch_num):
        switch_ids.append(str(int(serversPerTor * torSwitches + i)))
    content_lines.append(" ".join(switch_ids))
    
    # 服务器到TOR的连接
    for i in range(torSwitches):
        for j in range(serversPerTor):
            server_id = j + serversPerTor * i
            tor_id = serversPerTor * torSwitches + i
            content_lines.append(f"{server_id} {tor_id} {int(serverDataRate*1e9)} {serverTorDelay} {errorRate}")
    
    # TOR到Spine的连接
    torIndexBegin = serversPerTor * torSwitches
    spineIndexBegin = serversPerTor * torSwitches + torSwitches
    
    for i in range(torSwitches):
        for j in range(spineSwitches):
            tor_id = torIndexBegin + i
            spine_id = spineIndexBegin + j
            content_lines.append(f"{tor_id} {spine_id} {int(allOtherDataRate*1e9)} {torSpineDelay} {errorRate}")
    
    return "\n".join(content_lines)

@app.get("/")
async def root():
    """根路径，返回API信息"""
    return {
        "message": "Network Topology API",
        "version": "1.0.0",
        "endpoints": {
            "POST /generate-topology": "生成网络拓扑",
            "GET /docs": "API文档"
        }
    }

@app.post("/generate-topology", response_model=TopologyResponse)
async def generate_topology(request: TopologyRequest):
    """
    生成 Leaf-Spine 网络拓扑
    
    - **torSwitches**: TOR交换机数量
    - **spineSwitches**: Spine交换机数量
    - **serversPerTor**: 每个TOR下的服务器数量（默认8）
    - **serverTorDelay**: 服务器到TOR的延迟（默认2us）
    - **torSpineDelay**: TOR到Spine的延迟（默认2us）
    - **serverDataRate**: 服务器数据率（默认25Gbps）
    - **allOtherDataRate**: 其他链路数据率（默认25Gbps）
    - **errorRate**: 错误率（默认0）
    """
    try:
        # 验证输入参数
        if request.torSwitches <= 0 or request.spineSwitches <= 0:
            raise HTTPException(status_code=400, detail="torSwitches和spineSwitches必须大于0")
        
        if request.serversPerTor <= 0:
            raise HTTPException(status_code=400, detail="serversPerTor必须大于0")
        
        # 生成拓扑内容
        topology_content = generate_topology_leafspine(
            torSwitches=request.torSwitches,
            spineSwitches=request.spineSwitches,
            serversPerTor=request.serversPerTor,
            serverTorDelay=request.serverTorDelay,
            torSpineDelay=request.torSpineDelay,
            serverDataRate=request.serverDataRate,
            allOtherDataRate=request.allOtherDataRate,
            errorRate=request.errorRate
        )
        
        return TopologyResponse(
            success=True,
            content=topology_content,
            filename="leaf-spine.txt",
            message=f"成功生成拓扑：{request.torSwitches}个TOR，{request.spineSwitches}个Spine"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成拓扑时出错: {str(e)}")

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy", "message": "API服务正常运行"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)