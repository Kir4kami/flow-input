#ifndef KIRAFUNCTIONS_H
#define KIRAFUNCTIONS_H

#include <fstream>
#include <iostream>


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

}
#endif