#!/usr/bin/env bash
set -u

BASE_DIR="${QQ_HERMES_BASE_DIR:-/home/roxy/qq-hermes}"
if [ -f "$BASE_DIR/scripts/load_env.sh" ]; then
  # shellcheck source=/home/roxy/qq-hermes/scripts/load_env.sh
  . "$BASE_DIR/scripts/load_env.sh" "$BASE_DIR/.env"
fi
BASE_DIR="${QQ_HERMES_BASE_DIR:-$BASE_DIR}"
TOKEN="${ONEBOT_ACCESS_TOKEN:-}"
API_URL="${ONEBOT_HTTP_URL:-http://127.0.0.1:3000}"
BRIDGE_URL="${BRIDGE_URL:-http://127.0.0.1:18765/health}"
CONTAINER="${NAPCAT_CONTAINER:-${NAPCAT_CONTAINER_NAME:-napcat}}"
QR_PATH="$BASE_DIR/napcat-login/qrcode.png"

DOCKER="${DOCKER:-docker}"
if ! $DOCKER ps >/dev/null 2>&1 && command -v sudo >/dev/null 2>&1; then
  DOCKER="sudo docker"
fi

ok=0
warn=0
bad=0

say() { printf '%s\n' "$*"; }
section() { printf '\n== %s ==\n' "$*"; }
pass() { ok=$((ok+1)); say "[OK] $*"; }
notice() { warn=$((warn+1)); say "[WARN] $*"; }
fail() { bad=$((bad+1)); say "[FAIL] $*"; }

json_get_bool() {
  python3 -c 'import json,sys; data=json.load(sys.stdin); cur=data; 
for p in sys.argv[1].split("."):
    cur=cur[p]
print("true" if cur is True else "false" if cur is False else cur)' "$1" 2>/dev/null
}

section "Bridge"
if command -v systemctl >/dev/null 2>&1; then
  if systemctl --user is-active --quiet qq-hermes-bridge.service; then
    pass "qq-hermes-bridge.service active"
  else
    fail "qq-hermes-bridge.service not active；可执行：systemctl --user restart qq-hermes-bridge.service"
  fi
else
  notice "systemctl 不可用，跳过 bridge service 检查"
fi

bridge_resp="$(curl -sS --noproxy '*' -m 5 "$BRIDGE_URL" 2>/dev/null || true)"
if printf '%s' "$bridge_resp" | grep -q '"ok"[[:space:]]*:[[:space:]]*true'; then
  pass "bridge health ok: $BRIDGE_URL"
else
  fail "bridge health 不正常: ${bridge_resp:-无响应}"
fi

section "NapCat container"
if ! command -v docker >/dev/null 2>&1; then
  fail "docker 命令不存在"
else
  ps_line="$($DOCKER ps -a --filter name="$CONTAINER" --format 'name={{.Names}} status={{.Status}} ports={{.Ports}}' 2>/dev/null || true)"
  if [ -z "$ps_line" ]; then
    notice "当前用户暂时不能读取 Docker 容器列表，跳过容器名检查；如果 OneBot API reachable，NapCat 实际已经在运行。"
  else
    say "$ps_line"
    if printf '%s' "$ps_line" | grep -q 'status=Up'; then
      pass "NapCat container running"
    else
      fail "NapCat container not running；可执行：sudo docker start $CONTAINER"
    fi
  fi
fi

section "OneBot HTTP API"
if [ -n "$TOKEN" ]; then
  status_resp="$(curl -sS --noproxy '*' -m 8 -H "Authorization: Bearer ${TOKEN}" "$API_URL/get_status" 2>/dev/null || true)"
else
  status_resp="$(curl -sS --noproxy '*' -m 8 "$API_URL/get_status" 2>/dev/null || true)"
fi
if [ -z "$status_resp" ]; then
  fail "OneBot API 无响应：$API_URL/get_status"
elif printf '%s' "$status_resp" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'; then
  pass "OneBot API reachable"
  online="$(printf '%s' "$status_resp" | json_get_bool data.online || true)"
  good="$(printf '%s' "$status_resp" | json_get_bool data.good || true)"
  say "online=$online good=$good"
  if [ "$good" = "true" ] && [ "$online" = "true" ]; then
    pass "QQ 账号在线：不要重复登录"
  elif [ "$good" = "true" ] && [ "$online" = "false" ]; then
    fail "NapCat 服务正常，但 QQ 账号离线：需要扫码/手机确认登录"
  else
    notice "OneBot 返回异常状态：$status_resp"
  fi
else
  fail "OneBot API 返回异常：$status_resp"
  if printf '%s' "$status_resp" | grep -qi 'token verify failed'; then
    notice "token 不匹配。当前脚本使用 TOKEN=$TOKEN；如你改过 OneBot token，请用 ONEBOT_ACCESS_TOKEN=新token $0"
  fi
fi

section "Login hints"
if command -v docker >/dev/null 2>&1 && $DOCKER ps --filter name="$CONTAINER" --format '{{.Names}}' 2>/dev/null | grep -qx "$CONTAINER"; then
  latest_qr="$($DOCKER logs "$CONTAINER" 2>&1 | grep '二维码解码URL' | tail -1 || true)"
  latest_kick="$($DOCKER logs --since 2h "$CONTAINER" 2>&1 | grep -E 'KickedOffLine|登录态已失效|账号状态变更为离线|请重新登录' | tail -5 || true)"
  if [ -n "$latest_kick" ]; then
    notice "最近 2 小时出现登录失效/离线日志："
    printf '%s\n' "$latest_kick"
  fi
  if [ -n "$latest_qr" ]; then
    say "最新二维码 URL：$latest_qr"
  fi
  mkdir -p "$BASE_DIR/napcat-login"
  if $DOCKER cp "$CONTAINER:/app/napcat/cache/qrcode.png" "$QR_PATH" >/dev/null 2>&1; then
    say "二维码图片已复制到：$QR_PATH"
  else
    notice "未能复制二维码图片；如果当前已在线，这通常不影响使用"
  fi
fi

section "Summary"
say "OK=$ok WARN=$warn FAIL=$bad"
if [ "$bad" -eq 0 ]; then
  say "结论：服务链路正常。若 WebUI 提示重复登录，以 get_status 的 online=true 为准。"
  exit 0
fi
say "结论：存在需要处理的问题；优先看上面的 [FAIL]。"
exit 1
