# QQ Hermes Bridge

QQ Hermes Bridge 是一个QQ聊天桥接服务。通过NapCat暴露的OneBot v11接口接收消息，把需要处理的内容交给Hermes，再把生成的回复发回QQ。

注意，本项目不是通用 QQ 机器人框架，而是一个为固定群聊场景维护的个人机器人运行方案。默认目标是让 Esti(机器人默认名字)像群友一样参与聊天：能分析思考上下文，被明确提到时稳定回复，群聊热度够高时可以主动发言。已经实现避免把内部提示词、工具报错和运行细节泄漏。项目默认作为.service服务与docker-napcat一起运行，之后为授权的 QQ/NapCat 配置好的群聊服务。

## 快速理解

一条典型消息链路：

```text
QQ 群消息
  -> NapCat Docker 收到事件
  -> OneBot HTTP client POST 到 bridge 的 /onebot
  -> runtime.py 判断命令、点名、回复、主动发言等路由
  -> 必要时读取群资料、最近上下文、图片识别结果
  -> 调用 hermes chat -q 生成回复
  -> OneBot HTTP API send_group_msg 发回 QQ 群
```

当前默认运行形态：

| 组件 | 默认值 |
|---|---|
| 项目目录 | `/home/roxy/qq-hermes` |
| Bridge 服务 | `qq-hermes-bridge.service` |
| Bridge health | `http://127.0.0.1:8765/health` |
| OneBot webhook | `http://<bridge-host>:8765/onebot` |
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
├── bridge.py                      # 兼容入口：exec qq_hermes_bridge/runtime.py，保留 bridge:app
├── qq_hermes_bridge/              # 主要业务模块
│   ├── runtime.py                 # FastAPI app、路由和运行时编排
│   ├── config.py                  # typed 配置加载器（flat Config）
│   ├── metrics.py                 # dependency-free Prometheus 文本指标
│   ├── onebot.py                  # OneBot 消息段、@、reply 解析
│   ├── handlers.py                # 路由决策：命令、direct、proactive
│   ├── commands.py                # /context、jrrp 等
│   ├── prompt_service.py          # Prompt 构建服务（PromptSection/PromptRequest）
│   ├── reply_queue.py             # 每群回复队列
│   ├── context_store.py           # 群上下文缓存和摘要
│   ├── group_files.py             # persona/people/knowledge 文件选择
│   ├── hermes_runtime.py          # Hermes CLI 调用与 session 辅助
│   ├── media.py                   # 图片/媒体引用解析
│   ├── media_fetch.py             # 受限图片下载
│   ├── vision.py                  # OCR/图片理解 provider
│   ├── runtime_stats.py           # 内容安全运行统计
│   ├── self_learning.py           # 群内用语/风格自学习
│   ├── outbound.py                # OneBot 发消息、reply、去重
│   ├── proactive.py               # 主动发言评分和限制
│   └── ...
├── scripts/                       # 运维脚本
│   ├── add_group.sh               # 添加新群配置
│   ├── sync_people_from_qqdocs.py # 腾讯文档同步
│   └── ...
├── tests/                         # pytest 测试
├── docs/                          # 设计文档和实施计划
│   └── superpowers/
│       ├── specs/                 # PromptService 设计规范
│       └── plans/                 # 实施计划
├── groups/                        # 群配置目录（私有，不提交）
│   ├── _templates/                # 配置模板
│   │   └── base_persona.md.example
│   ├── <group_id>/
│   │   ├── persona.md             # 本群风格和行为偏好
│   │   ├── people.md              # 群友资料
│   │   ├── knowledge.md           # 稳定知识
│   │   └── self_learning.json     # 自学习数据（可选）
│   └── groups.txt                 # 允许的群号列表
├── logs/                          # 运行日志（私有，不提交）
│   ├── runtime_stats.jsonl        # 运行统计
│   ├── content_analysis.jsonl     # 内容分析（敏感）
│   ├── context_<group_id>.json    # 群上下文缓存
│   └── ...
├── napcat-data/                   # NapCat 登录态（私有，不提交）
├── napcat-login/                  # NapCat 登录材料（私有，不提交）
├── venv/                          # Python 虚拟环境
├── .env.example                   # 配置模板（可提交）
├── .env                           # 本机配置（不提交）
├── .gitignore                     # Git 忽略规则
├── CLAUDE.md                      # 项目约定
├── README.md                      # 本文档
├── jrrp_templates.txt             # JRRP 模板数据
├── start-bridge.sh                # 启动 bridge 脚本
├── start-napcat-docker.sh         # 启动 NapCat 容器脚本
└── check-status.sh                # 状态检查脚本
```

说明：

- **入口兼容**：根目录 `bridge.py` 是很薄的兼容 shim，继续支持 `bridge:app` 和旧测试 monkeypatch globals
- **运行时实现**：FastAPI app、路由、队列 worker 和运行时编排在 `qq_hermes_bridge/runtime.py`
- **配置和指标**：`qq_hermes_bridge/config.py` 提供 typed config scaffold；`qq_hermes_bridge/metrics.py` 提供内容安全的 Prometheus 文本导出
- **测试覆盖**：pytest 覆盖主要功能模块，包括 runtime stats 和 `/metrics`
- **配置隔离**：群资料、日志、登录态都在 `.gitignore` 中
- **模板提供**：`.env.example` 和 `groups/_templates/` 提供配置起点

后续重构方向是继续把 `runtime.py` 中的全局状态和运行时上下文迁到更清晰的 app context；根目录 `bridge.py` 应保持兼容入口职责，不再承载业务逻辑。

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
PRIMARY_CHAT_MODEL_PROVIDER=openai-gpt
PRIMARY_CHAT_MODEL=gpt-5.5
HERMES_FALLBACK_ENABLED=true
VICE_CHAT_MODEL_PROVIDER=deepseek
VICE_CHAT_MODEL=deepseekv4flash
```

