#!/bin/bash
# 同步实验脚本到虚拟机
# 使用方法：在VM中运行 bash sync_experiment_files.sh

echo "=========================================="
echo "实验脚本同步工具"
echo "=========================================="

# 定义路径
VM_TARGET_DIR="/home/chanel/flow-input-local/examples/Reverie/api"
WINDOWS_SOURCE_DIR="/mnt/hgfs/flow-input-yf/examples/Reverie/api"

echo ""
echo "目标目录: $VM_TARGET_DIR"
echo "源目录: $WINDOWS_SOURCE_DIR"
echo ""

# 创建目标目录
mkdir -p "$VM_TARGET_DIR"

# 要同步的实验文件
FILES_TO_SYNC=(
    "experiment_runner.py"
    "quick_comparison.py"
    "complete_api.py"
    "complete_frontend.html"
    "bandwidth_animation.html"
    "d3.v7.min.js"
    "plotly-2.32.0.min.js"
)

# 检查源目录
if [ ! -d "$WINDOWS_SOURCE_DIR" ]; then
    echo "❌ 共享文件夹未挂载: $WINDOWS_SOURCE_DIR"
    echo ""
    echo "正在尝试挂载..."
    sudo mkdir -p /mnt/hgfs
    sudo vmhgfs-fuse .host:/ /mnt/hgfs -o allow_other -o uid=$(id -u) -o gid=$(id -g) 2>/dev/null
    sleep 2
    
    if [ ! -d "$WINDOWS_SOURCE_DIR" ]; then
        echo "❌ 挂载失败！"
        echo ""
        echo "请手动复制文件："
        echo "1. 在Windows上找到这些文件："
        for file in "${FILES_TO_SYNC[@]}"; do
            echo "   - C:\\Users\\杨帆\\Desktop\\导师\\flow-input-yf\\examples\\Reverie\\api\\$file"
        done
        echo ""
        echo "2. 使用WinSCP或其他工具传输到VM: $VM_TARGET_DIR"
        exit 1
    fi
fi

# 同步文件
SUCCESS=0
FAILED=0

for file in "${FILES_TO_SYNC[@]}"; do
    SOURCE="$WINDOWS_SOURCE_DIR/$file"
    TARGET="$VM_TARGET_DIR/$file"
    
    if [ -f "$SOURCE" ]; then
        # 检查源文件大小
        SIZE=$(stat -c%s "$SOURCE" 2>/dev/null || echo "0")
        
        if [ "$SIZE" -gt "0" ]; then
            # 复制文件
            cp "$SOURCE" "$TARGET"
            
            if [ $? -eq 0 ]; then
                echo "✓ 已同步: $file ($SIZE 字节)"
                chmod +x "$TARGET" 2>/dev/null  # 添加执行权限
                ((SUCCESS++))
            else
                echo "❌ 复制失败: $file"
                ((FAILED++))
            fi
        else
            echo "⚠ 文件为空: $file"
            ((FAILED++))
        fi
    else
        echo "⚠ 文件不存在: $file"
        ((FAILED++))
    fi
done

echo ""
echo "=========================================="
echo "同步结果"
echo "成功: $SUCCESS 个文件"
echo "失败: $FAILED 个文件"
echo "=========================================="

if [ $SUCCESS -gt 0 ]; then
    echo ""
    echo "✓ 文件已同步到: $VM_TARGET_DIR"
    echo ""
    echo "下一步："
    echo "1. 清理端口: sudo lsof -ti:8000 | xargs sudo kill -9"
    echo "2. 启动API: cd $VM_TARGET_DIR && python3 complete_api.py &"
    echo "3. 运行实验: python3 quick_comparison.py"
fi

echo ""
echo "完成！"
























