#!/usr/bin/env python3
"""
混合粒度稳态监控API接口
功能：
1. 实时监控仿真过程中的稳态状态
2. 提供优化的询问间隔，确保能够捕捉到稳态
3. 支持前端实时展示稳态加速界面
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import re
import asyncio
import time
from pathlib import Path
from typing import Optional, Dict, List, Any
from datetime import datetime
import json

app = FastAPI(
    title="Steady State Monitor API",
    description="混合粒度稳态实时监控接口",
    version="1.0.0"
)

# 添加CORS中间件，允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 全局配置 ====================

# 监控配置
class MonitorConfig:
    # NS-3仿真的监测周期（纳秒）
    NS3_MONITOR_PERIOD_NS = 10000  # 10微秒
    
    # 稳态判定需要的数据点数量
    STEADY_STATE_DATA_POINTS = 10  # 需要10个监测周期的数据
    
    # 稳态检测的时间窗口（微秒）
    STEADY_STATE_WINDOW_US = NS3_MONITOR_PERIOD_NS * STEADY_STATE_DATA_POINTS / 1000  # 100微秒
    
    # API询问间隔配置（秒）
    # 策略1：高频询问（推荐用于捕捉稳态）
    POLL_INTERVAL_HIGH_FREQ = 0.000005  # 5微秒 = 0.005毫秒（小于NS-3检测周期10微秒）
    
    # 策略2：中频询问（平衡性能和捕捉率）
    POLL_INTERVAL_MEDIUM_FREQ = 0.00001  # 10微秒 = 0.01毫秒（等于NS-3检测周期）
    
    # 策略3：低频询问（节省资源，但可能错过稳态）
    POLL_INTERVAL_LOW_FREQ = 0.0001  # 100微秒 = 0.1毫秒
    
    # 默认使用中频询问
    DEFAULT_POLL_INTERVAL = POLL_INTERVAL_MEDIUM_FREQ
    
    # 日志文件路径
    DUMP_DIR = Path("examples/Reverie/dump")
    EVALUATION_OUT = DUMP_DIR / "evaluation.out"
    FLOW_STATS_FILE = DUMP_DIR / "flow_stats1.txt"

config = MonitorConfig()

# ==================== 稳态状态管理 ====================

class SteadyStateStatus:
    """稳态状态管理类"""
    def __init__(self):
        self.is_monitoring = False  # 是否正在监控
        self.mixed_granularity_enabled = False  # 混合粒度是否开启
        self.is_in_steady_state = False  # 当前是否处于稳态
        self.steady_state_count = 0  # 进入稳态的次数
        self.steady_state_history = []  # 稳态历史记录
        self.last_check_time = None  # 上次检查时间
        self.simulation_start_time = None  # 仿真开始时间
        self.last_log_position = 0  # 日志文件读取位置
        
    def reset(self):
        """重置状态"""
        self.is_monitoring = False
        self.is_in_steady_state = False
        self.steady_state_count = 0
        self.steady_state_history = []
        self.last_check_time = None
        self.last_log_position = 0

steady_state_status = SteadyStateStatus()

# ==================== WebSocket连接管理 ====================

class ConnectionManager:
    """WebSocket连接管理器"""
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """广播消息到所有连接的客户端"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass

manager = ConnectionManager()

# ==================== 请求/响应模型 ====================

class MonitorStartRequest(BaseModel):
    """启动监控请求"""
    mixed_granularity_enabled: bool = True  # 是否启用混合粒度
    poll_interval: Optional[float] = None  # 自定义询问间隔（秒）
    poll_strategy: Optional[str] = "medium"  # 询问策略：high, medium, low

class MonitorStopRequest(BaseModel):
    """停止监控请求"""
    save_history: bool = True  # 是否保存历史记录

class SteadyStateResponse(BaseModel):
    """稳态状态响应"""
    is_monitoring: bool  # 是否正在监控
    mixed_granularity_enabled: bool  # 混合粒度是否开启
    is_in_steady_state: bool  # 当前是否处于稳态
    steady_state_count: int  # 进入稳态的次数
    last_check_time: Optional[str]  # 上次检查时间
    poll_interval: float  # 当前询问间隔（秒）
    poll_interval_us: float  # 当前询问间隔（微秒）
    message: str  # 状态信息

