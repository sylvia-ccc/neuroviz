#!/bin/bash
# ============================================================
# NeuroViz 一键部署脚本
# 目标: 腾讯云轻量云服务器 (Ubuntu)
# 域名: neuroviz.bigmonsterclaw.com
# IP:   43.136.117.175
# ============================================================
set -e

# ---- 配置 ----
DOMAIN="neuroviz.bigmonsterclaw.com"
APP_DIR="/home/ubuntu/neuroviz"
SSL_DIR="/etc/nginx/ssl"
SERVICE_NAME="neuroviz"
BACKEND_PORT=8080

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
err()  { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# ============================================================
# Step 0: 前置检查
# ============================================================
echo ""
echo "=========================================="
echo "  NeuroViz 部署脚本"
echo "  域名: ${DOMAIN}"
echo "=========================================="
echo ""

[[ $EUID -eq 0 ]] && err "请不要用 root 运行，请用 ubuntu 用户"

# 检查是否在腾讯云
curl -s --connect-timeout 3 http://metadata.tencentyun.com/latest/meta-data/instance-id > /dev/null 2>&1 \
  && log "检测到腾讯云环境" \
  || warn "未检测到腾讯云元数据，继续执行..."

# ============================================================
# Step 1: 系统依赖
# ============================================================
echo ""
echo ">>> Step 1/7: 安装系统依赖..."
sudo apt update -qq
sudo apt install -y -qq python3 python3-pip python3-venv nginx git curl unzip > /dev/null 2>&1
log "系统依赖安装完成"

# ============================================================
# Step 2: 上传/更新代码
# ============================================================
echo ""
echo ">>> Step 2/7: 部署代码..."

if [[ -d "${APP_DIR}" ]]; then
  log "代码目录已存在: ${APP_DIR}"
  warn "如需更新代码，请手动执行: cd ${APP_DIR} && git pull"
else
  mkdir -p ${APP_DIR}
  log "已创建代码目录: ${APP_DIR}"
  echo ""
  echo "=========================================="
  echo "  请在本地 Mac 执行以下命令上传代码:"
  echo "=========================================="
  echo ""
  echo "  scp -r ~/projects/neuroviz/* ubuntu@43.136.117.175:${APP_DIR}/"
  echo "  scp -r ~/projects/neuroviz/.* ubuntu@43.136.117.175:${APP_DIR}/ 2>/dev/null"
  echo ""
  echo "=========================================="
  echo "  上传完成后，按回车继续..."
  echo "=========================================="
  read -p ""
fi

[[ -f "${APP_DIR}/backend/app.py" ]] || err "未找到 backend/app.py，请先上传代码"
log "代码文件检查通过"

# ============================================================
# Step 3: Python 虚拟环境
# ============================================================
echo ""
echo ">>> Step 3/7: 配置 Python 环境..."

cd ${APP_DIR}/backend

if [[ -d "venv" ]]; then
  log "虚拟环境已存在，跳过创建"
else
  python3 -m venv venv
  log "虚拟环境创建完成"
fi

source venv/bin/activate
pip install --quiet --upgrade pip
if [[ -f "requirements.txt" ]]; then
  pip install --quiet -r requirements.txt
  log "Python 依赖安装完成"
else
  err "未找到 requirements.txt"
fi
deactivate

# ============================================================
# Step 4: 修改前端 WebSocket 地址
# ============================================================
echo ""
echo ">>> Step 4/7: 修改前端配置..."

FRONTEND_HTML="${APP_DIR}/frontend/index.html"
if [[ -f "${FRONTEND_HTML}" ]]; then
  # 替换 WebSocket 地址为生产环境
  sed -i.bak "s|ws://localhost:8080/ws|wss://${DOMAIN}/ws|g" "${FRONTEND_HTML}"
  sed -i.bak "s|ws://127.0.0.1:8080/ws|wss://${DOMAIN}/ws|g" "${FRONTEND_HTML}"
  # 替换 API base URL (如果有)
  sed -i.bak "s|http://localhost:8080|https://${DOMAIN}|g" "${FRONTEND_HTML}"
  sed -i.bak "s|http://127.0.0.1:8080|https://${DOMAIN}|g" "${FRONTEND_HTML}"
  log "前端 WebSocket 地址已修改为: wss://${DOMAIN}/ws"
  # 清理备份
  rm -f "${FRONTEND_HTML}.bak"
else
  err "未找到 frontend/index.html"
fi

# ============================================================
# Step 5: 后端 systemd 服务
# ============================================================
echo ""
echo ">>> Step 5/7: 配置后端服务..."

sudo tee /etc/systemd/system/${SERVICE_NAME}.service > /dev/null <<EOF
[Unit]
Description=NeuroViz Backend Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=${APP_DIR}/backend
Environment=PYTHONUNBUFFERED=1
ExecStart=${APP_DIR}/backend/venv/bin/python -m uvicorn app:app --host 127.0.0.1 --port ${BACKEND_PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME} > /dev/null 2>&1
sudo systemctl restart ${SERVICE_NAME}

sleep 2
if sudo systemctl is-active --quiet ${SERVICE_NAME}; then
  log "后端服务启动成功 (端口 ${BACKEND_PORT})"
else
  err "后端服务启动失败，请检查日志: sudo journalctl -u ${SERVICE_NAME} -n 50"
fi

# ============================================================
# Step 6: Nginx 配置
# ============================================================
echo ""
echo ">>> Step 6/7: 配置 Nginx..."

# 创建 SSL 目录
sudo mkdir -p ${SSL_DIR}

# 写入 Nginx 配置
sudo tee /etc/nginx/sites-available/${SERVICE_NAME} > /dev/null <<'NGINX_CONF'
# ---- HTTP → HTTPS 重定向 ----
server {
    listen 80;
    server_name neuroviz.bigmonsterclaw.com;
    
    # 证书申请验证路径 (Let's Encrypt)
    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }
    
    # 如果已有 SSL 证书，重定向到 HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# ---- HTTPS 主服务 ----
server {
    listen 443 ssl http2;
    server_name neuroviz.bigmonsterclaw.com;

    # SSL 证书 (请替换为实际路径)
    ssl_certificate /etc/nginx/ssl/neuroviz.bigmonsterclaw.com_bundle.crt;
    ssl_certificate_key /etc/nginx/ssl/neuroviz.bigmonsterclaw.com.key;
    
    # 如果还没有证书，注释掉上面两行，取消下面一行的注释
    # ssl_certificate /etc/ssl/certs/ssl-cert-snakeoil.pem;
    # ssl_certificate_key /etc/ssl/private/ssl-cert-snakeoil.key;
    
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    # 文件上传大小限制
    client_max_body_size 200M;

    # 前端静态文件
    location /app {
        alias /home/ubuntu/neuroviz/frontend;
        try_files $uri $uri/ /index.html;
    }

    # 根路径重定向到前端
    location = / {
        return 301 https://$server_name/app;
    }

    # 后端 API + WebSocket 代理
    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket 支持
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        # WebSocket 长连接超时
        proxy_connect_timeout 1d;
        proxy_send_timeout 1d;
        proxy_read_timeout 1d;
    }
}
NGINX_CONF

