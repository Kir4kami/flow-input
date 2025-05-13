/*
 * reverie-evaluation-sigcomm2023.cc
 *
 *  Created on: Feb 02, 2023
 *      Author: vamsi
 */
#include <iostream>
#include <fstream>
#include <unordered_map>
#include <time.h>
#include "ns3/core-module.h"
#include "ns3/qbb-helper.h"
#include "ns3/point-to-point-helper.h"
#include "ns3/applications-module.h"
#include "ns3/internet-module.h"
#include "ns3/global-route-manager.h"
#include "ns3/ipv4-static-routing-helper.h"
#include "ns3/packet.h"
#include "ns3/error-model.h"
#include <ns3/rdma.h>
#include <ns3/rdma-client.h>
#include <ns3/rdma-client-helper.h>
#include <ns3/rdma-driver.h>
#include <ns3/switch-node.h>
#include <ns3/sim-setting.h>
#include "ns3/mpi-interface.h"

#include <cmath>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <map>
#include <ctime>
#include <set>
#include <string>
#include <unordered_map>
#include <stdlib.h>
#include <unistd.h>
#include <vector>

#include "kira_functions.h"

using namespace ns3;
using namespace std;

#define LOSSLESS 0
#define LOSSY 1
#define DUMMY 2

# define DT 101
# define FAB 102
# define CS 103
# define IB 104
# define ABM 110
# define REVERIE 111

# define DCQCNCC 1
# define INTCC 3
# define TIMELYCC 7
# define PINTCC 10

# define CUBIC 2
# define DCTCP 4

NS_LOG_COMPONENT_DEFINE("GENERIC_SIMULATION");

#define GIGA    1000000000          // 1Gbps

std::string topology_file, flow_file;

uint32_t packet_payload_size = 1400, l2_chunk_size = 0, l2_ack_interval = 0;
double pause_time = 5, simulator_stop_time = 3.01;

double alpha_resume_interval = 55, rp_timer, ewma_gain = 1 / 16;
double rate_decrease_interval = 4;
uint32_t fast_recovery_times = 5;
std::string rate_ai, rate_hai, min_rate = "100Mb/s";
std::string dctcp_rate_ai = "1000Mb/s";
bool clamp_target_rate = false, l2_back_to_zero = false;
double error_rate_per_link = 0.0;
uint32_t has_win = 1;
uint32_t global_t = 1;
uint32_t mi_thresh = 5;
bool var_win = false, fast_react = true;
bool multi_rate = true;
bool sample_feedback = false;
double pint_log_base = 1.05;
double pint_prob = 1.0;
double u_target = 0.95;
uint32_t int_multi = 1;
bool rate_bound = true;

uint32_t ack_high_prio = 0;

uint32_t qlen_dump_interval = 100000000, qlen_mon_interval = 100;
uint64_t qlen_mon_start = 2000000000, qlen_mon_end = 2100000000;
string qlen_mon_file;

unordered_map<uint64_t, uint32_t> rate2kmax, rate2kmin;
unordered_map<uint64_t, double> rate2pmax;

double alpha_values[8] = {1, 1, 1, 1, 1, 1, 1, 1};
uint32_t PORT_START[512] = {4444};

/************************************************
 * Runtime varibles
 ***********************************************/
std::ifstream topof, flowf;
std::ifstream flowInput;
NodeContainer n;
NetDeviceContainer switchToSwitchInterfaces;
std::map< uint32_t, std::map< uint32_t, std::vector<Ptr<QbbNetDevice>> > > switchToSwitch;

// vamsi
std::map<uint32_t, uint32_t> switchNumToId;
std::map<uint32_t, uint32_t> switchIdToNum;
std::map<uint32_t, NetDeviceContainer> switchUp;
std::map<uint32_t, NetDeviceContainer> switchDown;
std::map<uint32_t, NetDeviceContainer> sourceNodes;
NodeContainer servers;
NodeContainer tors;
uint64_t nic_rate;
uint64_t maxRtt, maxBdp;
struct Interface {
    uint32_t idx;
    bool up;
    uint64_t delay;
    uint64_t bw;

    Interface() : idx(0), up(false) {}
};
map<Ptr<Node>, map<Ptr<Node>, Interface> > nbr2if;
map<Ptr<Node>, map<Ptr<Node>, vector<Ptr<Node> > > > nextHop;
map<Ptr<Node>, map<Ptr<Node>, uint64_t> > pairDelay;
map<Ptr<Node>, map<Ptr<Node>, uint64_t> > pairTxDelay;
map<uint32_t, map<uint32_t, uint64_t> > pairBw;
map<Ptr<Node>, map<Ptr<Node>, uint64_t> > pairBdp;
map<uint32_t, map<uint32_t, uint64_t> > pairRtt;
std::vector<Ipv4Address> serverAddress;