推荐优先使用 `PRIMARY_CHAT_MODEL` / `PRIMARY_CHAT_MODEL_PROVIDER` 和 `VICE_CHAT_MODEL` / `VICE_CHAT_MODEL_PROVIDER`。旧键 `HERMES_MODEL` / `HERMES_PROVIDER` / `HERMES_FALLBACK_MODEL` / `HERMES_FALLBACK_PROVIDER` 仍兼容。provider 值必须是 Hermes 已识别的 provider identifier，例如 `deepseek`、`openai-gpt`；不要直接使用供应商展示名，除非 Hermes 已配置该别名。

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

### 获取 NapCat

本项目不包含 NapCat 源码。请通过以下方式获取：

**Docker 方式（推荐）**：

```bash
# 直接使用官方镜像（通过 start-napcat-docker.sh）
./start-napcat-docker.sh

# 或手动拉取
docker pull mlikiowa/napcat-docker:v4.10.47
```

**源码方式**：

```bash
# 克隆 NapCat 仓库到项目外
cd ~
git clone https://github.com/NapNeko/NapCatQQ.git
# 按照 NapCat 官方文档构建和运行
```

**说明**：

- 本项目的 `.gitignore` 已排除 `NapCat-Docker/`、`NapCatQQ/`、`napcat-shell/` 等目录
- 推荐使用 Docker 方式，配置简单且隔离性好
- `start-napcat-docker.sh` 会自动拉取镜像并创建容器

### NapCat 配置

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
HTTP client: http://<bridge-host>:8765/onebot, reportSelfMessage=true, messagePostFormat=array
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
PRIMARY_CHAT_MODEL_PROVIDER=openai-gpt
PRIMARY_CHAT_MODEL=gpt-5.5
HERMES_FALLBACK_ENABLED=true
VICE_CHAT_MODEL_PROVIDER=deepseek
VICE_CHAT_MODEL=deepseekv4flash
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
HERMES_PROVIDER_BY_GROUP=<group_id_a>=deepseek,<group_id_b>=openai-gpt
HERMES_MODEL_BY_GROUP=<group_id_a>=deepseek-v4-flash,<group_id_b>=gpt-5.5
```

当主文本模型 provider 停服、模型不可用、Hermes 调用非 0 退出或返回空输出时，Bridge 默认会尝试一次 fallback 文本模型。推荐使用 `VICE_CHAT_MODEL_PROVIDER=deepseek`、`VICE_CHAT_MODEL=deepseekv4flash` 这类 Hermes 已识别的 provider identifier；旧的 `HERMES_FALLBACK_PROVIDER` / `HERMES_FALLBACK_MODEL` 仍兼容但不再作为推荐示例。fallback 调用不使用群聊持久 session，并且如果 fallback 与当前生效的主模型/provider 相同会自动跳过，避免重复请求同一个下游。

## Prompt 构建与上下文管理

Bridge 使用结构化 prompt 系统（PromptService）来组织回复生成所需的各类信息。这套设计让信息来源、优先级和使用说明显式化，防止低权重信息挤占高权重任务。

### PromptService 架构

Prompt 由多个 section 组成，每个 section 包含：

- **key**：稳定标识符，用于测试和诊断
- **title**：人类可读的 section 标题
- **body**：实际内容
- **source**：信息来源（`current_message`、`recent_context`、`self_learning`、`persona` 等）
- **priority**：重要性（`critical`、`high`、`medium`、`low`）
- **instruction**：可选的使用说明

相关模块：

- `qq_hermes_bridge/prompt_service.py`：Prompt 对象模型和渲染器
- `qq_hermes_bridge/context_store.py`：群上下文缓存、摘要和格式化
- `qq_hermes_bridge/self_learning.py`：群内用语/风格自学习
- `qq_hermes_bridge/commands.py`：Prompt 构建入口（委托给 PromptService）

### Direct 回复 Prompt 结构

Direct 回复（被 @ 或回复机器人消息）的 prompt 按优先级组织：

```text
1. 当前日期（high）
2. 群聊近况摘要（low）
3. 群聊近二十条上下文（high）
   - 最新 6 条标记"高权重"，优先用于理解当前指代和语气
   - 较早消息标记"低权重"，只作背景
