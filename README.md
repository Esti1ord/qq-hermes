# QQ Hermes Bridge

QQ Hermes Bridge 是一个本地运行的 QQ 群聊桥接服务。它通过 NapCat 暴露的 OneBot v11 接口接收群消息，把需要处理的内容交给 Hermes CLI，再把生成的回复发回 QQ 群。

这个项目不是通用 QQ 机器人框架，更接近一个为固定群聊场景维护的个人机器人运行方案。默认目标是让 Esti 像群友一样参与聊天：能接住上下文，被明确点名时稳定回复，平时尽量少打扰，也避免把内部提示词、工具报错和运行细节漏到群里。项目默认运行在使用者自己的 Linux 主机上，通过本人授权的 QQ/NapCat 登录态服务明确配置过的群。

## 快速理解

一条典型消息链路：

```text
QQ 群消息
  -> NapCat Docker 收到事件
  -> OneBot HTTP client POST 到 bridge 的 /onebot
  -> bridge.py 判断命令、点名、回复、主动发言等路由
  -> 必要时读取群资料、最近上下文、图片 OCR、搜索结果
  -> 调用 hermes chat -q 生成回复
  -> OneBot HTTP API send_group_msg 发回 QQ 群
```

当前默认运行形态：

| 组件 | 默认值 |
|---|---|
| 项目目录 | `/home/roxy/qq-hermes` |
| Bridge 服务 | `qq-hermes-bridge.service` |
| Bridge health | `http://127.0.0.1:8765/health` |
| OneBot webhook | `http://172.17.0.1:8765/onebot` |
| NapCat HTTP API | `http://127.0.0.1:3000` |
| NapCat WebUI | `http://127.0.0.1:6099/webui` |
| NapCat 容器 | `napcat` |
| 群配置目录 | `groups/<group_id>/` |

## 重要边界

这个仓库可以公开或私有托管源代码，但运行数据不应提交。

不要提交或公开分享：

- `.env`、API key、token、provider base URL 中的私密部分；
- QQ 密码、扫码二维码、手机确认截图、cookie；
- `napcat-data/`、`napcat-login/`、`napcat-qrcode.png`：QQ/NapCat 登录态和登录材料；
- `logs/`：运行日志、群上下文、内容分析日志；
- `groups/`、`base_persona.md`：群资料、人设、私有知识；
- `venv/`、`__pycache__/`、`.pytest_cache/` 等本地构建/缓存目录；
- `NapCatQQ/`、`NapCat-Docker/`、`napcat-shell/` 等第三方源码或运行时目录。

当前 `.gitignore` 已覆盖这些路径。提交前仍建议检查：

```bash
git status --short
git add -n .
```

确认 staged/dry-run 清单里没有敏感文件后再提交。

## 目录结构

```text
qq-hermes/
├── bridge.py                  # FastAPI 入口和运行时编排
├── qq_hermes_bridge/          # 主要业务模块
│   ├── onebot.py              # OneBot 消息段、@、reply 解析
│   ├── handlers.py            # 路由决策：命令、direct、proactive
│   ├── commands.py            # /context、/search、/deepseek、jrrp 等
│   ├── reply_queue.py         # 每群回复队列
│   ├── context_store.py       # 群上下文缓存和摘要
│   ├── group_files.py         # persona/people/knowledge 文件选择
│   ├── hermes_runtime.py      # Hermes CLI 调用与 session 辅助
│   ├── media.py               # 图片/媒体引用解析
│   ├── media_fetch.py         # 受限图片下载
│   ├── vision.py              # OCR/图片理解 provider
│   ├── search.py              # 搜索命令辅助
│   ├── runtime_stats.py       # 内容安全运行统计
│   ├── outbound.py            # OneBot 发消息、reply、去重
│   └── proactive.py           # 主动发言评分和限制
├── scripts/                   # 运维脚本
├── tests/                     # pytest 测试
├── .env.example               # 配置模板，可提交
├── .env                       # 本机私密配置，不提交
├── groups/                    # 私有群资料，不提交
├── logs/                      # 私有运行日志，不提交
└── napcat-data/               # QQ/NapCat 登录态，不提交
```

