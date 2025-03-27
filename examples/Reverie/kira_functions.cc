#include "kira_functions.h"
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
namespace kira {
    std::ofstream log_stream;
    std::ostream cout(log_stream.rdbuf());

    bool init_log(const std::string& filename) {
        log_stream.open(filename);
        return log_stream.is_open();
    }

    StreamGuard::StreamGuard() {
        std::cout.rdbuf(cout.rdbuf()); // 重定向标准cout缓冲区
    }
    
    StreamGuard::~StreamGuard() {
        std::cout.rdbuf(nullptr); // 恢复原始缓冲区
    }
}

namespace ns3 {
}