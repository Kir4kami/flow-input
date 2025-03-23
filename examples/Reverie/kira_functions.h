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