`bridge.py` 仍承担入口和运行时协调职责；可复用逻辑大多已经下沉到 `qq_hermes_bridge/`。后续重构方向是继续削薄 `bridge.py`，把全局状态、配置读取和运行时上下文迁到更清晰的 app context，而不是再新建一套并行架构。

## 首次配置

首次部署时复制配置模板：

```bash
cd /home/roxy/qq-hermes
cp .env.example .env
```

配置读取优先级：

```text
已导出的 shell/systemd 环境变量 > 根目录 .env > 代码或脚本默认值
```

最少需要确认这些项：

```dotenv
BOT_QQ=<机器人 QQ>
GROUP_IDS=<允许服务的群号，逗号分隔>
ONEBOT_HTTP_URL=http://127.0.0.1:3000
ONEBOT_ACCESS_TOKEN=<NapCat OneBot HTTP API token，如未设置可留空>
BRIDGE_INBOUND_TOKEN=<NapCat 上报 bridge 时使用的 token，如未启用可留空>
HERMES_BIN=/home/roxy/.local/bin/hermes
HERMES_HOME=/home/roxy/.hermes
HERMES_PROVIDER=<默认 provider>
HERMES_MODEL=<默认模型>
```

修改 `.env` 后通常需要重启 bridge 才会生效。

## 启动和状态检查

整体状态检查：

```bash
cd /home/roxy/qq-hermes
./check-status.sh
```

Bridge 使用 user systemd 管理：

```bash
systemctl --user status qq-hermes-bridge.service
systemctl --user restart qq-hermes-bridge.service
systemctl --user stop qq-hermes-bridge.service
journalctl --user -u qq-hermes-bridge.service -f
```

健康检查接口：

```bash
curl -sS http://127.0.0.1:8765/health
```

NapCat 容器常用命令：

```bash
sudo docker ps --filter name=napcat
sudo docker logs --tail 100 napcat
sudo docker logs -f napcat
sudo docker restart napcat
```

启动或重建 NapCat 容器：

```bash
cd /home/roxy/qq-hermes
./start-napcat-docker.sh
```

这个脚本会读取 `.env`，创建所需目录，并在容器不存在或关键配置变化时创建/重建容器。

## NapCat 与 OneBot

QQ 登录态、群聊事件接收和 OneBot v11 HTTP API 由 NapCat 负责。Bridge 不直接处理 QQ 协议，只通过 OneBot 与 NapCat 交互。

常用端口：

```text
3000  OneBot HTTP API
3001  NapCat 额外端口
6099  NapCat WebUI
```

WebUI：

```text
http://127.0.0.1:6099/webui
```

登录态保存在：

```text
/home/roxy/qq-hermes/napcat-data/QQ
```

如果 NapCat 日志出现快速登录失败、登录态失效、需要手机 QQ 验证、扫码过期等情况，需要通过 WebUI 或手机 QQ 完成确认。二维码、验证码、密码和 cookie 不应交给模型，也不应提交到仓库。

这里有三类 token，不要混用：

| 用途 | NapCat 侧 | Bridge / `.env` | 说明 |
|---|---|---|---|
| Bridge 调 NapCat 发消息 | OneBot HTTP server token | `ONEBOT_ACCESS_TOKEN` | NapCat API 开 token 时 bridge 必须带同一个 |
| NapCat 上报 Bridge | OneBot HTTP client token/header | `BRIDGE_INBOUND_TOKEN` | Bridge 开启入站鉴权时必须匹配 |
| 登录 NapCat WebUI | WebUI token | `NAPCAT_WEBUI_TOKEN` | 只用于 WebUI 登录 |

推荐 OneBot 形态：

