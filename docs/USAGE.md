# ganren 使用手册

> 这份手册回答两个问题：**怎么把平台架起来给团队用**、**怎么用 Claude Code 跟队友异步协作**。

---

## 0. 谁读这份

| 你是 | 看哪部分 |
|---|---|
| 想架平台让大家用的人（一个团队只需要一个）| §A 全部 |
| 想跟别人协作的用户（每个协作者）| §B + §C + §D 速查 |

---

## §A 架平台（管理员，一次性）

### A.1 前置

- Python ≥ 3.12
- [`uv`](https://docs.astral.sh/uv/)（包管理）
- git
- 一台能持续跑的机器（你自己电脑、内网小服务器、或云主机均可）

### A.2 拿代码 + 装依赖

```bash
git clone <your-repo> ganren
cd ganren
uv sync --extra dev
```

### A.3 配置 + 启动

```bash
cp .env.example .env
# 编辑 .env：见下方
uv run python -m ganren_platform.main
```

`.env` 关键项：

```dotenv
BIND_ADDR=0.0.0.0:8787              # 默认监听所有网卡 8787 端口
GANREN_DB_PATH=./data/ganren.db     # SQLite 文件路径（首次启动自动 migrate）
SLACK_WEBHOOK_URL=                  # 可选，留空就不发 Slack
LOG_LEVEL=info
```

启动后看到 `Uvicorn running on http://0.0.0.0:8787`，再开一个终端验证：

```bash
curl http://localhost:8787/healthz
# {"ok":true}
```

### A.4 让队友连进来 —— 选一种网络方案

| 场景 | 方案 | 别人填的 URL |
|---|---|---|
| 同局域网（同 WiFi / VPN）| 直接告诉别人你机器的局域网 IP | `http://192.168.x.x:8787/mcp/` |
| 跨网络、轻量临时 | [ngrok](https://ngrok.com) 或 [cloudflare tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) | `https://xxx.ngrok-free.app/mcp/` |
| 长期生产用 | 云主机 + 域名 + Caddy 反代 + HTTPS | `https://ganren.yourdomain.com/mcp/` |

**ngrok 一行起公网 URL**（最快试水方案）：

```bash
ngrok http 8787
```

ngrok 终端会给你一条 `https://abc-xx.ngrok-free.app`，把这个 URL 给团队，他们 `.mcp.json` 里就用它。

**Caddy 反代示例**（生产场景）：

```caddyfile
ganren.yourdomain.com {
  reverse_proxy localhost:8787
}
```

### A.5 把团队成员加到平台

MVP 阶段成员表（`actors`）和小队表（`units`）需要手动写入。最简单的办法是用项目自带的脚本（**不需要装 `sqlite3` CLI**，用 Python stdlib）：

```bash
# 加成员
uv run python tools/add_actor.py alice "Alice 李"
uv run python tools/add_actor.py bob   "Bob 王"
uv run python tools/add_actor.py carol "Carol 张" squad_frontend   # 第 3 个参数 = 归属单元
```

脚本会自动把 stdout 切到 UTF-8，不管你在 Git Bash / PowerShell / cmd 里跑都不会中文乱码。

如果想直接走 SQL（你装了 `sqlite3` CLI 的话）：

```sql
-- 加成员（handle 必须唯一，是 CC 调工具时用的身份标识）
INSERT INTO actors (handle, display, onboarding_date) VALUES
  ('alice', 'Alice 李',  '2026-06-05'),
  ('bob',   'Bob 王',    '2026-06-05'),
  ('carol', 'Carol 张',  '2026-06-10');

-- （可选）加一个小队，把 coach 设为 alice
INSERT INTO units (id, name, type, coach_handle, created_at) VALUES
  ('squad_frontend', '前端小队', 'squad', 'alice', datetime('now'));

-- （可选）把成员归属到小队
UPDATE actors SET primary_unit_id='squad_frontend' WHERE handle IN ('bob','carol');
```

> `handle` 是后面所有协作里的"身份证号"，CC 调工具时会传它。**一旦发出去给别人用就不要改**，否则历史 events 里的 actor 字段会跟当前 actors 表对不上。
>
> Git Bash / Windows 默认没装 `sqlite3` 命令，但项目脚本和平台运行都不依赖它（用 Python `sqlite3` 模块）。要用 CLI 自查数据，可以 `winget install SQLite.SQLite` 或下载官方 zip。

### A.6 配置 Slack（可选但强推）

1. 在你的 Slack workspace 里建一个 **Incoming Webhook**（Slack 文档：<https://api.slack.com/messaging/webhooks>），得到一条 `https://hooks.slack.com/services/...` URL
2. 写进 `.env` 的 `SLACK_WEBHOOK_URL`
3. 重启平台
4. 现在所有任务事件（发布 / 接走 / 提问 / 回复 / 提交 / 关闭 / 取消 / 放弃）都会发到这个 webhook 对应的频道

通知模板示例：

```
📌 PUBLISH #t_01 优化首页响应时间 [Builder] 由 alice 发布
🙋 CLAIM #t_01 被 bob 接走
❓ Q @alice #t_01: AVIF fallback 选 WebP 还是 PNG？
💬 A @bob #t_01 已回复
✅ REVIEW @alice #t_01 待 review
↩️ REJECT @bob #t_01 打回：只 lazy 非关键路径
🎉 CLOSE #t_01 关闭
```

### A.6.1 V2 · 定时日报与池快照

平台内置 scheduler，工作日早 10:00 + 晚 18:00 自动推送日报；新任务发布时附加任务池快照。

`.env` 新增字段（详见 `.env.example`）：

```dotenv
SCHEDULER_ENABLED=true               # 平台启动时是否启 scheduler
SCHEDULER_TZ=Asia/Shanghai
MORNING_DIGEST_CRON=0 10 * * MON-FRI
EVENING_DIGEST_CRON=0 18 * * MON-FRI
SLACK_DIGEST_WEBHOOK=                # 留空则复用 SLACK_WEBHOOK_URL
PUBLISH_INCLUDES_SNAPSHOT=true       # publish 时是否附池快照
SNAPSHOT_MAX=50                      # 池快照单条上限
```

特性：
- 日报格式：等宽表格，emoji 状态标签，列含 ID/标题/负责人/停留时长
- 节流：模块级 60s 窗口防止短时间重复推送
- fail-safe：scheduler 故障不阻塞 web server
- 关掉：`SCHEDULER_ENABLED=false`

### A.7 备份

数据只在 `./data/ganren.db` 一个文件。备份就是定时 `cp`：

```bash
# 每天凌晨打个备份
cp ./data/ganren.db ./backups/ganren-$(date +%Y%m%d).db
```

WAL 模式下直接 `cp` 也是安全的（SQLite 保证 reader 一致性），但严谨做法是用 SQLite 的 `.backup`。一行 Python 即可：

```bash
uv run python -c "import sqlite3,sys; src=sqlite3.connect('./data/ganren.db'); dst=sqlite3.connect(sys.argv[1]); src.backup(dst); dst.close()" "./backups/ganren-$(date +%Y%m%d).db"
```

---

## §B 用户配置（每个协作者，一次性）

### 🚀 最简上手：跑配置脚本

管理员把这两个文件发给你（或直接告诉你仓库地址 `git clone https://github.com/chenjr-renlab-ai/ganren.git`）：

- `tools/setup_client.py`
- 平台 MCP URL（比如 `http://192.168.22.56:8787/mcp/`）

然后跑：

```bash
python tools/setup_client.py
```

脚本会引导你回答 3 个问题（actor handle、显示名、平台 URL），自动：
- 测试网络联通
- 调 `claude mcp add` 把 ganren 加进 user-scope MCP 配置
- 在 `~/.claude/CLAUDE.md` 追加你的 actor 身份说明
- 输出"请管理员把我加进 actors 表"的指令给你复制粘贴

跑完之后跳过 §B.2/§B.3，直接看 §B.4 试连。

下面是手动配置版本（不想跑脚本时用）。

### B.1 装 Claude Code

参考 [Claude Code 官方安装指引](https://docs.claude.com/claude-code)。

### B.2 配置 MCP server

**推荐**：用 `claude mcp add` 命令（不要手动改 `~/.claude.json`，那是个有很多其他东西的大文件）：

```bash
claude mcp add --transport http --scope user ganren http://<管理员给你的地址>:8787/mcp/
```

`--scope user` = 用户级配置，所有项目都能用。

如果一定要手动改文件，加到 `~/.claude.json` 顶层 `mcpServers` 字段下：

```json
{
  "mcpServers": {
    "ganren": {
      "type": "http",
      "url": "http://<管理员给你的地址>:8787/mcp/"
    }
  }
}
```

URL 填 §A.4 里管理员给你的那条（局域网 IP、ngrok URL、或域名）。

### B.3 让 CC 知道你是谁

ganren 平台所有工具都需要一个 `actor` 参数（你的 handle）。最简单的办法：在 **`~/.claude/CLAUDE.md`** 或项目级 `CLAUDE.md` 里加一行：

```markdown
# ganren 平台协作

我在 ganren 平台上的 actor handle 是 `bob`。
调用任何 `ganren__*` 工具时，actor 参数都用 `bob`。
```

这样 CC 调任何 ganren 工具都会自动带上你的 handle。

### B.4 第一次试连

跟 CC 说：

> 在 ganren 平台上跑一下 inbox 看看

CC 第一次调 `ganren__inbox` 时 Claude Code 会弹权限提示，确认允许。之后就不再问。

如果连不上：

- 平台地址不通：让管理员确认 §A.4 的网络方案是否还有效
- handle 不存在：让管理员去 `actors` 表 INSERT 一行
- 工具列表不出现：检查 `.mcp.json` URL 末尾有没有 `/mcp/` 这个尾斜杠

---

## §C 日常工作流

四个 flow 对应 product-demo.html 里的四个 tab。这里讲怎么跟 CC 开口。

### C.1 发布任务（你是发布者）

跟 CC 这样开口：

> 跟我聊聊最近这个事 —— [简述]。聊完了帮我打包成一个任务发到 ganren 平台。

或者直接：

> 我刚才跟你讨论的那个 X，打包成 ganren 任务发出去，找 bob 接。

CC 会：

1. 跟你确认任务的 **title / description / context_summary**
2. 根据讨论内容**自动推断**标签（IC / Builder / Coach / DRI）、AI 介入度（L1–L3）、agent 自主度（L1–L5）、难度（routine / hard）
3. 让你 review 它的提案，可以改 title、改 description、加 artifacts（文件路径、代码片段、链接）
4. 调 `publish_task`

**几个注意点**：

- 如果 `difficulty='hard'` 或 tags 包含 `DRI`，CC 会强制你写 `decision_record`（事前的"下注质量"：考虑过哪些选项、最终选了哪个、估计成功概率、为什么）。这是考核框架要求的，不是产品多事
- `tag_source` 默认 `auto`（CC 推断的），你后期改标签会标记 `override` 并留 event 审计
- 发布完不需要管，task 进任务池等人接

### C.2 接任务（你是协作者）

跟 CC 这样开口：

> 看看 ganren 池子里有什么活

CC 调 `list_open_tasks` 拿到 open 任务列表 —— **注意这里只显示 description + 标签 + AI 介入度，不显示完整 context_summary**。这是平台故意的，防"看了一眼就走"。

挑好了：

> 接 #t_01

CC 调 `claim_task`。成功后：

- 平台返回完整 payload（context_summary + artifacts + 历史问答）
- CC 把 payload **注入当前会话**作为干活前的初始上下文
- CC 同时把 payload **写到本地** `./.ganren/task-<id>.md`，方便你跨 session 续干或者人类查看
- 状态变 `claimed by <你>`

如果 list 上没看到合适的，可以让 CC 加 filter：

> 只看 Builder 标签的，AI L2 以上的

CC 调 `list_open_tasks(tags=['Builder'], ai_involvement='L2')`。

### C.3 干到一半求助（反馈循环）

跟 CC 这样开口：

> 帮我问下 ganren 那边发布者 [问题]

CC 会：

1. 把"为啥问"压成 **ctx_summary**（≤ 500 字节，发布者看一眼就懂）
2. 把最近若干轮讨论作为 **ctx_full**（≤ 4KB，发布者展开看细节）
3. 调 `ask_question`
4. 平台落库 + Slack ping 发布者

发布者那端的 CC 任何时候跑一下：

> 看看 ganren 上有没有人在等我回复

CC 调 `inbox()`，返回 `questions_to_answer`、`reviews_pending` 两组。挑一条让发布者口述/补充，CC 调 `answer_question`。

回到你这边：

> ganren 上有没有 alice 回我的？

CC 调 `inbox()` 看 `answers_received`。拿到回答后 CC 把答案注入当前会话，你继续干。

> **关键约定**：协作者每次"向单元外求助"会被 events 表记一笔，下游考核仪表盘按周聚合。求助本身不扣分 —— 但**逐周求助数减少**是 IC 货币里的强加分项（"你在变自主"）。所以 ask 要克制，能查文档先查文档。

### C.4 提交 + sign-off（关闭循环）

干完了：

> 帮我把 #t_01 提交 review

CC 会：

1. 让你确认一下"我做了什么 / 我决定了什么 / 还剩什么"作为 `summary`
2. 调 `submit_for_review`
3. 任务状态变 `awaiting_review`，发布者收到 Slack

发布者那端：

> ganren 上有没有我要 review 的？

CC `inbox()` 看 `reviews_pending`。三种走法：

- **sign-off**（通过）：`sign_off_task(comment="lgtm")` → task → `closed` 🎉
- **reject**（打回）：`reject_task(reason="...", hints="...")` → task 回 `claimed`，`rework_count + 1`（注意：rework 计数挂在**任务上**而不是协作者上，这是考核框架的设计 —— 鼓励反复打磨而不是惩罚返工）
- **事后回填结果**：任务 closed 之后还能 `record_outcome(summary, matched_estimate=True/False)`，用于 DRI 校准（"你当时估 70% 成的事是不是真的约 70% 成了"）

### C.5 中途想放弃 / 想撤销

- **协作者想放弃**：让 CC 调 `abandon_task(reason=...)` → 任务回 `open`，回池让别人接
- **发布者想撤销**（task 还没进 awaiting_review 时）：`cancel_task(reason=...)` → 直接 `closed`
- **task agent 跑不动需要人接手**：`report_escalation(note=...)` → 任务的 `escalated` 标志置 1，下游仪表盘会看到（"真正不用人接手的比例"是 L3 agent 自主度的考核指标）

---

## §D 操作速查表

CC 工具一览。前缀都是 `ganren__`（MCP namespace 自动加）。

| 场景中文 | 工具 | 角色 |
|---|---|---|
| 发布任务 | `publish_task` | 任何人 |
| 看可接任务 | `list_open_tasks` | 任何人 |
| 看任务详情 | `get_task` | 任何人 |
| 接任务 | `claim_task` | 任何人 |
| 放弃手上的任务 | `abandon_task` | 协作者 |
| 撤销自己发布的任务 | `cancel_task` | 发布者 |
| 提交 review | `submit_for_review` | 协作者 |
| 打回 | `reject_task` | 发布者 |
| sign-off 关闭 | `sign_off_task` | 发布者 |
| 改标签 | `retag_task` | 发布者 / 单元 coach |
| 事后回填结果 | `record_outcome` | 发布者（任务 closed 后）|
| agent 跑不动升级 | `report_escalation` | 协作者 |
| 提问 | `ask_question` | 协作者 |
| 回答 | `answer_question` | 发布者 |
| 看待办收件箱 | `inbox` | 任何人 |
| 看我自己的任务 | `my_tasks` | 任何人 |
| 看单元健康 | `unit_health` | 任何人 |

**对话触发词参考**：

| 你说 | CC 会调 |
|---|---|
| "看池子有什么活" / "ganren 上有什么任务" | `list_open_tasks` |
| "接 #t_01" / "让我接这个" | `claim_task` |
| "帮我问 alice X" / "问下发布者 X" | `ask_question` |
| "看下我的 inbox" / "有没有人等我" | `inbox` |
| "回 bob：X" / "答复那条 question" | `answer_question` |
| "提交 review" / "我干完了" | `submit_for_review` |
| "lgtm / 通过 / sign off" | `sign_off_task` |
| "打回让他重做" | `reject_task` |
| "我不接了" / "放弃这个任务" | `abandon_task` |
| "把这个任务取消" | `cancel_task` |
| "把 #t_01 标签改成 X" | `retag_task` |

---

## §E 故障排查

### E.1 常见错误码

| 错误码 | 含义 | 常见原因 / 怎么办 |
|---|---|---|
| `already_claimed` (409) | 你想 claim 的任务已经被别人接走 | 刷新 list 看别的 |
| `version_conflict` (409) | 乐观锁冲突（你读到的版本被别人改过了）| 让 CC 重新读再改 |
| `invalid_state` (409) | 状态不对（比如 submit 一个 open 的任务）| 查 `get_task` 看当前状态 |
| `not_allowed` (403) | 权限不对（比如非 claimer 想 abandon）| 确认你的 handle 是不是匹配的 actor |
| `missing_decision_record` (400) | hard / DRI 任务必须填 decision_record | 让 CC 引导你填 |
| `ctx_too_large` (400) | question 的 ctx 超长 | ctx_summary ≤ 500B、ctx_full ≤ 4KB；让 CC 压缩 |
| `task_not_found` (404) | 任务 ID 不存在 | 拼写错了 / 任务被 cancel 了 |

### E.2 自查 events 表

events 是平台的 single source of truth。任何疑问都可以读它。

最简单的办法是写一行 Python（不用装 CLI）：

```bash
uv run python -c "import sqlite3; c=sqlite3.connect('./data/ganren.db'); c.row_factory=sqlite3.Row; \
  [print(dict(r)) for r in c.execute(\"SELECT created_at,type,actor,payload FROM events WHERE actor='bob' ORDER BY created_at DESC LIMIT 20\")]"
```

如果装了 `sqlite3` CLI（Windows 下 `winget install SQLite.SQLite`）：

```bash
sqlite3 ./data/ganren.db
sqlite> .headers on
sqlite> .mode column

-- 我今天发了/接了/做了哪些任务
SELECT created_at, type, payload
FROM events
WHERE actor='bob' AND created_at > date('now')
ORDER BY created_at;

-- 某个任务的完整一生
SELECT created_at, type, actor, payload
FROM events
WHERE task_id='01KT...'
ORDER BY created_at;

-- 我这周向外求助了几次（IC 货币）
SELECT COUNT(*) FROM questions
WHERE asked_by='bob' AND asked_at > date('now','-7 days');
```

### E.3 Slack 没收到通知

按顺序排查：

1. `.env` 里 `SLACK_WEBHOOK_URL` 有填吗？
2. 平台启动日志有没有报错？
3. 直接 curl 一下 webhook 看 Slack 端是否能收到：
   ```bash
   curl -X POST $SLACK_WEBHOOK_URL -H 'Content-Type: application/json' -d '{"text":"test"}'
   ```
4. MVP 阶段 Slack 失败**不重试**也**不阻塞业务流程**，所以任务状态不会因为 Slack 故障而出问题。仅观感上没消息。

---

## §F 升级与迁移

平台代码本身的升级：

```bash
git pull
uv sync --extra dev    # 拉新依赖
# 重启平台
```

数据库 schema 升级：**自动**。`migrate()` 在每次启动时检查 `_migrations` 表，应用新的 `.sql` 文件。所以拉完代码直接重启就行，不需要手动跑迁移。

把数据迁去另一台机器：

```bash
# 旧机器（用 Python，不需要 sqlite3 CLI）
uv run python -c "import sqlite3; src=sqlite3.connect('./data/ganren.db'); dst=sqlite3.connect('./data/snapshot.db'); src.backup(dst); dst.close(); src.close()"

# 拷到新机器同样的 ./data/ 路径，启动平台，自动接管
```

---

## §G 不在 MVP 范围（已知缺口）

按设计，这些事**MVP 故意没做**，提前知道免得踩坑：

| 缺什么 | 现在的应对 | 何时补 |
|---|---|---|
| 用户登录 / 密码 / RBAC | 单租户、相互信任、X-Actor header 即可 | 跨组织协作时再加 |
| Coach 货币（judgments 表 + 复用追踪）| Coach 标签可以打，但复用率统计要等 V2 | IC/Builder 流程跑稳了再加 |
| 考核仪表盘前端 | 平台只出原始事件 + 聚合查询，仪表盘是独立项目 | 单独立项做 |
| A2A 直接互通 | MVP 走中心调度；A2A 是探索方向 | 详见 spec §9 |
| Slack 失败自动补发 | 失败仅 log；状态不受影响 | 接 cron 时再加 |
| 多频道 Slack 路由 | 单 webhook 单频道 | 团队规模上来再分 |

---

## §H 相关文档

- **设计 spec**：[`docs/superpowers/specs/2026-06-05-ganren-collab-platform-design.md`](./superpowers/specs/2026-06-05-ganren-collab-platform-design.md)
- **实施计划**：[`docs/superpowers/plans/2026-06-05-ganren-collab-platform.md`](./superpowers/plans/2026-06-05-ganren-collab-platform.md)
- **配套考核框架**：[`AI-Native-组织考核框架.pdf`](../AI-Native-组织考核框架.pdf)
- **产品演示**：[`product-demo.html`](../product-demo.html)（浏览器打开看四个 flow 的动画）