4. 被回复/引用的消息（high）
5. 当前被 @ 的消息（critical）
6. 本次回复策略（high）
7. 图片识别结果（medium）
8. 提问者资料（medium）
9. 被提及的人资料（medium）
10. 相关群友资料（low）
11. 群内用语与风格学习提示（low）
12. 回复风格样例与反例（low）
13. 预设提示词 / 基础人设（medium）
```

关键原则：

- **当前消息和最近上下文优先**：旧摘要、自学习、人设都是辅助，不能让模型被旧话题带偏
- **时间权重**：最新 6 条消息权重高于较早消息
- **低权重信息预算控制**：每个 section 有字符预算，防止过长内容挤占任务
- **截断保护**：重要 section（如最近上下文）截断时保留头部指导语和尾部最新消息

### Proactive 主动发言 Prompt 结构

主动发言（非 @ 场景）的 prompt 更聚焦判断策略：

```text
1. 当前日期（high）
2. 群聊近况摘要（low）
3. 群聊上下文（critical，带衰减权重）
4. 主动发言判断策略（high）
5. 触发原因（low，仅诊断）
6. 主动发言样例与反例（low）
7. 基础人设（medium）
```

Proactive prompt 必须包含 `<SILENT>` 标记，让模型在不适合插话时输出沉默标记而非解释。

### 上下文权重与时间衰减

`context_store.format_recent_context()` 实现了时间权重标注：

```python
# 选取最近 context_max_messages 条（默认 20）
# 分为两组：
focus_count = 6              # 最新 6 条标记"高权重"
memory_count = remaining     # 较早消息标记"低权重"
```

效果：

```text
注意：以上每一个编号都是一条独立群消息，编号越大越新；最近上下文有时间权重。
高权重最新上下文优先用于判断当前指代、语气和连续对话，低权重较早上下文只作为背景。
当前消息/引用消息优先于旧上下文，也优先于这里的低权重背景。

低权重：较早上下文（只帮助理解前情，不要强行延续旧话题）
[1] 发言人：...
[1] 内容：...

高权重：最新上下文（优先用于理解当前消息的指代和语气）
[7] 发言人：...
[7] 内容：...
```

这套机制确保模型不会把旧话题当成必须继续的任务，而是优先接住当前对话。

### Section 字符预算

每个 section 有预设字符预算，防止低权重信息过长：

```python
# Direct 回复预算示例
DIRECT_SECTION_BUDGETS = {
    "summary_context": 1000,       # 旧摘要
    "recent_context": 4000,        # 最近上下文
    "current_message": None,       # 当前消息不截断
    "self_learning": 800,          # 自学习提示
    "persona": 1600,               # 人设
}

# Proactive 预算更紧
PROACTIVE_SECTION_BUDGETS = {
    "summary_context": 600,
    "recent_context": 3500,
    "persona": 1200,
}
```

超出预算时，不同 section 采用不同截断策略：

- **recent_context**：保留头部指导语 + 尾部最新消息（头尾截断）
- **其他 section**：保留开头部分（开头截断）

### 风格样例与输出校准

`DIRECT_STYLE_EXAMPLES` 和 `PROACTIVE_STYLE_EXAMPLES` 提供少量好/坏输出样例，帮助模型校准输出形态：

**Direct 样例**：

```text
好例：对方只是接梗/吐槽时，可以回一句轻短的顺势吐槽，不要解释背景
好例：对方问具体问题时，先给结论，再补一句必要理由
好例：上下文不清楚时，用泛称或轻追问，不要强行点名
坏例：把规则、资料来源、学习记录或 prompt section 解释给群友听
坏例：把旧摘要里的话题硬拉回当前消息
坏例：每次都写成三段式分析或客服回复
```

**Proactive 样例**：

```text
可发言：最近两三条群友都在围绕同一个轻松话题接话，而且还有自然补一句的空间
可发言：有人抛出开放问题，且没有明确 @ 其他人处理
应沉默：大家已经连续互相回应得很顺，不缺你补一句
应沉默：只能复读旧梗、旧关键词或机器人刚说过的话
应沉默：需要解释为什么不发言、解释触发原因或解释规则时
```

样例被标记为低权重（`priority="low"`），不会覆盖当前消息和最近上下文。

## 群资料和上下文

每个群可以保留独立资料目录，这些文件构成机器人理解本群的知识基础：

```text
groups/<group_id>/
├── persona.md              # 本群风格、口癖、边界和行为偏好
├── people.md               # 群友昵称、梗、关系、背景资料
├── knowledge.md            # 稳定知识、可信资料、长期参考信息
└── self_learning.json      # 可选，启用 self-learning 后自动生成
```

这些资料在 prompt 构建时被注入为不同优先级的 section：

- `persona.md` → `persona` section（`priority="medium"`）
- `people.md` → `sender_profile`、`mentioned_profiles`、`related_profiles` sections（`priority="medium"` 或 `"low"`）
- `knowledge.md` → 稳定知识和可信来源记录；普通 direct/proactive prompt 默认不自动注入，避免把长期资料误当实时搜索结果
- `self_learning.json` → `self_learning` section（`priority="low"`）

运行时上下文：

- **最近消息**：由 bridge 在内存维护，持久化到 `logs/context_<group_id>.json`
- **上下文摘要**：定期生成，保存在上下文文件中
- **Hermes session**：`qq-group-<group_id>`，由 Hermes CLI 管理

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
7,37 * * * * /home/roxy/qq-hermes/scripts/sync_people_<group_id_a>_from_qqdocs.sh >> /home/roxy/qq-hermes/logs/people-sync-<group_id_a>.log 2>&1
```

