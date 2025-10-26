#!/bin/bash
echo "修改 stat.size 从 10 改为 7（匹配实际数据点数）"

# 备份原文件
cp /mnt/hgfs/flow-input-yf/src/point-to-point/model/flow-acc.h /mnt/hgfs/flow-input-yf/src/point-to-point/model/flow-acc.h.bak

# 修改 stat.size
sed -i 's/int size = 10;/int size = 7;/' /mnt/hgfs/flow-input-yf/src/point-to-point/model/flow-acc.h

echo "修改完成，查看修改结果："
grep "int size" /mnt/hgfs/flow-input-yf/src/point-to-point/model/flow-acc.h

echo ""
echo "重新编译..."
cd /mnt/hgfs/flow-input-yf
./ns3 build

echo ""
echo "完成！现在可以重新运行仿真了"
