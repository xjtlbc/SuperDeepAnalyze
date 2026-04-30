#!/bin/bash
# SuperDeepAnalyze 快速启动脚本
# 用法: ./start.sh [端口]

set -e

PORT=${1:-80}
IMAGE="superdeepanalyze:latest"
CONTAINER="sda"

echo "=== SuperDeepAnalyze 启动脚本 ==="

# 检查 .env
if [ ! -f .env ]; then
    echo "[!] 未找到 .env 文件，从模板创建..."
    cp .env.example .env
    echo "[!] 请编辑 .env 填入 API Key 后重新运行"
    echo "    必填项: MAIN_API_KEY, EMBEDDING_API_KEY"
    exit 1
fi

# 检查镜像
if ! docker image inspect $IMAGE >/dev/null 2>&1; then
    echo "[!] 镜像 $IMAGE 不存在，开始构建..."
    docker build -t $IMAGE .
fi

# 停止旧容器
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
    echo "[-] 停止并移除旧容器..."
    docker rm -f $CONTAINER >/dev/null
fi

# 创建数据目录
mkdir -p data

# 启动
echo "[+] 启动容器 (端口: $PORT)..."
docker run -d \
    --name $CONTAINER \
    -p ${PORT}:80 \
    -v $(pwd)/data:/app/data \
    --env-file .env \
    --restart unless-stopped \
    $IMAGE

# 等待启动
sleep 3

# 健康检查
echo "[*] 检查服务状态..."
if curl -sf http://localhost:${PORT}/api/health | grep -q "ok"; then
    echo "[+] 服务启动成功!"
    echo "    访问地址: http://localhost:${PORT}/"
else
    echo "[!] 服务尚未就绪，查看日志:"
    docker logs $CONTAINER --tail 20
fi