class SteadyStateHistoryResponse(BaseModel):
    """稳态历史记录响应"""
    total_count: int  # 总次数
    history: List[Dict[str, Any]]  # 历史记录列表

class MonitorConfigResponse(BaseModel):
    """监控配置响应"""
    ns3_monitor_period_ns: int  # NS-3监测周期（纳秒）
    steady_state_window_us: float  # 稳态窗口（微秒）
    poll_interval_high_freq: float  # 高频询问间隔（秒）
    poll_interval_medium_freq: float  # 中频询问间隔（秒）
    poll_interval_low_freq: float  # 低频询问间隔（秒）
    default_poll_interval: float  # 默认询问间隔（秒）
    recommended_strategy: str  # 推荐策略
    explanation: str  # 配置说明

# ==================== 核心功能：日志解析 ====================

def parse_steady_state_from_log(log_file: Path, last_position: int = 0) -> tuple:
    """
    从日志文件中解析稳态信息
    
    参数:
        log_file: 日志文件路径
        last_position: 上次读取的文件位置
    
    返回:
        (is_steady, steady_time, new_position, exit_detected)
        - is_steady: 是否检测到进入稳态
        - steady_time: 稳态开始时间（纳秒）
        - new_position: 新的文件位置
        - exit_detected: 是否检测到退出稳态
    """
    if not log_file.exists():
        return False, None, last_position, False
    
    try:
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            # 从上次读取的位置开始
            f.seek(last_position)
            new_content = f.read()
            new_position = f.tell()
            
            if not new_content:
                return False, None, last_position, False
            
            # 检查是否进入稳态
            steady_pattern = r"System entered steady state at time:\s+(\d+(?:\.\d+)?)\s*ns"
            steady_match = re.search(steady_pattern, new_content)
            
            # 检查是否退出稳态
            exit_pattern = r"System exit"
            exit_match = re.search(exit_pattern, new_content)
            
            is_steady = steady_match is not None
            steady_time = float(steady_match.group(1)) if is_steady else None
            exit_detected = exit_match is not None
            
            return is_steady, steady_time, new_position, exit_detected
            
    except Exception as e:
        print(f"解析日志文件时出错: {e}")
        return False, None, last_position, False

# ==================== 核心功能：稳态监控循环 ====================

async def monitor_steady_state_loop(poll_interval: float):
    """
    稳态监控循环（异步）
    
    参数:
        poll_interval: 询问间隔（秒）
    """
    print(f"启动稳态监控循环，询问间隔: {poll_interval*1000000:.2f}微秒")
    
    while steady_state_status.is_monitoring:
        try:
            current_time = datetime.now().isoformat()
            steady_state_status.last_check_time = current_time
            
            # 解析日志文件
            is_steady, steady_time, new_position, exit_detected = parse_steady_state_from_log(
                config.EVALUATION_OUT,
                steady_state_status.last_log_position
            )
            
            # 更新文件读取位置
            steady_state_status.last_log_position = new_position
            
            # 检测到进入稳态
            if is_steady and not steady_state_status.is_in_steady_state:
                steady_state_status.is_in_steady_state = True
                steady_state_status.steady_state_count += 1
                
                # 记录稳态历史
                steady_record = {
                    "count": steady_state_status.steady_state_count,
                    "enter_time": steady_time,
                    "enter_time_ns": steady_time,
                    "detected_at": current_time,
                    "status": "entered"
                }
                steady_state_status.steady_state_history.append(steady_record)
                
                print(f"检测到进入稳态！时间: {steady_time} ns，这是第 {steady_state_status.steady_state_count} 次")
                
                # 广播到所有WebSocket客户端
                await manager.broadcast({
                    "type": "steady_state_entered",
                    "data": steady_record,
                    "message": f"系统进入稳态加速模式（第{steady_state_status.steady_state_count}次）"
                })
            
            # 检测到退出稳态
            if exit_detected and steady_state_status.is_in_steady_state:
                steady_state_status.is_in_steady_state = False
                
                # 更新历史记录
                if steady_state_status.steady_state_history:
                    steady_state_status.steady_state_history[-1]["exit_time"] = current_time
                    steady_state_status.steady_state_history[-1]["status"] = "exited"
                
                print(f"检测到退出稳态！")
                
                # 广播到所有WebSocket客户端
                await manager.broadcast({
                    "type": "steady_state_exited",
                    "data": {"exit_time": current_time},
                    "message": "系统退出稳态加速模式"
                })
            
            # 等待下一次检查
            await asyncio.sleep(poll_interval)
            
        except Exception as e:
            print(f"监控循环出错: {e}")
            await asyncio.sleep(poll_interval)
    
    print("稳态监控循环已停止")

