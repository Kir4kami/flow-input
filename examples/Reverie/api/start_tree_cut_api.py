#!/usr/bin/env python3
# 启动拓扑切分API服务

import uvicorn
import sys
from pathlib import Path

# 添加当前目录到Python路径
current_dir = Path(__file__).parent
sys.path.append(str(current_dir))

if __name__ == "__main__":
    print("启动拓扑切分API服务...")
    print("API文档地址: http://localhost:8002/docs")
    print("健康检查地址: http://localhost:8002/health")
    print("按 Ctrl+C 停止服务")
    
    uvicorn.run(
        "tree_cut_api:app",
        host="0.0.0.0",
        port=8002,  # 改为8002端口
        reload=True,
        log_level="info"
    )
