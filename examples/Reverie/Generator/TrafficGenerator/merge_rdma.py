#!/usr/bin/env python3

import os
import re
import shutil
from pathlib import Path

def natural_sort_key(s):
    """将字符串按数字和非数字部分分割，用于自然排序"""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', str(s))]

def main():
    rdma_result_dir = Path("rdma_result")
    if not rdma_result_dir.is_dir():
        print("Error: rdma_result directory does not exist.", file=sys.stderr)
        sys.exit(1)

    os.chdir(rdma_result_dir)

    output_dir = Path("all_rdma_files")
    output_dir.mkdir(exist_ok=True)

    # 正则匹配：数字_大写字母+数字（如 1_TP, 123_EP2）
    dir_pattern = re.compile(r'^\d+_[A-Z]+\d*$')

    # 获取当前目录下所有一级子目录
    candidate_dirs = []
    for item in Path('.').iterdir():
        if item.is_dir() and dir_pattern.match(item.name):
            candidate_dirs.append(item)

    # 自然排序目录名
    candidate_dirs.sort(key=natural_sort_key)

    count = 0
    for d in candidate_dirs:
        # 查找 rdma_operate*.txt（仅当前目录）
        files = list(d.glob('rdma_operate*.txt'))
        # 自然排序文件名
        files.sort(key=natural_sort_key)
        for f in files:
            new_name = output_dir / f"rdma_operate{count}.txt"
            shutil.copy2(f, new_name)
            count += 1

    print(f"实际合并文件数: {count}")

if __name__ == "__main__":
    import sys
    main()