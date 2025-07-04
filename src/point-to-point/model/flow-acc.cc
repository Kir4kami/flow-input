#include "flow-acc.h"
#include <iostream>
#include <thread>  // 用于模拟时间延迟
#include "ns3/mixed-granularity.h"


using namespace std;

// 构造函数，初始化监测周�?
std::map<uint32_t, NodeStat>NodeStats;
uint64_t MONITOR_PERIOD =10000; // 监测周期(ns)
bool isFirstOpen = true;
std::map<std::string, FlowStat> flowStats; //flowid,size字节�?,存储流的统计信息
uint64_t steadyStateStartTime = 0;  // 记录稳态进入时�?
bool inSteadyState = false;         // 标识系统是否处于稳�?
double flowMinTime = 1.79769e+308;	//整个系统最小流完成时间
double transMinTime=0;
double next_trans_avail=0; //更新下一次状态转换时间
std::map<uint32_t,ns3::Time> node_latency_fix;
std::set<string> filter;
std::set<string> flow_fin_unack; //已发送待确认的流