Ipv4Address node_id_to_ip(uint32_t id) {
    return Ipv4Address(0x0b000001 + ((id / 256) * 0x00010000) + ((id % 256) * 0x00000100));
}
void CalculateRoute(Ptr<Node> host) {//静态路由计算
    // queue for the BFS.
    vector<Ptr<Node> > q;
    // Distance from the host to each node.
    map<Ptr<Node>, int> dis;
    map<Ptr<Node>, uint64_t> delay;
    map<Ptr<Node>, uint64_t> txDelay;
    map<Ptr<Node>, uint64_t> bw;
    map<Ptr<Node>, Ptr<Node>> predecessor;
    // init BFS.
    q.push_back(host);
    dis[host] = 0;
    delay[host] = 0;
    txDelay[host] = 0;
    bw[host] = 0xfffffffffffffffflu;
    // BFS.
    for (int i = 0; i < (int)q.size(); i++) {
        Ptr<Node> now = q[i];
        int d = dis[now];
        for (auto it = nbr2if[now].begin(); it != nbr2if[now].end(); it++) {
            // skip down link
            if (!it->second.up)
                continue;
            Ptr<Node> next = it->first;
            // If 'next' have not been visited.
            if (dis.find(next) == dis.end()) {
                predecessor[next] = now;
                dis[next] = d + 1;
                delay[next] = delay[now] + it->second.delay;
                txDelay[next] = txDelay[now] + packet_payload_size * 1000000000lu * 8 / it->second.bw;
                bw[next] = std::min(bw[now], it->second.bw);
                // we only enqueue switch, because we do not want packets to go through host as middle point
                if (next->GetNodeType() == 1)
                    q.push_back(next);
            }
            // if 'now' is on the shortest path from 'next' to 'host'.
            if (d + 1 == dis[next]) {
                nextHop[next][host].push_back(now);
            }
        }
    }
    for (uint32_t i = 0; i < n.GetN(); ++i) {
        Ptr<Node> node = n.Get(i);
        if (node->GetNodeType() != 0 || node == host) continue;
        vector<uint32_t> path;
        Ptr<Node> current = node;
        while (current != host) {
            path.push_back(current->GetId());
            current = predecessor[current];
            if (!current) break; // 防止环路
        }
        if (current == host) {
            path.push_back(host->GetId());
            reverse(path.begin(), path.end());
        }
    }
    for (auto it : delay)
        pairDelay[it.first][host] = it.second;
    for (auto it : txDelay)
        pairTxDelay[it.first][host] = it.second;
    for (auto it : bw)
        pairBw[it.first->GetId()][host->GetId()] = it.second;
}

void CalculateRoutes(NodeContainer &n) {
    for (int i = 0; i < (int)n.GetN(); i++) {
        Ptr<Node> node = n.Get(i);
        if (node->GetNodeType() == 0)
            CalculateRoute(node);
    }
}
bool show_routing_table = false;
void SetRoutingEntries() {
    // For each node.
    for (auto i = nextHop.begin(); i != nextHop.end(); i++) {
        Ptr<Node> node = i->first;
        auto &table = i->second;
        for (auto j = table.begin(); j != table.end(); j++) {
            // The destination node.
            Ptr<Node> dst = j->first;
            // The IP address of the dst.
            Ipv4Address dstAddr = dst->GetObject<Ipv4>()->GetAddress(1, 0).GetLocal();
            // The next hops towards the dst.
            vector<Ptr<Node> > nexts = j->second;
            for (int k = 0; k < (int)nexts.size(); k++) {
                Ptr<Node> next = nexts[k];
                uint32_t interface = nbr2if[node][next].idx;
                if (node->GetNodeType() == 1)
                    DynamicCast<SwitchNode>(node)->AddTableEntry(dstAddr, interface);
                else
                    node->GetObject<RdmaDriver>()->m_rdma->AddTableEntry(dstAddr, interface);
            }
        }
    }
    // 打印所有节点的路由表
    if(show_routing_table)
        for (auto &node_entry : nextHop) {
            Ptr<Node> node = node_entry.first;
            kira::cout << "Node " << node->GetId() << " Routing Table:\n";
            for (auto &dest_entry : node_entry.second) {
                Ptr<Node> dest = dest_entry.first;
                Ipv4Address destAddr = dest->GetObject<Ipv4>()->GetAddress(1,0).GetLocal();
                kira::cout << "  Destination: " << destAddr << " -> Next Hops: ";
                for (Ptr<Node> nexthop : dest_entry.second) {
                    uint32_t interface = nbr2if[node][nexthop].idx;
                    kira::cout << "via Iface " << interface << " (Node " << nexthop->GetId() << "), ";
                }
                kira::cout << "\n";
            }
        }
}
uint64_t get_nic_rate(NodeContainer &n) {
    for (uint32_t i = 0; i < n.GetN(); i++)
        if (n.Get(i)->GetNodeType() == 0)
            return DynamicCast<QbbNetDevice>(n.Get(i)->GetDevice(1))->GetDataRate().GetBitRate();
    return 0;
}