```text
HTTP API server: 0.0.0.0:3000, messagePostFormat=array
HTTP client: http://172.17.0.1:8765/onebot, reportSelfMessage=true, messagePostFormat=array
```

## Hermes 调用方式

Bridge 通过 Hermes CLI 生成文本回复。普通群聊建议启用持久 group session，让机器人能延续同一群的上下文。

典型调用形态：

```text
HERMES_BIN chat -q <prompt> --quiet \
  --continue qq-group-<group_id> \
  --source qq-bridge:<group_id> \
  --model <model> \
  --provider <provider>
```

常用配置：

```dotenv
HERMES_BIN=/home/roxy/.local/bin/hermes
HERMES_HOME=/home/roxy/.hermes
HERMES_PROVIDER=<默认 provider>
HERMES_MODEL=<默认模型>
HERMES_TIMEOUT=180
HERMES_GROUP_SESSIONS_ENABLED=true
HERMES_GROUP_SESSION_PREFIX=qq-group
```

普通群聊 session 名称：

```text
qq-group-<group_id>
```

可以按群覆盖模型：

```dotenv
HERMES_PROVIDER_BY_GROUP=781423661=deepseek,975805598=openai-gpt
HERMES_MODEL_BY_GROUP=781423661=deepseek-v4-flash,975805598=gpt-5.5
```

`/search` 和 `/deepseek` 使用独立配置，避免污染普通群聊 session：

```dotenv
WEB_SEARCH_PROVIDER=deepseek
WEB_SEARCH_MODEL=deepseek-v4-flash
DEEPSEEK_COMMAND_PROVIDER=deepseek
DEEPSEEK_COMMAND_MODEL=deepseek-v4-flash
```

## 群资料和上下文

每个群可以保留独立资料目录：

```text
groups/<group_id>/
├── persona.md
├── people.md
└── knowledge.md
```

这些文件的用途：

- `persona.md`：本群风格、口癖、边界和行为偏好；
- `people.md`：群友昵称、梗、关系、背景资料；
- `knowledge.md`：稳定知识、可信资料、长期参考信息；
- 最近上下文和摘要：由 bridge 在本地运行时维护；
- Hermes session：`qq-group-<group_id>`。

添加新群：

```bash
cd /home/roxy/qq-hermes
scripts/add_group.sh <group_id> [persona text]
```

脚本会创建群目录和基础文件，并把群号加入 `groups/groups.txt`。已有文件不会被覆盖。

`people.md` 建议写短一点，方便长期维护：

```markdown
<!-- people.md 示例 -->
### QQ号或主要昵称
- 昵称：常用昵称、别名
- 标签：关键词、梗、关系
- 背景：只写用户允许记录且对聊天理解有帮助的信息
- 备注：可选
```

### 腾讯文档同步 people.md

如果腾讯文档作为群资料的在线源，可以使用：

```text
scripts/sync_people_from_qqdocs.py
scripts/sync_people_<group_id>_from_qqdocs.sh
```

定时任务示例：

```cron
7,37 * * * * /home/roxy/qq-hermes/scripts/sync_people_781423661_from_qqdocs.sh >> /home/roxy/qq-hermes/logs/people-sync-781423661.log 2>&1
```

同步脚本会读取本机 Firefox 的腾讯文档登录 cookie。cookie 属于敏感数据，只应在本机使用；如果 cookie 过期，需要重新登录腾讯文档。

## 回复策略

Bridge 不会对每条消息都调用模型。消息会先经过路由判断，再决定是否回复。

### 直接回复 direct

这些情况会进入 direct 路由：

- 群消息中 `@` 机器人 QQ；
- 用户使用 QQ “回复”功能回复机器人上一条消息；
- 文本命中配置的机器人名字/昵称，如 `Esti`、`机器人` 等。

direct 消息会进入每群 direct 队列，由 worker 顺序处理，并尽量用 QQ reply 形式回到原消息：

```text
[CQ:reply,id=<message_id>]
```

