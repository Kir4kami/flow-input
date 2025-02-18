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

#include <iostream>
#include <cstdio>
#include <cmath>
#include <random>

using namespace std;
double poission_gen_interval(double avg_rate) {//avg_rate为平均到达率，返回一个随机时间间隔
    static std::default_random_engine generator;
    static std::uniform_real_distribution<double> distribution(0.0, 1.0); 
    if (avg_rate > 0) {
        double random_value = distribution(generator);
        return -log(static_cast<long double>(1.0 - random_value)) / avg_rate;
    } else {
        return 0;
    }
}
template<typename T>
T rand_range (T min, T max){
    return min + ((double)max - min) * rand () / RAND_MAX;
}
void incast_rdma (int fromLeafId, double requestRate, uint32_t requestSize,
                                    long &flowCount, int SERVER_COUNT, int LEAF_COUNT, double START_TIME, double END_TIME, double FLOW_LAUNCH_END_TIME){
    uint32_t fan = SERVER_COUNT;
    for (int i = 0; i < SERVER_COUNT; i++){
        int fromServerIndexX = fromLeafId * SERVER_COUNT + i;
        double startTime = START_TIME + poission_gen_interval (requestRate);
        while (startTime < FLOW_LAUNCH_END_TIME && startTime > START_TIME){
            int leaftarget = (fromLeafId + 1)%LEAF_COUNT;
            int destServerIndex = fromServerIndexX;
            uint32_t query = 0;
            uint32_t flowSize = double(requestSize) / double(fan);
            for (int r = 0; r < fan; r++) {
                uint32_t fromServerIndex = SERVER_COUNT * leaftarget + r ; //rand_range(0, SERVER_COUNT);
                if (DestportNumder[fromServerIndex][destServerIndex] == UINT16_MAX - 1)
                    DestportNumder[fromServerIndex][destServerIndex] = rand_range(10000, 11000);
                if (portNumder[fromServerIndex][destServerIndex] == UINT16_MAX - 1)
                    portNumder[fromServerIndex][destServerIndex] = rand_range(10000, 11000);
                uint16_t dport = DestportNumder[fromServerIndex][destServerIndex]++;
                uint16_t sport = portNumder[fromServerIndex][destServerIndex]++;
                query += flowSize;
                flowCount++;
                //RdmaClientHelper clientHelper(3, serverAddress[fromServerIndex], serverAddress[destServerIndex], sport, dport, flowSize, has_win ? (global_t == 1 ? maxBdp : pairBdp[n.Get(fromServerIndex)][n.Get(destServerIndex)]) : 0, global_t == 1 ? maxRtt : pairRtt[fromServerIndex][destServerIndex], Simulator::GetMaximumSimulationTime()-MicroSeconds(1));
                //ApplicationContainer appCon = clientHelper.Install(n.Get(fromServerIndex));
                std::cout << " from " << fromServerIndex << " to " << destServerIndex <<  " fromLeadId " << fromLeafId << " serverCount " << SERVER_COUNT << " leafCount " << LEAF_COUNT <<  std::endl;
                //appCon.Start(Seconds(startTime));
            }
            startTime += poission_gen_interval (requestRate);
            // break;
        }
        // break;
    }
}


void workload_rdma (int fromLeafId, double requestRate, struct cdf_table *cdfTable,
                           long &flowCount, int SERVER_COUNT, int LEAF_COUNT, double START_TIME, double END_TIME, double FLOW_LAUNCH_END_TIME)
{
    for (int i = 0; i < SERVER_COUNT; i++)
    {
        int fromServerIndex = fromLeafId * SERVER_COUNT + i;

        double startTime = START_TIME + poission_gen_interval (requestRate);
        while (startTime < FLOW_LAUNCH_END_TIME && startTime > START_TIME)
        {

            int destServerIndex = fromServerIndex;
            // while (destServerIndex >= fromLeafId * SERVER_COUNT && destServerIndex < fromLeafId * SERVER_COUNT + SERVER_COUNT && destServerIndex == fromServerIndex)
            // {
            //     destServerIndex = rand_range ((fromLeafId+1) * SERVER_COUNT, (fromLeafId+2) * SERVER_COUNT); // Permutation demand matrix
            // }
            // Permutation demand matrix
            int targetLeaf = fromLeafId + 1;
            if (targetLeaf == LEAF_COUNT) {
                targetLeaf = 0;
            }
            destServerIndex = targetLeaf*SERVER_COUNT + rand_range(0,SERVER_COUNT);

            if (DestportNumder[fromServerIndex][destServerIndex] == UINT16_MAX - 1)
                DestportNumder[fromServerIndex][destServerIndex] = rand_range(10000, 11000);

            if (portNumder[fromServerIndex][destServerIndex] == UINT16_MAX - 1)
                portNumder[fromServerIndex][destServerIndex] = rand_range(10000, 11000);


            uint16_t dport = DestportNumder[fromServerIndex][destServerIndex]++; //uint16_t (rand_range (PORT_START, PORT_END));
            uint16_t sport = portNumder[fromServerIndex][destServerIndex]++;

            uint64_t flowSize = gen_random_cdf (cdfTable);
            while (flowSize == 0)
                flowSize = gen_random_cdf (cdfTable);
            flowCount += 1;
            RdmaClientHelper clientHelper(3, serverAddress[fromServerIndex], serverAddress[destServerIndex], sport, dport, flowSize, has_win ? (global_t == 1 ? maxBdp : pairBdp[n.Get(fromServerIndex)][n.Get(destServerIndex)]) : 0, global_t == 1 ? maxRtt : pairRtt[fromServerIndex][destServerIndex], Simulator::GetMaximumSimulationTime());
            ApplicationContainer appCon = clientHelper.Install(n.Get(fromServerIndex));
            // std::cout << " from " << fromServerIndex << " to " << destServerIndex <<  " fromLeadId " << fromLeafId << " serverCount " << SERVER_COUNT << " leafCount " << LEAF_COUNT <<  std::endl;
            appCon.Start(Seconds(startTime));

            startTime += poission_gen_interval (requestRate);
        }
    }
    std::cout << "Finished installation of applications from leaf-" << fromLeafId << std::endl;
}


