# Flow-Input Docker 运行环境

这个文档说明如何在 Docker 中运行 Flow-Input 项目。

## 环境要求

- Docker
- Docker Compose

## 快速开始

### 1. 构建 Docker 环境

```bash
./scripts/build.sh
```

### 2. 启动容器

```bash
./scripts/run.sh
```

### 3. 进入容器

```bash
docker exec -it flow-input-container bash
```

### 4. 运行仿真

在容器内执行：

```bash
# 进入 Reverie 目录
cd examples/Reverie/

# 运行完整仿真
./sim.sh

# 或者分步运行
cd TrafficGenerator/
./trafficGen.py --input_file deepseek.txt
./merge_dependency.sh
./merge_rdma.sh
cd ../
./kira-parallel.sh
```

## 可选：使用 Jupyter

启动 Jupyter 服务：

```bash
./scripts/run-jupyter.sh
```

然后访问 http://localhost:8888

## 管理命令

### 停止服务

```bash
./scripts/stop.sh
```

### 清理环境

```bash
./scripts/clean.sh
```

## 目录结构

- `results/` - 仿真结果输出目录
- `data/` - 数据文件目录
- `scripts/` - 管理脚本

## 故障排除

### 构建失败

1. 检查 Docker 是否正常运行
2. 检查网络连接（需要下载依赖）
3. 清理后重新构建：`./scripts/clean.sh && ./scripts/build.sh`

### 运行失败

1. 检查容器日志：`docker-compose logs`
2. 检查 NS-3 是否正确构建：`./ns3 --version`
3. 检查 Python 依赖：`pip3 list`

## 开发模式

如果需要修改代码，容器会自动挂载项目目录，修改会实时生效。

## 性能优化

- 使用 `--depth 1` 进行浅克隆
- 使用 `--filter=blob:none` 减少数据传输
- 在容器内使用 `ccache` 加速编译
