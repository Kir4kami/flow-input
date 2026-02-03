#!/usr/bin/env python3
#def process_file(file_path):
#    processed_lines = []
#    file_name = file_path.split('/')[-1].split('.')[0]  # 获取文档名称，不带路径和扩展名
#    with open(file_path, 'r') as file:
#        for line in file:
#            # 去除行末的换行符并分割字符串
#            parts = line.strip().split('->')
#            if len(parts) == 2:
#                # 如果是第一种情况 "数字1->数字2"
#                processed_lines.append(f"{parts[1]}_{parts[0]}")
#            else:
#                # 如果是第二种情况 "数字1->数字2->数字3"
#                processed_lines.append(f"{parts[0]}_{parts[1]}")
#                processed_lines.append(f"{parts[1]}_{parts[2]}")
#    return processed_lines

def process_file(file_path):
   """
   解析 ECMP 输出，返回节点和端口之间的完整链路（包含端口信息）。
   每一行可能是:
     - Nxxx->Pyy  (节点xxx通过端口yy发送)
     - Pyy->Nxxx->Pzz  (从端口yy进入节点xxx，然后通过端口zz发送)
     - Pyy->Nxxx  (从端口yy进入节点xxx，路径结束)
   
   我们按文件顺序收集出现的节点和端口，并在同一条路径内按顺序构建边（包含端口信息）。
   遇到新的路径起点（行首为 Nxxx）时，会重置路径，避免跨路径拼接。
    
   输出格式：Nxxx_Pyy_Nzzz_Pww 表示从节点xxx的端口yy到节点zzz的端口ww
   如果缺少端口信息，则使用格式：Nxxx_Nzzz
   """
   edges = []
   current_path_edges = []
   prev_node = None
   prev_out_port = None  # 前一个节点的出端口

   def flush_path():
       nonlocal current_path_edges
       if len(current_path_edges) > 2:
           edges.extend(current_path_edges[1:-1])
       elif len(current_path_edges) == 2:
           # 路径只有首尾两条边，移除后无剩余
           pass
       current_path_edges = []
   
   with open(file_path, 'r') as file:
       for raw_line in file:
           line = raw_line.strip()
           if not line:
               continue
   
           parts = line.split('->')
           # 行首是节点，表明进入一条新的路径，重置状态
           if parts and parts[0].startswith('N'):
               if current_path_edges:
                   flush_path()
               prev_node = None
               prev_out_port = None
           
           # 解析当前行的节点和端口信息
           i = 0
           in_port = None  # 当前行的入端口（如果有）
           current_node = None
           current_out_port = None  # 当前节点的出端口
           
           # 首先检查是否有入端口（行首是端口）
           if parts and parts[0].startswith('P'):
               in_port = parts[0]
               i = 1
           
           # 解析节点和出端口
           while i < len(parts):
               part = parts[i]
               
               if part.startswith('N'):
                   current_node = part
                   # 检查下一个部分是否是端口（出端口）
                   if i + 1 < len(parts) and parts[i + 1].startswith('P'):
                       current_out_port = parts[i + 1]
                       i += 2
                   else:
                       current_out_port = None
                       i += 1
                   break  # 找到节点后退出循环
               else:
                   i += 1
           
           # 如果有前一个节点和当前节点，构建边（包含端口信息）
           if prev_node is not None and current_node is not None:
               # 构建边：前一个节点_前一个出端口_当前节点_当前入端口
               if prev_out_port is not None and in_port is not None:
                   # 完整格式：Nxxx_Pyy_Nzzz_Pww (节点xxx通过端口yy连接到节点zzz的端口ww)
                   current_path_edges.append(f"{prev_node}_{prev_out_port}_{current_node}_{in_port}")
               elif prev_out_port is not None:
                   # 只有前一个出端口，没有当前入端口
                   current_path_edges.append(f"{prev_node}_{prev_out_port}_{current_node}")
               elif in_port is not None:
                   # 只有当前入端口，没有前一个出端口
                   current_path_edges.append(f"{prev_node}_{current_node}_{in_port}")
               else:
                   # 都没有端口，使用旧格式
                   current_path_edges.append(f"{prev_node}_{current_node}")
           
           # 更新状态
           if current_node is not None:
               prev_node = current_node
               prev_out_port = current_out_port
   
   # 处理最后一条路径
   if current_path_edges:
       flush_path()
   
   return edges


