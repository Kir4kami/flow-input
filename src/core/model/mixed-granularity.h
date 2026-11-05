#ifndef NS3_MIXED_GRANULARITY_H
#define NS3_MIXED_GRANULARITY_H

#include <cstdint>
#include <string>
#include <vector>
//文件下维护着当前系统的跃迁次数及每次跃迁修正的时间
extern int transition_cnt;
extern std::vector<uint64_t> transition_delay;

namespace ns3 {
bool IsMixedGranularityEnabled();
// Absolute external release gates must execute before event-queue time shifts.
void SetPendingExternalReleases(const std::vector<uint64_t>& releases);
void MarkExternalReleaseProcessed(uint64_t releaseNs);
bool HasPendingExternalReleases();
// A just-launched flow is part of the network before its first measured packet.
void RegisterUnobservedFlow(const std::string& flowId);
void MarkFlowObserved(const std::string& flowId);
bool HasUnobservedFlows();
std::string GetSimulationOutputPath(const std::string& filename);
void RecordSteadyStateEvent(const std::string& event, uint64_t simTimeNs);
}

#endif