# ==================== API端点 ====================

@app.get("/")
async def root():
    """根端点"""
    return {
        "service": "Steady State Monitor API",
        "version": "1.0.0",
        "status": "running",
        "endpoints": {
            "start_monitor": "POST /start-monitor",
            "stop_monitor": "POST /stop-monitor",
            "get_status": "GET /steady-state-status",
            "get_history": "GET /steady-state-history",
            "get_config": "GET /monitor-config",
            "websocket": "WS /ws/steady-state"
        }
    }

@app.post("/start-monitor")
async def start_monitor(request: MonitorStartRequest):
    """
    启动稳态监控
    
    请求参数:
        - mixed_granularity_enabled: 是否启用混合粒度（默认True）
        - poll_interval: 自定义询问间隔（秒，可选）
        - poll_strategy: 询问策略 high/medium/low（可选）
    """
    if steady_state_status.is_monitoring:
        raise HTTPException(status_code=400, detail="监控已在运行中")
    
    # 确定询问间隔
    if request.poll_interval is not None:
        poll_interval = request.poll_interval
    elif request.poll_strategy == "high":
        poll_interval = config.POLL_INTERVAL_HIGH_FREQ
    elif request.poll_strategy == "low":
        poll_interval = config.POLL_INTERVAL_LOW_FREQ
    else:
        poll_interval = config.POLL_INTERVAL_MEDIUM_FREQ
    
    # 初始化状态
    steady_state_status.reset()
    steady_state_status.is_monitoring = True
    steady_state_status.mixed_granularity_enabled = request.mixed_granularity_enabled
    steady_state_status.simulation_start_time = datetime.now().isoformat()
    
    # 启动监控循环
    asyncio.create_task(monitor_steady_state_loop(poll_interval))
    
    return {
        "success": True,
        "message": "稳态监控已启动",
        "config": {
            "mixed_granularity_enabled": request.mixed_granularity_enabled,
            "poll_interval_seconds": poll_interval,
            "poll_interval_microseconds": poll_interval * 1000000,
            "poll_strategy": request.poll_strategy or "medium",
            "start_time": steady_state_status.simulation_start_time
        }
    }

@app.post("/stop-monitor")
async def stop_monitor(request: MonitorStopRequest):
    """
    停止稳态监控
    
    请求参数:
        - save_history: 是否保存历史记录（默认True）
    """
    if not steady_state_status.is_monitoring:
        raise HTTPException(status_code=400, detail="监控未在运行")
    
    # 停止监控
    steady_state_status.is_monitoring = False
    
    # 保存历史记录
    history = []
    if request.save_history:
        history = steady_state_status.steady_state_history.copy()
        
        # 保存到文件
        history_file = config.DUMP_DIR / "steady_state_history.json"
        config.DUMP_DIR.mkdir(parents=True, exist_ok=True)
        with open(history_file, 'w', encoding='utf-8') as f:
            json.dump({
                "stop_time": datetime.now().isoformat(),
                "total_count": steady_state_status.steady_state_count,
                "history": history
            }, f, indent=2, ensure_ascii=False)
    
    return {
        "success": True,
        "message": "稳态监控已停止",
        "statistics": {
            "total_steady_state_count": steady_state_status.steady_state_count,
            "history_saved": request.save_history,
            "history_count": len(history)
        }
    }

