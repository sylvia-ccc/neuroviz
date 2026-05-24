#!/bin/bash
set -e

# ============================================================
# NeuroViz 一键安装脚本
# 适用于腾讯云轻量云服务器 Ubuntu 22.04
# 使用方式: curl -fsSL https://raw.githubusercontent.com/sylvia-ccc/neuroviz/main/install.sh | bash
# ============================================================

DOMAIN="neuroviz.bigmonsterclaw.com"
APP_DIR="/var/www/neuroviz"
PYTHON_ENV="/opt/neuroviz-venv"
PORT=8080

echo "🚀 NeuroViz 安装中..."
echo "========================================"

# 1. 安装依赖
echo "📦 安装系统依赖..."
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip nginx certbot python3-certbot-nginx curl > /dev/null 2>&1

# 2. 拉取代码（不含 venv）
echo "📥 拉取 NeuroViz 代码..."
rm -rf $APP_DIR
mkdir -p $APP_DIR
cd $APP_DIR
curl -fsSL https://github.com/sylvia-ccc/neuroviz/archive/refs/heads/main.tar.gz | tar -xz --strip-components=1

# 3. 创建 Python 虚拟环境
echo "🐍 创建 Python 环境..."
rm -rf $PYTHON_ENV
python3 -m venv $PYTHON_ENV
$PYTHON_ENV/bin/pip install --upgrade pip -q
$PYTHON_ENV/bin/pip install -r requirements.txt -q

# 4. 修改前端 WebSocket 地址
echo "⚙️ 配置 WebSocket 域名..."
sed -i "s|ws://[^/]*/ws|wss://${DOMAIN}/ws|g" frontend/index.html

# 5. 创建 systemd 服务
echo "🔧 配置 systemd 服务..."
cat > /etc/systemd/system/neuroviz.service <<EOF
[Unit]
Description=NeuroViz EEG Visualization
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$APP_DIR/backend
Environment="PATH=$PYTHON_ENV/bin"
ExecStart=$PYTHON_ENV/bin/python -m uvicorn app:app --host 0.0.0.0 --port $PORT
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable neuroviz
systemctl restart neuroviz

# 6. 配置 Nginx 反向代理
echo "🌐 配置 Nginx..."
cat > /etc/nginx/sites-available/neuroviz <<EOF
server {
    listen 80;
    server_name $DOMAIN;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_read_timeout 86400;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:$PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOF

ln -sf /etc/nginx/sites-available/neuroviz /etc/nginx/sites-enabled/neuroviz
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

echo ""
echo "========================================"
echo "✅ NeuroViz 安装完成！"
echo "📊 访问地址: https://$DOMAIN"
echo "🔧 服务管理: systemctl restart neuroviz"
echo ""
echo "⚠️  后续步骤："
echo "   1. 在腾讯云控制台添加 DNS A 记录 → $DOMAIN 指向本服务器 IP"
echo "   2. 申请 SSL 证书: certbot --nginx -d $DOMAIN"
echo "   3. 或使用腾讯云免费 DV SSL 证书"
echo ""