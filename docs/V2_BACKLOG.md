# V2 Backlog

> 第一次给队友（HuangTang）真实试用后收集到的痛点 + 用户后续提出的体验诉求。
> 每项都标了**真痛点的证据** + **候选方案** + **是否要 brainstorm**。
> 标 ⭐ 的是 V2 必做（核心体验缺口），其他按价值排序。

---

## V2 主题：从"能用"到"使用者用得舒服"

V1 把核心数据流跑通了。试用证明**协作循环本身没问题**（HuangTang 半天走完 claim → ask → submit → 闭环）。但暴露出 V1 是**开发者视角**做的产品 —— 工具命名、看板、配置流程都依赖用户懂技术。V2 的主线：**让非开发者背景的人也能顺畅协作**。

---

## ⭐ 1. 异步问答的 push 信号（最痛）

### 真痛点的证据

HuangTang submit summary 里原话：

> 从提问到收到回答约 **1h21m**（07:28→08:49），期间只能手动轮询 inbox，不知道何时回。希望有 push / watch_inbox（阻塞等待）/ 回调机制。

### 当前状态

- 全局 Slack webhook 已有，所有事件广播到一个频道。
- 但 **个人级 push 没做**：HuangTang 个人 IM 收不到"alice 回你了"
- 协作者只能让 CC 反复跑 `inbox` 工具，体验不闭环

### 候选方案（待 brainstorm 选）

| 方案 | 优 | 劣 |
|---|---|---|
| A. 个人级 Slack DM | 用户已习惯 Slack；webhook 升级为 Slack App（OAuth）才能 DM 个人 | 要升级到 Slack App、走 OAuth；管理员配置变复杂 |
| B. 多 webhook 路由（按 actor → webhook） | 不需要 OAuth，只需多个 incoming webhook | 队友每人得自己建一个 Slack channel + webhook |
| C. `watch_inbox` 阻塞 MCP 工具（长轮询/SSE）| MCP 协议原生支持；CC 端体验最丝滑 | 需要在 MCP 层实现 SSE/长轮询；本地 CC 会话需要"挂"在那儿 |
| D. 桌面通知（推 macOS Notification Center / Windows Toast） | 真正的 OS 级 push | 需要每个队友机器跑一个 daemon 拉队列 |

**初步倾向**：**B + C 组合**。多 webhook 路由（同步通知）做基础设施，`watch_inbox` 做高级 CC 体验。两个独立可分别落地。

### Open questions（要先 brainstorm 决的）

- 协作者愿意为通知建私人 channel + 配 webhook 吗？还是宁可走全局频道凑合？
- `watch_inbox` 长轮询的超时阈值多少（5 分钟？15 分钟？）？
- 长轮询和 polling 共存还是替代？

---

## ⭐ 2. 队友 onboarding 全自动（管理员零干预）

### 真痛点的证据

HuangTang setup 时踩了几个连环坑：

1. setup_client.py 默认 URL 是 localhost → 他没改 → 配错了
2. 在 ganren 仓库目录里启 CC → CC 误以为要本地部署
3. server 端 DNS rebinding protection 拦了局域网 IP（HTTP 421）
4. 加完 actor 还要管理员手动跑 `add_actor.py`

每个坑都让管理员（你）卡了一次。**总耗时大约 1 小时**才让 HuangTang 真正能用。

### 当前状态

- `tools/setup_client.py` 引导配置 + 诊断已经做了
- 但**仍依赖管理员**手动加 actor + 转告 URL
- `docs/USAGE.md` 给的是**人类读者**视角的指引

### 候选方案

| 方案 | 描述 |
|---|---|
| A. **写一份 CC 专用的 onboarding 指引** | 在仓库根放 `ONBOARDING_FOR_CLAUDE.md`，队友 clone 后跟自己的 CC 说"按 ONBOARDING_FOR_CLAUDE 给我配 ganren"，CC 自己读文档 + 调 setup_client.py + 提示步骤 |
| B. **平台端 self-register endpoint** | 队友的 CC 直接调一个 `register_actor(handle, display)` 端点，平台自动加（无需管理员介入）。配合 token 防滥用 |
| C. **管理员发邀请链接** | 管理员生成 `https://.../invite/<token>`，队友 CC 拿这个链接一行命令搞定（带 token 一次性自动注册） |

**初步倾向**：**A + B 组合**。A 是文档活，立刻能做。B 让管理员彻底不用介入，但需要平台升级（加 endpoint + token 机制）。

### Open questions

- self-register 要不要管理员审批？（一键拉黑/允许）
- handle 冲突时怎么处理？
- onboarding 文档要写成 CC 一步一步跟的"checklist + 验证命令"形式吗？

---

## ⭐ 3. 数据看板对非开发者也能看懂

### 真痛点的证据

用户原话：

> 数据看板感觉**开发者才能一眼看懂**、不方便使用者用

确实 —— V1 看板把 events 数、SQL 字段、ULID 截断这些"实现细节"都暴露了。非开发者只想知道"我手上有几件事 / 这周协作健康吗"。

### 当前状态

- 看板长 60+ 行，9 个 section
- 标题用 SQL/字段名（`events.task.signed_off`、`tags_snapshot`）
- 终端 ASCII 表格，Slack 上勉强能看

### 候选方案