当前原则是：明确 direct 提问不因普通用户冷却而丢弃。同一用户连续问，只要不是重复事件、队列没满、发送没失败，就尽量做到“一问一答”。

同时保留这些保护：

- OneBot 事件去重；
- 每群队列上限；
- 每群 worker 串行处理；
- outbound 重复发送抑制；
- 全局最小发送间隔；
- Hermes 空输出/超时兜底。

如果 direct 生成失败，bridge 会先尝试一次 no-session 重试。仍失败时，才发送简短可见提示：

```text
[CQ:reply,id=<message_id>][CQ:at,qq=<user_id>] 稍后重试一下
```

### 主动发言 proactive

普通群消息默认只写入上下文，不一定回复。主动发言由热度分数、关键词、问题形态、多用户活跃、夜间倍率、敏感词冷却和群级限速共同决定。

常用配置：

```dotenv
PROACTIVE_ENABLED=true
PROACTIVE_TRIGGER_THRESHOLD=16
PROACTIVE_TRIGGER_THRESHOLDS_BY_GROUP=781423661=999,975805598=16
PROACTIVE_GROUP_COOLDOWN_SECONDS=20
PROACTIVE_DAILY_LIMIT_PER_GROUP=80
PROACTIVE_RATE_LIMIT_WINDOW_SECONDS=60
PROACTIVE_RATE_LIMIT_MAX_REPLIES=10
PROACTIVE_NAME_TRIGGERS=Esti,Estilord,Esti1ord,机器人,bot,小E
```

示例：

- `781423661=999` 基本禁用普通热度主动发言；direct 和命令仍可用；
- `975805598=16` 热度达到 16 才考虑主动接话；
- 名字触发按 direct/名称提及处理，不等于绕过所有安全和队列限制。

## 群内命令

### `/context`

查看本群当前本地上下文摘要和最近消息。不调用 LLM，也不进入普通回复队列。

```text
/context
@Esti /context
```

### `/search`

显式联网搜索命令。普通闲聊不会自动联网。

```text
/search 你要查的内容
@Esti /search 你要查的内容
```

设计边界：

- 只服务本次命令；
- 不写入普通 Hermes group session；
- 证据不足时返回不确定，不硬编。

### `/deepseek`

深度搜索/分析命令。命令名叫 `/deepseek`，但不和 DeepSeek 模型强绑定。

```text
/deepseek 你要深度分析的问题
@Esti /deepseek 你要深度分析的问题
```

行为：

1. 先搜索查证；
2. 再用全新的 no-session Hermes 调用生成深度回答；
3. 不继承普通群聊上下文、persona、摘要缓存或 `qq-group-<id>` session；
4. 超长时会尝试压缩重写，避免半句话截断。

### `jrrp`

今日人品，纯确定性命令，不调用 LLM。

触发规则很严格：整条消息去掉首尾空白后必须等于 `jrrp`，大小写不敏感。

会触发：

```text
jrrp
JRRP
 jrrp
```

不会触发：

```text
今天jrrp
jrrp一下
我的 jrrp 怎么样
@Esti jrrp
```

## 图片理解 / OCR

Bridge 支持图片理解，但默认关闭。不开 OCR 时，图片会降级为 `[图片]` 占位符进入文本处理。

相关模块：

- `media.py`：提取 OneBot 图片引用；
- `media_fetch.py`：按大小、Content-Type、超时、跳转限制下载图片；
- `vision.py`：OCR/图片理解 provider，支持 Hermes `chat --image`、mock、none；
- `bridge.py`：把图片理解结果放进本次 prompt 或群上下文。

常用配置：

