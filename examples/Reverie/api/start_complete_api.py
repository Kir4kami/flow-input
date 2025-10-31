#!/usr/bin/env python3
"""
完整API服务启动脚本
包含所有功能：拓扑设置、负载配置、拓扑切分、仿真控制、稳态监控、结果分析
"""

import uvicorn
import sys
import os
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def main():
    """启动API服务"""
    print("="*60)
    print("   完整网络仿真API服务启动")
    print("="*60)
    print()
    print("📌 功能列表:")
    print("  1. 拓扑设置 - /generate-topology")
    print("  2. 负载配置 - /generate-load")
    print("  3. 拓扑切分 - /tree-cut")
    print("  4. 仿真控制 - /run-simulation")
    print("  5. 稳态监控 - /steady-state-monitor")
    print("  6. 结果分析 - /analyze-results")
    print("  7. 文件访问 - /read-file, /list-files")
    print("  8. 拓扑可视化 - /visualize-topology")
    print()
    print("📌 API文档地址: http://localhost:8000/docs")
    print("📌 前端页面: 请在浏览器中打开 complete_frontend.html")
    print()
    print("="*60)
    print()
    
    # 启动服务
    try:
        uvicorn.run(
            "api.complete_api:app",
            host="0.0.0.0",
            port=8000,
            reload=True,
            log_level="info"
        )
    except KeyboardInterrupt:
        print("\n\n服务已停止")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