同步脚本会读取本机 Firefox 的腾讯文档登录 cookie。cookie 属于敏感数据，只应在本机使用；如果 cookie 过期，需要重新登录腾讯文档。

### 群聊自学习 / self-learning

Bridge 可以按群收集少量群友发言样本，用来提炼本群常见表达、语气词和短句风格，再作为 direct 回复 prompt 里的低权重提示。这个功能默认关闭，适合在你明确授权的私有群里试用。

#### 工作原理

Self-learning 分为采集和注入两个阶段：

**采集阶段**（`qq_hermes_bridge/self_learning.py`）：

1. 用户普通群消息进入本地最近上下文时，`collect_learning_sample()` 会尝试采集一条样本
2. 采集过滤规则：
   - 不采集机器人自己的回复
   - 不采集命令（`/context`、`jrrp` 等）
   - 不采集纯图片、纯链接或过短/过长消息
   - 不采集包含敏感词（token、api key、password、traceback 等）的消息
   - OCR 文本如果标记为非持久化，使用去 OCR 的原始文本
3. 采集的样本保存在 `groups/<group_id>/self_learning.json`：
   ```json
   {
     "version": 1,
     "group_id": "<group_id_b>",
     "samples": [
       {"ts": 1704067200.0, "text": "笑死 这也太离谱了"},
       {"ts": 1704067201.0, "text": "好耶 今天也很棒"}
     ]
   }
   ```
4. 样本数量受 `SELF_LEARNING_MAX_SAMPLES_PER_GROUP`（默认 500）和 `SELF_LEARNING_RETENTION_DAYS`（默认 30 天）限制

**注入阶段**（构建 direct prompt 时）：

1. `learning_context_for_prompt()` 读取同群 `self_learning.json`
2. 提取有界风格信号：平均消息长度、短句比例、表情使用率、感叹/疑问语气比例
3. 生成低权重提示，强调它只能作为节奏和互动方式参考，不能覆盖基础人设，也不能主动模仿、复读或强化群友口癖：
   ```text
   低权重理解线索：只用于判断本群消息的大致节奏和互动方式，不是事实来源，也不是必须提到的话题
   使用边界：不得覆盖 Esti 的基础人设和原始语气；不得主动模仿、复读或强化群友口癖/梗/高频表达
   风格信号：平均消息长度约 15 字；偏短句接话；常带表情
   ```
4. 提示限制在 `SELF_LEARNING_MAX_PROMPT_CHARS`（默认 500）字符内

#### 配置示例

```dotenv
SELF_LEARNING_ENABLED=false
SELF_LEARNING_COLLECT_ENABLED=false
SELF_LEARNING_INJECT_ENABLED=false
SELF_LEARNING_ALLOWED_GROUP_IDS=
SELF_LEARNING_MIN_MESSAGE_CHARS=2
SELF_LEARNING_MAX_MESSAGE_CHARS=300
SELF_LEARNING_MAX_SAMPLES_PER_GROUP=500
SELF_LEARNING_RETENTION_DAYS=30
SELF_LEARNING_MAX_PROMPT_CHARS=500
SELF_LEARNING_MIN_COUNT_FOR_PROMPT=3
SELF_LEARNING_DATA_FILENAME=self_learning.json
```

启用方式示例：

```dotenv
SELF_LEARNING_ENABLED=true
SELF_LEARNING_COLLECT_ENABLED=true
SELF_LEARNING_INJECT_ENABLED=true
SELF_LEARNING_ALLOWED_GROUP_IDS=<group_id_b>
```

#### 设计边界和隐私原则

- **群隔离**：只对 `SELF_LEARNING_ALLOWED_GROUP_IDS` 里的群生效，不跨群复用
- **本地存储**：学习数据保存在 `groups/<group_id>/self_learning.json`，属于真实群聊派生数据，不要提交或公开分享
- **过滤机制**：不学习机器人自己的回复、命令、敏感内容、纯媒体消息
- **时间衰减**：超过 `RETENTION_DAYS` 的样本自动清理
- **数量限制**：每群最多保留 `MAX_SAMPLES_PER_GROUP` 条样本（FIFO 队列）
- **汇总提示**：只生成节奏和互动方式统计信号，不包含用户 QQ、消息 id、长篇原文或高频原句清单
- **不改写群资料**：不自动修改 `persona.md`、`people.md` 或 `knowledge.md`
- **低权重使用**：self-learning section 标记为 `priority=”low”`，在 prompt 中排序靠后，不覆盖当前消息和最近上下文
- **路由限制**：v1 只注入 direct 回复 prompt，主动发言 proactive 不使用 self-learning，避免把旧梗硬拉回当前聊天
- **容错设计**：采集或读取失败只记录内部 warning，不影响正常聊天回复

