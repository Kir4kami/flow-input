#include <cstdint>
#include <vector>
//文件下维护着当前系统的跃迁次数及每次跃迁修正的时间
extern int transition_cnt;
extern std::vector<uint64_t> transition_delay;