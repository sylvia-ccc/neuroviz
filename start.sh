#!/bin/bash
# NeuroViz 启动脚本

set -e

echo "=== NeuroViz 启动 ==="

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 错误: 未找到 python3"
    exit 1
fi

# 检查后端目录
if [ ! -d "backend" ]; then
    echo "❌ 错误: 未找到 backend/ 目录"
    exit 1
fi

# 创建虚拟环境（如果不存在）
if [ ! -d "backend/venv" ]; then
    echo "创建虚拟环境..."
    cd backend
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cd ..
fi

# 杀掉旧进程
echo "停止旧进程..."
lsof -ti:8080 | xargs kill -9 2>/dev/null || true
sleep 1

# 启动后端
echo "启动后端 (端口 8080)..."
cd backend
source venv/bin/activate
nohup python3 -m uvicorn app:app --host 0.0.0.0 --port 8080 > /tmp/neuroviz.log 2>&1 &
BACKEND_PID=$!
echo "后端已启动 (PID: $BACKEND_PID)"

cd ..

# 等待后端启动
echo "等待后端启动..."
sleep 3

# 检查后端状态
if curl -s <a href="http://localhost:8080/docs">http://localhost:8080/docs</a> > /dev/null; then
    echo "✅ 后端运行正常"
else
    echo "❌ 后端启动失败，查看日志: tail -f /tmp/neuroviz.log"
    exit 1
fi

echo ""
echo "=== 启动完成 ==="
echo "后端 API: <a href="http://localhost:8080">http://localhost:8080</a>"
echo "API 文档: <a href="http://localhost:8080/docs">http://localhost:8080/docs</a>"
echo "前端: 用浏览器打开 frontend/index.html"
echo "日志: tail -f /tmp/neuroviz.log"
echo ""
echo "停止后端: lsof -ti:8080 | xargs kill -9"
