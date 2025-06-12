#ifndef KIRAFUNCTIONS_H
#define KIRAFUNCTIONS_H

#include <fstream>
#include <iostream>
#include <functional>

namespace kira {
    // 文件流对象声明
    extern std::ofstream log_stream;
    
    // 自定义输出流对象
    class FileBuffer : public std::streambuf { /*...*/ };
    extern std::ostream cout;
    
    // 初始化日志文件
    bool init_log(const std::string& filename);
    
    // RAII缓冲区管理
    class StreamGuard {
    public:
        StreamGuard();
        ~StreamGuard();
    };
}
// extern u_int16_t systemId;
struct FlowInfo {
    char type[32];
    int src_node;
    int src_port;
    int dst_node;
    int dst_port;
    int priority;
    uint64_t msg_len;
};
namespace ns3{
    uint32_t GetFlowHash(uint32_t src_node, uint32_t dst_node, uint16_t sport, uint16_t dport, uint32_t current_id);
    uint32_t EcmpHash(const uint8_t* key, size_t len, uint32_t seed);
    struct FlowKey {
        int src;
        int dst;    
        bool operator==(const FlowKey& o) const {
            return src == o.src && dst == o.dst;
        }
    };
}
namespace std{
    template<>
    struct hash<ns3::FlowKey> {
        size_t operator()(const ns3::FlowKey& k) const {
             return hash<int>()(k.src) ^ (hash<int>()(k.dst) << 1);
        }
    };
}
#endif