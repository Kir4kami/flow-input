def process_file(file_path):
    processed_lines = []
    file_name = file_path.split('/')[-1].split('.')[0]  # 获取文档名称，不带路径和扩展名
    with open(file_path, 'r') as file:
        for line in file:
            # 去除行末的换行符并分割字符串
            parts = line.strip().split('->')
            if len(parts) == 2:
                # 如果是第一种情况 "数字1->数字2"
                processed_lines.append(f"{parts[1]}_{parts[0]}")
            else:
                # 如果是第二种情况 "数字1->数字2->数字3"
                processed_lines.append(f"{parts[0]}_{parts[1]}")
                processed_lines.append(f"{parts[1]}_{parts[2]}")
    return processed_lines