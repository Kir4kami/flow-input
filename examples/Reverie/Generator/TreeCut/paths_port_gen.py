#!/usr/bin/env python3
#from ecmp_path import get_rdma_files, load_file, find_ecmp_path
#
#
#def parse_flow_paths_port(flow_paths_port, filename):
#    with open(filename, 'w') as file:
#        for tup in flow_paths_port:
#            if len(tup) > 1 and isinstance(tup[1], list):
#                for item in tup[1]:
#                    file.write(f"{item}\n")
#
#
## 主函數入口
#if __name__ == "__main__":
#    # 在此处更改工作目录
#    Working_Directory = "./rdma_result/1_TP1"
#    file_path_list = get_rdma_files(Working_Directory)
#    Flow_Info_List, Link_Info_List, Route_Info_Table, Link_Map, Reverse_Link_Map, host_num, leaf_num, spine_num = load_file(
#        Working_Directory, file_path_list)
#    Total_Flow_Path, Flow_Paths_Port = find_ecmp_path(Flow_Info_List, Link_Info_List, Route_Info_Table, Link_Map,
#                                                      Reverse_Link_Map)
#    parse_flow_paths_port(Flow_Paths_Port, 'flow_paths_port_output.txt')
import os
from ecmp_path import get_rdma_files, load_file, find_ecmp_path


def parse_flow_paths_port(flow_paths_port, filename):
    """将 flow_paths_port 写入指定文件，每行一个路径项"""
    with open(filename, 'w') as file:
        for tup in flow_paths_port:
            if len(tup) > 1 and isinstance(tup[1], list):
                for item in tup[1]:
                    file.write(f"{item}\n")


def main():
    # 输入根目录
    input_base_dir = "./rdma_result"
    # 输出目录（自动创建）
    output_dir = "./ecmp_outputs"
    
    # 创建输出目录（如果不存在）
    os.makedirs(output_dir, exist_ok=True)

    # 检查输入目录是否存在
    if not os.path.exists(input_base_dir):
        print(f"错误：输入目录 '{input_base_dir}' 不存在！")
        return

    # 遍历 rdma_result 下的所有子项
    for item in os.listdir(input_base_dir):
        input_subdir = os.path.join(input_base_dir, item)
        
        # 只处理子目录
        if not os.path.isdir(input_subdir):
            continue

        print(f"正在处理: {item}")

        try:
            # 获取该子目录下的 RDMA 文件
            file_path_list = get_rdma_files(input_subdir)
            if not file_path_list:
                print(f"警告：'{item}' 中未找到有效 RDMA 文件，跳过。")
                continue

            # 加载数据
            Flow_Info_List, Link_Info_List, Route_Info_Table, Link_Map, Reverse_Link_Map, host_num, leaf_num, spine_num = load_file(
                input_subdir, file_path_list
            )

            # 计算 ECMP 路径
            _, Flow_Paths_Port = find_ecmp_path(
                Flow_Info_List, Link_Info_List, Route_Info_Table, Link_Map, Reverse_Link_Map
            )

            # 构造输出文件路径：ecmp_outputs/子目录名.txt
            safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in item)  # 防止非法文件名
            output_file = os.path.join(output_dir, f"{safe_name}.txt")

            # 写入结果
            parse_flow_paths_port(Flow_Paths_Port, output_file)
            print(f"输出已保存: {output_file}")

        except Exception as e:
            print(f"处理 '{item}' 时出错: {e}")


if __name__ == "__main__":
    main()