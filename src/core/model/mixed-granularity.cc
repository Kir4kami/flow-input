#include "mixed-granularity.h"

//文件下维护着当前系统的跃迁次数以及每次跃迁修正的时间
int transition_cnt=0;
std::vector<uint64_t> transition_delay;