#!/bin/bash
# 小智MCP客户端 — 启动脚本
# 在服务器上运行: bash start_xiaozhi_mcp.sh

cd /opt/ultrasound-report-mvp

# 安装依赖
pip3 install websocket-client -q 2>/dev/null

echo "=== 小智MCP超声报告客户端 ==="
echo "连接 wss://api.xiaozhi.me/mcp/ ..."
echo ""

# 启动客户端 (后台运行)
nohup python3 xiaozhi_mcp_client.py > /tmp/xiaozhi_mcp.log 2>&1 &

echo "已启动 (PID: $!)"
echo "查看日志: tail -f /tmp/xiaozhi_mcp.log"
echo "停止: kill $!"
