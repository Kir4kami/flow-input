#ifndef FLOW_ACC_H
#define FLOW_ACC_H

#include<map>
#include<set>
#include<string>
#include<vector>
#include "ns3/nstime.h"

using namespace std;

// 流统计结构体，记录字节数和时间戳
struct FlowStat {
    uint64_t byteCount;    // 累计的字节数
    uint64_t timestamp;    // 数据包到达的时间戳（单位：毫秒）
    std::vector<double> rate;   //用来存储速率的队�?
    bool ifnewpacket = true; //新的周期内是否有新数据包进入
    int size = 10;//队列大小(判断是否进入稳�?)
    bool steadyStateReached = false; //是否进入稳态的标志�?
};

struct NodeStat{
    uint64_t byteCount;    // 累计的字节数
    uint64_t timestamp;
    double rate;
};

extern uint64_t MONITOR_PERIOD; // 监测周期（us�?
extern std::map<string, FlowStat> flowStats; //flowid,size字节�?,存储流的统计信息
extern std::map<uint32_t, NodeStat>NodeStats; //flowid,size字节�?,存储流的统计信息
extern bool isFirstOpen;
extern uint64_t steadyStateStartTime;  // 记录稳态进入时�?
extern bool inSteadyState;         // 标识系统是否处于稳�?
extern double flowMinTime;	//整个系统最小流完成时间
extern double transMinTime;	//整个系统最小流完成时间
extern std::map<uint32_t,ns3::Time> node_latency_fix;
extern std::set<string> filter;
extern double next_trans_avail;

extern std::set<string> flow_fin_unack;
//extern std::set<string> flow_fin_ack;

#endif