```dotenv
OCR_ENABLED=false
OCR_TRIGGER_MODE=direct_only
OCR_PROVIDER=hermes
OCR_EXTERNAL_PROVIDER_ALLOWED=false
OCR_MAX_IMAGES_PER_MESSAGE=2
OCR_MAX_BYTES_PER_IMAGE=6291456
OCR_ALLOWED_CONTENT_TYPES=image/jpeg,image/png,image/webp,image/gif
OCR_DOWNLOAD_TIMEOUT=8
OCR_PROVIDER_TIMEOUT=30
OCR_MAX_RESULT_CHARS=800
OCR_INCLUDE_IN_PROMPT=true
OCR_INCLUDE_IN_CONTEXT=true
OCR_PERSIST_TEXT_IN_CONTEXT=false
OCR_LOG_TEXT=false
OCR_LOG_IMAGE_URLS=false
```

模式：

- `direct_only`：只处理 direct 消息里的图片；
- `direct_and_context`：direct 同步识别，普通允许群图片异步识别并加入上下文；
- `context_only`：只做普通上下文图片识别；
- `all` / `all_allowed_messages`：允许更多路由使用 OCR。

隐私原则：默认不识图、不持久化 OCR 文本、不记录 OCR 文本、不记录图片 URL。图片文件只作为临时文件传给 provider，调用后删除。若要使用 Hermes 或其他外部 provider，需要显式设置：

```dotenv
OCR_EXTERNAL_PROVIDER_ALLOWED=true
```

如果需要让机器人长期记住图片等价文字上下文，可以这样配置：

```dotenv
OCR_ENABLED=true
OCR_TRIGGER_MODE=direct_and_context
OCR_EXTERNAL_PROVIDER_ALLOWED=true
OCR_INCLUDE_IN_CONTEXT=true
OCR_PERSIST_TEXT_IN_CONTEXT=true
```

开启前需要确认：这些文字描述会进入本地上下文文件，属于真实群聊内容。

## 日志和统计

### `logs/runtime_stats.jsonl`

这是用于排查性能和稳定性的运行统计。设计上不记录群聊正文、prompt、模型输出、OCR 文本、图片 URL、token、cookie 或完整接口响应。

主要用于观察：

- direct/proactive 请求量、成功率、失败原因；
- 入站、排队、Hermes 调用、OneBot 发送耗时；
- 队列积压、队列满、重复发送抑制；
- OCR fetch/provider/context update 耗时；
- `/search`、`/deepseek` 阶段耗时。

### `logs/content_analysis.jsonl`

这是更敏感的真实内容分析日志。开启后会记录群聊文本、上下文片段和机器人回复，只适合本地定性分析。公开分享、提交 issue 或交给他人分析前，应先手动复查和脱敏。

相关配置：

```dotenv
CONTENT_ANALYSIS_LOG_ENABLED=true
CONTENT_ANALYSIS_LOG_FILE=/home/roxy/qq-hermes/logs/content_analysis.jsonl
CONTENT_ANALYSIS_ALLOWED_GROUP_IDS=
CONTENT_ANALYSIS_CONTEXT_MESSAGES=8
CONTENT_ANALYSIS_MAX_TEXT_CHARS=1000
CONTENT_ANALYSIS_MAX_REPLY_CHARS=1000
CONTENT_ANALYSIS_INCLUDE_SUMMARIES=true
```

## 常用调参

机器人太吵：

```dotenv
PROACTIVE_TRIGGER_THRESHOLD=20
PROACTIVE_RATE_LIMIT_MAX_REPLIES=6
PROACTIVE_GROUP_COOLDOWN_SECONDS=60
PROACTIVE_DAILY_LIMIT_PER_GROUP=8
```

机器人太安静：

```dotenv
PROACTIVE_TRIGGER_THRESHOLD=12
PROACTIVE_SCORE_TOPIC_KEYWORD=5
PROACTIVE_SCORE_LIGHT_KEYWORD=3
```

某个群基本禁用普通主动发言：

```dotenv
PROACTIVE_TRIGGER_THRESHOLDS_BY_GROUP=<group_id>=999
```

回复太长：

```dotenv
MAX_REPLY_CHARS=300
```

上下文太少：