# 删除默认站点（避免冲突）
sudo rm -f /etc/nginx/sites-enabled/default

# 启用站点
sudo ln -sf /etc/nginx/sites-available/${SERVICE_NAME} /etc/nginx/sites-enabled/

# 检查配置语法
if sudo nginx -t 2>&1 | grep -q "successful"; then
  log "Nginx 配置检查通过"
else
  # 如果因为缺少 SSL 证书文件导致失败，临时禁用 SSL
  warn "Nginx 配置检查失败（可能缺少 SSL 证书）"
  warn "将使用临时 HTTP 配置..."
  
  # 写入纯 HTTP 配置（临时）
  sudo tee /etc/nginx/sites-available/${SERVICE_NAME} > /dev/null <<'NGINX_HTTP'
server {
    listen 80;
    server_name neuroviz.bigmonsterclaw.com;

    client_max_body_size 200M;

    location /app {
        alias /home/ubuntu/neuroviz/frontend;
        try_files $uri $uri/ /index.html;
    }

    location = / {
        return 301 http://$server_name/app;
    }

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        
        proxy_connect_timeout 1d;
        proxy_send_timeout 1d;
        proxy_read_timeout 1d;
    }
}
NGINX_HTTP

  sudo nginx -t 2>&1 | grep -q "successful" && log "临时 HTTP 配置检查通过" || err "Nginx 配置仍然失败"
