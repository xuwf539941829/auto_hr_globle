# Auto HR Copilot 完整部署指南

本指南详细说明如何将 Auto HR 项目部署到云服务器 + Cloudflare Pages。

**部署架构:**
```
Cloudflare Pages (前端) → 云服务器 (后端 Docker 容器)
```

---

## 目录

1. [前置条件](#前置条件)
2. [第一步：本地构建 Docker 镜像](#第一步本地构建-docker-镜像)
3. [第二步：推送镜像到仓库](#第二步推送镜像到仓库)
4. [第三步：云服务器部署](#第三步云服务器部署)
5. [第四步：Cloudflare Pages 部署](#第四步cloudflare-pages-部署)
6. [第五步：验证和测试](#第五步验证和测试)
7. [常见问题](#常见问题)

---

## 前置条件

### 需要准备的账号和工具

1. **Docker Hub 账号**（推送镜像）
   - 注册: https://hub.docker.com/
   - 或用其他仓库：Aliyun、腾讯云、私有仓库

2. **云服务器**（用于运行后端）
   - 云服务商：阿里云、腾讯云、AWS、Linode 等
   - 操作系统：Linux (Ubuntu 20.04+ 推荐)
   - 配置：1 CPU, 2GB 内存起步
   - 已开放端口：8000（后端 API）

3. **GitHub 账号**（代码仓库）
   - 用于 Cloudflare Pages 部署

4. **Cloudflare 账号**（前端托管）
   - 注册: https://dash.cloudflare.com/

### 本地安装

```bash
# 1. 安装 Docker Desktop
# Windows/Mac: https://www.docker.com/products/docker-desktop
# Linux: 按照官方文档安装

# 2. 验证安装
docker --version
docker run hello-world

# 3. Git 推送准备
git --version
```

---

## 第一步：本地构建 Docker 镜像

### 1.1 进入项目目录

```bash
cd auto_hr
```

### 1.2 构建镜像

```bash
# 基本构建
docker build -t auto-hr-backend:latest ./backend

# 完整构建（带版本号和账号信息）
# 替换 <你的Docker账号> 为实际的 Docker Hub 用户名
docker build -t docker.io/<你的Docker账号>/auto-hr-backend:latest ./backend
docker build -t docker.io/<你的Docker账号>/auto-hr-backend:v1.0 ./backend
```

**构建输出示例:**
```
Step 1/10 : FROM python:3.11-slim
Step 2/10 : WORKDIR /app
...
Successfully built abc123def456
Successfully tagged docker.io/yourusername/auto-hr-backend:latest
```

### 1.3 测试镜像

```bash
# 运行测试容器
docker run -d \
  --name test-auto-hr \
  -p 8000:8000 \
  -e CORS_ORIGINS="*" \
  docker.io/<你的Docker账号>/auto-hr-backend:latest

# 等待 5 秒容器启动
sleep 5

# 测试健康检查端点
curl http://localhost:8000/health

# 预期返回
# {"status":"ok"}

# 查看日志
docker logs test-auto-hr

# 停止测试容器
docker stop test-auto-hr
docker rm test-auto-hr
```

---

## 第二步：推送镜像到仓库

### 2.1 登录 Docker Hub

```bash
docker login

# 输入用户名和密码
# Username: <你的Docker账号>
# Password: <你的密码>

# 登录成功输出
# Login Succeeded
```

### 2.2 推送镜像

```bash
# 推送 latest 标签
docker push docker.io/<你的Docker账号>/auto-hr-backend:latest

# 推送版本号标签（可选）
docker push docker.io/<你的Docker账号>/auto-hr-backend:v1.0

# 验证推送成功
# 访问 https://hub.docker.com/r/<你的Docker账号>/auto-hr-backend
```

**推送输出示例:**
```
The push refers to repository [docker.io/yourusername/auto-hr-backend]
latest: digest: sha256:abc123... size: 1234
```

### 2.3 验证镜像已推送

访问 Docker Hub：
```
https://hub.docker.com/r/<你的Docker账号>/auto-hr-backend/tags
```

看到 `latest` 和 `v1.0` 标签表示成功。

---

## 第三步：云服务器部署

### 3.1 连接到云服务器

```bash
# SSH 连接
# 替换 <服务器IP> 和 <用户名>
ssh -i <密钥文件> <用户名>@<服务器IP>

# 例如
ssh -i ~/.ssh/my_key.pem ubuntu@123.45.67.89

# 或如果用密码
ssh ubuntu@123.45.67.89
```

### 3.2 在服务器上安装 Docker

```bash
# 更新包列表
sudo apt-get update

# 安装 Docker（自动脚本）
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 添加当前用户到 docker 组（可选，避免每次都用 sudo）
sudo usermod -aG docker $USER
newgrp docker

# 验证安装
docker --version
```

### 3.3 创建配置文件

在服务器上创建 `.env` 文件：

```bash
# 进入工作目录
cd ~
mkdir auto-hr
cd auto-hr

# 创建 .env 文件
cat > .env << 'EOF'
# Docker 镜像配置
REGISTRY=docker.io
IMAGE_NAME=<你的Docker账号>/auto-hr-backend
TAG=latest

# 后端服务配置
BACKEND_PORT=8000

# CORS 配置（允许的来源）
CORS_ORIGINS=https://auto-hr.pages.dev,http://localhost:3000

# LLM 配置（可选）
AUTO_HR_LLM_API_KEY=<你的API密钥>
AUTO_HR_LLM_BASE_URL=https://api.openai.com/v1
AUTO_HR_LLM_MODEL=gpt-4-mini
AUTO_HR_LLM_API_STYLE=chat_completions
AUTO_HR_LLM_TIMEOUT_SECONDS=45
EOF

# 查看配置文件
cat .env
```

### 3.4 创建 docker-compose.yml

```bash
# 创建 docker-compose.yml
cat > docker-compose.yml << 'EOF'
version: '3.8'

services:
  auto-hr-backend:
    image: ${REGISTRY}/${IMAGE_NAME}:${TAG}
    container_name: auto-hr-backend
    ports:
      - "${BACKEND_PORT}:8000"
    environment:
      - CORS_ORIGINS=${CORS_ORIGINS}
      - AUTO_HR_LLM_API_KEY=${AUTO_HR_LLM_API_KEY}
      - AUTO_HR_LLM_BASE_URL=${AUTO_HR_LLM_BASE_URL}
      - AUTO_HR_LLM_MODEL=${AUTO_HR_LLM_MODEL}
      - AUTO_HR_LLM_API_STYLE=${AUTO_HR_LLM_API_STYLE}
      - AUTO_HR_LLM_TIMEOUT_SECONDS=${AUTO_HR_LLM_TIMEOUT_SECONDS}
      - AUTHR_DATA_DIR=/app/storage

    volumes:
      - auto-hr-storage:/app/storage
      - auto-hr-logs:/app/logs

    restart: unless-stopped

    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 5s

    networks:
      - auto-hr-network

volumes:
  auto-hr-storage:
    driver: local
  auto-hr-logs:
    driver: local

networks:
  auto-hr-network:
    driver: bridge
EOF

# 查看文件
cat docker-compose.yml
```

### 3.5 启动容器

```bash
# 安装 Docker Compose（如果没有）
sudo apt-get install -y docker-compose

# 启动服务
docker-compose up -d

# 查看启动日志
docker-compose logs -f

# 按 Ctrl+C 退出日志查看
```

**正常启动日志示例:**
```
Creating auto-hr-backend ... done
auto-hr-backend  | [INFO] Auto HR API app created.
auto-hr-backend  | [INFO] Task scheduler and monitor started
```

### 3.6 验证后端运行

```bash
# 本地测试（在服务器上）
curl http://localhost:8000/health

# 预期返回
# {"status":"ok"}

# 查看容器状态
docker-compose ps

# 预期状态为 Up
# NAME                  STATUS
# auto-hr-backend       Up 2 minutes (healthy)
```

### 3.7 远程测试后端

从本地测试服务器后端：

```bash
# 本地机器上
curl http://<服务器IP>:8000/health

# 例如
curl http://123.45.67.89:8000/health

# 如果连接失败，检查防火墙
# 云服务商安全组 → 入站规则 → 开放 TCP 8000 端口
```

### 3.8 查看日志

```bash
# 实时日志
docker-compose logs -f

# 查看最后 100 行
docker-compose logs --tail=100

# 查看特定时间段
docker-compose logs --since 2024-01-15T10:00:00
```

### 3.9 停止和重启

```bash
# 停止服务
docker-compose down

# 重启服务（更新镜像后）
docker-compose pull
docker-compose up -d

# 删除所有数据（谨慎）
docker-compose down -v
```

---

## 第四步：Cloudflare Pages 部署

### 4.1 推送代码到 GitHub

```bash
# 本地机器上
cd auto_hr

# 初始化 Git（如果还没有）
git init
git add .
git commit -m "Initial commit"

# 添加远程仓库
git remote add origin https://github.com/<你的账号>/auto_hr.git

# 推送代码
git branch -M main
git push -u origin main
```

### 4.2 连接 Cloudflare Pages

1. 访问 https://dash.cloudflare.com/
2. Pages → 创建项目 → 连接 Git
3. 授权 Cloudflare 访问 GitHub
4. 选择仓库 `auto_hr`
5. 点击 "Begin setup"

### 4.3 配置构建设置

**构建配置:**

| 字段 | 值 |
|---|---|
| Production branch | main |
| Build command | `cd frontend && npm install && npm run build` |
| Build output directory | `frontend/out` 或 `frontend/.next` |
| Root directory | (留空) |

### 4.4 配置环境变量

在 Cloudflare Pages 项目设置中添加：

```
NEXT_PUBLIC_API_BASE = https://<服务器IP>:8000
```

或用域名：

```
NEXT_PUBLIC_API_BASE = https://api.yourserver.com
```

### 4.5 触发部署

配置完成后 Cloudflare 自动部署。等待构建完成，大约 3-5 分钟。

**查看部署状态:**
1. Pages → 项目名 → Deployments
2. 查看最新部署状态

---

## 第五步：验证和测试

### 5.1 访问前端

访问 Cloudflare Pages URL：

```
https://auto-hr-xxxx.pages.dev
```

应该看到 Auto HR 应用首页。

### 5.2 检查 API 连接

打开浏览器 F12 开发者工具：

1. **Network 标签**
2. 尝试任何会调用 API 的操作（如加载职位）
3. 查看 Network 中的请求

**成功示例:**
```
GET /api/jobs → Status: 200
```

**失败示例:**
```
GET /api/jobs → Status: 0 (CORS error)
或
GET /api/jobs → Error: net::ERR_CONNECTION_REFUSED
```

### 5.3 检查 CORS 配置

浏览器控制台（F12 → Console）查看错误：

**CORS 错误示例:**
```
Access to XMLHttpRequest at 'https://123.45.67.89:8000/api/jobs' 
from origin 'https://auto-hr-xxxx.pages.dev' 
has been blocked by CORS policy
```

**解决方案:**
检查 `.env` 中的 `CORS_ORIGINS` 配置是否包含 Cloudflare 域名。

### 5.4 检查后端日志

```bash
# SSH 连接到服务器
ssh ubuntu@<服务器IP>

# 查看最新日志
docker-compose logs -f

# 查看错误日志
docker-compose logs | grep -i error
```

### 5.5 测试 LLM 功能（如配置了）

1. 创建或编辑职位描述
2. 检查是否成功翻译 JD
3. 检查是否成功评分候选人
4. 如果失败，查看后端日志中的 LLM 错误

### 5.6 性能测试

```bash
# 本地机器上测试响应时间
time curl http://<服务器IP>:8000/api/jobs

# 应该在 1-3 秒内返回
```

---

## 常见问题

### Q1: 前端无法连接后端（API 超时）

**症状:** 浏览器控制台 ERR_CONNECTION_REFUSED 或超时

**检查步骤:**

1. 后端是否运行
   ```bash
   ssh ubuntu@<服务器IP>
   docker-compose ps
   # 应该看到 auto-hr-backend 为 Up
   ```

2. 防火墙是否开放端口
   ```bash
   # 在云服务商后台检查安全组
   # 入站规则 → TCP 8000 应该允许
   ```

3. 测试直接连接
   ```bash
   curl http://<服务器IP>:8000/health
   ```

4. 检查 API 地址是否正确
   ```bash
   # Cloudflare Pages 环境变量
   NEXT_PUBLIC_API_BASE = 应该正确指向后端
   ```

**解决方案:**

```bash
# 1. 重启后端
docker-compose restart

# 2. 检查日志
docker-compose logs --tail=50

# 3. 查看容器状态
docker ps
```

---

### Q2: CORS 错误

**症状:** 浏览器控制台出现 CORS 错误

**原因:** Cloudflare 域名没有在 CORS_ORIGINS 中配置

**解决方案:**

```bash
# SSH 到服务器
ssh ubuntu@<服务器IP>
cd ~/auto-hr

# 编辑 .env 文件
nano .env

# 修改 CORS_ORIGINS，添加 Cloudflare 域名
CORS_ORIGINS=https://auto-hr-xxxx.pages.dev,https://api.yourserver.com

# 保存（Ctrl+O, Enter, Ctrl+X）

# 重启服务
docker-compose up -d
```

---

### Q3: Docker 镜像太大

**症状:** 推送镜像很慢

**检查:**

```bash
# 查看镜像大小
docker images | grep auto-hr-backend

# 预期大小: 300-500 MB
```

**优化:**

1. 检查 `.dockerignore` 是否包含 `storage/` 和 `logs/`
2. 从基础镜像清理缓存

```bash
# 重新构建（使用 --no-cache）
docker build --no-cache -t docker.io/<你的账号>/auto-hr-backend:latest ./backend
```

---

### Q4: 服务器磁盘空间不足

**症状:** 容器无法启动或日志输出异常

**检查:**

```bash
# SSH 到服务器
ssh ubuntu@<服务器IP>

# 查看磁盘使用
df -h

# 查看 Docker 存储
docker system df
```

**清理:**

```bash
# 删除未使用的镜像
docker image prune -a

# 删除未使用的容器
docker container prune

# 删除未使用的卷
docker volume prune
```

---

### Q5: 如何更新后端代码

```bash
# 1. 本地修改代码
# 编辑代码...

# 2. 提交并推送到 GitHub
git add .
git commit -m "Update backend logic"
git push origin main

# 3. 本地重新构建镜像
docker build -t docker.io/<你的账号>/auto-hr-backend:latest ./backend

# 4. 推送到 Docker Hub
docker push docker.io/<你的账号>/auto-hr-backend:latest

# 5. 在服务器上重新部署
ssh ubuntu@<服务器IP>
cd ~/auto-hr
docker-compose pull
docker-compose up -d
```

---

### Q6: 如何定时备份数据

```bash
# SSH 到服务器
ssh ubuntu@<服务器IP>
cd ~/auto-hr

# 查看数据卷位置
docker inspect auto-hr-backend | grep Mounts

# 手动备份
docker cp auto-hr-backend:/app/storage ./backup-$(date +%Y%m%d)

# 定时备份（crontab）
crontab -e
# 添加行: 0 2 * * * cd ~/auto-hr && docker cp auto-hr-backend:/app/storage ./backups/backup-$(date +\%Y\%m\%d)
```

---

## 检查清单

### 本地准备
- [ ] Docker Desktop 已安装
- [ ] 项目代码已克隆
- [ ] `backend/Dockerfile` 存在
- [ ] `frontend/next.config.ts` 已改为 `output: 'export'`

### Docker 构建
- [ ] 本地镜像构建成功
- [ ] 本地测试容器运行正常
- [ ] Docker Hub 账号已创建

### 镜像推送
- [ ] `docker login` 成功
- [ ] 镜像已推送到 Docker Hub
- [ ] Docker Hub 上可以看到镜像

### 云服务器部署
- [ ] SSH 可连接到服务器
- [ ] Docker 已安装
- [ ] `.env` 文件已创建并配置
- [ ] `docker-compose.yml` 已创建
- [ ] 容器已启动并运行
- [ ] 防火墙已开放 8000 端口
- [ ] `http://<服务器IP>:8000/health` 返回 200

### Cloudflare Pages 部署
- [ ] 代码已推送到 GitHub
- [ ] Cloudflare Pages 项目已连接 GitHub
- [ ] 构建命令配置正确
- [ ] 环境变量 `NEXT_PUBLIC_API_BASE` 已设置
- [ ] 前端部署成功
- [ ] 前端可访问
- [ ] 后端 CORS 已配置 Cloudflare 域名

### 验证测试
- [ ] 前端可访问（https://auto-hr-xxxx.pages.dev）
- [ ] 后端健康检查通过
- [ ] 前端能连接后端 API
- [ ] Browser F12 Console 无 CORS 错误
- [ ] Network 中的 API 请求返回 200

---

## 支持和反馈

部署遇到问题？

1. **查看日志:**
   ```bash
   docker-compose logs -f
   ```

2. **重启服务:**
   ```bash
   docker-compose restart
   ```

3. **检查配置:**
   ```bash
   cat .env
   docker-compose ps
   ```

4. **GitHub Issues:**
   在项目 GitHub 上提交问题

---

**祝部署顺利！** 🚀
