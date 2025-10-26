#!/bin/bash

echo "=== FCT（流完成时间）详细分析 ==="
echo ""

FCT_FILE="dump/evaluation.fct1"

if [ ! -f "$FCT_FILE" ]; then
    echo "[错误] FCT文件不存在"
    exit 1
fi

echo "1. 文件基本信息:"
echo "   文件大小: $(ls -lh $FCT_FILE | awk '{print $5}')"
echo "   总流数量: $(($(wc -l < $FCT_FILE) - 1))"
echo ""

echo "2. FCT列说明:"
echo "   timestamp    - 流完成时间戳（秒）"
echo "   flowsize     - 流大小（字节）"
echo "   fctus        - FCT（微秒）"
echo "   basefctus    - 基准FCT（微秒）"
echo "   slowdown     - 减速比（实际FCT/基准FCT）"
echo "   baserttus    - 基准RTT（微秒）"
echo "   priority     - 优先级"
echo "   incastflow   - 是否为incast流"
echo ""

echo "3. FCT统计（跳过表头）:"
tail -n +2 $FCT_FILE | awk '{
    fct_sum += $3;
    slowdown_sum += $5;
    count++;
    
    if (min_fct == "" || $3 < min_fct) min_fct = $3;
    if (max_fct == "" || $3 > max_fct) max_fct = $3;
    
    if (min_slowdown == "" || $5 < min_slowdown) min_slowdown = $5;
    if (max_slowdown == "" || $5 > max_slowdown) max_slowdown = $5;
    
    # 收集所有FCT值用于计算中位数
    fct_values[count] = $3;
} END {
    if (count > 0) {
        printf "   流数量: %d\n", count;
        printf "   平均FCT: %.2f μs (%.4f ms)\n", fct_sum/count, fct_sum/count/1000;
        printf "   最小FCT: %.2f μs\n", min_fct;
        printf "   最大FCT: %.2f μs\n", max_fct;
        printf "   平均Slowdown: %.4f\n", slowdown_sum/count;
        printf "   最小Slowdown: %.4f\n", min_slowdown;
        printf "   最大Slowdown: %.4f\n", max_slowdown;
    }
}'

echo ""
echo "4. FCT时间分布（按时间戳分段）:"
tail -n +2 $FCT_FILE | awk '{
    # 将时间戳转换为微秒并分组（每100微秒一组）
    time_bucket = int($1 * 1000000 / 100) * 100;
    fct_by_time[time_bucket] += $3;
    count_by_time[time_bucket]++;
} END {
    printf "   时间段(μs)   平均FCT(μs)   流数量\n";
    printf "   ----------------------------------------\n";
    n = asorti(fct_by_time, sorted_times);
    for (i = 1; i <= (n < 10 ? n : 10); i++) {
        t = sorted_times[i];
        printf "   %6d-%6d   %8.2f      %4d\n", t, t+100, fct_by_time[t]/count_by_time[t], count_by_time[t];
    }
    if (n > 10) printf "   ... (还有 %d 个时间段)\n", n-10;
}'

echo ""
echo "5. FCT分布（按值分段）:"
tail -n +2 $FCT_FILE | awk '{
    # FCT分组（每5微秒一组）
    fct_bucket = int($3 / 5) * 5;
    count_by_fct[fct_bucket]++;
} END {
    printf "   FCT范围(μs)      流数量\n";
    printf "   --------------------------------\n";
    n = asorti(count_by_fct, sorted_fcts);
    for (i = 1; i <= (n < 15 ? n : 15); i++) {
        f = sorted_fcts[i];
        printf "   %5d - %5d      %4d\n", f, f+5, count_by_fct[f];
    }
    if (n > 15) printf "   ... (还有 %d 个分段)\n", n-15;
}'

echo ""
echo "6. 查看前10个流的详细信息:"
head -11 $FCT_FILE | column -t

echo ""
echo "7. 查看最后10个流的详细信息:"
tail -10 $FCT_FILE | column -t

echo ""
echo "8. Slowdown分析:"
tail -n +2 $FCT_FILE | awk '{
    if ($5 < 1.1) excellent++;
    else if ($5 < 1.5) good++;
    else if ($5 < 2.0) fair++;
    else poor++;
    total++;
} END {
    printf "   优秀 (< 1.1):  %4d (%.1f%%)\n", excellent, excellent*100/total;
    printf "   良好 (1.1-1.5): %4d (%.1f%%)\n", good, good*100/total;
    printf "   一般 (1.5-2.0): %4d (%.1f%%)\n", fair, fair*100/total;
    printf "   较差 (> 2.0):  %4d (%.1f%%)\n", poor, poor*100/total;
}'



