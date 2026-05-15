#!/bin/bash
# Docker 构建和推送脚本

set -e

# 配置
IMAGE_NAME="${1:-auto-hr-backend}"
REGISTRY="${2:-docker.io}"  # 默认 Docker Hub，改为自己的仓库
TAG="${3:-latest}"
FULL_IMAGE="$REGISTRY/$IMAGE_NAME:$TAG"

echo "================================"
echo "Auto HR Backend Docker 构建脚本"
echo "================================"
echo "镜像名称: $FULL_IMAGE"
echo ""

# Step 1: 构建镜像
echo "📦 Step 1: 构建 Docker 镜像..."
docker build -t "$FULL_IMAGE" ./backend

echo "✅ 镜像构建完成"
echo ""

# Step 2: 本地测试 (可选)
echo "🧪 Step 2: 本地测试镜像..."
echo "运行容器测试 (30 秒后停止)..."
docker run --rm -d \
  --name test-auto-hr \
  -p 8000:8000 \
  -e CORS_ORIGINS="*" \
  "$FULL_IMAGE" &

CONTAINER_ID=$!
sleep 5

# 检查健康
if curl -s http://localhost:8000/health | grep -q "ok"; then
  echo "✅ 健康检查通过"
else
  echo "⚠️ 健康检查失败（可能是预期的）"
fi

docker stop test-auto-hr 2>/dev/null || true
sleep 2

echo ""

# Step 3: 推送到仓库
echo "📤 Step 3: 推送镜像到仓库..."
echo "运行以下命令推送镜像:"
echo ""
echo "  docker push $FULL_IMAGE"
echo ""
echo "如果还没有登录，先运行:"
echo "  docker login"
echo ""
echo "完整推送命令:"
docker push "$FULL_IMAGE" || {
  echo ""
  echo "❌ 推送失败"
  echo ""
  echo "可能的原因:"
  echo "1. 没有登录 docker login"
  echo "2. 仓库权限不足"
  echo "3. 网络连接问题"
  exit 1
}

echo ""
echo "✅ Docker 镜像推送完成！"
echo ""
echo "================================"
echo "下一步部署到云服务器:"
echo "================================"
echo ""
echo "1. 在云服务器上安装 Docker"
echo "2. 运行以下命令:"
echo ""
echo "   docker run -d \\
     --name auto-hr-backend \\
     -p 8000:8000 \\
     -e CORS_ORIGINS=\"https://auto-hr.pages.dev,http://localhost:3000\" \\
     -e AUTO_HR_LLM_API_KEY=\"<your-key>\" \\
     -e AUTO_HR_LLM_BASE_URL=\"<your-api-url>\" \\
     -v auto-hr-storage:/app/storage \\
     $FULL_IMAGE"
echo ""