//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/* Applications */
vector<vector<FlowInfo>> flowInfos;
u_int16_t systemId=0;
u_int16_t BatchCur=0;
u_int16_t flowCom=0;
MPI_Datatype MPI_FlowInfo;

std::vector<std::pair<uint32_t, uint32_t>> TraceActualPath(uint32_t src_node, uint32_t dst_node, uint16_t sport, uint16_t dport) {
    Ptr<Node> current = n.Get(src_node);
    uint32_t current_id = src_node;
    std::vector<std::pair<uint32_t, uint32_t>> path; // <node_id, port>
    while (current_id != dst_node) {
        // 获取当前节点的路由表
        auto& next_hops = nextHop[current][n.Get(dst_node)];
        if (next_hops.empty()) break;
        // 使用ECMP哈希选择下一跳
        uint32_t hash = ns3::GetFlowHash(src_node, dst_node, sport, dport, current_id);
        uint32_t idx = hash % next_hops.size();
        Ptr<Node> next = next_hops[idx];
        // 获取出端口
        uint32_t port = nbr2if[current][next].idx;
        path.emplace_back(current_id, port);
        current = next;
        current_id = current->GetId();
    }
    path.emplace_back(dst_node,0);
    // 打印实际路径
    kira::cout << "Flow actual path: ";
    for (size_t i = 0; i < path.size(); ++i) {
        kira::cout << path[i].first << ":" << path[i].second;
        if (i != path.size() - 1) {
            kira::cout << " -> ";
        }
    }
    kira::cout << std::endl;
    return path;
}
bool CheckPathIntersection(
    const std::vector<std::pair<uint32_t, uint32_t>>& path1,
    const std::vector<std::pair<uint32_t, uint32_t>>& path2) 
{
    std::set<std::pair<uint32_t, uint32_t>> pathSet;
    for (const auto& node_port : path1) {
        pathSet.insert(node_port);
    }
    for (const auto& node_port : path2) {
        if (pathSet.count(node_port) > 0) {
            return true;
        }
    }
    return false;
}
/******************************************************************************************************************************************************************************************************/

