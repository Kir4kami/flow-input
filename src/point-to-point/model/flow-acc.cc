#include "flow-acc.h"
#include <iostream>
#include <thread>  // 用于模拟时间延迟

using namespace std;

// 构造函数，初始化监测周期
FlowStats::FlowStats(uint64_t monitorPeriod) : MONITOR_PERIOD(monitorPeriod) {}

// 模拟接收到一个数据包的函数
void FlowStats::onPacketReceived(uint32_t flowid, uint64_t packetSize) {
    uint64_t currentTime = chrono::duration_cast<chrono::milliseconds>(chrono::steady_clock::now().time_since_epoch()).count();
    
    // 检查该流是否存在
    auto it = flowStats.find(flowid);
    
    if (it != flowStats.end()) {
        // 流已经存在，更新字节数和时间戳
        FlowStat& stat = it->second;
        stat.byteCount += packetSize;  // 增加字节数
        //stat.timestamp = currentTime;  // 更新时间戳
    } else {
        // 流不存在，创建新流
        FlowStat newStat = { packetSize, currentTime };
        flowStats[flowid] = newStat;
    }
}

// 计算速率并输出
void FlowStats::calculateRate() {
    uint64_t currentTime = chrono::duration_cast<chrono::milliseconds>(chrono::steady_clock::now().time_since_epoch()).count();
    
    // 遍历所有流，计算速率
    for (auto& entry : flowStats) {
        uint32_t flowid = entry.first;
        FlowStat& stat = entry.second;
        
        // 判断是否超过监测周期
        if (currentTime - stat.timestamp >= MONITOR_PERIOD) {
            // 计算速率（单位：字节/秒）
            double rate = (stat.byteCount * 1000.0) / MONITOR_PERIOD;  // 转换为字节/秒
            cout << "Flow ID: " << flowid << " - Rate: " << rate << " bytes/s" << endl;
            
            // 清空流的统计信息
            stat.byteCount = 0;
            stat.timestamp = currentTime;
        }
    }
}