@app.get("/steady-state-status", response_model=SteadyStateResponse)
async def get_steady_state_status():
    """
    获取当前稳态状态（轮询端点）
    前端可以定期调用此接口来检查稳态状态
    """
    # 如果正在监控，实时检查日志
    if steady_state_status.is_monitoring:
        is_steady, steady_time, new_position, exit_detected = parse_steady_state_from_log(
            config.EVALUATION_OUT,
            steady_state_status.last_log_position
        )
        steady_state_status.last_log_position = new_position
    
    # 确定询问间隔
    poll_interval = config.DEFAULT_POLL_INTERVAL
    
    # 生成状态消息
    if not steady_state_status.is_monitoring:
        message = "监控未启动"
    elif steady_state_status.is_in_steady_state:
        message = f"系统处于稳态加速模式（第{steady_state_status.steady_state_count}次）"
    else:
        message = "监控中，等待进入稳态..."
    
    return SteadyStateResponse(
        is_monitoring=steady_state_status.is_monitoring,
        mixed_granularity_enabled=steady_state_status.mixed_granularity_enabled,
        is_in_steady_state=steady_state_status.is_in_steady_state,
        steady_state_count=steady_state_status.steady_state_count,
        last_check_time=steady_state_status.last_check_time,
        poll_interval=poll_interval,
        poll_interval_us=poll_interval * 1000000,
        message=message
    )

@app.get("/steady-state-history", response_model=SteadyStateHistoryResponse)
async def get_steady_state_history():
    """
    获取稳态历史记录
    """
    return SteadyStateHistoryResponse(
        total_count=steady_state_status.steady_state_count,
        history=steady_state_status.steady_state_history
    )

@app.get("/monitor-config", response_model=MonitorConfigResponse)
async def get_monitor_config():
    """
    获取监控配置信息
    """
    explanation = f"""
NS-3监测周期: {config.NS3_MONITOR_PERIOD_NS} 纳秒
稳态判定窗口: {config.STEADY_STATE_WINDOW_US} 微秒
询问间隔 - 高频: {config.POLL_INTERVAL_HIGH_FREQ*1000000:.2f} 微秒
询问间隔 - 中频: {config.POLL_INTERVAL_MEDIUM_FREQ*1000000:.2f} 微秒
询问间隔 - 低频: {config.POLL_INTERVAL_LOW_FREQ*1000000:.2f} 微秒
"""
    
    return MonitorConfigResponse(
        ns3_monitor_period_ns=config.NS3_MONITOR_PERIOD_NS,
        steady_state_window_us=config.STEADY_STATE_WINDOW_US,
        poll_interval_high_freq=config.POLL_INTERVAL_HIGH_FREQ,
        poll_interval_medium_freq=config.POLL_INTERVAL_MEDIUM_FREQ,
        poll_interval_low_freq=config.POLL_INTERVAL_LOW_FREQ,
        default_poll_interval=config.DEFAULT_POLL_INTERVAL,
        recommended_strategy="medium",
        explanation=explanation
    )

@app.websocket("/ws/steady-state")
async def websocket_steady_state(websocket: WebSocket):
    """
    WebSocket端点：实时推送稳态状态变化
    
    使用方式:
        const ws = new WebSocket('ws://localhost:8001/ws/steady-state');
        ws.onmessage = (event) => {
            const data = JSON.parse(event.data);
            if (data.type === 'steady_state_entered') {
                // 显示稳态加速界面
            } else if (data.type === 'steady_state_exited') {
                // 隐藏稳态加速界面
            }
        };
    """
    await manager.connect(websocket)
    try:
        # 发送欢迎消息
        await websocket.send_json({
            "type": "connected",
            "message": "已连接到稳态监控WebSocket",
            "timestamp": datetime.now().isoformat()
        })
        
        # 保持连接
        while True:
            # 接收客户端消息（心跳）
            data = await websocket.receive_text()
            
            # 响应心跳
            if data == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                })
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        print("WebSocket客户端断开连接")

# ==================== 启动说明 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