#def process_file(file_path):
#   """
#   解析 ECMP 输出，返回节点之间的完整链路（包含端口信息），包括首尾跳。
#   与 process_file 的区别：此函数保留所有边，包括 host->leaf 和 leaf->host 的边。
#   
#   每一行可能是:
#     - Nxxx->Pyy  (节点xxx通过端口yy发送)
#     - Pyy->Nxxx->Pzz  (从端口yy进入节点xxx，然后通过端口zz发送)
#     - Pyy->Nxxx  (从端口yy进入节点xxx，路径结束)
#   
#   我们按文件顺序收集出现的节点和端口，并在同一条路径内按顺序构建边（包含端口信息）。
#   遇到新的路径起点（行首为 Nxxx）时，会重置路径，避免跨路径拼接。
#    
#   输出格式：Nxxx_Pyy_Nzzz_Pww 表示从节点xxx通过端口yy连接到节点zzz的端口ww
#   """
#   edges = []
#   current_path_edges = []
#   prev_node = None
#   prev_out_port = None  # 前一个节点的出端口
#   
#   with open(file_path, 'r') as file:
#       for raw_line in file:
#           line = raw_line.strip()
#           if not line:
#               continue
#   
#           parts = line.split('->')
#           # 行首是节点，表明进入一条新的路径，重置状态
#           if parts and parts[0].startswith('N'):
#               if current_path_edges:
#                   # 保存当前路径的所有边（包括首尾）
#                   edges.extend(current_path_edges)
#               current_path_edges = []
#               prev_node = None
#               prev_out_port = None
#           
#           # 解析当前行的节点和端口信息
#           i = 0
#           in_port = None  # 当前行的入端口（如果有）
#           current_node = None
#           current_out_port = None  # 当前节点的出端口
#           
#           # 首先检查是否有入端口（行首是端口）
#           if parts and parts[0].startswith('P'):
#               in_port = parts[0]
#               i = 1
#           
#           # 解析节点和出端口
#           while i < len(parts):
#               part = parts[i]
#               
#               if part.startswith('N'):
#                   current_node = part
#                   # 检查下一个部分是否是端口（出端口）
#                   if i + 1 < len(parts) and parts[i + 1].startswith('P'):
#                       current_out_port = parts[i + 1]
#                       i += 2
#                   else:
#                       current_out_port = None
#                       i += 1
#                   break  # 找到节点后退出循环
#               else:
#                   i += 1
#           
#           # 如果有前一个节点和当前节点，构建边
#           if prev_node is not None and current_node is not None:
#               # 构建边：前一个节点_前一个出端口_当前节点_当前入端口
#               if prev_out_port is not None and in_port is not None:
#                   # 完整格式：Nxxx_Pyy_Nzzz_Pww (节点xxx通过端口yy连接到节点zzz的端口ww)
#                   current_path_edges.append(f"{prev_node}_{prev_out_port}_{current_node}_{in_port}")
#               elif prev_out_port is not None:
#                   # 只有前一个出端口，没有当前入端口
#                   current_path_edges.append(f"{prev_node}_{prev_out_port}_{current_node}")
#               elif in_port is not None:
#                   # 只有当前入端口，没有前一个出端口
#                   current_path_edges.append(f"{prev_node}_{current_node}_{in_port}")
#               else:
#                   # 都没有端口
#                   current_path_edges.append(f"{prev_node}_{current_node}")
#           
#           # 更新状态
#           if current_node is not None:
#               prev_node = current_node
#               prev_out_port = current_out_port
#   
#   # 处理最后一条路径
#   if current_path_edges:
#       edges.extend(current_path_edges)
#   
#   return edges