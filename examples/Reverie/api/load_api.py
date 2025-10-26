#!/usr/bin/env python3
# 负载接口，接收节点数量和流量大小，返回operate.txt文件内容

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import os
import sys
import subprocess
from pathlib import Path

# 添加父目录到路径，以便导入原始脚本
sys.path.append(str(Path(__file__).parent.parent))

app = FastAPI(
    title="Network Load API",
    description="生成网络负载配置的 API 接口",
    version="1.0.0"
)

class LoadRequest(BaseModel):
    """
    网络负载生成请求模型
    
    用于定义生成网络负载配置所需的参数
    """
    host_num: int  # 节点数量，64
    msg_len: str  # 流量大小，"32*(1024)"
    dp: int  # 数据并行度，8
    device: int  # 设备ID，0
    forward: int  # 前向传播标志，1表示前向，0表示后向
    model_name: str = "custom"  # 模型名称，默认为custom
    stage_type: str = "TP"  # 阶段类型，默认为TP（张量并行）
    parent_stage: str = "Root"  # 父阶段，默认为Root

class LoadResponse(BaseModel):
    success: bool
    content: str
    filename: str
    message: str


def generate_load_config(host_num, msg_len, dp, device, forward, 
                        model_name="custom", stage_type="TP", parent_stage="Root"):
    """生成负载配置的核心函数"""
    
    # 生成负载配置内容
    content_lines = []
    
    # 第一行：模型名称 张量并行度 流水线并行度
    content_lines.append(f"{model_name} 1 1")
    
    # 第二行：阶段配置
    stage_line = f"1\t{stage_type}\t{parent_stage}\t--host_num {host_num}\t--msg_len {msg_len}\t--dp {dp} --device {device} --forward {forward}"
    content_lines.append(stage_line)
    
    return "\n".join(content_lines)

def generate_operate_files(load_config_content, output_dir="rdma_result"):
    """根据负载配置生成operate.txt文件"""
    import os
    import re
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 解析配置内容
    lines = load_config_content.strip().split('\n')
    if len(lines) < 2:
        return []
    
    # 解析第一行获取模型信息
    model_info = lines[0].split()
    model_name = model_info[0] if model_info else "custom"
    
    # 解析阶段配置
    stage_line = lines[1]
    parts = stage_line.split('\t')
    if len(parts) < 6:
        return []
    
    stage_id = parts[0]
    stage_type = parts[1]
    parent_stage = parts[2]
    
    # 解析参数
    host_num = 64
    msg_len = "32*(1024)"
    dp = 8
    device = 0
    forward = 1
    
    for part in parts[3:]:
        if part.startswith("--host_num"):
            host_num = int(part.split()[1])
        elif part.startswith("--msg_len"):
            msg_len = part.split()[1]
        elif part.startswith("--dp"):
            dp = int(part.split()[1])
        elif part.startswith("--device"):
            device = int(part.split()[1])
        elif part.startswith("--forward"):
            forward = int(part.split()[1])
    
    # 计算消息长度（字节）
    msg_len_bytes = eval(msg_len.replace('*', '*').replace('(', '').replace(')', ''))
    
    # 生成operate.txt文件
    operate_files = []
    stage_dir = f"{output_dir}/{stage_id}_{stage_type}{stage_id}"
    os.makedirs(stage_dir, exist_ok=True)
    
    # 生成rdma_operate.txt
    operate_file = os.path.join(stage_dir, "rdma_operate.txt")
    with open(operate_file, 'w', encoding='utf-8') as f:
        f.write("stat rdma operate:\n")
        f.write("phase:3000\n")
        
        # 生成RDMA操作指令
        for i in range(host_num - 1):
            src_node = i
            dst_node = i + 1
            f.write(f"Type rdma_send src_node {src_node} src_port 1000 dst_node {dst_node} dst_port 1000 priority 0 msg_len {msg_len_bytes}\n")
    
    operate_files.append(operate_file)
    
    # 生成额外的operate文件（如果需要）
    for i in range(1, min(3, dp)):  # 最多生成3个额外的operate文件
        extra_file = os.path.join(stage_dir, f"rdma_operate{i}.txt")
        with open(extra_file, 'w', encoding='utf-8') as f:
            f.write("stat rdma operate:\n")
            f.write("phase:3000\n")
            
            # 生成额外的RDMA操作指令
            for j in range(0, host_num, dp):
                if j + i < host_num:
                    src_node = j
                    dst_node = j + i
                    f.write(f"Type rdma_send src_node {src_node} src_port 1000 dst_node {dst_node} dst_port 1000 priority 0 msg_len {msg_len_bytes}\n")
        
        operate_files.append(extra_file)
    
    return operate_files

@app.get("/")
async def root():
    """根路径，返回API信息"""
    return {
        "message": "Network Load API",
        "version": "1.0.0",
        "endpoints": {
            "POST /generate-load": "生成网络负载配置",
            "GET /docs": "API文档"
        }
    }

@app.post("/generate-load", response_model=LoadResponse)
async def generate_load(request: LoadRequest):
    """
    生成网络负载配置
    
    - **host_num**: 节点数量
    - **msg_len**: 流量大小，如"32*(1024)"
    - **dp**: 数据并行度
    - **device**: 设备ID
    - **forward**: 前向传播标志（1表示前向，0表示后向）
    - **model_name**: 模型名称（默认custom）
    - **stage_type**: 阶段类型（默认TP）
    - **parent_stage**: 父阶段（默认Root）
    """
    try:
        # 验证输入参数
        if request.host_num <= 0:
            raise HTTPException(status_code=400, detail="host_num必须大于0")
        
        if request.dp <= 0:
            raise HTTPException(status_code=400, detail="dp必须大于0")
        
        if request.device < 0:
            raise HTTPException(status_code=400, detail="device必须大于等于0")
        
        if request.forward not in [0, 1]:
            raise HTTPException(status_code=400, detail="forward必须是0或1")
        
        # 生成负载配置内容
        load_content = generate_load_config(
            host_num=request.host_num,
            msg_len=request.msg_len,
            dp=request.dp,
            device=request.device,
            forward=request.forward,
            model_name=request.model_name,
            stage_type=request.stage_type,
            parent_stage=request.parent_stage
        )
        
        # 生成operate.txt文件
        operate_files = generate_operate_files(load_content)
        
        # 生成文件列表信息
        file_info = f"生成了{len(operate_files)}个operate.txt文件"
        if operate_files:
            file_info += f"：{', '.join([os.path.basename(f) for f in operate_files])}"
        
        return LoadResponse(
            success=True,
            content=load_content,
            filename=f"{request.model_name}_load.txt",
            message=f"成功生成负载配置：{request.host_num}个节点，流量大小{request.msg_len}，{file_info}"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成负载配置时出错: {str(e)}")

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {"status": "healthy", "message": "API服务正常运行"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