fi

sudo systemctl restart nginx
sudo systemctl enable nginx > /dev/null 2>&1
log "Nginx 启动成功"

# ============================================================
# Step 7: 验证
# ============================================================
echo ""
echo ">>> Step 7/7: 验证部署..."

# 检查后端
BACKEND_OK=false
if curl -s --connect-timeout 5 http://127.0.0.1:${BACKEND_PORT}/docs > /dev/null 2>&1; then
  log "后端 API 正常: http://127.0.0.1:${BACKEND_PORT}/docs"
  BACKEND_OK=true
else
  warn "后端 API 无响应，请检查: sudo journalctl -u ${SERVICE_NAME} -n 50"
fi

# 检查 Nginx
if sudo systemctl is-active --quiet nginx; then
  log "Nginx 运行正常"
else
  warn "Nginx 未运行"
fi

# 检查端口
if ss -tlnp | grep -q ":80 "; then
  log "端口 80 已监听"
else
  warn "端口 80 未监听，请检查 Nginx"
fi

if ss -tlnp | grep -q ":443 "; then
  log "端口 443 已监听 (HTTPS)"
fi

# ============================================================
# 完成
# ============================================================
echo ""
echo "=========================================="
echo "  ✅ NeuroViz 部署完成！"
echo "=========================================="
echo ""
echo "  📍 访问地址:"
echo "     http://${DOMAIN}/app"
echo "     http://${DOMAIN}/docs"
echo ""
echo "  ⚠️  还需要手动完成:"
echo ""
echo "  1. DNS 解析（腾讯云控制台）"
echo "     添加 A 记录: neuroviz → 43.136.117.175"
echo ""
echo "  2. 安全组（腾讯云控制台）"
echo "     放行端口: 80 (HTTP), 443 (HTTPS)"
echo ""
echo "  3. SSL 证书（二选一）"
echo "     方式A - 腾讯云免费SSL（推荐国内）:"
echo "       控制台 → SSL证书 → 申请免费证书 → ${DOMAIN}"
echo "       下载 Nginx 格式后执行:"
echo "       sudo cp *.crt /etc/nginx/ssl/${DOMAIN}_bundle.crt"
echo "       sudo cp *.key /etc/nginx/ssl/${DOMAIN}.key"
echo "       然后重新运行: sudo nginx -t && sudo systemctl reload nginx"
echo ""
echo "     方式B - Let's Encrypt:"
echo "       sudo apt install certbot python3-certbot-nginx"
echo "       sudo certbot --nginx -d ${DOMAIN}"
echo ""
echo "  4. 切换到 HTTPS 配置（证书就位后）"
echo "     sudo nginx -t && sudo systemctl reload nginx"
echo ""
echo "  📋 常用命令:"
echo "     查看后端日志: sudo journalctl -u ${SERVICE_NAME} -f"
echo "     查看Nginx日志: sudo tail -f /var/log/nginx/error.log"
echo "     重启后端: sudo systemctl restart ${SERVICE_NAME}"
echo "     重启Nginx: sudo systemctl restart nginx"
echo "     更新代码后: cd ${APP_DIR} && sudo systemctl restart ${SERVICE_NAME}"
echo ""
echo "=========================================="
