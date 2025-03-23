#include "kira_functions.h"

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