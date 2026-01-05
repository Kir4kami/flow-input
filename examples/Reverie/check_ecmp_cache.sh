#!/bin/bash
# 检查ECMP路径缓存

cd /home/chanel/flow-input-local/examples/Reverie

echo "检查ECMP路径缓存..."
echo ""

CACHE_FILE="Generator/Generator/TreeCut/ecmp_paths_cache.json"

if [ -f "$CACHE_FILE" ]; then
    echo "✓ 缓存文件存在: $CACHE_FILE"
    echo ""
    
    # 检查文件大小
    file_size=$(stat -f%z "$CACHE_FILE" 2>/dev/null || stat -c%s "$CACHE_FILE" 2>/dev/null || echo "未知")
    echo "文件大小: $file_size 字节"
    echo ""
    
    # 检查路径数量
    path_count=$(python3 -c "import json; data=json.load(open('$CACHE_FILE')); print(len(data.get('paths', [])))" 2>/dev/null || echo "无法解析")
    echo "路径数量: $path_count"
    echo ""
    
    # 检查是否有主机对之间的路径
    echo "检查主机对之间的路径（前10个）:"
    python3 -c "
import json
with open('$CACHE_FILE', 'r') as f:
    data = json.load(f)
paths = data.get('paths', [])
host_paths = [p for p in paths if p.get('src', 999) < 64 and p.get('dst', 999) < 64]
print(f'主机对路径数: {len(host_paths)}')
for p in host_paths[:10]:
    print(f\"  H{p.get('src')} -> H{p.get('dst')}: 路径长度={len(p.get('node_path', []))}\")
" 2>/dev/null || echo "无法解析JSON"
    
else
    echo "✗ 缓存文件不存在: $CACHE_FILE"
    echo ""
    echo "需要先计算ECMP路径。可能的方法："
    echo "1. 运行API接口计算路径"
    echo "2. 使用Generator工具计算路径"
fi


