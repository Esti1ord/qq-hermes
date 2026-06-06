#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [ -f "./scripts/load_env.sh" ]; then
  # shellcheck source=./scripts/load_env.sh
  source "./scripts/load_env.sh" "./.env"
fi

NAPCAT_ACCOUNT="${NAPCAT_ACCOUNT:-3975680980}"
NAPCAT_WEBUI_TOKEN="${NAPCAT_WEBUI_TOKEN:-}"
NAPCAT_WEBUI_PREFIX="${NAPCAT_WEBUI_PREFIX:-/webui}"
NAPCAT_CONTAINER_NAME="${NAPCAT_CONTAINER_NAME:-napcat}"
NAPCAT_HOSTNAME="${NAPCAT_HOSTNAME:-desktop-48c50d740a70}"
NAPCAT_MAC_ADDRESS="${NAPCAT_MAC_ADDRESS:-02:c2:0e:1c:42:03}"
NAPCAT_IMAGE="${NAPCAT_IMAGE:-mlikiowa/napcat-docker:v4.10.47}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker 未安装。请先安装 Docker。" >&2
  exit 1
fi

DOCKER="docker"
if ! docker ps >/dev/null 2>&1; then
  DOCKER="sudo docker"
fi

mkdir -p ./napcat-data/QQ ./napcat-data/config ./napcat-data/plugins

if $DOCKER ps -a --format '{{.Names}}' | grep -qx "$NAPCAT_CONTAINER_NAME"; then
  current_hostname="$($DOCKER inspect "$NAPCAT_CONTAINER_NAME" --format '{{.Config.Hostname}}' 2>/dev/null || true)"
  current_mac="$($DOCKER inspect "$NAPCAT_CONTAINER_NAME" --format '{{range .NetworkSettings.Networks}}{{.MacAddress}}{{end}}' 2>/dev/null || true)"
  current_image="$($DOCKER inspect "$NAPCAT_CONTAINER_NAME" --format '{{.Config.Image}}' 2>/dev/null || true)"
  if [ "$current_hostname" != "$NAPCAT_HOSTNAME" ] || { [ -n "$NAPCAT_MAC_ADDRESS" ] && [ "$current_mac" != "$NAPCAT_MAC_ADDRESS" ]; } || [ "$current_image" != "$NAPCAT_IMAGE" ]; then
    echo "检测到现有容器 image=$current_image hostname=$current_hostname mac=${current_mac:-unknown}，不是期望的 image=$NAPCAT_IMAGE hostname=$NAPCAT_HOSTNAME mac=${NAPCAT_MAC_ADDRESS:-auto}。"
    echo "Docker 容器 image/hostname/MAC 无法原地修改，将重建容器但保留 napcat-data 挂载数据。"
    $DOCKER rm -f "$NAPCAT_CONTAINER_NAME" >/dev/null
  else
    $DOCKER start "$NAPCAT_CONTAINER_NAME" >/dev/null
  fi
fi

if ! $DOCKER ps -a --format '{{.Names}}' | grep -qx "$NAPCAT_CONTAINER_NAME"; then
  $DOCKER run -d \
    -e NAPCAT_UID="$(id -u)" \
    -e NAPCAT_GID="$(id -g)" \
    -e ACCOUNT="$NAPCAT_ACCOUNT" \
    -e WEBUI_TOKEN="$NAPCAT_WEBUI_TOKEN" \
    -e WEBUI_PREFIX="$NAPCAT_WEBUI_PREFIX" \
    --hostname "$NAPCAT_HOSTNAME" \
    ${NAPCAT_MAC_ADDRESS:+--mac-address "$NAPCAT_MAC_ADDRESS"} \
    -p 3000:3000 \
    -p 3001:3001 \
    -p 6099:6099 \
    -v "$PWD/napcat-data/QQ:/app/.config/QQ" \
    -v "$PWD/napcat-data/config:/app/napcat/config" \
    -v "$PWD/napcat-data/plugins:/app/napcat/plugins" \
    --name "$NAPCAT_CONTAINER_NAME" \
    --restart unless-stopped \
    "$NAPCAT_IMAGE" >/dev/null
fi

echo "NapCat 已启动。正在显示日志；按 Ctrl+C 只会退出日志查看，不会删除容器。"
echo "容器名：$NAPCAT_CONTAINER_NAME"
echo "容器 hostname / 设备名候选：$NAPCAT_HOSTNAME"
echo "容器 MAC 地址：${NAPCAT_MAC_ADDRESS:-Docker auto}"
echo "Docker 镜像：$NAPCAT_IMAGE"
echo "如需停止 NapCat：sudo docker stop $NAPCAT_CONTAINER_NAME"
echo
exec $DOCKER logs -f "$NAPCAT_CONTAINER_NAME"