void incast_tcp (int incastLeaf, double requestRate, uint32_t requestSize, struct cdf_table *cdfTable,
                                  long &flowCount, int SERVER_COUNT, int LEAF_COUNT, double START_TIME, double END_TIME, double FLOW_LAUNCH_END_TIME)
{
    int fan = SERVER_COUNT;
    uint64_t flowSize = double(requestSize) / double(fan);

    uint32_t prior = 1; // hardcoded for tcp

    for (int incastServer = 0; incastServer < SERVER_COUNT; incastServer++)
    {
        double startTime = START_TIME + poission_gen_interval (requestRate);
        while (startTime < FLOW_LAUNCH_END_TIME && startTime > START_TIME)
        {
            // Permutation demand matrix
            int txLeaf = incastLeaf + 1;
            if (txLeaf == LEAF_COUNT) {
                txLeaf = 0;
            }
            for (uint32_t txServer = 0; txServer < fan; txServer++) {

                uint16_t port = PORT_START[incastLeaf * SERVER_COUNT + incastServer]++;
                if (port >= UINT16_MAX - 1) {
                    port = 4444;
                    PORT_START[incastLeaf * SERVER_COUNT + incastServer] = 4444;
                }
                Time startApp = (NanoSeconds (150) + MilliSeconds(rand_range(50, 500)));
                Ptr<Node> rxNode = n.Get (incastLeaf*SERVER_COUNT + incastServer);
                Ptr<Ipv4> ipv4 = rxNode->GetObject<Ipv4> ();
                Ipv4InterfaceAddress rxInterface = ipv4->GetAddress (1, 0);
                Ipv4Address rxAddress = rxInterface.GetLocal ();

                InetSocketAddress ad (rxAddress, port);
                Address sinkAddress(ad);
                Ptr<BulkSendApplication> bulksend = CreateObject<BulkSendApplication>();
                bulksend->SetAttribute("Protocol", TypeIdValue(TcpSocketFactory::GetTypeId()));
                bulksend->SetAttribute ("SendSize", UintegerValue (flowSize));
                bulksend->SetAttribute ("MaxBytes", UintegerValue(flowSize));
                bulksend->SetAttribute("FlowId", UintegerValue(flowCount++));
                bulksend->SetAttribute("priorityCustom", UintegerValue(prior));
                bulksend->SetAttribute("Remote", AddressValue(sinkAddress));
                bulksend->SetAttribute("InitialCwnd", UintegerValue (flowSize / packet_payload_size + 1));
                bulksend->SetAttribute("priority", UintegerValue(prior));
                bulksend->SetAttribute("sendAt", TimeValue(Seconds (startTime)));
                bulksend->SetStartTime (startApp);
                bulksend->SetStopTime (Seconds (END_TIME));
                n.Get (txLeaf*SERVER_COUNT + txServer)->AddApplication(bulksend);

                PacketSinkHelper sink ("ns3::TcpSocketFactory", InetSocketAddress (Ipv4Address::GetAny (), port));
                ApplicationContainer sinkApp = sink.Install (n.Get(incastLeaf*SERVER_COUNT + incastServer));
                sinkApp.Get(0)->SetAttribute("TotalQueryBytes", UintegerValue(flowSize));
                sinkApp.Get(0)->SetAttribute("recvAt", TimeValue(Seconds(startTime)));
                sinkApp.Get(0)->SetAttribute("priority", UintegerValue(1)); // ack packets are prioritized
                sinkApp.Get(0)->SetAttribute("priorityCustom", UintegerValue(1)); // ack packets are prioritized
                sinkApp.Get(0)->SetAttribute("senderPriority", UintegerValue(prior));
                sinkApp.Get(0)->SetAttribute("flowId", UintegerValue(flowCount));
                flowCount += 1;
                sinkApp.Start (startApp);
                sinkApp.Stop (Seconds (END_TIME));
                sinkApp.Get(0)->TraceConnectWithoutContext("FlowFinish", MakeBoundCallback(&TraceMsgFinish, fctOutput));
            }
            startTime += poission_gen_interval (requestRate);
        }
    }
}

