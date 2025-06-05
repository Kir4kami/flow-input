
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
#include <iomanip>
#include <map>
#include <ctime>
#include <set>
#include <string>
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

Ptr<OutputStreamWrapper> fctOutput;
AsciiTraceHelper asciiTraceHelper;

Ptr<OutputStreamWrapper> torStats;
AsciiTraceHelper torTraceHelper;

Ptr<OutputStreamWrapper> pfc_file;
AsciiTraceHelper asciiTraceHelperpfc;

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
std::ifstream topof, flowf, tracef;
std::ifstream flowInput;
NodeContainer n;
NetDeviceContainer switchToSwitchInterfaces;
std::map< uint32_t, std::map< uint32_t, std::vector<Ptr<QbbNetDevice>> > > switchToSwitch;

// vamsi
std::map<uint32_t, uint32_t> switchNumToId;
std::map<uint32_t, uint32_t> switchIdToNum;
std::map<uint32_t, NetDeviceContainer> switchUp;
std::map<uint32_t, NetDeviceContainer> switchDown;
//NetDeviceContainer switchUp[switch_num];
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
// Mapping destination to next hop for each node: <node, <dest, <nexthop0, ...> > >
map<Ptr<Node>, map<Ptr<Node>, vector<Ptr<Node> > > > nextHop;
map<Ptr<Node>, map<Ptr<Node>, uint64_t> > pairDelay;
map<Ptr<Node>, map<Ptr<Node>, uint64_t> > pairTxDelay;
map<uint32_t, map<uint32_t, uint64_t> > pairBw;
map<Ptr<Node>, map<Ptr<Node>, uint64_t> > pairBdp;
map<uint32_t, map<uint32_t, uint64_t> > pairRtt;
std::map<std::pair<uint32_t,uint32_t>,std::vector<std::vector<uint32_t>>> flowPath;//流量路径
std::vector<Ipv4Address> serverAddress;

// maintain port number for each host pair
std::unordered_map<uint32_t, unordered_map<uint32_t, uint16_t> > portNumder;
std::unordered_map<uint32_t, unordered_map<uint32_t, uint16_t> > DestportNumder;

Ipv4Address node_id_to_ip(uint32_t id) {
    return Ipv4Address(0x0b000001 + ((id / 256) * 0x00010000) + ((id % 256) * 0x00000100));
}

uint32_t ip_to_node_id(Ipv4Address ip) {
    return (ip.Get() >> 8) & 0xffff;
}

void TraceMsgFinish (Ptr<OutputStreamWrapper> stream, double size, double start, bool incast, uint32_t prior )
{
    double fct, standalone_fct, slowdown;
    fct = Simulator::Now().GetNanoSeconds() - start;
    standalone_fct = maxRtt + (1e9*size * 8.0) / nic_rate;
    slowdown = fct / standalone_fct;

    *stream->GetStream ()
            << Simulator::Now().GetSeconds()
            << " " << size
            << " " << fct
            << " " << standalone_fct
            << " " << slowdown
            << " " << maxRtt
            << " " << 1
            << " " << incast
            << std::endl;
}

void qp_finish(Ptr<OutputStreamWrapper> fout, Ptr<RdmaQueuePair> q) {
    uint32_t sid = ip_to_node_id(q->sip), did = ip_to_node_id(q->dip);
    uint64_t base_rtt = pairRtt[sid][did], b = pairBw[sid][did];
    uint32_t total_bytes = q->m_size + ((q->m_size - 1) / packet_payload_size + 1) * (CustomHeader::GetStaticWholeHeaderSize() - IntHeader::GetStaticSize()); // translate to the minimum bytes required (with header but no INT)
    uint64_t standalone_fct = base_rtt + total_bytes * 8 * 1e9 / b;
    uint64_t fct = (Simulator::Now() - q->startTime).GetNanoSeconds();
    double slowdown = double(fct)/standalone_fct;
    *fout->GetStream () 
            << Simulator::Now().GetSeconds()
            << '\t' << q->m_size
            << '\t' << fct 
            << '\t' << standalone_fct
            << '\t' << slowdown
            << '\t' << base_rtt
            << '\t' << 3
            << '\t' << q->incastFlow
            << std::endl;

    // remove rxQp from the receiver
    Ptr<Node> dstNode = n.Get(did);
    Ptr<RdmaDriver> rdma = dstNode->GetObject<RdmaDriver> ();
    rdma->m_rdma->DeleteRxQp(q->sip.Get(), q->m_pg, q->sport);
}


