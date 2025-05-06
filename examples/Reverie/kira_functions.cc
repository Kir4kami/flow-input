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
    uint32_t GetFlowHash(uint32_t src_node, uint32_t dst_node, uint16_t sport, uint16_t dport, uint32_t current_id) {
        union {
            uint8_t u8[12];
            uint32_t u32[3];
        } hashKey;
        hashKey.u32[0] = 0x0b000001 + ((src_node / 256) * 0x00010000) + ((src_node % 256) * 0x00000100);
        hashKey.u32[1] = 0x0b000001 + ((dst_node / 256) * 0x00010000) + ((dst_node % 256) * 0x00000100);
        hashKey.u32[2] = sport | (dport << 16);
        return ns3::EcmpHash(hashKey.u8, 12, current_id); // 使用与switch-node.cc相同的哈希算法
    }
    uint32_t EcmpHash(const uint8_t* key, size_t len, uint32_t seed) {
        uint32_t h = seed;
        if (len > 3) {
            const uint32_t* key_x4 = (const uint32_t*) key;
            size_t i = len >> 2;
            do {
                uint32_t k = *key_x4++;
                k *= 0xcc9e2d51;
                k = (k << 15) | (k >> 17);
                k *= 0x1b873593;
                h ^= k;
                h = (h << 13) | (h >> 19);
                h += (h << 2) + 0xe6546b64;
            } while (--i);
            key = (const uint8_t*) key_x4;
        }
        if (len & 3) {
            size_t i = len & 3;
            uint32_t k = 0;
            key = &key[i - 1];
            do {
                k <<= 8;
                k |= *key--;
            } while (--i);
            k *= 0xcc9e2d51;
            k = (k << 15) | (k >> 17);
            k *= 0x1b873593;
            h ^= k;
        }
        h ^= len;
        h ^= h >> 16;
        h *= 0x85ebca6b;
        h ^= h >> 13;
        h *= 0xc2b2ae35;
        h ^= h >> 16;
        return h;
    }
}