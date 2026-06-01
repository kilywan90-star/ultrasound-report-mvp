#!/bin/bash
# 超声报告语音结构化 — 阿里云一键部署脚本
# 复制整段到服务器终端执行

set -e
echo "========================================="
echo "  超声报告语音结构化系统 — 服务器部署"
echo "========================================="

# 1. 更新系统 + 安装依赖
echo "[1/5] 安装系统依赖..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv git nginx 2>/dev/null

# 2. 克隆项目
echo "[2/5] 拉取代码..."
cd /opt
rm -rf ultrasound-report-mvp 2>/dev/null
git clone https://github.com/kilywan90-star/ultrasound-report-mvp.git
cd ultrasound-report-mvp

# 3. 安装 Python 依赖
echo "[3/5] 安装 Python 依赖..."
pip3 install --break-system-packages -r backend/requirements.txt 2>/dev/null || pip3 install -r backend/requirements.txt

# 4. 写入环境变量
echo "[4/5] 配置 API 密钥..."
cat > .env << 'EOF'
DASHSCOPE_API_KEY=sk-8d3e69bd0fd842ddb996ca263328d1a2
DEEPSEEK_API_KEY=sk-707a90a4206b45e9962d606d7a6434f3
EOF

# 5. 配置 systemd 服务
echo "[5/5] 配置系统服务..."
cat > /etc/systemd/system/ultrasound.service << 'EOF'
[Unit]
Description=Ultrasound Report Voice-to-Structured System
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/ultrasound-report-mvp/backend
EnvironmentFile=/opt/ultrasound-report-mvp/.env
ExecStart=python3 -m uvicorn main:app --host 0.0.0.0 --port 8700
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ultrasound
systemctl restart ultrasound

# 6. 检查状态
sleep 3
echo ""
echo "========================================="
echo "  部署完成！"
echo "========================================="
if systemctl is-active --quiet ultrasound; then
    echo "  服务状态: ✅ 运行中"
    echo "  访问地址: http://47.109.151.238:8700"
else
    echo "  服务状态: ❌ 启动失败"
    journalctl -u ultrasound --no-pager -n 20
fi
echo ""
echo "  阿里云安全组需要开放 8700 端口！"
echo "  控制台 → 安全组 → 入方向 → 添加 8700"
echo "========================================="