void get_pfc(Ptr<OutputStreamWrapper> fout, Ptr<QbbNetDevice> dev, uint32_t type) {
    *fout->GetStream()
        << Simulator::Now().GetSeconds()
        << " " << dev->GetNode()->GetId()
        << " " << dev->GetNode()->GetNodeType()
        << " " << dev->GetIfIndex()
        << " " << type
        << std::endl;
    // fprintf(fout, "%lu %u %u %u %u\n", Simulator::Now().GetTimeStep(), dev->GetNode()->GetId(), dev->GetNode()->GetNodeType(), dev->GetIfIndex(), type);
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
            flowPath[{host->GetId(), node->GetId()}].emplace_back(path);
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
    // for (auto &node_entry : nextHop) {
    //     Ptr<Node> node = node_entry.first;
    //     kira::cout << "Node " << node->GetId() << " Routing Table:\n";
    //     for (auto &dest_entry : node_entry.second) {
    //         Ptr<Node> dest = dest_entry.first;
    //         Ipv4Address destAddr = dest->GetObject<Ipv4>()->GetAddress(1,0).GetLocal();
    //         kira::cout << "  Destination: " << destAddr << " -> Next Hops: ";
    //         for (Ptr<Node> nexthop : dest_entry.second) {
    //             uint32_t interface = nbr2if[node][nexthop].idx;
    //             kira::cout << "via Iface " << interface << " (Node " << nexthop->GetId() << "), ";
    //         }
    //         kira::cout << "\n";
    //     }
    // }
}
//实际转发时交换机根据五元组生成hash值，在多个下一跳中选择

uint64_t get_nic_rate(NodeContainer &n) {
    for (uint32_t i = 0; i < n.GetN(); i++)
        if (n.Get(i)->GetNodeType() == 0)
            return DynamicCast<QbbNetDevice>(n.Get(i)->GetDevice(1))->GetDataRate().GetBitRate();
    return 0;
}

//////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
/* Applications */

template<typename T>
T rand_range (T min, T max)
{
    return min + ((double)max - min) * rand () / RAND_MAX;
}

//written by Kira START
std::string ReadFolder = "examples/Reverie/task";
vector<vector<vector<FlowInfo>>> flowInfos;//流量信息，flowInfos[第几个DP][第几个phase][第几个flow]
uint16_t systemId=0;
uint16_t systemNum=0;
uint16_t operateNum=0;
vector<uint16_t> phaseCur;
vector<uint16_t> flowCom;
std::unordered_map<FlowKey,uint16_t> flowToPar;//多个DP并行
std::vector<vector<int>> opDependence;//存储rdma_operate的依赖关系
std::vector<bool> opStart;//记录这个operate有没有开始过,避免重复启动
MPI_Datatype MPI_FlowInfo;

void TraceActualPath(uint32_t src_node, uint32_t dst_node, uint16_t sport, uint16_t dport) {
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
}

void flowSend(FlowInfo &flow){
    RdmaClientHelper clientHelper(3, serverAddress[flow.src_node], serverAddress[flow.dst_node], flow.src_port, flow.dst_port,
        flow.msg_len, has_win ? (global_t == 1 ? maxBdp : pairBdp[n.Get(flow.src_node)][n.Get(flow.dst_node)]) : 0,
        global_t == 1 ? maxRtt : pairRtt[flow.src_node][flow.dst_node], Simulator::GetMaximumSimulationTime());    
    ApplicationContainer appCon = clientHelper.Install(n.Get(flow.src_node));

    appCon.Start(Seconds(0));//to be changed?
    kira::cout <<"system "<< systemId << " from " << flow.src_node << " to " << flow.dst_node <<
            " fromportNumber " << flow.src_port <<" destportNumder " << flow.dst_port <<
            " time " << Simulator::Now().GetSeconds() << " flowsize "<< flow.msg_len <<" ";
    TraceActualPath(flow.src_node, flow.dst_node, flow.src_port, flow.dst_port);
}
MPI_Datatype create_MPI_FlowInfo() {
    // 定义结构体的成员数量（7个）
    const int num_members = 7;
    MPI_Datatype types[num_members] = {
        MPI_CHAR,           // type[32]
        MPI_INT,            // src_node
        MPI_INT,            // src_port
        MPI_INT,            // dst_node
        MPI_INT,            // dst_port
        MPI_INT,            // priority
        MPI_UNSIGNED_LONG_LONG // msg_len (uint64_t)
    };
    int block_lengths[num_members] = {32, 1, 1, 1, 1, 1, 1};  // 每个成员的块长度
    // 计算每个成员的位移
    MPI_Aint displacements[num_members];
    FlowInfo dummy={0,0,0,0,0,0,0};  // 临时结构体实例，用于计算地址偏移
    MPI_Get_address(&dummy.type,         &displacements[0]);
    MPI_Get_address(&dummy.src_node,     &displacements[1]);
    MPI_Get_address(&dummy.src_port,     &displacements[2]);
    MPI_Get_address(&dummy.dst_node,     &displacements[3]);
    MPI_Get_address(&dummy.dst_port,     &displacements[4]);
    MPI_Get_address(&dummy.priority,     &displacements[5]);
    MPI_Get_address(&dummy.msg_len,      &displacements[6]);
    // 转换为相对于结构体起始地址的位移
    for (int i = num_members - 1; i >= 0; i--) 
        displacements[i] -= displacements[0];
    // 创建 MPI 数据类型
    MPI_Datatype MPI_FlowInfo;
    MPI_Type_create_struct(num_members, block_lengths, displacements, types, &MPI_FlowInfo);
    MPI_Type_commit(&MPI_FlowInfo);
    return MPI_FlowInfo;
}

