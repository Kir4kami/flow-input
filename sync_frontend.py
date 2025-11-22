#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从Windows共享文件夹同步 complete_frontend.html 到Linux
"""
import shutil
from pathlib import Path

win_file = Path("/mnt/hgfs/flow-input-yf/examples/Reverie/api/complete_frontend.html")
linux_file = Path.home() / "flow-input-local/examples/Reverie/api/complete_frontend.html"

if not win_file.exists():
    print(f"❌ Windows文件不存在: {win_file}")
    print("   请检查VMware共享文件夹是否已挂载")
    exit(1)

# 读取文件内容并检查
with open(win_file, 'r', encoding='utf-8') as f:
    content = f.read()
    
line_count = len(content.splitlines())
has_workflow = "Workflow 自动化" in content
has_window_app = "window.__flowApp" in content

print(f"📄 文件行数: {line_count}")
print(f"   'Workflow 自动化': {'✅' if has_workflow else '❌'}")
print(f"   'window.__flowApp': {'✅' if has_window_app else '❌'}")

# 如果包含Workflow，就复制
if has_workflow and has_window_app:
    print("\n📋 正在复制文件...")
    with open(linux_file, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ 文件已复制到: {linux_file}")
    
    # 验证
    with open(linux_file, 'r', encoding='utf-8') as f:
        new_content = f.read()
        new_has_workflow = "Workflow 自动化" in new_content
        new_line_count = len(new_content.splitlines())
    print(f"✅ 验证: 行数={new_line_count}, 包含Workflow={new_has_workflow}")
    print("\n🎉 同步完成！请在浏览器中 Ctrl+Shift+R 强制刷新")
else:
    print("\n⚠️  文件似乎还是旧版本")
    print("   请确保在Windows端保存文件（Ctrl+S），然后重新运行此脚本")
    print(f"   或者手动复制: cp {win_file} {linux_file}")











