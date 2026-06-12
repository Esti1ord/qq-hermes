#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [ $# -lt 1 ]; then
  echo "用法: $0 <group_id> [persona text]" >&2
  exit 1
fi

group_id="$1"
persona_text="${2:-}"
group_dir="groups/$group_id"

if ! [[ "$group_id" =~ ^[0-9]+$ ]]; then
  echo "group_id 必须是数字: $group_id" >&2
  exit 1
fi

mkdir -p "$group_dir"
if [ ! -f "$group_dir/persona.md" ]; then
  if [ -n "$persona_text" ]; then
    printf '%s\n' "$persona_text" > "$group_dir/persona.md"
  else
    cat > "$group_dir/persona.md" <<EOF
# 群 $group_id 提示词

- 按当前群聊上下文自然接话。
- 人设只作弱约束，优先理解最近消息、回复链和群友语气。
EOF
  fi
fi

if [ ! -f "$group_dir/people.md" ]; then
  cat > "$group_dir/people.md" <<EOF
# 群 $group_id 群友资料

按需补充群友资料；这是弱提示，不是事实裁判。建议格式：

## QQ号或主要昵称
- 昵称：常用昵称、别名
- 标签：关键词、梗、关系
- 经历/背景：只写用户允许记录且对聊天理解有帮助的信息
- 备注：可选
EOF
fi

if [ ! -f "$group_dir/knowledge.md" ]; then
  cat > "$group_dir/knowledge.md" <<EOF
# 群 $group_id 知识库

记录本群稳定知识、常用链接和可信来源。
普通闲聊不会直接读取这里；涉及实时或不确定事实时不要把这里当成搜索结果。
EOF
fi

touch groups/groups.txt
if ! grep -Eq "^[[:space:]]*$group_id([[:space:]]*(#.*)?)?$" groups/groups.txt; then
  printf '%s\n' "$group_id" >> groups/groups.txt
fi

echo "已接入群聊: $group_id"
echo "群列表: groups/groups.txt"
echo "群提示词: $group_dir/persona.md"
echo "群友资料: $group_dir/people.md"
echo "群知识库: $group_dir/knowledge.md"
echo "如修改 .env/允许群配置，请重启 bridge；修改群 markdown 文件通常下次回复自动生效。"