void sendPhase(uint16_t par){//指定operate发送下一个phase
    for(FlowInfo flow:flowInfos[par][phaseCur[par]])
        flowSend(flow);
};
void checkDpd(){//检查依赖关系,该启动的启动
    for(int i=0;i<operateNum;i++){
        if(opStart[i])//如果这个operate已经启动了
            continue;
        bool flag=true;
        for(int j=opDependence[i][0];j<=opDependence[i][1];j++){
            if(phaseCur[j]<flowInfos[j].size()){//依赖的operate没有完成
                flag=false;
                break;
            }
        }
        if(flag){//这个operate的依赖都完成了,那我该开始这个operate了
            kira::cout<<"operate "<< i <<" start"<<std::endl;
            opStart[i]=true;
            for(size_t phase=0;phase<flowInfos[i].size();phase++)//启动operate时记录映射
                for(FlowInfo flow:flowInfos[i][phase])
                    flowToPar[{flow.src_node,flow.dst_node}]=i;
            for(FlowInfo flow:flowInfos[i][phaseCur[i]])
                flowSend(flow);
        }
    }
}
void flowinput_cb(Ptr<OutputStreamWrapper> fout, Ptr<RdmaQueuePair> q){
    FlowKey key = {(int)ip_to_node_id(q->sip),(int)ip_to_node_id(q->dip)};
    auto it=flowToPar.find(key);
    if(it==flowToPar.end()){
        kira::cout << (int)ip_to_node_id(q->sip)<< " " << (int)ip_to_node_id(q->dip)<<std::endl;
        kira::cout << "错误：键不存在于 unordered_map 中！" << std::endl;
        std::exit(EXIT_FAILURE); 
    }
    uint16_t par=it->second;
    flowCom[par]++;
    kira::cout<<" operate "<< par <<" phase "<<phaseCur[par]<<" flow "<<
        flowCom[par]<<" "<<Simulator::Now().GetSeconds()<<std::endl;
    if(flowCom[par]>=flowInfos[par][phaseCur[par]].size()){//完成一个phase
        phaseCur[par]++;
        flowCom[par]=0;
        kira::cout<<"operate "<<par<<" complete a phase"<<std::endl;
        if(phaseCur[par]>=flowInfos[par].size()){//完成一个operate
            kira::cout<<"operate "<<par<<" complete a operate"<<std::endl;
            Simulator::Schedule(Seconds(0),checkDpd);
        }
        else//这个operate没完成,继续发送下一个phase
            Simulator::Schedule(Seconds(0),sendPhase,par);
    }
}
uint16_t DST;
uint16_t PARRAL=1;
// void branch_read_info(uint16_t sysid){//branch process send flowInfo
//     kira::cout<<"system :"<< systemId <<"Reading flow info"<< std::endl;
//     for(int i=systemId-1;i<PARRAL;i+=(systemNum-1)){
//         flowInfos.clear();
//         std::string flowInputFileName= "examples/Reverie/rdma_operate"+to_string(i)+".txt";
//         flowInput.open(flowInputFileName.c_str());
//         if (!flowInput.is_open())
//             kira::cout << "system :"<< systemId <<"unable to open flowInputFile!" << std::endl;
//         std::string line;
//         int batch = -1;
//         while (std::getline(flowInput, line)) {
//             if (line.empty() || line[0] == '#' || line.find("stat")!=string::npos) continue;
//             std::stringstream ss(line);
//             std::string  type_str;
//             if (line.find("phase")!=string::npos){//phase
//                 double phase;
//                 ss >> type_str >> phase;
//                 flowInfos.emplace_back(vector<FlowInfo> {});
//                 batch++;
//                 continue;
//             }
//             FlowInfo flow;
//             ss >> type_str >> flow.type;
//             ss >> type_str >> flow.src_node;
//             ss >> type_str >> flow.src_port;
//             ss >> type_str >> flow.dst_node;
//             ss >> type_str >> flow.dst_port;
//             ss >> type_str >> flow.priority;
//             ss >> type_str >> flow.msg_len;
//             flowInfos[batch].emplace_back(flow);
//         }
//         flowInput.close();//read file end
//         int length=flowInfos.size();
//         MPI_Send(&length, 1, MPI_INT, 0, 0, MPI_COMM_WORLD);
//         for (auto& row : flowInfos) {
//             int cols = row.size();
//             MPI_Send(&cols, 1, MPI_INT, 0, 1, MPI_COMM_WORLD);
//             MPI_Send(row.data(), cols, MPI_FlowInfo, 0, 2, MPI_COMM_WORLD);
//         }
//     }
// }

