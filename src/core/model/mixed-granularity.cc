#include "mixed-granularity.h"
#include <chrono>
#include <algorithm>
#include <cstdlib>
#include <fstream>
#include <iomanip>
#include <stdexcept>
#include <set>

//文件下维护着当前系统的跃迁次数以及每次跃迁修正的时间
int transition_cnt=0;
std::vector<uint64_t> transition_delay;

namespace ns3 {
namespace {
std::vector<uint64_t> pendingExternalReleases;
std::set<std::string> unobservedFlows;
}

void SetPendingExternalReleases(const std::vector<uint64_t>& releases)
{
    pendingExternalReleases = releases;
    std::sort(pendingExternalReleases.begin(), pendingExternalReleases.end());
    pendingExternalReleases.erase(std::unique(pendingExternalReleases.begin(),
        pendingExternalReleases.end()), pendingExternalReleases.end());
}

void MarkExternalReleaseProcessed(uint64_t releaseNs)
{
    pendingExternalReleases.erase(std::remove(pendingExternalReleases.begin(),
        pendingExternalReleases.end(), releaseNs), pendingExternalReleases.end());
}

bool HasPendingExternalReleases()
{
    return !pendingExternalReleases.empty();
}

void RegisterUnobservedFlow(const std::string& flowId)
{
    unobservedFlows.insert(flowId);
}

void MarkFlowObserved(const std::string& flowId)
{
    unobservedFlows.erase(flowId);
}

bool HasUnobservedFlows()
{
    return !unobservedFlows.empty();
}

bool IsMixedGranularityEnabled()
{
    const char* value = std::getenv("FLOW_INPUT_MIXED_GRANULARITY");
    return !value || std::string(value) == "1";
}

std::string GetSimulationOutputPath(const std::string& filename)
{
    const char* directory = std::getenv("FLOW_INPUT_OUTPUT_DIR");
    if (!directory || !*directory) return filename;
    const auto separator = filename.find_last_of("/\\");
    return std::string(directory) + "/" + filename.substr(
        separator == std::string::npos ? 0 : separator + 1);
}

void RecordSteadyStateEvent(const std::string& event, uint64_t simTimeNs)
{
    const char* task = std::getenv("FLOW_INPUT_TASK_ID");
    const auto taskId = task ? std::strtoul(task, nullptr, 10) : 1;
    const double wallTime = std::chrono::duration<double>(
        std::chrono::system_clock::now().time_since_epoch()).count();
    std::ofstream output(GetSimulationOutputPath("steady_events.jsonl"), std::ios::app);
    if (!output) throw std::runtime_error("Unable to write steady-state events");
    output << "{\"task_id\":" << taskId << ",\"event\":\"" << event
           << "\",\"sim_time_ns\":" << simTimeNs << ",\"wall_clock_ts\":"
           << std::fixed << std::setprecision(9) << wallTime << "}" << std::endl;
}
}
