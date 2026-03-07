from fastapi import FastAPI
import os
import re
from pathlib import Path

app = FastAPI()

@app.get("/steady-state")
def check_steady():
    env_flow_stats = os.getenv("FLOW_STATS_FILE")
    if env_flow_stats:
        flow_stats = Path(env_flow_stats).expanduser().resolve()
    else:
        reverie_root = Path(__file__).resolve().parent.parent
        flow_stats = reverie_root / "flow_stats.txt"

    # 兼容部分部署形态：flow-input 根目录
    if not flow_stats.exists():
        flow_stats = Path(__file__).resolve().parent.parent.parent / "flow_stats.txt"

    if not flow_stats.exists():
        return {"error": "文件不存在"}
    
    steady_times = []
    steady_counts = []
    
    with open(flow_stats, 'r', errors='ignore') as f:
        for line in f:
            # 匹配: System entered steady state at time: 107083 ns
            m1 = re.search(r'System entered steady state at time:\s+(\d+)\s+ns', line)
            if m1:
                steady_times.append(int(m1.group(1)))
            
            # 匹配: Steady state count: 1
            m2 = re.search(r'Steady state count:\s+(\d+)', line)
            if m2:
                steady_counts.append(int(m2.group(1)))
    
    return {
        "is_steady": len(steady_times) > 0,
        "steady_state_count": len(steady_times),
        "steady_times_ns": steady_times,
        "last_steady_time_ns": steady_times[-1] if steady_times else None,
        "message": f"检测到 {len(steady_times)} 次稳态进入"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