//解析范围字符串
void parseRange(const std::string& s, int& start, int& end) {
    size_t dash = s.find('-');
    if (dash == string::npos)
        start = end = stoi(s);
    else {
        start = stoi(s.substr(0, dash));
        end = stoi(s.substr(dash+1));
    }
}

//解析依赖配置文件
void parseDependenceFile() {
    kira::cout<<"Reading dependence"<< std::endl;
    string filename = "examples/Reverie/rdma_operates/dependence.txt";
    opDependence.resize(operateNum, {-1,-1});
    ifstream fin(filename);
    string line;
    while (getline(fin, line)) {
        if (line.empty() || line[0] == '#') continue;

        size_t colon = line.find(':');
        if (colon == string::npos) {
            kira::cout << "Invalid line format: " << line << std::endl;
            continue;
        }
        string dependent = line.substr(0, colon);
        string prerequisite = line.substr(colon+1);
        int depStart, depEnd, preStart, preEnd;
        parseRange(dependent, depStart, depEnd);
        parseRange(prerequisite, preStart, preEnd);
        // 为每个依赖operate设置范围
        for (int i = depStart; i <= depEnd; i++) {
            opDependence[i][0] = preStart;
            opDependence[i][1] = preEnd;
        }
    }
    fin.close();
}
void workload_rdma (long &flowCount, int SERVER_COUNT, int LEAF_COUNT, double START_TIME, double END_TIME, double FLOW_LAUNCH_END_TIME){
    parseDependenceFile();
    kira::cout<<"Reading flow info"<< std::endl;
    flowInfos.resize(operateNum);
    flowCom.resize(operateNum,0);
    phaseCur.resize(operateNum,0);
    opStart.resize(operateNum,false);
    std::string line;
    for(int i=0;i<operateNum;i++){
        std::string flowInputFileName= "examples/Reverie/rdma_operates/rdma_operate"+to_string(i)+".txt";
        flowInput.open(flowInputFileName.c_str());
        if (!flowInput.is_open())
            kira::cout << "system :"<< systemId <<" unable to open flowInputFile!" << std::endl;
        int phase = -1;
        while (std::getline(flowInput, line)) {
            if (line.empty() || line[0] == '#' || line.find("stat")!=string::npos) continue;
            std::stringstream ss(line);
            std::string type_str;
            if (line.find("phase")!=string::npos){//phase
                ss >> type_str >> type_str;
                flowInfos[i].emplace_back(vector<FlowInfo> {});
                phase++;
                continue;
            }
            FlowInfo flow;
            ss >> type_str >> flow.type;
            ss >> type_str >> flow.src_node;
            ss >> type_str >> flow.src_port;
            ss >> type_str >> flow.dst_node;
            ss >> type_str >> flow.dst_port;
            ss >> type_str >> flow.priority;
            ss >> type_str >> flow.msg_len;
            flowInfos[i][phase].emplace_back(flow);
            //flowToPar[{flow.src_node,flow.dst_node}]=i;
        }
        flowInput.close();
        if(opDependence[i][0]!=-1)//如果这个operate有依赖,跳过
            continue;
        opStart[i]=true;
        for(size_t phase=0;phase<flowInfos[i].size();phase++)//启动operate时记录映射
            for(FlowInfo flow:flowInfos[i][phase])
                flowToPar[{flow.src_node,flow.dst_node}]=i;
        for(FlowInfo flow:flowInfos[i][phaseCur[i]])//start first phase
            flowSend(flow);
    }
    
}

