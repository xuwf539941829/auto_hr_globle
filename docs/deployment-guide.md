# Auto HR Copilot 线上部署指南

## 目录

1. [架构概述](#架构概述)
2. [前置准备](#前置准备)
3. [服务器环境配置](#服务器环境配置)
4. [Docker 配置](#docker-配置)
5. [Nginx 反向代理](#nginx-反向代理)
6. [Cloudflare CDN 配置](#cloudflare-cdn-配置)
7. [SSL 证书配置](#ssl-证书配置)
8. [部署流程](#部署流程)
9. [监控和维护](#监控和维护)
10. [故障排查](#故障排查)
11. [性能优化](#性能优化)

---

## 架构概述

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                        用户浏览器                              │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  Cloudflare CDN      │
                    │  - 加速              │
                    │  - SSL/TLS           │
                    │  - DDoS 防护         │
                    │  - 缓存              │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │  你的服务器 IP        │
                    │  (Ubuntu 22.04)      │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │   Nginx              │
                    │   反向代理           │
                    │   - 路由请求         │
                    │   - 负载均衡         │
                    │   - 压缩             │
                    └──────────┬───────────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
                ▼              ▼              ▼
        ┌────────────┐  ┌────────────┐  ┌──────────┐
        │ Frontend   │  │ Backend    │  │ Storage  │
        │ Next.js    │  │ FastAPI    │  │ 数据卷   │
        │ :3000      │  │ :8000      │  │          │
        │ (Docker)   │  │ (Docker)   │  │          │
        └────────────┘  └────────────┘  └──────────┘
```

### 流量路由

| 请求路径 | 目标 | 说明 |
|---------|------|------|
| `/` | Frontend :3000 | 前端页面 |
| `/_next/*` | Frontend :3000 | Next.js 静态资源 |
| `/api/*` | Backend :8000 | 后端 API |
| `/docs` | Backend :8000 | API 文档 |
| `/health` | Backend :8000 | 健康检查 |

---

## 前置准备

### 1. 购买服务器

**推荐配置**：
- **系统**：Ubuntu 22.04 LTS
- **CPU**：2 核心
- **内存**：4 GB
- **存储**：50 GB SSD
- **带宽**：5 Mbps

**推荐服务商**：
- 阿里云（国内）
- 腾讯云（国内）
- DigitalOcean（国际）
- Linode（国际）

### 2. 购买/转入域名

**推荐注册商**：
- Cloudflare（推荐，可直接管理 DNS）
- 阿里云万网
- 腾讯云
- GoDaddy

### 3. 准备 GitHub 仓库

确保代码已推送到 GitHub：
```bash
git remote -v
# 应该看到类似：origin  https://github.com/your-username/auto_hr.git
```

### 4. 获取 LLM API 密钥（可选）

如果使用 LLM 功能，需要：
- OpenAI API Key，或
- 其他兼容 OpenAI 的 LLM 服务（如 Zhipu GLM）

---

## 服务器环境配置

### 1. 连接到服务器

```bash
# 使用 SSH 连接
ssh root@your-server-ip

# 或使用密钥
ssh -i /path/to/key.pem ubuntu@your-server-ip
```

### 2. 更新系统

```bash
# 更新包管理器
sudo apt update
sudo apt upgrade -y

# 安装基础工具
sudo apt install -y \
    curl \
    wget \
    git \
    vim \
    htop \
    net-tools \
    build-essential
```

### 3. 安装 Docker

```bash
# 下载 Docker 安装脚本
curl -fsSL https://get.docker.com -o get-docker.sh

# 运行安装脚本
sudo sh get-docker.sh

# 将当前用户加入 docker 组（避免每次都用 sudo）
sudo usermod -aG docker $USER

# 验证安装
docker --version
docker run hello-world
```

### 4. 安装 Docker Compose

```bash
# 下载最新版本
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose

# 添加执行权限
sudo chmod +x /usr/local/bin/docker-compose

# 验证安装
docker-compose --version
```

### 5. 安装 Nginx

```bash
sudo apt install -y nginx

# 启动 Nginx
sudo systemctl start nginx
sudo systemctl enable nginx

# 验证状态
sudo systemctl status nginx
```

### 6. 安装 Certbot（SSL 证书管理）

```bash
sudo apt install -y certbot python3-certbot-nginx

# 验证安装
certbot --version
```

### 7. 创建应用目录

```bash
# 创建应用目录
sudo mkdir -p /opt/auto-hr
cd /opt/auto-hr

# 创建数据卷目录
sudo mkdir -p storage logs

# 设置权限
sudo chown -R $USER:$USER /opt/auto-hr
```

### 8. 克隆项目代码

```bash
cd /opt/auto-hr

# 克隆仓库
git clone https://github.com/your-username/auto_hr.git .

# 或者如果已有代码，直接上传
# scp -r ./auto_hr/* root@your-server-ip:/opt/auto-hr/
```

---

## Docker 配置

### 1. 后端 Dockerfile

创建 `backend/Dockerfile`：

```dockerfile
# 使用官方 Python 运行时作为基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制 requirements.txt
COPY backend/requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY backend/ .

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动应用
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 2. 前端 Dockerfile

创建 `frontend/Dockerfile`：

```dockerfile
# 构建阶段
FROM node:20-alpine AS builder

WORKDIR /app

# 复制 package 文件
COPY frontend/package*.json ./

# 安装依赖
RUN npm ci

# 复制源代码
COPY frontend/ .

# 构建应用
RUN npm run build

# 运行阶段
FROM node:20-alpine

WORKDIR /app

# 从构建阶段复制构建结果
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

# 暴露端口
EXPOSE 3000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:3000 || exit 1

# 启动应用
CMD ["node", "server.js"]
```

### 3. docker-compose.yml

创建项目根目录的 `docker-compose.yml`：

```yaml
version: '3.8'

services:
  # 后端服务
  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    container_name: auto-hr-backend
    ports:
      - "8000:8000"
    environment:
      # LLM 配置（可选）
      - AUTO_HR_LLM_API_KEY=${AUTO_HR_LLM_API_KEY:-}
      - AUTO_HR_LLM_BASE_URL=${AUTO_HR_LLM_BASE_URL:-https://api.openai.com/v1}
      - AUTO_HR_LLM_MODEL=${AUTO_HR_LLM_MODEL:-gpt-4-mini}
      - AUTO_HR_LLM_API_STYLE=${AUTO_HR_LLM_API_STYLE:-chat_completions}
      - AUTO_HR_LLM_TIMEOUT_SECONDS=${AUTO_HR_LLM_TIMEOUT_SECONDS:-45}
      # 数据目录
      - AUTHR_DATA_DIR=/app/storage
    volumes:
      # 持久化存储
      - ./storage:/app/storage
      - ./logs:/app/logs
    restart: unless-stopped
    networks:
      - auto-hr-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  # 前端服务
  frontend:
    build:
      context: .
      dockerfile: frontend/Dockerfile
    container_name: auto-hr-frontend
    ports:
      - "3000:3000"
    environment:
      # 后端 API 地址（容器内部通信）
      - NEXT_PUBLIC_API_URL=http://backend:8000
    depends_on:
      backend:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - auto-hr-network
    healthcheck:
      test: ["CMD", "wget", "--quiet", "--tries=1", "--spider", "http://localhost:3000"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

networks:
  auto-hr-network:
    driver: bridge

volumes:
  storage:
  logs:
```

### 4. .dockerignore 文件

创建 `backend/.dockerignore`：

```
__pycache__
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.venv
.git
.gitignore
.env
.env.local
.DS_Store
*.log
node_modules/
dist/
build/
.pytest_cache/
.coverage
htmlcov/
```

创建 `frontend/.dockerignore`：

```
node_modules
.next
.git
.gitignore
.env
.env.local
.DS_Store
*.log
dist
build
.pytest_cache
.coverage
```

### 5. 环境变量文件

创建 `.env` 文件（在项目根目录）：

```bash
# LLM 配置（如果使用 LLM 功能）
AUTO_HR_LLM_API_KEY=your-api-key-here
AUTO_HR_LLM_BASE_URL=https://api.openai.com/v1
AUTO_HR_LLM_MODEL=gpt-4-mini
AUTO_HR_LLM_API_STYLE=chat_completions
AUTO_HR_LLM_TIMEOUT_SECONDS=45

# 前端配置
NEXT_PUBLIC_API_URL=https://your-domain.com/api

# 后端配置
AUTHR_DATA_DIR=/app/storage
```

**⚠️ 安全提示**：
- 不要将 `.env` 提交到 Git
- 在服务器上手动创建 `.env` 文件
- 使用强密钥和 API 密钥

---

## Nginx 反向代理

### 1. 创建 Nginx 配置文件

创建 `/etc/nginx/sites-available/auto-hr`：

```bash
sudo vim /etc/nginx/sites-available/auto-hr
```

内容如下：

```nginx
# 上游服务器定义
upstream frontend {
    server 127.0.0.1:3000;
    keepalive 32;
}

upstream backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

# HTTP 重定向到 HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name your-domain.com www.your-domain.com;

    # Certbot 验证
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # 其他请求重定向到 HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS 服务器配置
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name your-domain.com www.your-domain.com;

    # SSL 证书配置（由 Certbot 自动生成）
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # SSL 安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # 安全头
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

    # 日志
    access_log /var/log/nginx/auto-hr-access.log;
    error_log /var/log/nginx/auto-hr-error.log;

    # 客户端上传大小限制
    client_max_body_size 100M;

    # Gzip 压缩
    gzip on;
    gzip_vary on;
    gzip_min_length 1000;
    gzip_proxied any;
    gzip_types text/plain text/css text/xml text/javascript 
               application/x-javascript application/xml+rss 
               application/json application/javascript;

    # ============ 前端路由 ============
    location / {
        proxy_pass http://frontend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $server_name;
        proxy_redirect off;

        # WebSocket 支持
        proxy_read_timeout 86400;
    }

    # ============ 后端 API 路由 ============
    location /api/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $server_name;
        proxy_redirect off;

        # 超时配置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # ============ API 文档 ============
    location /docs {
        proxy_pass http://backend/docs;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /openapi.json {
        proxy_pass http://backend/openapi.json;
        proxy_set_header Host $host;
    }

    # ============ 健康检查 ============
    location /health {
        proxy_pass http://backend/health;
        access_log off;
    }

    # ============ 静态资源缓存 ============
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
        proxy_pass http://frontend;
        proxy_cache_valid 200 30d;
        proxy_cache_bypass $http_pragma $http_authorization;
        add_header Cache-Control "public, max-age=2592000";
        expires 30d;
    }

    # ============ 禁止访问敏感文件 ============
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }

    location ~ ~$ {
        deny all;
        access_log off;
        log_not_found off;
    }
}
```

### 2. 启用 Nginx 配置

```bash
# 创建符号链接
sudo ln -s /etc/nginx/sites-available/auto-hr /etc/nginx/sites-enabled/auto-hr

# 删除默认配置（可选）
sudo rm /etc/nginx/sites-enabled/default

# 测试配置语法
sudo nginx -t

# 重启 Nginx
sudo systemctl restart nginx
```

### 3. 验证 Nginx 状态

```bash
# 查看状态
sudo systemctl status nginx

# 查看日志
sudo tail -f /var/log/nginx/auto-hr-access.log
sudo tail -f /var/log/nginx/auto-hr-error.log
```

---

## Cloudflare CDN 配置

### 1. 域名转入 Cloudflare

**步骤 1**：在 Cloudflare 创建账户
- 访问 https://dash.cloudflare.com
- 注册或登录

**步骤 2**：添加站点
- 点击 "Add a Site"
- 输入你的域名（如 `your-domain.com`）
- 选择免费计划

**步骤 3**：更改 DNS 服务器
- Cloudflare 会提供两个 nameserver
- 登录你的域名注册商
- 修改 DNS 服务器为 Cloudflare 提供的地址
- 等待 DNS 生效（通常 24 小时内）

### 2. DNS 记录配置

在 Cloudflare 控制面板，进入 "DNS" 选项卡：

```
类型    名称              内容              代理状态
A       your-domain.com   你的服务器IP      已代理 (Cloudflare)
CNAME   www               your-domain.com   已代理 (Cloudflare)
```

**验证 DNS 配置**：
```bash
# 查看 DNS 记录
nslookup your-domain.com

# 应该返回 Cloudflare 的 IP 地址
```

### 3. SSL/TLS 配置

在 Cloudflare 控制面板，进入 "SSL/TLS" 选项卡：

**步骤 1**：选择 SSL 模式
- 点击 "Overview"
- 选择 "Full (strict)" 模式
  - 这要求服务器有有效的 SSL 证书（我们会通过 Certbot 获取）

**步骤 2**：启用 HTTPS 重定向
- 进入 "Edge Certificates"
- 启用 "Always Use HTTPS"

**步骤 3**：配置 TLS 版本
- 进入 "Overview"
- 最小 TLS 版本：1.2

### 4. 缓存配置

在 Cloudflare 控制面板，进入 "Caching" 选项卡：

**缓存规则**：

```
规则 1：API 不缓存
路径：/api/*
缓存级别：绕过

规则 2：静态资源缓存
路径：/_next/static/*
缓存级别：缓存所有内容
浏览器缓存 TTL：30 天

规则 3：页面缓存
路径：/*
缓存级别：缓存所有内容
浏览器缓存 TTL：1 小时
```

### 5. 性能优化

在 Cloudflare 控制面板，进入 "Speed" 选项卡：

**启用以下功能**：
- ✅ Brotli 压缩
- ✅ Minify JavaScript, CSS, HTML
- ✅ Early Hints
- ✅ Rocket Loader（可选，可能影响某些 JS）

### 6. 安全配置

在 Cloudflare 控制面板，进入 "Security" 选项卡：

**启用以下功能**：
- ✅ DDoS Protection（免费）
- ✅ Bot Management（免费基础版）
- ✅ WAF Rules（免费基础规则）

**配置防火墙规则**：
```
规则：允许中国流量
条件：Country is CN
操作：Allow

规则：阻止恶意 Bot
条件：Bot Score is less than 30
操作：Block
```

---

## SSL 证书配置

### 1. 使用 Certbot 获取 Let's Encrypt 证书

```bash
# 停止 Nginx（Certbot 需要绑定 80 端口）
sudo systemctl stop nginx

# 获取证书
sudo certbot certonly --standalone -d your-domain.com -d www.your-domain.com

# 按提示输入邮箱和同意条款
```

### 2. 自动续期配置

```bash
# 启用 Certbot 自动续期定时任务
sudo systemctl enable certbot.timer
sudo systemctl start certbot.timer

# 验证定时任务
sudo systemctl status certbot.timer

# 测试续期（不会真正续期，只是测试）
sudo certbot renew --dry-run
```

### 3. 验证证书

```bash
# 查看证书信息
sudo certbot certificates

# 应该看到类似输出：
# Certificate Name: your-domain.com
#   Domains: your-domain.com, www.your-domain.com
#   Expiry Date: 2025-08-14 (VALID: 89 days)
```

### 4. 证书续期提醒

Certbot 会在证书过期前 30 天自动续期。如果需要手动续期：

```bash
sudo certbot renew
```

---

## 部署流程

### 1. 完整部署步骤

#### 第一步：准备服务器

```bash
# 登录服务器
ssh root@your-server-ip

# 进入应用目录
cd /opt/auto-hr

# 确保代码是最新的
git pull origin main
```

#### 第二步：配置环境变量

```bash
# 创建 .env 文件
cat > .env << 'EOF'
AUTO_HR_LLM_API_KEY=your-api-key-here
AUTO_HR_LLM_BASE_URL=https://api.openai.com/v1
AUTO_HR_LLM_MODEL=gpt-4-mini
AUTO_HR_LLM_API_STYLE=chat_completions
AUTO_HR_LLM_TIMEOUT_SECONDS=45
NEXT_PUBLIC_API_URL=https://your-domain.com/api
AUTHR_DATA_DIR=/app/storage
EOF

# 验证文件
cat .env
```

#### 第三步：构建并启动 Docker

```bash
# 构建镜像（首次部署）
docker-compose build

# 启动容器
docker-compose up -d

# 查看日志
docker-compose logs -f

# 验证容器状态
docker-compose ps
```

#### 第四步：验证服务

```bash
# 检查后端健康状态
curl http://127.0.0.1:8000/health

# 检查前端
curl http://127.0.0.1:3000

# 查看 Docker 日志
docker-compose logs backend
docker-compose logs frontend
```

#### 第五步：配置 Nginx

```bash
# 创建 Nginx 配置（参考前面的配置）
sudo vim /etc/nginx/sites-available/auto-hr

# 启用配置
sudo ln -s /etc/nginx/sites-available/auto-hr /etc/nginx/sites-enabled/auto-hr

# 测试配置
sudo nginx -t

# 启动 Nginx
sudo systemctl start nginx
```

#### 第六步：获取 SSL 证书

```bash
# 停止 Nginx
sudo systemctl stop nginx

# 获取证书
sudo certbot certonly --standalone -d your-domain.com -d www.your-domain.com

# 启动 Nginx
sudo systemctl start nginx
```

#### 第七步：配置 Cloudflare

- 登录 Cloudflare 控制面板
- 添加 DNS 记录指向你的服务器 IP
- 配置 SSL/TLS 为 "Full (strict)"
- 启用 HTTPS 重定向
- 配置缓存规则

#### 第八步：验证部署

```bash
# 访问你的域名
curl https://your-domain.com

# 检查 SSL 证书
curl -I https://your-domain.com

# 查看 Nginx 日志
sudo tail -f /var/log/nginx/auto-hr-access.log
```

### 2. 部署脚本（自动化）

创建 `scripts/deploy.sh`：

```bash
#!/bin/bash

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}========== Auto HR 部署脚本 ==========${NC}"

# 检查是否在正确的目录
if [ ! -f "docker-compose.yml" ]; then
    echo -e "${RED}错误：未找到 docker-compose.yml，请在项目根目录运行此脚本${NC}"
    exit 1
fi

# 步骤 1：更新代码
echo -e "${YELLOW}[1/6] 更新代码...${NC}"
git pull origin main || echo -e "${RED}Git 更新失败，继续...${NC}"

# 步骤 2：检查 .env 文件
echo -e "${YELLOW}[2/6] 检查环境变量...${NC}"
if [ ! -f ".env" ]; then
    echo -e "${RED}错误：未找到 .env 文件${NC}"
    echo "请创建 .env 文件并配置必要的环境变量"
    exit 1
fi

# 步骤 3：构建镜像
echo -e "${YELLOW}[3/6] 构建 Docker 镜像...${NC}"
docker-compose build --no-cache

# 步骤 4：停止旧容器
echo -e "${YELLOW}[4/6] 停止旧容器...${NC}"
docker-compose down

# 步骤 5：启动新容器
echo -e "${YELLOW}[5/6] 启动新容器...${NC}"
docker-compose up -d

# 步骤 6：验证部署
echo -e "${YELLOW}[6/6] 验证部署...${NC}"
sleep 5

# 检查后端
if curl -f http://127.0.0.1:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 后端服务正常${NC}"
else
    echo -e "${RED}✗ 后端服务异常${NC}"
    docker-compose logs backend
    exit 1
fi

# 检查前端
if curl -f http://127.0.0.1:3000 > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 前端服务正常${NC}"
else
    echo -e "${RED}✗ 前端服务异常${NC}"
    docker-compose logs frontend
    exit 1
fi

echo -e "${GREEN}========== 部署完成！==========${NC}"
echo -e "${GREEN}前端地址：https://your-domain.com${NC}"
echo -e "${GREEN}后端地址：https://your-domain.com/api${NC}"
echo -e "${GREEN}API 文档：https://your-domain.com/docs${NC}"
```

使用脚本：

```bash
# 添加执行权限
chmod +x scripts/deploy.sh

# 运行部署
./scripts/deploy.sh
```

---

## 监控和维护

### 1. 日志管理

#### 查看 Docker 日志

```bash
# 查看所有服务日志
docker-compose logs

# 实时查看后端日志
docker-compose logs -f backend

# 实时查看前端日志
docker-compose logs -f frontend

# 查看最后 100 行日志
docker-compose logs --tail=100

# 查看特定时间范围的日志
docker-compose logs --since 2024-01-01 --until 2024-01-02
```

#### 查看 Nginx 日志

```bash
# 访问日志
sudo tail -f /var/log/nginx/auto-hr-access.log

# 错误日志
sudo tail -f /var/log/nginx/auto-hr-error.log

# 查看特定 IP 的请求
sudo grep "192.168.1.1" /var/log/nginx/auto-hr-access.log
```

#### 查看系统日志

```bash
# 查看 Docker 守护进程日志
sudo journalctl -u docker -f

# 查看 Nginx 日志
sudo journalctl -u nginx -f
```

### 2. 监控系统资源

```bash
# 查看 Docker 容器资源使用
docker stats

# 查看系统资源
htop

# 查看磁盘使用
df -h

# 查看内存使用
free -h

# 查看网络连接
netstat -an | grep ESTABLISHED | wc -l
```

### 3. 定期备份

#### 备份数据卷

```bash
# 备份存储目录
sudo tar -czf /backup/auto-hr-storage-$(date +%Y%m%d).tar.gz /opt/auto-hr/storage

# 备份日志
sudo tar -czf /backup/auto-hr-logs-$(date +%Y%m%d).tar.gz /opt/auto-hr/logs

# 列出备份
ls -lh /backup/
```

#### 自动备份脚本

创建 `scripts/backup.sh`：

```bash
#!/bin/bash

BACKUP_DIR="/backup"
RETENTION_DAYS=30

# 创建备份目录
mkdir -p $BACKUP_DIR

# 备份时间戳
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# 备份存储目录
echo "备份存储目录..."
tar -czf $BACKUP_DIR/auto-hr-storage-$TIMESTAMP.tar.gz /opt/auto-hr/storage

# 备份日志
echo "备份日志..."
tar -czf $BACKUP_DIR/auto-hr-logs-$TIMESTAMP.tar.gz /opt/auto-hr/logs

# 删除旧备份（保留 30 天）
echo "清理旧备份..."
find $BACKUP_DIR -name "auto-hr-*.tar.gz" -mtime +$RETENTION_DAYS -delete

echo "备份完成！"
```

#### 定时备份

```bash
# 编辑 crontab
sudo crontab -e

# 添加每天凌晨 2 点执行备份
0 2 * * * /opt/auto-hr/scripts/backup.sh >> /var/log/auto-hr-backup.log 2>&1
```

### 4. 监控脚本

创建 `scripts/monitor.sh`：

```bash
#!/bin/bash

# 监控间隔（秒）
INTERVAL=60

while true; do
    clear
    echo "========== Auto HR 监控面板 =========="
    echo "时间：$(date '+%Y-%m-%d %H:%M:%S')"
    echo ""

    # 容器状态
    echo "--- 容器状态 ---"
    docker-compose ps

    echo ""
    echo "--- 资源使用 ---"
    docker stats --no-stream

    echo ""
    echo "--- 磁盘使用 ---"
    df -h | grep -E "^/dev|^Filesystem"

    echo ""
    echo "--- 内存使用 ---"
    free -h

    echo ""
    echo "--- 网络连接 ---"
    echo "活跃连接数：$(netstat -an | grep ESTABLISHED | wc -l)"

    echo ""
    echo "--- 最近错误 ---"
    docker-compose logs --tail=5 2>&1 | grep -i error || echo "无错误"

    echo ""
    echo "下次刷新：${INTERVAL}秒后"
    sleep $INTERVAL
done
```

使用监控脚本：

```bash
chmod +x scripts/monitor.sh
./scripts/monitor.sh
```

### 5. 健康检查

```bash
# 检查后端健康状态
curl -I http://127.0.0.1:8000/health

# 检查前端
curl -I http://127.0.0.1:3000

# 检查 Nginx
curl -I http://127.0.0.1

# 检查 SSL 证书有效期
echo | openssl s_client -servername your-domain.com -connect your-domain.com:443 2>/dev/null | openssl x509 -noout -dates
```

---

## 故障排查

### 1. 容器无法启动

#### 问题：容器立即退出

```bash
# 查看日志
docker-compose logs backend
docker-compose logs frontend

# 检查镜像是否构建成功
docker images | grep auto-hr

# 重新构建
docker-compose build --no-cache
```

#### 问题：端口已被占用

```bash
# 查看占用端口的进程
sudo lsof -i :8000
sudo lsof -i :3000

# 杀死进程
sudo kill -9 <PID>

# 或修改 docker-compose.yml 中的端口映射
```

#### 问题：内存不足

```bash
# 查看内存使用
free -h

# 查看 Docker 容器内存限制
docker stats

# 在 docker-compose.yml 中添加内存限制
# services:
#   backend:
#     mem_limit: 2g
```

### 2. 网络连接问题

#### 问题：前端无法连接后端

```bash
# 检查容器网络
docker network ls
docker network inspect auto-hr-network

# 检查容器 IP
docker inspect auto-hr-backend | grep IPAddress

# 在前端容器中测试连接
docker-compose exec frontend curl http://backend:8000/health

# 检查防火墙
sudo ufw status
sudo ufw allow 8000
sudo ufw allow 3000
```

#### 问题：外部无法访问

```bash
# 检查 Nginx 是否运行
sudo systemctl status nginx

# 检查 Nginx 配置
sudo nginx -t

# 查看 Nginx 日志
sudo tail -f /var/log/nginx/auto-hr-error.log

# 检查防火墙
sudo ufw status
sudo ufw allow 80
sudo ufw allow 443
```

### 3. SSL 证书问题

#### 问题：证书过期

```bash
# 检查证书有效期
sudo certbot certificates

# 手动续期
sudo certbot renew --force-renewal

# 重启 Nginx
sudo systemctl restart nginx
```

#### 问题：证书验证失败

```bash
# 检查 DNS 解析
nslookup your-domain.com

# 检查 Cloudflare DNS 设置
# 确保 A 记录指向正确的 IP

# 检查防火墙是否允许 80 端口
sudo ufw allow 80

# 重新获取证书
sudo certbot certonly --standalone -d your-domain.com
```

### 4. 性能问题

#### 问题：响应缓慢

```bash
# 检查 CPU 使用
docker stats

# 查看慢查询日志
docker-compose logs backend | grep "slow"

# 检查 Nginx 配置是否有问题
sudo nginx -T

# 增加 Nginx 工作进程
# worker_processes auto;
```

#### 问题：内存泄漏

```bash
# 监控内存使用
docker stats --no-stream

# 重启容器
docker-compose restart backend

# 查看内存使用趋势
docker stats --no-stream | tee -a /tmp/memory-log.txt
```

### 5. 数据丢失

#### 问题：容器删除后数据丢失

```bash
# 检查数据卷
docker volume ls

# 查看数据卷挂载点
docker inspect auto-hr-backend | grep -A 5 "Mounts"

# 备份数据
sudo tar -czf /backup/auto-hr-data-backup.tar.gz /opt/auto-hr/storage
```

### 6. 常见错误信息

| 错误 | 原因 | 解决方案 |
|------|------|--------|
| `Connection refused` | 服务未启动 | `docker-compose up -d` |
| `Port already in use` | 端口被占用 | 修改端口或杀死占用进程 |
| `Out of memory` | 内存不足 | 增加服务器内存或优化代码 |
| `SSL certificate problem` | 证书过期 | `sudo certbot renew` |
| `DNS resolution failed` | DNS 配置错误 | 检查 Cloudflare DNS 设置 |

---

## 性能优化

### 1. 前端优化

#### 启用 Next.js 优化

在 `frontend/next.config.ts` 中：

```typescript
import type { NextConfig } from 'next';

const nextConfig: NextConfig = {
  // 生产环境优化
  swcMinify: true,
  
  // 输出为独立应用
  output: 'standalone',
  
  // 图片优化
  images: {
    unoptimized: false,
    formats: ['image/avif', 'image/webp'],
  },
  
  // 压缩
  compress: true,
  
  // 生成 sitemap（可选）
  // generateEtags: true,
};

export default nextConfig;
```

#### 启用 Gzip 压缩

在 Nginx 配置中已启用：

```nginx
gzip on;
gzip_vary on;
gzip_min_length 1000;
gzip_types text/plain text/css text/xml text/javascript 
           application/x-javascript application/xml+rss 
           application/json application/javascript;
```

#### 缓存策略

在 Nginx 配置中已配置：

```nginx
# 静态资源缓存 30 天
location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
    expires 30d;
    add_header Cache-Control "public, max-age=2592000";
}
```

### 2. 后端优化

#### 启用 Uvicorn 多进程

修改 `docker-compose.yml`：

```yaml
backend:
  command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

#### 数据库连接池

在 `backend/app/services/` 中配置连接池：

```python
# 如果使用数据库，配置连接池
from sqlalchemy.pool import QueuePool

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=20,
    max_overflow=40,
    pool_recycle=3600,
)
```

#### 缓存策略

使用 Redis 缓存（可选）：

```python
# 在 docker-compose.yml 中添加 Redis
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data

# 在代码中使用 Redis
from redis import Redis
redis_client = Redis(host='redis', port=6379)
```

### 3. 数据库优化

#### 添加索引

```python
# 在 Pydantic 模型中定义索引
class JobProfile(BaseModel):
    id: str
    title: str
    # 添加索引以加快查询
    # db_index=True
```

#### 查询优化

```python
# 使用 select() 而不是 select(*)
# 避免 N+1 查询
# 使用分页
```

### 4. CDN 优化

#### Cloudflare 缓存优化

```
规则 1：API 不缓存
路径：/api/*
缓存级别：绕过

规则 2：静态资源长期缓存
路径：/_next/static/*
缓存级别：缓存所有内容
浏览器缓存 TTL：1 年

规则 3：页面短期缓存
路径：/*
缓存级别：缓存所有内容
浏览器缓存 TTL：1 小时
```

#### 启用 Cloudflare 高级功能

- ✅ Brotli 压缩
- ✅ Minify JavaScript, CSS, HTML
- ✅ Early Hints
- ✅ HTTP/3 (QUIC)

### 5. 监控性能指标

#### 使用 Cloudflare Analytics

在 Cloudflare 控制面板查看：
- 页面加载时间
- 缓存命中率
- 带宽使用
- 请求数

#### 使用 Google PageSpeed Insights

```bash
# 访问
https://pagespeed.web.dev/

# 输入你的域名
https://your-domain.com
```

#### 自定义监控

创建 `scripts/performance-monitor.sh`：

```bash
#!/bin/bash

echo "========== 性能监控 =========="
echo "时间：$(date)"
echo ""

# 前端性能
echo "--- 前端性能 ---"
curl -w "DNS: %{time_namelookup}s\n" \
     -w "连接: %{time_connect}s\n" \
     -w "首字节: %{time_starttransfer}s\n" \
     -w "总耗时: %{time_total}s\n" \
     -o /dev/null -s https://your-domain.com

echo ""
echo "--- 后端性能 ---"
curl -w "API 响应时间: %{time_total}s\n" \
     -o /dev/null -s https://your-domain.com/api/health

echo ""
echo "--- 资源使用 ---"
docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}"
```

---

## 常见问题 (FAQ)

### Q1：如何更新应用代码？

```bash
cd /opt/auto-hr

# 拉取最新代码
git pull origin main

# 重新构建镜像
docker-compose build

# 重启容器
docker-compose up -d

# 验证
docker-compose logs -f
```

### Q2：如何修改 LLM 配置？

```bash
# 编辑 .env 文件
vim .env

# 修改相关环境变量
AUTO_HR_LLM_API_KEY=new-key
AUTO_HR_LLM_MODEL=gpt-4

# 重启后端
docker-compose restart backend
```

### Q3：如何查看数据库数据？

```bash
# 如果使用 SQLite（默认）
docker-compose exec backend sqlite3 /app/storage/auto_hr.db

# 如果使用 PostgreSQL
docker-compose exec postgres psql -U user -d auto_hr
```

### Q4：如何处理 CORS 错误？

在 `backend/app/main.py` 中检查 CORS 配置：

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.com", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Q5：如何扩展到多个服务器？

使用 Docker Swarm 或 Kubernetes：

```bash
# Docker Swarm
docker swarm init
docker stack deploy -c docker-compose.yml auto-hr

# Kubernetes
kubectl apply -f k8s-deployment.yaml
```

### Q6：如何备份和恢复数据？

```bash
# 备份
docker-compose exec backend tar -czf /app/storage/backup.tar.gz /app/storage

# 恢复
docker-compose exec backend tar -xzf /app/storage/backup.tar.gz -C /
```

---

## 总结

这份指南涵盖了从服务器准备到生产部署的所有步骤：

1. ✅ 服务器环境配置
2. ✅ Docker 容器化
3. ✅ Nginx 反向代理
4. ✅ Cloudflare CDN 加速
5. ✅ SSL 证书配置
6. ✅ 监控和维护
7. ✅ 故障排查
8. ✅ 性能优化

**部署完成后**：
- 访问 `https://your-domain.com` 查看前端
- 访问 `https://your-domain.com/docs` 查看 API 文档
- 访问 `https://your-domain.com/api/health` 检查后端健康状态

**需要帮助？**
- 查看 Docker 日志：`docker-compose logs -f`
- 查看 Nginx 日志：`sudo tail -f /var/log/nginx/auto-hr-error.log`
- 检查系统资源：`docker stats`

祝部署顺利！🚀
