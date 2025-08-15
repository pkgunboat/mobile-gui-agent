#!/usr/bin/env python3
"""
Mobile Agent 模块化前端服务器启动脚本
"""

import os
import sys
import subprocess
import time
import requests
from pathlib import Path

def check_backend_service():
    """检查后端服务是否运行"""
    try:
        response = requests.get("http://localhost:50005/ping", timeout=5)
        if response.status_code == 200:
            print("✓ 后端服务正在运行")
            return True
    except requests.exceptions.RequestException:
        pass
    
    print("✗ 后端服务未运行")
    return False

def start_backend_service():
    """启动后端服务"""
    print("正在启动后端服务...")
    
    # 检查server.py是否存在
    server_path = Path("server.py")
    if not server_path.exists():
        print("错误: 找不到 server.py 文件")
        print("请确保在正确的目录中运行此脚本")
        return False
    
    try:
        # 启动后端服务
        backend_process = subprocess.Popen(
            [sys.executable, "server.py"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 等待服务启动
        print("等待后端服务启动...")
        for i in range(30):  # 最多等待30秒
            time.sleep(1)
            if check_backend_service():
                print("✓ 后端服务启动成功")
                return True
        
        print("✗ 后端服务启动超时")
        backend_process.terminate()
        return False
        
    except Exception as e:
        print(f"启动后端服务失败: {e}")
        return False

def main():
    print("=== Mobile Agent 模块化前端服务器启动器 ===")
    print()
    
    # 检查当前目录
    current_dir = Path.cwd()
    print(f"当前目录: {current_dir}")
    
    # 检查必要文件
    required_files = [
        "frontend_server_modular.py",
        "server.py",
        "frontend/index.html",
        "frontend/script.js",
        "modular/__init__.py"
    ]
    
    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)
    
    if missing_files:
        print("错误: 缺少必要文件:")
        for file_path in missing_files:
            print(f"  - {file_path}")
        print("\n请确保在正确的项目目录中运行此脚本")
        return
    
    print("✓ 所有必要文件已找到")
    print()
    
    # 检查后端服务
    if not check_backend_service():
        print("后端服务未运行，尝试启动...")
        if not start_backend_service():
            print("无法启动后端服务，请手动运行:")
            print("  python server.py")
            return
        print()
    
    # 安装依赖
    print("检查依赖...")
    try:
        import flask
        import flask_cors
        print("✓ Flask依赖已安装")
    except ImportError:
        print("安装Flask依赖...")
        subprocess.run([
            sys.executable, "-m", "pip", "install", 
            "-r", "frontend_requirements.txt"
        ])
    
    print()
    print("启动模块化前端服务器...")
    print("访问地址: http://localhost:50006")
    print("按 Ctrl+C 停止服务器")
    print()
    
    try:
        # 启动模块化前端服务器
        subprocess.run([sys.executable, "frontend_server_modular.py"])
    except KeyboardInterrupt:
        print("\n服务器已停止")
    except Exception as e:
        print(f"启动失败: {e}")

if __name__ == "__main__":
    main() 