void workload_tcp (int txLeaf, double requestRate, struct cdf_table *cdfTable,
                           long &flowCount, int SERVER_COUNT, int LEAF_COUNT, double START_TIME, double END_TIME, double FLOW_LAUNCH_END_TIME)
{
    uint64_t flowSize;
    uint32_t prior = 1; // hardcoded for tcp

    for (int txServer = 0; txServer < SERVER_COUNT; txServer++)
    {
        double startTime = START_TIME + poission_gen_interval (requestRate);
        while (startTime < FLOW_LAUNCH_END_TIME && startTime > START_TIME)
        {
            // Permutation demand matrix
            int rxLeaf = txLeaf + 1;
            if (rxLeaf == LEAF_COUNT) {
                rxLeaf = 0;
            }

            uint32_t rxServer = rand_range(0, SERVER_COUNT);

            uint16_t port = PORT_START[rxLeaf * SERVER_COUNT + rxServer]++;
            if (port >= UINT16_MAX - 1) {
                port = 4444;
                PORT_START[rxLeaf * SERVER_COUNT + rxServer] = 4444;
            }

            uint64_t flowSize = gen_random_cdf (cdfTable);
            while (flowSize == 0) {
                flowSize = gen_random_cdf (cdfTable);
            }

            Ptr<Node> rxNode = n.Get (rxLeaf*SERVER_COUNT + rxServer);
            Ptr<Ipv4> ipv4 = rxNode->GetObject<Ipv4> ();
            Ipv4InterfaceAddress rxInterface = ipv4->GetAddress (1, 0);
            Ipv4Address rxAddress = rxInterface.GetLocal ();

            InetSocketAddress ad (rxAddress, port);
            Address sinkAddress(ad);
            Ptr<BulkSendApplication> bulksend = CreateObject<BulkSendApplication>();
            bulksend->SetAttribute("Protocol", TypeIdValue(TcpSocketFactory::GetTypeId()));
            bulksend->SetAttribute ("SendSize", UintegerValue (flowSize));
            bulksend->SetAttribute ("MaxBytes", UintegerValue(flowSize));
            bulksend->SetAttribute("FlowId", UintegerValue(flowCount++));
            bulksend->SetAttribute("priorityCustom", UintegerValue(prior));
            bulksend->SetAttribute("Remote", AddressValue(sinkAddress));
            bulksend->SetAttribute("InitialCwnd", UintegerValue (maxBdp/packet_payload_size + 1));
            bulksend->SetAttribute("priority", UintegerValue(prior));
            bulksend->SetStartTime (Seconds(startTime));
            bulksend->SetStopTime (Seconds (END_TIME));
            n.Get (txLeaf*SERVER_COUNT + txServer)->AddApplication(bulksend);

            PacketSinkHelper sink ("ns3::TcpSocketFactory", InetSocketAddress (Ipv4Address::GetAny (), port));
            ApplicationContainer sinkApp = sink.Install (n.Get(rxLeaf*SERVER_COUNT + rxServer));
            sinkApp.Get(0)->SetAttribute("TotalQueryBytes", UintegerValue(flowSize));
            sinkApp.Get(0)->SetAttribute("priority", UintegerValue(0)); // ack packets are prioritized
            sinkApp.Get(0)->SetAttribute("priorityCustom", UintegerValue(0)); // ack packets are prioritized
            sinkApp.Get(0)->SetAttribute("flowId", UintegerValue(flowCount));
            sinkApp.Get(0)->SetAttribute("senderPriority", UintegerValue(prior));
            flowCount += 1;
            sinkApp.Start (Seconds(startTime));
            sinkApp.Stop (Seconds (END_TIME));
            sinkApp.Get(0)->TraceConnectWithoutContext("FlowFinish", MakeBoundCallback(&TraceMsgFinish, fctOutput));
            startTime += poission_gen_interval (requestRate);
        }
    }
}