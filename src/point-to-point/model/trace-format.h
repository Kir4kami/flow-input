#ifndef TRACE_FORMAT_H
#define TRACE_FORMAT_H

#include <stdint.h>
#include <cstdio>
#include <cassert>
#include <vector>
#include <stddef.h>
#include <cstring>
#include <string>
#include <iostream>

namespace ns3 {

// 枚举类型定义不同类型的事件
enum PEvent {
    Recv = 0,
    Enqu = 1,
    Dequ = 2,
    Drop = 3
};

// 主要的跟踪格式结构体
struct TraceFormat {
    uint64_t time;        // 时间戳
    uint16_t node;        // 节点ID
    uint8_t intf;         // 接口ID
    uint8_t qidx;         // 队列索引
    uint32_t qlen;        // 队列长度
    uint32_t sip;         // 源IP地址
    uint32_t dip;         // 目的IP地址
    uint16_t size;        // 数据包大小
    uint8_t l3Prot;       // 第三层协议类型
    uint8_t event;        // 事件类型
    uint8_t ecn;          // IP ECN位
    uint8_t nodeType;     // 节点类型（0: 主机, 1: 交换机）

    union {
        struct {
            uint16_t sport, dport; // 源端口和目的端口
            uint32_t seq;          // 序列号
            uint64_t ts;           // 时间戳
            uint16_t pg;           // PG值
            uint16_t payload;      // 不包括SeqTsHeader的大小
        } data;

        struct {
            uint16_t fid;          // 流ID
            uint8_t qIndex;        // 队列索引
            uint8_t ecnBits;       // CNP中的ECN位
            union {
                struct {
                    uint16_t qfb;   // QFB值
                    uint16_t total; // 总数
                };
                uint32_t seq;       // 序列号
            };
        } cnp;

        struct {
            uint16_t sport, dport; // 源端口和目的端口
            uint16_t flags;        // 标志位
            uint16_t pg;           // PG值
            uint32_t seq;          // 序列号
            uint64_t ts;           // 时间戳
        } ack;

        struct {
            uint32_t time;         // 时间
            uint32_t qlen;         // 队列长度
            uint8_t qIndex;        // 队列索引
        } pfc;

        struct {
            uint16_t sport, dport; // 源端口和目的端口
        } qp;
    };

    // 序列化方法
    void Serialize(FILE *file) {
        if (fwrite(this, sizeof(TraceFormat), 1, file) != 1) {
            std::cerr << "Failed to serialize TraceFormat." << std::endl;
            assert(false);
        }
    }

    // 反序列化方法
    int Deserialize(FILE *file) {
        int ret = fread(this, sizeof(TraceFormat), 1, file);
        if (ret != 1) {
            std::cerr << "Failed to deserialize TraceFormat." << std::endl;
            return -1;
        }
        return ret;
    }
};

// 将PEvent枚举值转换为对应的字符串
static inline const char* EventToStr(PEvent e) {
    switch (e) {
        case Recv:
            return "Recv";
        case Enqu:
            return "Enqu";
        case Dequ:
            return "Dequ";
        case Drop:
            return "Drop";
        default:
            return "Unknown";
    }
}

} // namespace ns3

#endif // TRACE_FORMAT_H