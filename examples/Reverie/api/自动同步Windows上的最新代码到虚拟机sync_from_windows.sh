#!/bin/bash
# 自动同步Windows上的最新代码到虚拟机
# 使用方法：./sync_from_windows.sh

echo "=========================================="
echo "代码同步工具"
echo "=========================================="

# 定义路径
VM_TARGET_DIR="$HOME/flow-input-local/examples/Reverie/api"
WINDOWS_SOURCE_DIR="/mnt/hgfs/flow-input-yf/examples/Reverie/api"

# 要同步的文件列表
FILES_TO_SYNC=(
    "complete_api.py"
    "complete_frontend.html"
    "topology_visualization.py"
)

echo ""
echo "目标目录: $VM_TARGET_DIR"
echo "源目录: $WINDOWS_SOURCE_DIR"
echo ""

# 检查源目录是否存在
if [ ! -d "$WINDOWS_SOURCE_DIR" ]; then
    echo "❌ 错误：共享文件夹不存在或未正确挂载"
    echo ""
    echo "尝试重新挂载共享文件夹..."
    
    # 尝试挂载
    if command -v vmhgfs-fuse &> /dev/null; then
        sudo mkdir -p /mnt/hgfs
        sudo vmhgfs-fuse .host:/ /mnt/hgfs -o allow_other -o uid=$(id -u) -o gid=$(id -g) 2>/dev/null
        sleep 1
        
        if [ -d "$WINDOWS_SOURCE_DIR" ]; then
            echo "✓ 挂载成功！"
        else
            echo "❌ 挂载失败"
            echo ""
            echo "请手动传输文件，或使用以下替代方案："
            echo "1. 使用WinSCP: 从Windows传输文件到虚拟机"
            echo "2. 使用rsync/scp: 如果Windows开启了SSH服务"
            echo "3. 手动复制粘贴: 编辑器打开文件后复制内容"
            exit 1
        fi
    else
        echo "❌ vmhgfs-fuse 未安装"
        echo ""
        echo "请安装VMware Tools:"
        echo "  sudo apt-get install open-vm-tools open-vm-tools-desktop"
        exit 1
    fi
fi

# 创建备份目录
BACKUP_DIR="$VM_TARGET_DIR/backup_$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

echo "备份目录: $BACKUP_DIR"
echo ""

# 同步文件
SUCCESS_COUNT=0
FAIL_COUNT=0

for file in "${FILES_TO_SYNC[@]}"; do
    SOURCE_FILE="$WINDOWS_SOURCE_DIR/$file"
    TARGET_FILE="$VM_TARGET_DIR/$file"
    
    if [ -f "$SOURCE_FILE" ]; then
        # 备份旧文件
        if [ -f "$TARGET_FILE" ]; then
            cp "$TARGET_FILE" "$BACKUP_DIR/$file"
            echo "✓ 已备份: $file"
        fi
        
        # 复制新文件
        cp "$SOURCE_FILE" "$TARGET_FILE"
        
        if [ $? -eq 0 ]; then
            echo "✓ 已同步: $file"
            ((SUCCESS_COUNT++))
        else
            echo "❌ 同步失败: $file"
            ((FAIL_COUNT++))
        fi
    else
        echo "⚠ 跳过（源文件不存在）: $file"
        ((FAIL_COUNT++))
    fi
done

echo ""
echo "=========================================="
echo "同步完成"
echo "成功: $SUCCESS_COUNT 个文件"
echo "失败: $FAIL_COUNT 个文件"
echo "=========================================="

if [ $SUCCESS_COUNT -gt 0 ]; then
    echo ""
    echo "是否重启API服务？(y/n)"
    read -r RESTART
    
    if [ "$RESTART" = "y" ] || [ "$RESTART" = "Y" ]; then
        echo ""
        echo "正在重启API服务..."
        
        # 停止旧服务
        pkill -f "complete_api.py"
        sleep 2
        
        # 启动新服务
        cd "$VM_TARGET_DIR"
        nohup python3 complete_api.py > api.log 2>&1 &
        
        sleep 2
        
        # 测试服务
        if curl -s http://localhost:8000/health > /dev/null; then
            echo "✓ API服务启动成功"
            echo ""
            VM_IP=$(hostname -I | awk '{print $1}')
            echo "访问地址: http://$VM_IP:8000/complete_frontend.html"
        else
            echo "❌ API服务启动失败，请检查日志:"
            echo "  tail -f $VM_TARGET_DIR/api.log"
        fi
    fi
fi

echo ""
echo "完成！"