```dotenv
CONTEXT_MAX_MESSAGES=30
CONTEXT_SUMMARY_MAX=50
```

指定某群模型：

```dotenv
HERMES_PROVIDER_BY_GROUP=781423661=deepseek
HERMES_MODEL_BY_GROUP=781423661=deepseek-v4-flash
```

修改 `.env` 后通常需要重启 bridge；修改 `groups/<group_id>/*.md` 通常下一次生成回复会重新读取。

## 测试与开发

常用验证：

```bash
cd /home/roxy/qq-hermes
./venv/bin/python -m py_compile bridge.py scripts/sync_people_from_qqdocs.py
./venv/bin/python -m pytest tests -q
```

局部测试：

```bash
./venv/bin/python -m pytest tests/test_direct_reply_inflight.py -q
./venv/bin/python -m pytest tests/test_bridge_ocr.py tests/test_media_fetch_module.py tests/test_vision_module.py -q
./venv/bin/python -m pytest tests/test_hermes_group_sessions.py tests/test_config_utils_module.py -q
./venv/bin/python -m pytest tests/test_runtime_stats_module.py tests/test_content_analysis_log_module.py -q
```

Shell 脚本语法检查：

```bash
bash -n start-bridge.sh
bash -n start-napcat-docker.sh
bash -n check-status.sh
bash -n scripts/add_group.sh
bash -n scripts/load_env.sh
```

提交前建议运行：

```bash
git status --short
git diff --check
git add -n .
```

只提交源代码、测试、文档、模板和脚本。

## 常见排障

### Bridge 不在线

```bash
systemctl --user status qq-hermes-bridge.service --no-pager
journalctl --user -u qq-hermes-bridge.service -n 100 --no-pager
curl -sS http://127.0.0.1:8765/health
```

常见原因：`.env` 配置错误、Python 虚拟环境不可执行、端口被占用、Hermes CLI 路径错误。

### NapCat / OneBot 离线

```bash
./check-status.sh
sudo docker ps --filter name=napcat
sudo docker logs --tail 100 napcat
```

如果出现 `[KickedOffLine] 登录已失效`、快速登录需要验证、扫码过期等，需要重新登录。二维码、验证码和密码都不能外传。

### token mismatch

现象：OneBot API 返回 token verify failed，或 bridge `/onebot` 返回 401。

检查：

- NapCat OneBot HTTP server token 是否匹配 `ONEBOT_ACCESS_TOKEN`；
- NapCat HTTP client 入站 token 是否匹配 `BRIDGE_INBOUND_TOKEN`；
- WebUI token 与 OneBot token 不是同一个用途。

### 机器人不回复

按这个顺序排查：

1. 群号是否在 `groups/groups.txt`、`GROUP_IDS` 或 `TARGET_GROUP_ID` 中；
2. 是否明确 @ 机器人、回复机器人消息，或命中名字触发；
3. 主动发言是否被阈值、每日上限、群冷却、窗口频率限制压住；
4. direct 队列是否满；
5. Hermes 是否超时、返回空、provider/model 是否可用；
6. OneBot 发送是否失败；
7. 如果是图片问题，OCR 是否开启、provider 是否允许、图片 URL 是否可拉取。

### 机器人回复“稍后重试一下”

这表示 direct 回复生成失败。当前逻辑会先对空输出做一次 no-session 重试；仍为空才发送可见失败提示。优先检查：

- `logs/runtime_stats.jsonl` 中的 `direct_reply_result`、`hermes_call`；
- Hermes provider/model 配置；
- group session 是否异常；
- 是否触发超时或空输出。

### 腾讯文档同步失败

```bash
tail -n 100 /home/roxy/qq-hermes/logs/people-sync-781423661.log
/home/roxy/qq-hermes/scripts/sync_people_781423661_from_qqdocs.sh
```

常见原因：Firefox 腾讯文档登录态过期、cookie 路径不对、文档权限变化、网络/API 临时失败。