#### 与 Prompt 系统的集成

Self-learning 提示作为独立 section 插入 direct prompt：

```python
PromptSection(
    key="self_learning",
    title="群内用语与说话风格学习提示",
    body=learning_context,           # 从 self_learning.json 生成
    source="self_learning",
    priority="low",                 # 低权重
    instruction="低权重理解线索；当前消息、基础人设和 Esti 原始语气优先。不得主动复刻群友话术/梗，不要暴露学习数据。",
)
```

在 section 顺序中，self-learning 位于：

- **之后**：当前消息、最近上下文、回复策略、群友资料
- **之前**：风格样例、预设人设

这确保自学习提示只作为风格参考，不改变事实判断或任务理解。

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

如果 direct 生成失败，bridge 会先尝试主文本模型；主模型报错、停服或空输出时会尝试 fallback 文本模型。仍失败时，才发送简短可见提示：

```text
[CQ:reply,id=<message_id>][CQ:at,qq=<user_id>] 没有油烧了谁给我加加油
```

### 主动发言 proactive

普通群消息默认只写入上下文，不一定回复。主动发言由热度分数、关键词、问题形态、多用户活跃、夜间倍率、敏感词冷却和群级限速共同决定。

常用配置：

```dotenv
PROACTIVE_ENABLED=true
PROACTIVE_TRIGGER_THRESHOLD=16
PROACTIVE_TRIGGER_THRESHOLDS_BY_GROUP=<group_id_a>=999,<group_id_b>=16
PROACTIVE_GROUP_COOLDOWN_SECONDS=20
PROACTIVE_DAILY_LIMIT_PER_GROUP=80
PROACTIVE_RATE_LIMIT_WINDOW_SECONDS=60
PROACTIVE_RATE_LIMIT_MAX_REPLIES=10
PROACTIVE_NAME_TRIGGERS=Esti,Estilord,Esti1ord,机器人,bot,小E
```

示例：

- `<group_id_a>=999` 基本禁用普通热度主动发言；direct 和命令仍可用；
- `<group_id_b>=16` 热度达到 16 才考虑主动接话；
- 名字触发按 direct/名称提及处理，不等于绕过所有安全和队列限制。

## 群内命令

### `/context`

查看本群当前本地上下文摘要和最近消息。不调用 LLM，也不进入普通回复队列。

```text
/context
@Esti /context
```

### `jrrp`

今日人品，纯确定性命令，不调用 LLM。

触发规则很严格：整条消息去掉首尾空白后必须等于 `jrrp`（兼容误拼 `jrro`），大小写不敏感。

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
- `vision.py`：OCR/图片理解 provider，支持 OpenAI-compatible 模型接口、Hermes `chat --image`、mock、none；
- `runtime.py`：把图片理解结果放进本次 prompt 或群上下文。

推荐的模型识图配置：

```dotenv
OCR_ENABLED=true
OCR_TRIGGER_MODE=direct_only
PRIMARY_OCR_MODEL_PROVIDER=model
PRIMARY_OCR_MODEL=<vision-capable-model>
PRIMARY_OCR_MODEL_BASE_URL=<provider base url or chat/completions endpoint>
PRIMARY_OCR_MODEL_API_KEY_ENV=<env var containing API key>
OCR_FALLBACK_ENABLED=true
VICE_OCR_MODEL_PROVIDER=model
VICE_OCR_MODEL=gpt-5.4
VICE_OCR_MODEL_BASE_URL=<fallback provider base url or chat/completions endpoint>
VICE_OCR_MODEL_API_KEY_ENV=<env var containing fallback API key>
OCR_EXTERNAL_PROVIDER_ALLOWED=true
```

`PRIMARY_OCR_MODEL_API_KEY_ENV` / `VICE_OCR_MODEL_API_KEY_ENV` 配的是“环境变量名”，不是 key 本身。例如可以把它设为 `VISION_API_KEY`，再由 shell 或 systemd EnvironmentFile 提供 `VISION_API_KEY=<api key>`。旧键 `OCR_API_KEY_ENV` / `OCR_FALLBACK_API_KEY_ENV` 仍兼容。不要把真实 key、provider base URL 中的私密部分写进 README、issue、聊天或提交记录。

`OCR_PROVIDER_BASE_URL` 可以是 provider 根路径，也可以已经是 `/chat/completions` endpoint；Bridge 会规范化为 OpenAI-compatible `/chat/completions` 请求。请求会把下载后的图片 bytes 编成 base64 data URL 放进 `messages[0].content`，同时发送 `OCR_IMAGE_PROMPT` 文本。当前支持这些 provider 名称别名：

