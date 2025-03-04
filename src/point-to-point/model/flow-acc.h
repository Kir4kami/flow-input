#ifndef FLOW_ACC_H
#define FLOW_ACC_H

#include<map>
#include<string>
#include<vector>

using namespace std;

// 流统计结构体，记录字节数和时间戳
struct FlowStat {
    uint64_t byteCount;    // 累计的字节数
    uint64_t timestamp;    // 数据包到达的时间戳（单位：毫秒）
    std::vector<double> rate;   //用来存储速率的队列
    int size = 10;//队列大小(判断是否进入稳态)
    bool steadyStateReached = false; //是否进入稳态的标志位
};

extern uint64_t MONITOR_PERIOD; // 监测周期（us）
extern std::map<string, FlowStat> flowStats; //flowid,size字节数,存储流的统计信息



#endif