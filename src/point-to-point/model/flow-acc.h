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
    std::vector<double> rate;   //用来存储速率的队列
    bool ifnewpacket = true; //新的周期内是否有新数据包进入
    int size = 10;//队列大小(判断是否进入稳态)
    bool steadyStateReached = false; //是否进入稳态的标志
    uint32_t steadyCooldown = 0; //稳态降级缓冲周期计数

};

struct NodeStat{
    uint64_t byteCount;    // 累计的字节数
    uint64_t timestamp;
    double rate;
};

constexpr uint32_t pCnt = 257;  // 端口数量
constexpr uint32_t qCnt = 8;    // 队列数量
constexpr double kSteadyRelativeThreshold = 0.2; // 稳态相对波动阈值
constexpr uint32_t kSteadyMinSamples = 5;         // 判定稳态的最小样本数,没有用到
constexpr uint32_t kSteadyCooldownCycles = 3;     // 稳态降级前的缓冲周期数
constexpr double kSteadyRateEpsilon = 1e-9;       // 避免除零的速率下限


struct SwitchStat
{
    uint64_t totalUsed;//总缓冲区使用量（包括预留、headroom 和共享缓冲区）
	uint64_t egressPoolUsed[2];//lossless 和 lossy 出端口缓冲区使用量
	uint64_t xoffTotalUsed;//总 headroom 使用量
	uint64_t totalIngressReservedUsed;//更新预留缓冲区使用量
	uint64_t sharedPoolUsed;//Reverie 模型的共享缓冲区使用量
    double dequeueRateIngress[pCnt][qCnt];
    uint64_t bandwidth[pCnt];

    uint32_t m_bytes[pCnt][pCnt][qCnt];
    uint64_t ingressLpf_bytes[pCnt][qCnt];//入口队列当前占用的字节数
	uint64_t egressLpf_bytes[pCnt][qCnt];//出口队列当前占用的字节数
    uint64_t ingress_bytes[pCnt][qCnt];//入口队列的低通滤波（LPF）占用字节数
	uint64_t egress_bytes[pCnt][qCnt];//出口队列的低通滤波占用字节数
};

extern std::map<uint32_t,SwitchStat> SwitchStats;
extern std::map<uint32_t,SwitchStat> exit_SwitchStats;

struct SwitchStatsPair
{
    std::map<uint32_t, SwitchStat> normalStats; // 对应 SwitchStats
    std::map<uint32_t, SwitchStat> exitStats;   // 对应 exit_SwitchStats
};

// 包含多个 pair
extern std::vector<SwitchStatsPair> multiSwitchStats;

extern uint64_t MONITOR_PERIOD; // 监测周期（us）
extern std::map<string, FlowStat> flowStats; //flowid,size字节大小,存储流的统计信息
extern std::map<uint32_t, NodeStat>NodeStats; //flowid,size字节大小,存储流的统计信息
extern bool isFirstOpen;
extern bool isFirstOpen_SwitchStats;
extern bool isFirstOpen_SwitchDiff;
extern uint64_t steadyStateStartTime;  // 记录稳态进入时间
extern bool inSteadyState;         // 标识系统是否处于稳态
extern double flowMinTime;	//整个系统最小流完成时间
extern double transMinTime;	//整个系统最小流完成时间
extern std::map<uint32_t,ns3::Time> node_latency_fix;
extern std::set<string> filter;
extern double next_trans_avail;//更新下一次状态转换时间

extern std::set<string> flow_fin_unack; //已发送待确认的流
//extern std::set<string> flow_fin_ack;

extern bool g_enableSwitchDiffLogging;//在开启跃迁时，是否记录进入稳态和退出稳态SwitchStats的差异

bool IsAllZero(const SwitchStat& stat);
void loadFlowSwitchStats(const std::string &filename);
void RemoveFlowStat(const std::string& flowid);
void LogSwitchStatsDiff(const std::map<uint32_t,SwitchStat>& normalStats,
                        const std::map<uint32_t,SwitchStat>& exitStats,
                        int transitionStage);
void SetSwitchDiffLogging(bool enable);
bool GetSwitchDiffLogging();
#endif