- `model`
- `model_vision`
- `openai`
- `openai_compatible`
- `openai-gpt`
- `custom`
- `axonhub`
- `siliconflow` / `silicon-flow`

如果继续使用 Hermes CLI 识图，可以保留：

```dotenv
OCR_PROVIDER=hermes
OCR_MODEL=<optional override, otherwise HERMES_MODEL>
OCR_EXTERNAL_PROVIDER_ALLOWED=true
```

完整常用配置：

```dotenv
OCR_ENABLED=false
OCR_TRIGGER_MODE=direct_only
PRIMARY_OCR_MODEL_PROVIDER=model
# Fill these only when enabling an OpenAI-compatible OCR provider. API env fields are env var names, not key values.
PRIMARY_OCR_MODEL=
PRIMARY_OCR_MODEL_BASE_URL=
PRIMARY_OCR_MODEL_API_KEY_ENV=
OCR_FALLBACK_ENABLED=true
VICE_OCR_MODEL_PROVIDER=model
VICE_OCR_MODEL=gpt-5.4
VICE_OCR_MODEL_BASE_URL=
VICE_OCR_MODEL_API_KEY_ENV=
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

- `direct_only`：只处理 direct 消息里的图片；direct 包括 @ 机器人、回复机器人上一条消息，或文本命中机器人名字/昵称（如 `Esti`、`机器人`）。
- `direct_and_context`：direct 同步识别，普通允许群图片异步识别并加入上下文；
- `context_only`：只做普通上下文图片识别；
- `all` / `all_allowed_messages`：允许更多路由使用 OCR。

当 direct 消息本身是 QQ 回复/引用时，Bridge 会优先识别当前消息里的图片，也会尝试识别被回复/引用消息里的图片。被引用图片可能来自 OneBot reply segment 内嵌的原消息，也可能来自本轮运行期最近上下文中缓存的图片引用；这些图片引用只保留在内存里，不写入持久化上下文文件。

隐私原则：默认不识图、不持久化 OCR 文本、不记录 OCR 文本、不记录图片 URL。使用 `model`、`openai_compatible`、`hermes` 或其他外部 provider 前，必须显式设置：

```dotenv
OCR_EXTERNAL_PROVIDER_ALLOWED=true
```

开启后，图片内容会发送给所选外部 provider。Bridge 的运行统计仍只记录状态、耗时、长度、桶和哈希，不记录原始聊天文本、OCR 文本、图片 URL、token、API key、完整 provider 响应或完整报错正文。

如果需要让机器人长期记住图片等价文字上下文，可以这样配置：

```dotenv
OCR_ENABLED=true
OCR_TRIGGER_MODE=direct_and_context
OCR_PROVIDER=model
OCR_EXTERNAL_PROVIDER_ALLOWED=true
OCR_INCLUDE_IN_CONTEXT=true
OCR_PERSIST_TEXT_IN_CONTEXT=true
```

开启前需要确认：这些文字描述会进入本地上下文文件，属于真实群聊内容。

## 日志和统计

Bridge 主要有三类本地观测输出，默认都在 `logs/` 下或由 `/metrics` 暴露。它们的定位是“出问题时帮助定位”，不是需要每天盯盘的运行面板；平时只看 `/health`、systemd 状态和实际聊天表现通常就够了。

共同原则：不要提交或公开分享日志；排障时也不要把原始群聊文本、prompt、模型输出、OCR 文本、图片 URL、API key、token、cookie、provider base URL 或完整接口响应贴给别人。需要描述问题时，优先贴状态码、耗时、计数、错误类型和已脱敏摘要。

### `logs/runtime_stats.jsonl`

这是 `qq_hermes_bridge/runtime_stats.py` 清洗后的内容安全运行统计，用来回答“桥接服务有没有收到消息、有没有排队、模型/发送/OCR 哪一步慢或失败”。它和普通运行日志是互补关系：runtime stats 更适合看结构化计数、耗时和状态，普通日志更适合看服务级事件顺序。

设计上它不记录群聊正文、prompt、模型输出、OCR 文本、图片 URL、token、cookie、API key、完整 provider 响应或完整接口错误正文。记录的是长度、bucket、状态、低基数字段、耗时、队列规模和必要的本地安全 hash。

主要用于观察：

- direct/proactive 请求量、成功率、失败原因；
- 入站、排队、Hermes 调用、OneBot 发送耗时；
- 队列积压、队列满、重复发送抑制；
- OCR fetch/provider/context update 耗时；
- 周期性 runtime summary 里的累计计数和 uptime。

查看方式：

```bash
# 实时查看最新统计事件；只在排障时需要
tail -f /home/roxy/qq-hermes/logs/runtime_stats.jsonl

# 只看 OCR provider 结果
grep '"stat": "ocr_provider_result"' /home/roxy/qq-hermes/logs/runtime_stats.jsonl | tail -n 20