//written by Kira END

uint32_t flowEnd = 0;

void printBuffer(Ptr<OutputStreamWrapper> fout, NodeContainer switches, double delay) {
    for (uint32_t i = 0; i < switches.GetN(); i++) {
        if (switches.Get(i)->GetNodeType()) { // switch
            Ptr<SwitchNode> sw = DynamicCast<SwitchNode>(switches.Get(i));
            *fout->GetStream() 
                << i
                << " " << sw->m_mmu->totalUsed
                << " " << sw->m_mmu->egressPoolUsed[0]
                << " " << sw->m_mmu->egressPoolUsed[1]
                << " " << sw->m_mmu->totalUsed - sw->m_mmu->xoffTotalUsed
                << " " << sw->m_mmu->xoffTotalUsed
                << " " << sw->m_mmu->sharedPoolUsed
                << " " << Simulator::Now().GetSeconds()
                << std::endl;
        }
    }
    if (Simulator::Now().GetSeconds() < flowEnd)
        Simulator::Schedule(Seconds(delay), printBuffer, fout, switches, delay);
}


/******************************************************************************************************************************************************************************************************/

int main(int argc, char *argv[]){
    MpiInterface::Enable(&argc, &argv); // 初始化MPI
    systemId = MpiInterface::GetSystemId(); // 获取当前进程ID
    systemNum = MpiInterface::GetSize();//记录当前所有进程数
    MPI_FlowInfo = create_MPI_FlowInfo();
    
    if (!kira::init_log("examples/Reverie/dump/system"+to_string(systemId)+".log")) {
        std::cout << "system: " << systemId << " 日志文件创建失败" << std::endl;
        return -1;
    }

    // if(systemId!=0){ // 分支进程
    //     branch_read_info(systemId);
    //     kira::cout<<"system" <<systemId<<"read end"<<std::endl;
    //     MPI_Barrier(MPI_COMM_WORLD); // 等待所有进程完成读取
    //     kira::cout<<"system" <<systemId<<"end"<<std::endl;
    //     MpiInterface::Disable(); // 禁用MPI
    //     return systemId;
    // }
    
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
    cmd.AddValue("DST", "number of system", DST);
    cmd.AddValue("OPERATENUM", "number of operate", operateNum);
    cmd.AddValue("PARRAL", "PARRALEL DP", PARRAL);
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

    flowEnd = FLOW_LAUNCH_END_TIME;

    fctOutput = asciiTraceHelper.CreateFileStream (fctOutFile);

    *fctOutput->GetStream () 
            << "timestamp"
            << " " << "flowsize"
            << " " << "fctus"
            << " " << "basefctus"
            << " " << "slowdown"
            << " " << "baserttus"
            << " " << "priority"
            << " " << "incastflow"
            << std::endl;

    torStats = torTraceHelper.CreateFileStream (torOutFile);
    *torStats->GetStream() 
                << "switch"
                << " " << "totalused"
                << " " << "egressOccupancyLossless"
                << " " << "egressOccupancyLossy"
                << " " << "ingressPoolOccupancy"
                << " " << "headroomOccupancy"
                << " " << "sharedPoolOccupancy"
                << " " << "time"
                << std::endl;

    pfc_file = asciiTraceHelperpfc.CreateFileStream(pfcOutFile);

    *pfc_file->GetStream()
        << "Time"
        << " " << "NodeId"
        << " " << "NodeType"
        << " " << "IfIndex"
        << " " << "type"
        << std::endl;

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
    kira::cout << "config finished" << std::endl;

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
    NS_LOG_INFO("Create nodes.");
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
    NS_LOG_INFO("Create channels.");
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
    for (uint32_t i = 0; i < link_num; i++)
    {
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

        // setup PFC trace
        DynamicCast<QbbNetDevice>(d.Get(0))->TraceConnectWithoutContext("QbbPfc", MakeBoundCallback (&get_pfc, pfc_file, DynamicCast<QbbNetDevice>(d.Get(0))));
        DynamicCast<QbbNetDevice>(d.Get(1))->TraceConnectWithoutContext("QbbPfc", MakeBoundCallback (&get_pfc, pfc_file, DynamicCast<QbbNetDevice>(d.Get(1))));
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
            rdma->TraceConnectWithoutContext("QpComplete", MakeBoundCallback (qp_finish, fctOutput));
            rdma->TraceConnectWithoutContext("QpComplete", MakeBoundCallback (flowinput_cb, fctOutput));
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
    //
    // get BDP and delay
    //
    maxRtt = maxBdp = 0;
    uint64_t minRtt = 1e9;
    for (uint32_t i = 0; i < node_num; i++) {
        if (n.Get(i)->GetNodeType() != 0)
            continue;
        for (uint32_t j = 0; j < node_num; j++) {
            if (n.Get(j)->GetNodeType() != 0)
                continue;
            if (i == j)
                continue;
            uint64_t delay = pairDelay[n.Get(i)][n.Get(j)];
            uint64_t txDelay = pairTxDelay[n.Get(i)][n.Get(j)];
            uint64_t rtt = delay * 2 + txDelay;
            uint64_t bw = pairBw[i][j];
            uint64_t bdp = rtt * bw / 1000000000 / 8;
            pairBdp[n.Get(i)][n.Get(j)] = bdp;
            pairRtt[i][j] = rtt;
            if (bdp > maxBdp)
                maxBdp = bdp;
            if (rtt > maxRtt)
                maxRtt = rtt;
            if (rtt < minRtt)
                minRtt = rtt;
        }
    }
    printf("maxRtt=%lu maxBdp=%lu minRtt=%lu\n", maxRtt, maxBdp, minRtt);

    // config switch
    // The switch mmu runs Dynamic Thresholds (DT) by default.
    uint64_t totalHeadroom=0;
    for (uint32_t i = 0; i < node_num; i++) {
        if (n.Get(i)->GetNodeType()) { // is switch
            Ptr<SwitchNode> sw = DynamicCast<SwitchNode>(n.Get(i));
            totalHeadroom = 0;
            sw->m_mmu->SetIngressLossyAlg(bufferalgIngress);
            sw->m_mmu->SetIngressLosslessAlg(bufferalgIngress);
            sw->m_mmu->SetEgressLossyAlg(bufferalgEgress);
            sw->m_mmu->SetEgressLosslessAlg(bufferalgEgress);
            sw->m_mmu->SetABMalphaHigh(1024);
            sw->m_mmu->SetABMdequeueUpdateNS(maxRtt);
            sw->m_mmu->SetPortCount(sw->GetNDevices() - 1); // set the actual port count here so that we don't always iterate over the default 256 ports.
            sw->m_mmu->SetBufferModel(bufferModel);
            sw->m_mmu->SetGamma(gamma);
            // std::cout << "ports " << sw->GetNDevices() << " node " << i << std::endl;
            for (uint32_t j = 1; j < sw->GetNDevices(); j++) {
                Ptr<QbbNetDevice> dev = DynamicCast<QbbNetDevice>(sw->GetDevice(j));
                uint64_t rate = dev->GetDataRate().GetBitRate();
                // set port bandwidth in the mmu, used by ABM.
                sw->m_mmu->bandwidth[j] = rate;
                for (uint32_t qu = 0; qu < 8; qu++) {
                    if (qu == 3 || qu == 0) { // lossless
                        sw->m_mmu->SetAlphaIngress(alpha_values[qu], j, qu);
                        sw->m_mmu->SetAlphaEgress(10000, j, qu);
                        // set pfc
                        double delay = DynamicCast<QbbChannel>(dev->GetChannel())->GetDelay().GetSeconds();
                        uint32_t headroom = (packet_payload_size + 48) * 2 + 3860 + (2 * rate * delay / 8);
                        // std::cout << headroom << std::endl;
                        sw->m_mmu->SetHeadroom(headroom, j, qu);
                        totalHeadroom += headroom;
                    }
                    else { // lossy
                        sw->m_mmu->SetAlphaIngress(10000, j, qu);
                        sw->m_mmu->SetAlphaEgress(alpha_values[qu], j, qu);
                    }

                    // set ecn
                    NS_ASSERT_MSG(rate2kmin.find(rate) != rate2kmin.end(), "must set kmin for each link speed");
                    NS_ASSERT_MSG(rate2kmax.find(rate) != rate2kmax.end(), "must set kmax for each link speed");
                    NS_ASSERT_MSG(rate2pmax.find(rate) != rate2pmax.end(), "must set pmax for each link speed");
                    sw->m_mmu->ConfigEcn(j, rate2kmin[rate], rate2kmax[rate], rate2pmax[rate]);
                }

            }
            sw->m_mmu->SetBufferPool(buffer_size);
            sw->m_mmu->SetIngressPool(buffer_size - totalHeadroom);
            sw->m_mmu->SetSharedPool(buffer_size  - totalHeadroom);
            sw->m_mmu->SetEgressLosslessPool(buffer_size);
            sw->m_mmu->SetEgressLossyPool((buffer_size - totalHeadroom) * egressLossyShare);
            sw->m_mmu->node_id = sw->GetId();
        }
        if (n.Get(i)->GetNodeType())
            kira::cout << "total headroom: " << totalHeadroom << " ingressPool " << buffer_size - totalHeadroom << " egressLosslessPool " 
                      << buffer_size << " egressLossyPool " << (uint64_t)((buffer_size - totalHeadroom) * egressLossyShare) 
                      << " sharedPool " << buffer_size - totalHeadroom <<  std::endl;
    }
    //
    // setup switch CC
    //
    for (uint32_t i = 0; i < node_num; i++) {
        if (n.Get(i)->GetNodeType()) { // switch
            Ptr<SwitchNode> sw = DynamicCast<SwitchNode>(n.Get(i));
            sw->SetAttribute("CcMode", UintegerValue(rdmacc));
            sw->SetAttribute("MaxRtt", UintegerValue(maxRtt));
            sw->SetAttribute("PowerEnabled", BooleanValue(powertcp));
        }
    }

    Ipv4GlobalRoutingHelper::PopulateRoutingTables();

    NS_LOG_INFO("Create Applications.");
    // maintain port number for each host
    for (uint32_t i = 0; i < node_num; i++) {
        if (n.Get(i)->GetNodeType() == 0)
            for (uint32_t j = 0; j < node_num; j++) {
                if (n.Get(j)->GetNodeType() == 0)
                    portNumder[i][j] = rand_range(10000, 11000); // each host pair use port number from 10000
            }
    }
    DestportNumder = portNumder;

/////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
    /* Applications Background*/
    double oversubRatio = static_cast<double>(SERVER_COUNT * LEAF_SERVER_CAPACITY) / (SPINE_LEAF_CAPACITY * SPINE_COUNT * LINK_COUNT);
    kira::cout << "SERVER_COUNT " << SERVER_COUNT << " LEAF_COUNT " << LEAF_COUNT << " SPINE_COUNT " << SPINE_COUNT << " LINK_COUNT " << LINK_COUNT << " RDMALOAD " << rdmaload << " TCPLOAD " << tcpload << " oversubRatio " << oversubRatio << std::endl;
    if (randomSeed == 0){
        srand ((unsigned)time (NULL));
    }
    else{
        srand (randomSeed);
    }

    for (uint32_t i = 0; i < SERVER_COUNT * LEAF_COUNT; i++)
        PORT_START[i] = 4444;
    long flowCount = 1;

    // 主进程处理
    workload_rdma(flowCount, SERVER_COUNT, LEAF_COUNT, START_TIME, END_TIME, FLOW_LAUNCH_END_TIME);

    kira::cout << "apps finished" << std::endl;
    topof.close();
    tracef.close();
    double delay = 1.5 * maxRtt * 1e-9; // 10 micro seconds
    Simulator::Schedule(Seconds(START_TIME), printBuffer, torStats, spineNodes, delay);

    Ipv4GlobalRoutingHelper::PopulateRoutingTables();
    NS_LOG_INFO("Run Simulation.");
    Simulator::Stop(Seconds(END_TIME));
    Simulator::Run();
    Simulator::Destroy();
    MPI_Barrier(MPI_COMM_WORLD); // 等待所有进程完成模拟
    MPI_Type_free(&MPI_FlowInfo); // 释放MPI数据类型
    NS_LOG_INFO("Done.");
    kira::cout<<"Done"<<std::endl;
    MpiInterface::Disable(); // 禁用MPI
}
