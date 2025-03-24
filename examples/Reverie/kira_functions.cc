#include "kira_functions.h"
#include "ns3/mpi-interface.h"
#include <string>
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
// namespace ns3 {
//     MPI_Controller::MPI_Controller(int* pargc, char*** pargv){
//         MpiInterface::Enable(pargc, pargv);
//         systemId = MpiInterface::GetSystemId();
//         MPI_FlowInfo = create_MPI_FlowInfo();
//         if (!kira::init_log("examples/Reverie/dump_sigcomm/system"+std::to_string(systemId)+".log")) {
//             std::cout << "system: " << systemId << " 日志文件创建失败" << std::endl;
//         }
//     }
//     MPI_Controller::~MPI_Controller(){
//         MPI_Type_free(&MPI_FlowInfo);
//         MpiInterface::Disable();
//     }
//     MPI_Datatype MPI_Controller::create_MPI_FlowInfo() {
//         // 定义结构体的成员数量（7个）
//         const int num_members = 7;
//         MPI_Datatype types[num_members] = {
//             MPI_CHAR,           // type[32]
//             MPI_INT,            // src_node
//             MPI_INT,            // src_port
//             MPI_INT,            // dst_node
//             MPI_INT,            // dst_port
//             MPI_INT,            // priority
//             MPI_UNSIGNED_LONG_LONG // msg_len (uint64_t)
//         };
//         int block_lengths[num_members] = {32, 1, 1, 1, 1, 1, 1};  // 每个成员的块长度
//         // 计算每个成员的位移
//         MPI_Aint displacements[num_members];
//         FlowInfo dummy={0,0,0,0,0,0,0};  // 临时结构体实例，用于计算地址偏移
//         MPI_Get_address(&dummy.type,         &displacements[0]);
//         MPI_Get_address(&dummy.src_node,     &displacements[1]);
//         MPI_Get_address(&dummy.src_port,     &displacements[2]);
//         MPI_Get_address(&dummy.dst_node,     &displacements[3]);
//         MPI_Get_address(&dummy.dst_port,     &displacements[4]);
//         MPI_Get_address(&dummy.priority,     &displacements[5]);
//         MPI_Get_address(&dummy.msg_len,      &displacements[6]);
//         // 转换为相对于结构体起始地址的位移
//         for (int i = num_members - 1; i >= 0; i--) 
//             displacements[i] -= displacements[0];
//         // 创建 MPI 数据类型
//         MPI_Datatype MPI_FlowInfo;
//         MPI_Type_create_struct(num_members, block_lengths, displacements, types, &MPI_FlowInfo);
//         MPI_Type_commit(&MPI_FlowInfo);
//         return MPI_FlowInfo;
//     }
//     int MPI_Controller::SendFI(const void *buf, int count, int dest, int tag, MPI_Comm comm){
//         MPI_Send(buf, count, MPI_FlowInfo, dest, tag, comm);
//     }
//     int MPI_Controller::RecvFI(void *buf, int count, int source,
//             int tag, MPI_Comm comm, MPI_Status *status){
//         MPI_Recv(buf, count, MPI_FlowInfo, source, tag, comm, status);
//     };
// }