# 查看最近 runtime summary
grep '"stat": "runtime_summary"' /home/roxy/qq-hermes/logs/runtime_stats.jsonl | tail -n 5
```

每行都是 JSONL，外层含 `ts`，内层 `event` 里通常有：

- `stat`：事件类型，例如 `route_decision`、`direct_reply_result`、`hermes_call`、`send_group_msg`、`ocr_provider_result`；
- `ok` / `status` / `error`：是否成功、归一化状态和安全错误类型；
- `duration_ms` / `duration_bucket` / `e2e_ms` / `queue_wait_ms`：耗时和端到端延迟；
- `*_len` / `*_len_bucket`：输入输出或结果长度，不是原文；
- `queue_size`、`direct_queue_size`、`proactive_queue_size`：当前排队情况；
- `segment_types`、`media_count`、`ok_count`、`error_count`：消息段或 OCR 统计数量。

常见解读：

- `route_decision` 频繁出现但没有 `*_reply_result`：多半是消息未命中 direct/proactive/命令，或被阈值、冷却、队列限制挡住；
- `queue_size` 长时间偏高或出现 `queue_full`：模型调用或发送速度跟不上入站消息；
- `hermes_call` 的 `duration_bucket` 很大、`ok=false` 或 reply result 标记 `generation_failed`：优先检查模型 provider、网络、Hermes CLI 和 timeout；
- `send_group_msg` 失败或 `qq_hermes_errors_total{component="onebot"...}` 增加：优先检查 NapCat/OneBot token、登录态和 HTTP API；
- OCR 相关 `error_count` 增加：检查 OCR 是否启用、外部 provider 是否允许、图片大小/类型限制、provider 配置和 timeout；
- `runtime_summary` 只适合看累计趋势，不表示每条消息的具体内容。

相关开关：

```dotenv
RUNTIME_STATS_ENABLED=true
RUNTIME_STATS_FILE=/home/roxy/qq-hermes/logs/runtime_stats.jsonl
PERF_OBS_ENABLED=true
PERF_OBS_DETAIL_LEVEL=standard
PERF_OBS_SAMPLE_RATE=1.0
```

### `logs/bridge.log`

这是普通运行事件日志，会记录路由、下载、识图、发送、prompt section 元数据等事件摘要。它适合配合 systemd 日志看“某个时间点发生了什么”，但仍然不应该当成内容审计日志使用。

为保持内容安全，Bridge 不会把原始 prompt、OCR 文本、完整图片 URL、API key、token 或完整 provider 响应写进普通运行日志；prompt 诊断只记录 section key、source、priority、字符数和截断情况。`OCR_LOG_TEXT`、`OCR_LOG_IMAGE_URLS` 作为旧配置项保留但不再开启 raw 内容日志。

排障时可重点看这些安全事件名：

- `prompt_rendered`：确认 direct/proactive prompt 是否包含预期 section，以及是否被截断；
- `reply_queued` / `reply_queue_rejected`：确认回复是否进入队列；
- `metrics_observe_error` / `metrics_counter_error`：Prometheus 记录失败但主流程继续；
- `ocr_context_task_error`：异步 OCR 任务异常，日志只保留异常类型。

### Prometheus `/metrics`

Bridge 也提供 Prometheus 兼容文本指标端点：

```bash
curl -sS http://127.0.0.1:8765/metrics
```

`/metrics` 面向 Prometheus、Grafana 或临时 curl 诊断，用来观察当前桥接服务的总体健康趋势：消息是否还在进来、回复是否成功、队列是否积压、Hermes/OCR 是否变慢、OneBot 是否发送失败。它不是聊天内容查询接口，也不是每日必看的人工仪表盘。

相关配置：

```dotenv
PROMETHEUS_ENABLED=true
PROMETHEUS_INCLUDE_GROUP_ID_LABEL=false
```

指标由 `qq_hermes_bridge/metrics.py` 直接渲染，不依赖 `prometheus-client`。如果 `PROMETHEUS_ENABLED=false`，`GET /metrics` 返回 404。默认不会导出 `group_id` label，以减少指标标签里的群号暴露和标签基数；只有在你明确需要按群拆分监控并接受这个暴露面时，才设置 `PROMETHEUS_INCLUDE_GROUP_ID_LABEL=true`。

指标同样遵循内容安全原则：只导出路由、状态、组件、错误类型、耗时、队列深度等低基数字段，不导出消息正文、prompt、模型输出、用户标识、token、URL、OCR 文本、API key、provider base URL 或完整 provider 响应。未知或不安全的 label value 会被归一化为 `unknown` 或被丢弃。

常见指标包括：

- `qq_hermes_messages_total{route,result}`：消息路由决策计数；`route` 常见为 `direct`、`proactive`、`ignored`，`result` 表示 queued、not_at_me、error 等归一化结果；
- `qq_hermes_replies_total{type,status}`：回复结果计数；`type` 常见为 `direct`、`proactive`、命令名，`status` 可用于看 sent、generation_failed、send_failed、skipped；
- `qq_hermes_errors_total{component,error_type}`：组件错误计数；`component` 常见为 `hermes`、`ocr`、`onebot`、`queue`；
- `qq_hermes_reply_duration_seconds`、`qq_hermes_hermes_call_duration_seconds`、`qq_hermes_ocr_duration_seconds`：耗时直方图；看 `_bucket`、`_count`、`_sum` 可判断是否整体变慢；
- `qq_hermes_queue_size{type}`：当前 direct/proactive 队列深度；持续升高通常说明下游处理变慢；
- `qq_hermes_context_messages`：最近上下文规模，用于确认上下文缓存是否在更新。

快速解读：

- `/metrics` 404：通常是 `PROMETHEUS_ENABLED=false`，不是 bridge 整体故障；
- `qq_hermes_messages_total` 增长但 `qq_hermes_replies_total` 不增长：消息可能未命中回复条件，或被冷却/队列/阈值挡住；
- `qq_hermes_replies_total{status="generation_failed"}` 增加：优先排查 Hermes CLI、主/备用模型 provider 和 timeout；
- `qq_hermes_replies_total{status="send_failed"}` 或 OneBot errors 增加：优先排查 NapCat/OneBot；
- `qq_hermes_ocr_duration_seconds` 变慢或 OCR errors 增加：优先排查图片下载限制、OCR provider 配置和网络。

Prometheus scrape 示例：

```yaml
scrape_configs:
  - job_name: qq-hermes-bridge
    static_configs:
      - targets: ["127.0.0.1:8765"]