int main(int argc, char *argv[]){
    if (!kira::init_log("examples/Reverie/dump/checkflow.log")) {
        std::cout << "日志文件创建失败" << std::endl;
        return -1;
    }
    uint32_t src_node1=0,src_node2=32,dst_node1=16,dst_node2=48;
    uint16_t src_port1=0,src_port2=0,dst_port1=0,dst_port2=0;
    std::string confFile = "examples/Reverie/config-workload.txt";
    std::ifstream conf;
    uint32_t LEAF_COUNT = 2;
    uint32_t SERVER_COUNT = 48;
    uint32_t SPINE_COUNT = 2;
    uint32_t LINK_COUNT = 1;

    uint64_t LEAF_SERVER_CAPACITY = 10;
    uint64_t SPINE_LEAF_CAPACITY = 40;

    double START_TIME = 1;
    double END_TIME = 3;
    double FLOW_LAUNCH_END_TIME = 2;

    uint32_t incast = 5;

    bool powertcp = false;
    bool thetapowertcp = false;

    unsigned randomSeed = 1;

    CommandLine cmd;
    cmd.AddValue("src_node1","src_node1",src_node1);
    cmd.AddValue("src_port1","src_port1",src_port1);
    cmd.AddValue("dst_node1","dst_node1",dst_node1);
    cmd.AddValue("dst_port1","dst_port1",dst_port1);
    cmd.AddValue("src_node2","src_node2",src_node2);
    cmd.AddValue("src_port2","src_port2",src_port2);
    cmd.AddValue("dst_node2","dst_node2",dst_node2);
    cmd.AddValue("dst_port2","dst_port2",dst_port2);
    cmd.AddValue("show_routing","show routing table",show_routing_table);
    cmd.AddValue("conf", "config file path", confFile);
    cmd.AddValue("powertcp", "enable powertcp", powertcp);
    cmd.AddValue("thetapowertcp", "enable theta-powertcp, delay version", thetapowertcp);
    cmd.AddValue ("randomSeed", "Random seed, 0 for random generated", randomSeed);
    cmd.AddValue ("START_TIME", "sim start time", START_TIME);
    cmd.AddValue ("END_TIME", "sim end time", END_TIME);
    cmd.AddValue ("FLOW_LAUNCH_END_TIME", "flow launch process end time", FLOW_LAUNCH_END_TIME);
    uint32_t tcprequestSize = 4000000;
    cmd.AddValue ("tcprequestSize", "Query Size in Bytes", tcprequestSize);
    double tcpqueryRequestRate = 0;
    cmd.AddValue("tcpqueryRequestRate", "Query request rate (poisson arrivals)", tcpqueryRequestRate);
    uint32_t rdmarequestSize = 2000000;
    cmd.AddValue ("rdmarequestSize", "Query Size in Bytes", rdmarequestSize);
    double rdmaqueryRequestRate = 1;
    cmd.AddValue("rdmaqueryRequestRate", "Query request rate (poisson arrivals)", rdmaqueryRequestRate);
    uint32_t rdmacc = 0;//DCQCNCC;
    cmd.AddValue ("rdmacc", "specify CC mode. This is added for my convinience since I prefer cmd rather than parsing files.", rdmacc);
    uint32_t tcpcc = 2;
    cmd.AddValue ("tcpcc", "specify CC for Tcp/Ip applications", tcpcc);
    double rdmaload = 0.8;
    cmd.AddValue ("rdmaload", "RDMA load", rdmaload);
    double tcpload = 0;
    cmd.AddValue ("tcpload", "TCP load", tcpload);
    bool enable_qcn = true;
    cmd.AddValue ("enableEcn", "enable ECN markin", enable_qcn);
    uint32_t rdmaWindowCheck = 0;
    cmd.AddValue("rdmaWindowCheck", "windowCheck", rdmaWindowCheck);
    uint32_t rdmaVarWin = 9;
    cmd.AddValue("rdmaVarWin", "windowCheck", rdmaVarWin);
    uint64_t buffer_size = 2610000;//5.4;
    cmd.AddValue("buffersize", "buffer size in MB",buffer_size);
    uint32_t bufferalgIngress = DT;
    cmd.AddValue ("bufferalgIngress", "specify buffer management algorithm to be used at the ingress", bufferalgIngress);
    uint32_t bufferalgEgress = DT;
    cmd.AddValue ("bufferalgEgress", "specify buffer management algorithm to be used at the egress", bufferalgEgress);
    double egressLossyShare = 0.8;
    cmd.AddValue("egressLossyShare", "buffer pool for egress lossy specified as fraction of ingress buffer",egressLossyShare);
    std::string bufferModel = "sonic";//"blank";
    cmd.AddValue("bufferModel", "the buffer model to be used in the switch MMU", bufferModel);
    double gamma = 0.99;
    cmd.AddValue("gamma","gamma parameter value for Reverie", gamma);
    std::string alphasFile = "/home/vamsi/src/phd/codebase/ns3-datacenter/simulator/ns-3.35/examples/Reverie/alphas"; // On lakewood
    cmd.AddValue ("alphasFile", "alpha values file (should be exactly nPrior lines)", alphasFile);
    cmd.AddValue("incast", "incast", incast);
    std::string fctOutFile = "./fcts.txt";
    cmd.AddValue ("fctOutFile", "File path for FCTs", fctOutFile);
    std::string torOutFile = "./tor.txt";
    cmd.AddValue ("torOutFile", "File path for ToR statistic", torOutFile);
    std::string pfcOutFile = "./pfc.txt";
    cmd.AddValue ("pfcOutFile", "File path for pfc events", pfcOutFile);
    cmd.Parse (argc, argv);
    std::string line;
    std::fstream aFile;
    aFile.open(alphasFile);
    uint32_t p = 0;
    while ( getline( aFile, line ) && p < 8 ) { // hard coded to read only 8 alpha values.
        std::istringstream iss( line );
        double a;
        iss >> a;
        alpha_values[p] = a;
        // std::cout << "alpha-" << p << " " << alpha_values[p] << std::endl;
        p++;
    }
    aFile.close();

    SPINE_LEAF_CAPACITY = SPINE_LEAF_CAPACITY * GIGA;
    LEAF_SERVER_CAPACITY = LEAF_SERVER_CAPACITY * GIGA;

    conf.open(confFile.c_str());

    while (!conf.eof()){
        std::string key;
        conf >> key;
        if (key.compare("CLAMP_TARGET_RATE") == 0)
        {
            uint32_t v;
            conf >> v;
            clamp_target_rate = v;
        }
        else if (key.compare("PAUSE_TIME") == 0)
        {
            double v;
            conf >> v;
            pause_time = v;
        }
        else if (key.compare("PACKET_PAYLOAD_SIZE") == 0)
        {
            uint32_t v;
            conf >> v;
            packet_payload_size = v;
        }
        else if (key.compare("L2_CHUNK_SIZE") == 0)
        {
            uint32_t v;
            conf >> v;
            l2_chunk_size = v;
        }
        else if (key.compare("L2_ACK_INTERVAL") == 0)
        {
            uint32_t v;
            conf >> v;
            l2_ack_interval = v;
        }
        else if (key.compare("L2_BACK_TO_ZERO") == 0)
        {
            uint32_t v;
            conf >> v;
            l2_back_to_zero = v;
        }
        else if (key.compare("TOPOLOGY_FILE") == 0)
        {
            std::string v;
            conf >> v;
            topology_file = v;
        }
        else if (key.compare("FLOW_FILE") == 0)
        {
            std::string v;
            conf >> v;
            flow_file = v;
        }
        else if (key.compare("SIMULATOR_STOP_TIME") == 0)
        {
            double v;
            conf >> v;
            simulator_stop_time = v;
        }
        else if (key.compare("ALPHA_RESUME_INTERVAL") == 0)
        {
            double v;
            conf >> v;
            alpha_resume_interval = v;
        }
        else if (key.compare("RP_TIMER") == 0)
        {
            double v;
            conf >> v;
            rp_timer = v;
        }
        else if (key.compare("EWMA_GAIN") == 0)
        {
            double v;
            conf >> v;
            ewma_gain = v;
        }
        else if (key.compare("FAST_RECOVERY_TIMES") == 0)
        {
            uint32_t v;
            conf >> v;
            fast_recovery_times = v;
        }
        else if (key.compare("RATE_AI") == 0)
        {
            std::string v;
            conf >> v;
            rate_ai = v;
        }
        else if (key.compare("RATE_HAI") == 0)
        {
            std::string v;
            conf >> v;
            rate_hai = v;
        }
        else if (key.compare("ERROR_RATE_PER_LINK") == 0)
        {
            double v;
            conf >> v;
            error_rate_per_link = v;
        }
        else if (key.compare("RATE_DECREASE_INTERVAL") == 0) {
            double v;
            conf >> v;
            rate_decrease_interval = v;
        } else if (key.compare("MIN_RATE") == 0) {
            conf >> min_rate;
        } else if (key.compare("GLOBAL_T") == 0) {
            conf >> global_t;
        } else if (key.compare("MI_THRESH") == 0) {
            conf >> mi_thresh;
        } else if (key.compare("FAST_REACT") == 0) {
            uint32_t v;
            conf >> v;
            fast_react = v;
        } else if (key.compare("U_TARGET") == 0) {
            conf >> u_target;
        } else if (key.compare("INT_MULTI") == 0) {
            conf >> int_multi;
        } else if (key.compare("RATE_BOUND") == 0) {
            uint32_t v;
            conf >> v;
            rate_bound = v;
        } else if (key.compare("ACK_HIGH_PRIO") == 0) {
            conf >> ack_high_prio;
        } else if (key.compare("DCTCP_RATE_AI") == 0) {
            conf >> dctcp_rate_ai;
        } else if (key.compare("KMAX_MAP") == 0) {
            int n_k ;
            conf >> n_k;
            for (int i = 0; i < n_k; i++) {
                uint64_t rate;
                uint32_t k;
                conf >> rate >> k;
                rate2kmax[rate] = k;
            }
        } else if (key.compare("KMIN_MAP") == 0) {
            int n_k ;
            conf >> n_k;
            for (int i = 0; i < n_k; i++) {
                uint64_t rate;
                uint32_t k;
                conf >> rate >> k;
                rate2kmin[rate] = k;
            }
        } else if (key.compare("PMAX_MAP") == 0) {
            int n_k ;
            conf >> n_k;
            for (int i = 0; i < n_k; i++) {
                uint64_t rate;
                double p;
                conf >> rate >> p;
                rate2pmax[rate] = p;
            }
        }else if (key.compare("QLEN_MON_FILE") == 0) {
            conf >> qlen_mon_file;
        } else if (key.compare("QLEN_MON_START") == 0) {
            conf >> qlen_mon_start;
        } else if (key.compare("QLEN_MON_END") == 0) {
            conf >> qlen_mon_end;
        } else if (key.compare("MULTI_RATE") == 0) {
            int v;
            conf >> v;
            multi_rate = v;
        } else if (key.compare("SAMPLE_FEEDBACK") == 0) {
            int v;
            conf >> v;
            sample_feedback = v;
        } else if (key.compare("PINT_LOG_BASE") == 0) {
            conf >> pint_log_base;
        } else if (key.compare("PINT_PROB") == 0) {
            conf >> pint_prob;
        }
        fflush(stdout);
    }
    conf.close();
    has_win = rdmaWindowCheck;
    var_win = rdmaVarWin;

    Config::SetDefault("ns3::QbbNetDevice::PauseTime", UintegerValue(pause_time));
    Config::SetDefault("ns3::QbbNetDevice::QcnEnabled", BooleanValue(enable_qcn));

    // set int_multi
    IntHop::multi = int_multi;
    // IntHeader::mode
    if (rdmacc == TIMELYCC) // timely, use ts
        IntHeader::mode = IntHeader::TS;
    else if (rdmacc == INTCC) // hpcc, powertcp, use int
        IntHeader::mode = IntHeader::NORMAL;
    else if (rdmacc == PINTCC) // hpcc-pint
        IntHeader::mode = IntHeader::PINT;
    else // others, no extra header
        IntHeader::mode = IntHeader::NONE;

    // Set Pint
    if (rdmacc == PINTCC) {
        Pint::set_log_base(pint_log_base);
        IntHeader::pint_bytes = Pint::get_n_bytes();
        printf("PINT bits: %d bytes: %d\n", Pint::get_n_bits(), Pint::get_n_bytes());
    }

    topof.open(topology_file.c_str());
    flowf.open(flow_file.c_str());
    uint32_t node_num, switch_num, tors, link_num ;
    topof >> node_num >> switch_num >> tors >> link_num >> LEAF_SERVER_CAPACITY >> SPINE_LEAF_CAPACITY ;
    LEAF_COUNT = tors;
    SPINE_COUNT = switch_num - tors;
    SERVER_COUNT = (node_num - switch_num) / tors;
    LINK_COUNT = (link_num - (SERVER_COUNT * tors))/(LEAF_COUNT*SPINE_COUNT); // number of links between each tor-spine pair

    NodeContainer serverNodes;
    NodeContainer torNodes;
    NodeContainer spineNodes;
    NodeContainer switchNodes;
    NodeContainer allNodes;

    std::vector<uint32_t> node_type(node_num, 0);

    for (uint32_t i = 0; i < switch_num; i++) {//交换机节点
        uint32_t sid;
        topof >> sid;
        switchNumToId[i] = sid;
        switchIdToNum[sid] = i;
        if (i < tors) {
            node_type[sid] = 1;
        }
        else
            node_type[sid] = 2;
    }
    for (uint32_t i = 0; i < node_num; i++) {
        if (node_type[i] == 0) {
            Ptr<Node> node = CreateObject<Node>();
            n.Add(node);
            allNodes.Add(node);
            serverNodes.Add(node);
        }
        else {
            Ptr<SwitchNode> sw = CreateObject<SwitchNode>();
            n.Add(sw);
            switchNodes.Add(sw);
            allNodes.Add(sw);
            sw->SetAttribute("EcnEnabled", BooleanValue(enable_qcn));
            sw->SetNodeType(1);
            if (node_type[i] == 1) {
                torNodes.Add(sw);
            }
            else if (node_type[i] == 2) {
                spineNodes.Add(sw);
            }
        }
    }
    Config::SetDefault ("ns3::Ipv4GlobalRouting::FlowEcmpRouting", BooleanValue(false));
    InternetStackHelper internet;
    Ipv4GlobalRoutingHelper globalRoutingHelper;
    internet.SetRoutingHelper (globalRoutingHelper);
    internet.Install(n);
    // Assign IP to each server
    for (uint32_t i = 0; i < node_num; i++) {
        if (n.Get(i)->GetNodeType() == 0) { // is server
            serverAddress.resize(i + 1);
            serverAddress[i] = node_id_to_ip(i);
        }
    }
    //
    // Explicitly create the channels required by the topology.
    //

    Ptr<RateErrorModel> rem = CreateObject<RateErrorModel>();
    Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();
    rem->SetRandomVariable(uv);
    uv->SetStream(50);
    rem->SetAttribute("ErrorRate", DoubleValue(error_rate_per_link));
    rem->SetAttribute("ErrorUnit", StringValue("ERROR_UNIT_PACKET"));

    QbbHelper qbb;
    Ipv4AddressHelper ipv4;
    for (uint32_t i = 0; i < link_num; i++){
        uint32_t src, dst;
        std::string data_rate, link_delay;
        double error_rate;
        topof >> src >> dst >> data_rate >> link_delay >> error_rate;
        Ptr<Node> snode = n.Get(src), dnode = n.Get(dst);

        qbb.SetDeviceAttribute("DataRate", StringValue(data_rate));
        qbb.SetChannelAttribute("Delay", StringValue(link_delay));

        if (error_rate > 0){
            Ptr<RateErrorModel> rem = CreateObject<RateErrorModel>();
            Ptr<UniformRandomVariable> uv = CreateObject<UniformRandomVariable>();
            rem->SetRandomVariable(uv);
            uv->SetStream(50);
            rem->SetAttribute("ErrorRate", DoubleValue(error_rate));
            rem->SetAttribute("ErrorUnit", StringValue("ERROR_UNIT_PACKET"));
            qbb.SetDeviceAttribute("ReceiveErrorModel", PointerValue(rem));
        }
        else{
            qbb.SetDeviceAttribute("ReceiveErrorModel", PointerValue(rem));
        }

        fflush(stdout);

        // Assigne server IP
        // Note: this should be before the automatic assignment below (ipv4.Assign(d)),
        // because we want our IP to be the primary IP (first in the IP address list),
        // so that the global routing is based on our IP
        NetDeviceContainer d = qbb.Install(snode, dnode);
        //qbb.EnablePcapAll("traffic_trace");
        if (snode->GetNodeType() == 0) {
            Ptr<Ipv4> ipv4 = snode->GetObject<Ipv4>();
            ipv4->AddInterface(d.Get(0));
            ipv4->AddAddress(1, Ipv4InterfaceAddress(serverAddress[src], Ipv4Mask(0xff000000)));
        }
        if (dnode->GetNodeType() == 0) {
            Ptr<Ipv4> ipv4 = dnode->GetObject<Ipv4>();
            ipv4->AddInterface(d.Get(1));
            ipv4->AddAddress(1, Ipv4InterfaceAddress(serverAddress[dst], Ipv4Mask(0xff000000)));
        }
        if (!snode->GetNodeType()) {
            sourceNodes[src].Add(DynamicCast<QbbNetDevice>(d.Get(0)));
        }
        if (!snode->GetNodeType() && dnode->GetNodeType()) {
            switchDown[switchIdToNum[dst]].Add(DynamicCast<QbbNetDevice>(d.Get(1)));
        }
        if (snode->GetNodeType() && dnode->GetNodeType()) {
            switchToSwitchInterfaces.Add(d);
            switchUp[switchIdToNum[src]].Add(DynamicCast<QbbNetDevice>(d.Get(0)));
            switchUp[switchIdToNum[dst]].Add(DynamicCast<QbbNetDevice>(d.Get(1)));
            switchToSwitch[src][dst].push_back(DynamicCast<QbbNetDevice>(d.Get(0)));
            switchToSwitch[src][dst].push_back(DynamicCast<QbbNetDevice>(d.Get(1)));
        }

        // used to create a graph of the topology
        nbr2if[snode][dnode].idx = DynamicCast<QbbNetDevice>(d.Get(0))->GetIfIndex();
        nbr2if[snode][dnode].up = true;
        nbr2if[snode][dnode].delay = DynamicCast<QbbChannel>(DynamicCast<QbbNetDevice>(d.Get(0))->GetChannel())->GetDelay().GetTimeStep();
        nbr2if[snode][dnode].bw = DynamicCast<QbbNetDevice>(d.Get(0))->GetDataRate().GetBitRate();
        nbr2if[dnode][snode].idx = DynamicCast<QbbNetDevice>(d.Get(1))->GetIfIndex();
        nbr2if[dnode][snode].up = true;
        nbr2if[dnode][snode].delay = DynamicCast<QbbChannel>(DynamicCast<QbbNetDevice>(d.Get(1))->GetChannel())->GetDelay().GetTimeStep();
        nbr2if[dnode][snode].bw = DynamicCast<QbbNetDevice>(d.Get(1))->GetDataRate().GetBitRate();

        // This is just to set up the connectivity between nodes. The IP addresses are useless
        std::stringstream ipstring;
        ipstring << "10." << i / 254 + 1 << "." << i % 254 + 1 << ".0";
        // sprintf(ipstring, "10.%d.%d.0", i / 254 + 1, i % 254 + 1);
        ipv4.SetBase(ipstring.str().c_str(), "255.255.255.0");
        // ipv4.SetBase(ipstring, "255.255.255.0");
        ipv4.Assign(d);
    }
    nic_rate = get_nic_rate(n);
#if ENABLE_QP
    //
    // install RDMA driver
    //
    for (uint32_t i = 0; i < node_num; i++) {
        if (n.Get(i)->GetNodeType() == 0) { // is server
            // create RdmaHw
            Ptr<RdmaHw> rdmaHw = CreateObject<RdmaHw>();
            rdmaHw->SetAttribute("ClampTargetRate", BooleanValue(clamp_target_rate));
            rdmaHw->SetAttribute("AlphaResumInterval", DoubleValue(alpha_resume_interval));
            rdmaHw->SetAttribute("RPTimer", DoubleValue(rp_timer));
            rdmaHw->SetAttribute("FastRecoveryTimes", UintegerValue(fast_recovery_times));
            rdmaHw->SetAttribute("EwmaGain", DoubleValue(ewma_gain));
            rdmaHw->SetAttribute("RateAI", DataRateValue(DataRate(rate_ai)));
            rdmaHw->SetAttribute("RateHAI", DataRateValue(DataRate(rate_hai)));
            rdmaHw->SetAttribute("L2BackToZero", BooleanValue(l2_back_to_zero));
            rdmaHw->SetAttribute("L2ChunkSize", UintegerValue(l2_chunk_size));
            rdmaHw->SetAttribute("L2AckInterval", UintegerValue(l2_ack_interval));
            rdmaHw->SetAttribute("CcMode", UintegerValue(rdmacc));
            rdmaHw->SetAttribute("RateDecreaseInterval", DoubleValue(rate_decrease_interval));
            rdmaHw->SetAttribute("MinRate", DataRateValue(DataRate(min_rate)));
            rdmaHw->SetAttribute("Mtu", UintegerValue(packet_payload_size));
            rdmaHw->SetAttribute("MiThresh", UintegerValue(mi_thresh));
            rdmaHw->SetAttribute("VarWin", BooleanValue(var_win));
            rdmaHw->SetAttribute("FastReact", BooleanValue(fast_react));
            rdmaHw->SetAttribute("MultiRate", BooleanValue(multi_rate));
            rdmaHw->SetAttribute("SampleFeedback", BooleanValue(sample_feedback));
            rdmaHw->SetAttribute("TargetUtil", DoubleValue(u_target));
            rdmaHw->SetAttribute("RateBound", BooleanValue(rate_bound));
            rdmaHw->SetAttribute("DctcpRateAI", DataRateValue(DataRate(dctcp_rate_ai)));
            rdmaHw->SetAttribute("PowerTCPEnabled", BooleanValue(powertcp));
            rdmaHw->SetAttribute("PowerTCPdelay", BooleanValue(thetapowertcp));
            rdmaHw->SetPintSmplThresh(pint_prob);
            // create and install RdmaDriver
            Ptr<RdmaDriver> rdma = CreateObject<RdmaDriver>();
            Ptr<Node> node = n.Get(i);
            rdma->SetNode(node);
            rdma->SetRdmaHw(rdmaHw);

            node->AggregateObject (rdma);
            rdma->Init();
        }
    }
#endif
    // set ACK priority on hosts
    if (ack_high_prio)
        RdmaEgressQueue::ack_q_idx = 0;
    else
        RdmaEgressQueue::ack_q_idx = 3;
    // setup routing
    CalculateRoutes(n);
    SetRoutingEntries();
    /* Applications Background*/
    kira::cout << "SERVER_COUNT " << SERVER_COUNT << " LEAF_COUNT " << LEAF_COUNT << " SPINE_COUNT " << SPINE_COUNT << " LINK_COUNT " << LINK_COUNT << std::endl;
    topof.close();

    auto path1 = TraceActualPath(src_node1,dst_node1,src_port1,dst_port1);
    auto path2 = TraceActualPath(src_node2,dst_node2,src_port2,dst_port2);
    bool hasIntersection = CheckPathIntersection(path1, path2);
    kira::cout << "Paths intersection status: " << std::boolalpha << hasIntersection << std::endl;

    // Simulator::Stop(Seconds(END_TIME));
    // Simulator::Run();
    // Simulator::Destroy();
    kira::cout<<"Done"<<std::endl;
}