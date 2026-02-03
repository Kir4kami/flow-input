#include "flow-acc.h"
#include <iostream>
#include <thread>  // 用于模拟时间延迟
#include <cmath>
#include <sstream>
#include "ns3/mixed-granularity.h"


using namespace std;

// 构造函数，初始化监测周期
std::map<uint32_t, NodeStat>NodeStats;
uint64_t MONITOR_PERIOD =10000; // 监测周期(ns)


std::map<uint32_t,SwitchStat> SwitchStats;
std::map<uint32_t,SwitchStat> exit_SwitchStats;

std::vector<SwitchStatsPair> multiSwitchStats;

bool isFirstOpen = true;
bool isFirstOpen_SwitchStats=true;
bool isFirstOpen_SwitchDiff = true;
bool g_enableSwitchDiffLogging = true;  //是否记录进入稳态和退出稳态SwitchStats的差异
std::map<std::string, FlowStat> flowStats; //flowid,size字节大小,存储流的统计信息
uint64_t steadyStateStartTime = 0;  // 记录稳态进入时间
bool inSteadyState = false;         // 标识系统是否处于稳态
double flowMinTime = 1.79769e+308;	//整个系统最小流完成时间
double transMinTime=0;
double next_trans_avail=0; //更新下一次状态转换时间
std::map<uint32_t,ns3::Time> node_latency_fix;
std::set<string> filter;
std::set<string> flow_fin_unack; //已发送待确认的流
bool flag_ENABLE_SWITCH_PORT_RATE_CALC = true; // 启用交换机端口流速率计算
bool flag_ENABLE_SWITCH_PORT_RATE_LOG = true; // 启用交换机端口流速率日志输出
bool flag_ENABLE_SWITCH_PORT_QUEUE_BYTES_LOG = true; // 启用交换机端口队列数据量日志输出
bool flag_ENABLE_QBB_DEVICE_RATE_CALC = true; // 启用QbbNetDevice接收端流速率计算


bool IsAllZero(const SwitchStat& stat) {
    if (stat.totalUsed != 0 ||
        stat.egressPoolUsed[0] != 0 ||
        stat.egressPoolUsed[1] != 0 ||
        stat.xoffTotalUsed != 0 ||
        stat.totalIngressReservedUsed != 0 ||
        stat.sharedPoolUsed != 0) {
        return false;
    }

    for (int i = 0; i < pCnt; ++i) {
        for (int j = 0; j < pCnt; ++j) {
            for (int k = 0; k < qCnt; ++k) {
                if (stat.m_bytes[i][j][k] != 0)
                    return false;
            }
        }
    }

    for (int i = 0; i < pCnt; ++i) {
        for (int j = 0; j < qCnt; ++j) {
            if (stat.ingressLpf_bytes[i][j] != 0 ||
                stat.egressLpf_bytes[i][j] != 0 ||
                stat.ingress_bytes[i][j] != 0 ||
                stat.egress_bytes[i][j] != 0) {
                return false;
            }
        }
    }

    return true;
}

void loadFlowSwitchStats(const std::string &filename) {
    std::ifstream fin(filename);
    if (!fin.is_open()) {
        std::cerr << "无法打开文件: " << filename << std::endl;
        return;
    }

    std::string line;
    SwitchStatsPair currentPair;
    bool readingNormal = false;
    uint32_t currentSwitchId = 0;

    while (std::getline(fin, line)) {
        // 去除行首尾的空白字符
        line.erase(0, line.find_first_not_of(" \t"));
        line.erase(line.find_last_not_of(" \t") + 1);

        if (line.empty()) continue; // 跳过空行

        if (line.find("SwitchStats") != std::string::npos && line.find("exit_SwitchStats") == std::string::npos) {
            readingNormal = true;
        } else if (line.find("exit_SwitchStats") != std::string::npos) {
            readingNormal = false;
        } else if (line.find("===== Switch ID:") != std::string::npos) {
            // 提取 Switch ID
            if (std::sscanf(line.c_str(), "===== Switch ID: %u =====", &currentSwitchId) == 1) {
                if (readingNormal) {
                    currentPair.normalStats[currentSwitchId] = SwitchStat();
                } else {
                    currentPair.exitStats[currentSwitchId] = SwitchStat();
                }
            }
        } else if (line.find("Port") != std::string::npos && line.find("iPort") == std::string::npos) {
            int port, queue;
            uint64_t egressBytes, ingressBytes, egressLpf, ingressLpf, bandwidth;
            double dequeueRateIngress;
            // 解析端口和队列数据
            if (std::sscanf(line.c_str(),
                            "Port %d, Queue %d: Egress Bytes = %lu, Ingress Bytes = %lu, Egress LPF = %lu, Ingress LPF = %lu, DequeueRateIngress = %lf, Bandwidth = %lu",
                            &port, &queue, &egressBytes, &ingressBytes, &egressLpf, &ingressLpf, &dequeueRateIngress, &bandwidth) == 8) {
                SwitchStat &stat = readingNormal ? currentPair.normalStats[currentSwitchId]
                                               : currentPair.exitStats[currentSwitchId];

                if (port >= 0 && port < pCnt && queue >= 0 && queue < qCnt) {
                    stat.egress_bytes[port][queue] = egressBytes;
                    stat.ingress_bytes[port][queue] = ingressBytes;
                    stat.egressLpf_bytes[port][queue] = egressLpf;
                    stat.ingressLpf_bytes[port][queue] = ingressLpf;
                    stat.dequeueRateIngress[port][queue] = dequeueRateIngress;
                    stat.bandwidth[port] = bandwidth;
                } else {
                    std::cerr << "无效的端口或队列号: Port " << port << ", Queue " << queue << std::endl;
                }
            } else {
                std::cerr << "解析行失败: " << line << std::endl;
            }
        } else if (line.find("iPort") != std::string::npos) {
            int iPort, ePort, queue;
            uint32_t bytes;
            // 解析 iPort 和 ePort 数据
            if (std::sscanf(line.c_str(), "iPort %d, ePort %d, Queue %d: %u,",
                           &iPort, &ePort, &queue, &bytes) == 4) {
                SwitchStat &stat = readingNormal ? currentPair.normalStats[currentSwitchId]
                                               : currentPair.exitStats[currentSwitchId];

                if (iPort >= 0 && iPort < pCnt && ePort >= 0 && ePort < pCnt && queue >= 0 && queue < qCnt) {
                    stat.m_bytes[iPort][ePort][queue] = bytes;
                } else {
                    std::cerr << "无效的端口或队列号: iPort " << iPort << ", ePort " << ePort << ", Queue " << queue << std::endl;
                }
            } else {
                std::cerr << "解析 iPort 行失败: " << line << std::endl;
            }
        }
    }

    // 保存最后一组数据（如果存在）
    if (!currentPair.normalStats.empty() || !currentPair.exitStats.empty()) {
        multiSwitchStats.push_back(currentPair);
    }

    fin.close();
}