| 方案 | 描述 |
|---|---|
| A. **个人视角看板** | 不再是"全组聚合"，而是"你当前的 3 件待办 + 这周你的进展" |
| B. **图形化 HTML 看板** | 平台多一个 endpoint 返回 HTML 报表（可挂在浏览器看），含图表（任务/事件趋势）+ 任务卡片 |
| C. **Slack 块状卡片** | 用 Slack Block Kit 重写看板消息，分块、按钮、emoji，可视化 |

**初步倾向**：**A + C**。Slack 上就出"今天的简报"（个人视角 + 全组健康），不放 SQL 术语；HTML 看板作为可选的"经理视图"。

### Open questions

- 看板核心 KPI：每个角色（IC/Builder/Coach/DRI）要看到什么 1-3 个最关键的数字？
- "本周你向外求助多少次"这种 IC 货币，要不要在个人看板**主动提示**（怕引发焦虑），还是只让本人有意问才显示？

---

## ⭐ 4. Slack 看板/状态推送自动化（不要人工触发）

### 真痛点的证据

用户原话：

> slack 的发布也要定期（形式可以再商量）不要我手动叫你发布叫你 python 代码，要自动化全程

V1 看板是我手动跑 Python 脚本推到 Slack 的。这不是产品。

### 候选方案

| 方案 | 描述 |
|---|---|
| A. **server 内置 scheduler** | 用 `apscheduler` 在 platform 进程内跑定时（每日 9 点推日报、每周一推周报） |
| B. **外部 cron** | 在管理员机器加一个系统级 cron，定时调 `tools/dashboard_push.py` |
| C. **新 endpoint + 触发器** | `POST /v1/admin/push_dashboard?audience=daily` —— 配合 cron 或 CC `loop` skill 来调 |

**初步倾向**：**A**。MVP 简单：平台启动时拉起 scheduler，配置写 `.env`：

```
SCHEDULER_DAILY_AT=09:00
SCHEDULER_WEEKLY_AT=mon 09:00
SLACK_DAILY_WEBHOOK=...
SLACK_WEEKLY_WEBHOOK=...
```

每天/每周触发自动推 Slack。

### Open questions

- 推到主频道还是单独的 #ganren-reports 频道？
- 不同时段推不同看板（早会前推待办 / 周五下班推这周成绩单）？
- 个别活跃事件实时推送时（task.created / 关闭）+ 定期看板的关系怎么协调（不重复）？

---

## 5. list_open_tasks 重复任务检测

### 真痛点的证据

HuangTang 反馈第 3 点：

> list_open_tasks 出现**重复任务**（同一个「首页响应时间」发布了两条），列表无去重，也没有「已读/忽略」标记

### 当前状态

平台没有任何去重逻辑。`list_open_tasks` 直接 select。

### 候选方案

| 方案 | 描述 |
|---|---|
| A. 发布时检测 | publish_task 检测最近 1 小时内同 created_by 是否有同标题/相似 description → 返回时给 warning，发布者 confirm 后才入库 |
| B. 列表时标注 | list_open_tasks 检测疑似重复，返回时附 `possibly_duplicate_of: <id>` 字段，客户端可选过滤 |
| C. 协作者忽略 | 加 `ignore_task(actor, task_id)` 工具，协作者主动屏蔽某条 |

**初步倾向**：**A**（防患于发布前最干净）。B 作为补救。C 是后期 nice-to-have。

---

## 6. MCP 工具 deferred 摩擦（**不属于本平台**）

### 反馈

HuangTang 第 1 条反馈：

> 17 个工具首次调用每个都要先 ToolSearch 加载 schema

### 处理

这是 **Claude Code 自身**的 DeferredTools 机制，不是 ganren 能改的。**记在文档里让用户知情**就行（USAGE.md 加一段说明）。如果 CC 后续放宽 deferred 阈值/允许 server 端预热，自然就好了。

---

## 优先级建议

| 排序 | 项 | 估算工作量 |
|---|---|---|
| P0 | **#2 队友 onboarding 文档**（ONBOARDING_FOR_CLAUDE.md）| 小（半天）|
| P0 | **#4 Slack 看板定时推**（server 内置 scheduler）| 中（1-2 天）|
| P1 | **#3 非开发者看板**（个人视角 + Slack 卡片）| 中（1-2 天）|
| P1 | **#1 异步 push 通知**（多 webhook 路由 + 可选 watch_inbox）| 大（3-5 天，含两条路线）|
| P2 | **#5 list_open 去重** | 小（半天）|
| --- | #6 MCP deferred 摩擦 | 文档说明即可 |

**建议第一波就做 P0 两项** —— onboarding 文档 + 定时看板。先解决"管理员每次都得手动介入"的痛点，新队友加进来更顺，体验立刻可见。

---

## 不在 V2 范围

继续沿用 V1 spec §G 列的：
- 用户登录 / RBAC / 跨组织
- judgments + judgment_usages（Coach 货币）
- 考核仪表盘前端（独立项目）
- A2A 直接互通
- Slack 失败自动补发 cron

---

## 演进决策记录

- 2026-06-10：基于 HuangTang 试用反馈 + 用户体验诉求，初始版本写下。
- HuangTang 提交 summary 完整存档于 events 表 `task.submitted` payload 中（任务 id `01KTK4NEK1SNGQAT642DA0M8A0`），随时可回溯佐证。
- 2026-06-10：V2 #4 实施时简化了 spec §3.4 的 publish 池快照消息，没做 bucket-summary 一行预览和"← 新"高亮。原因：emoji 等宽对齐风险（spec §10 开放问题 #4）+ MVP 节奏优先。补全留 V2.x（追加 `new_task_id` 参数 + bucket header row）。
