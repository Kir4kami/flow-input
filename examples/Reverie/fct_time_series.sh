#!/bin/bash

echo "=== FCT时间序列分析 ==="
echo ""

FCT_FILE="dump/evaluation.fct1"

echo "1. FCT随时间的变化（每个时间点的统计）:"
echo "   时间戳(ms)   平均FCT(μs)   最小FCT   最大FCT   流数量"
echo "   ------------------------------------------------------------"
tail -n +2 $FCT_FILE | awk '{
    # 将时间戳转换为毫秒
    time_ms = $1 * 1000;
    time_key = sprintf("%.2f", time_ms);
    
    fct_sum[time_key] += $3;
    count[time_key]++;
    
    if (min_fct[time_key] == "" || $3 < min_fct[time_key]) min_fct[time_key] = $3;
    if (max_fct[time_key] == "" || $3 > max_fct[time_key]) max_fct[time_key] = $3;
    
    # 保存时间戳用于排序
    times[time_key] = time_ms;
} END {
    # 手动排序（简单冒泡排序）
    n = 0;
    for (t in times) {
        time_array[n] = t;
        n++;
    }
    
    # 打印前20个时间点
    printed = 0;
    for (i = 0; i < n && printed < 20; i++) {
        for (j = i+1; j < n; j++) {
            if (times[time_array[i]] > times[time_array[j]]) {
                temp = time_array[i];
                time_array[i] = time_array[j];
                time_array[j] = temp;
            }
        }
        t = time_array[i];
        printf "   %8.2f      %10.2f    %8.2f  %8.2f   %4d\n", 
               times[t], fct_sum[t]/count[t], min_fct[t], max_fct[t], count[t];
        printed++;
    }
    if (n > 20) printf "   ... (还有 %d 个时间点)\n", n-20;
}'

echo ""
echo "2. 不同流大小的FCT:"
tail -n +2 $FCT_FILE | awk '{
    flowsize_sum[$2] += $3;
    flowsize_count[$2]++;
} END {
    printf "   流大小(Bytes)   平均FCT(μs)   流数量\n";
    printf "   -----------------------------------------\n";
    for (size in flowsize_sum) {
        printf "   %12d    %10.2f    %6d\n", size, flowsize_sum[size]/flowsize_count[size], flowsize_count[size];
    }
}'

echo ""
echo "3. 不同优先级的FCT:"
tail -n +2 $FCT_FILE | awk '{
    priority_sum[$7] += $3;
    priority_count[$7]++;
} END {
    printf "   优先级   平均FCT(μs)   流数量\n";
    printf "   ------------------------------------\n";
    for (pri in priority_sum) {
        printf "   %6d    %10.2f    %6d\n", pri, priority_sum[pri]/priority_count[pri], priority_count[pri];
    }
}'

echo ""
echo "4. 查看FCT最大的10个流:"
tail -n +2 $FCT_FILE | sort -k3 -rn | head -10 | column -t