void RemoveFlowStat(const std::string& flowid) {
    auto it = flowStats.find(flowid);
    if (it != flowStats.end()) {
        flowStats.erase(it);
    }
    flow_fin_unack.erase(flowid);
}

void LogSwitchStatsDiff(const std::map<uint32_t,SwitchStat>& normalStats,
                        const std::map<uint32_t,SwitchStat>& exitStats,
                        int transitionStage)
{
    if (!g_enableSwitchDiffLogging) {
        return;
    }

    std::set<uint32_t> switchIds;
    for (const auto& entry : normalStats) {
        switchIds.insert(entry.first);
    }
    for (const auto& entry : exitStats) {
        switchIds.insert(entry.first);
    }

    std::ostringstream stageStream;
    bool anySwitch = false;

    for (auto switchId : switchIds) {
        auto normalIt = normalStats.find(switchId);
        auto exitIt = exitStats.find(switchId);

        if (normalIt == normalStats.end() || exitIt == exitStats.end()) {
            continue;
        }

        const SwitchStat& normalStat = normalIt->second;
        const SwitchStat& exitStat = exitIt->second;

        std::ostringstream switchStream;
        bool switchHasOutput = false;

        for (int port = 0; port < static_cast<int>(pCnt); ++port) {
            for (int queue = 0; queue < static_cast<int>(qCnt); ++queue) {
                uint64_t ingressEnter = normalStat.ingress_bytes[port][queue];
                uint64_t ingressExit = exitStat.ingress_bytes[port][queue];
                if (ingressEnter != 0 || ingressExit != 0) {
                    int64_t ingressDelta = static_cast<int64_t>(ingressExit) - static_cast<int64_t>(ingressEnter);
                    switchHasOutput = true;
                    switchStream << "  Ingress port " << port << " queue " << queue
                                 << ": enter=" << ingressEnter
                                 << ", exit=" << ingressExit
                                 << ", delta=" << ingressDelta << std::endl;
                }

                uint64_t egressEnter = normalStat.egress_bytes[port][queue];
                uint64_t egressExit = exitStat.egress_bytes[port][queue];
                if (egressEnter != 0 || egressExit != 0) {
                    int64_t egressDelta = static_cast<int64_t>(egressExit) - static_cast<int64_t>(egressEnter);
                    switchHasOutput = true;
                    switchStream << "  Egress port " << port << " queue " << queue
                                 << ": enter=" << egressEnter
                                 << ", exit=" << egressExit
                                 << ", delta=" << egressDelta << std::endl;
                }
            }
        }

        if (switchHasOutput) {
            anySwitch = true;
            stageStream << "Switch ID: " << switchId << std::endl;
            stageStream << switchStream.str();
            stageStream << std::endl;
        }
    }

    std::ios_base::openmode mode = isFirstOpen_SwitchDiff ? std::ios::out : std::ios::app;
    std::ofstream fout("flow_switch_diff.txt", mode);
    if (!fout.is_open()) {
        throw std::runtime_error("Unable to open file for writing switch diff statistics.");
    }
    if (isFirstOpen_SwitchDiff) {
        isFirstOpen_SwitchDiff = false;
    }

    fout << "===== Transition Stage: " << transitionStage << " =====" << std::endl;
    if (anySwitch) {
        fout << stageStream.str();
    } else {
        fout << "No difference detected." << std::endl;
    }
}

void SetSwitchDiffLogging(bool enable)
{
    g_enableSwitchDiffLogging = enable;
}

bool GetSwitchDiffLogging()
{
    return g_enableSwitchDiffLogging;
}