```

### `logs/content_analysis.jsonl`

这是更敏感的真实内容分析日志。开启后会记录群聊文本、上下文片段和机器人回复，只适合本地定性分析。平时不建议开启；公开分享、提交 issue 或交给他人分析前，必须先手动复查和脱敏。

查看方式：

```bash
tail -f /home/roxy/qq-hermes/logs/content_analysis.jsonl
```

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
HERMES_PROVIDER_BY_GROUP=<group_id_a>=deepseek
HERMES_MODEL_BY_GROUP=<group_id_a>=deepseek-v4-flash
```

修改 `.env` 后通常需要重启 bridge；修改 `groups/<group_id>/*.md` 通常下一次生成回复会重新读取。

## 测试与开发

常用验证：

```bash
cd /home/roxy/qq-hermes
./venv/bin/python -m py_compile bridge.py qq_hermes_bridge/*.py scripts/sync_people_from_qqdocs.py
./venv/bin/python -m pytest tests -q
```

局部测试：

```bash
./venv/bin/python -m pytest tests/test_direct_reply_inflight.py -q
./venv/bin/python -m pytest tests/test_bridge_ocr.py tests/test_media_fetch_module.py tests/test_vision_module.py -q
./venv/bin/python -m pytest tests/test_hermes_group_sessions.py tests/test_config_utils_module.py -q
./venv/bin/python -m pytest tests/test_runtime_stats_module.py tests/test_metrics_module.py tests/test_content_analysis_log_module.py -q
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
5. Hermes 是否超时、返回空、主/备用 provider/model 是否可用；
6. OneBot 发送是否失败；
7. 如果是图片问题，OCR 是否开启、provider 是否允许、图片 URL 是否可拉取。

### self-learning 没有生成或没有进入 prompt

先确认功能是显式开启的：

```dotenv
SELF_LEARNING_ENABLED=true
SELF_LEARNING_COLLECT_ENABLED=true
SELF_LEARNING_INJECT_ENABLED=true
SELF_LEARNING_ALLOWED_GROUP_IDS=<group_id>
```

再按顺序检查：

1. 群号是否在 `SELF_LEARNING_ALLOWED_GROUP_IDS` 中；
2. 消息是否是普通用户消息，而不是 bot 自己的回复；
3. 消息是否被过滤为命令、链接、CQ 图片码、过短、过长或疑似敏感内容；
4. `groups/<group_id>/self_learning.json` 是否能由 bridge 进程写入；
5. 是否已达到 `SELF_LEARNING_MIN_COUNT_FOR_PROMPT`，未达到时 prompt 会显示暂无学习提示；
6. 本次是否是 direct 回复，主动发言 proactive 不注入 self-learning 提示。

`self_learning.json` 属于群聊派生数据，排障时不要贴到公开 issue 或提交到仓库。

### 机器人回复“没有油烧了谁给我加加油”

这表示 direct 回复生成失败。当前逻辑会先尝试主文本模型；主模型报错、停服或空输出时会尝试 fallback 文本模型；仍无法得到可发送内容时才发送这个可见失败提示。优先检查：

- `logs/runtime_stats.jsonl` 中的 `direct_reply_result`、`hermes_call`；
- Hermes 主 provider/model 与 `HERMES_FALLBACK_PROVIDER` / `HERMES_FALLBACK_MODEL` 配置；
- group session 是否异常；
- 是否触发超时、空输出，或主/备用 provider 都不可用。

### 腾讯文档同步失败

```bash
tail -n 100 /home/roxy/qq-hermes/logs/people-sync-<group_id_a>.log
/home/roxy/qq-hermes/scripts/sync_people_<group_id_a>_from_qqdocs.sh
```

常见原因：Firefox 腾讯文档登录态过期、cookie 路径不对、文档权限变化、网络/API 临时失败。
