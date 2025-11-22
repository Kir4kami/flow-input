#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
强制从Windows共享文件夹同步 complete_frontend.html 到Linux
忽略时间戳，直接读取内容并写入
"""
import shutil
from pathlib import Path

win_file = Path("/mnt/hgfs/flow-input-yf/examples/Reverie/api/complete_frontend.html")
linux_file = Path.home() / "flow-input-local/examples/Reverie/api/complete_frontend.html"

if not win_file.exists():
    print(f"❌ Windows文件不存在: {win_file}")
    print("   请检查VMware共享文件夹是否已挂载")
    exit(1)

print(f"📄 正在从共享文件夹读取文件...")
print(f"   源文件: {win_file}")

# 直接读取文件内容（忽略时间戳）
try:
    with open(win_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    line_count = len(content.splitlines())
    has_workflow = "Workflow 自动化" in content
    has_window_app = "window.__flowApp" in content
    
    print(f"✅ 文件读取成功")
    print(f"   行数: {line_count}")
    print(f"   'Workflow 自动化': {'✅' if has_workflow else '❌'}")
    print(f"   'window.__flowApp': {'✅' if has_window_app else '❌'}")
    
    if not has_workflow or not has_window_app:
        print("\n⚠️  文件内容不完整，可能仍是旧版本")
        print("   请确保在Windows端保存文件（Ctrl+S）")
        exit(1)
    
    # 写入Linux文件
    print(f"\n📋 正在写入Linux文件...")
    print(f"   目标文件: {linux_file}")
    
    linux_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(linux_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    # 验证写入结果
    with open(linux_file, 'r', encoding='utf-8') as f:
        verify_content = f.read()
    
    verify_line_count = len(verify_content.splitlines())
    verify_workflow = "Workflow 自动化" in verify_content
    verify_window_app = "window.__flowApp" in verify_content
    
    print(f"✅ 文件写入成功")
    print(f"   验证行数: {verify_line_count}")
    print(f"   验证 'Workflow 自动化': {'✅' if verify_workflow else '❌'}")
    print(f"   验证 'window.__flowApp': {'✅' if verify_window_app else '❌'}")
    
    if verify_line_count == line_count and verify_workflow and verify_window_app:
        print(f"\n🎉 同步完成！文件已成功复制到Linux")
        print(f"   现在可以在浏览器中刷新页面（Ctrl+Shift+R）")
    else:
        print(f"\n⚠️  验证失败，文件可能未完全同步")
        
except Exception as e:
    print(f"❌ 同步失败: {e}")
    import traceback
    traceback.print_exc()
    exit(1)











