# 干人协作平台 · 设计文档

> 一句话：把"人 ↔ 人"的工作交接，转成"agent ↔ 中心调度平台 ↔ agent"的工作流；事件日志是 AI-Native 组织考核仪表盘的 single source of truth。

---

## 0. 上下文与约束

- **使用场景**：个人/小团队内部工具（≤10 人，单租户，相互信任）。不做密码、不做 RBAC、不做多租户。
- **技术路线**：MVP 纯中心调度；A2A 仅作可行性探索章节，不进 MVP 实现。
- **配套考核框架**：本平台的 `events` 表是组织考核仪表盘的原始数据源；schema 必须支撑 IC / Builder / Coach / DRI 四类标签 + AI 介入度 L1/L2/L3 + agent 自主度 L1–L5 的聚合。仪表盘本身**不属于本 MVP**，但所有字段对得上即可。
- **不变量**：
  1. 标签是工作流贴的，不是协作者选的（`tag_source='auto'`，retag 留审计）
  2. 平台不计算合成分；只存原始事件 + 聚合查询；地板灯由下游仪表盘按绝对地板算
  3. 平台不暴露"开除"动作 —— 诊断不裁决

---

## 1. 架构

```
            ┌──────────── 协作平台（单进程） ────────────┐
 发布者 CC ─┤ MCP 适配 ─┐                                 │
 协作者 CC ─┤ MCP 适配 ─┼─→ service 层 ─→ SQLite (WAL)   │
   Hermes ─┤ HTTP REST ─┘        └─→ Slack outbound      │
            └────────────────────────────────────────────┘
                       │
                       └─→ events 表 = 考核仪表盘的 single source of truth
```

- **单进程** Python 应用，FastAPI 作为 ASGI 主体，FastMCP 以 streamable HTTP mount 进同一 app
- 业务逻辑全部集中在 `service/` 包；MCP 与 HTTP 都是薄适配，**不写业务**
- SQLite 单文件 + WAL 模式；所有 mutation 走 `UPDATE ... WHERE 守卫 + version` 乐观锁
- Slack 推送：异步 fire-and-forget；失败仅在 `events.delivery_failed=true` 标记，不阻塞主流程

---

## 2. 数据模型

### 2.1 tasks（工作单元）

```text
tasks
  id              TEXT PK (ulid)
  title           TEXT
  description     TEXT
  context_summary TEXT             -- CC 自动总结，markdown
  artifacts       JSON             -- [{kind, ...}], 见 §3.2

  -- 框架对齐字段 --
  tags            JSON             -- ["IC"]|["Builder"]|["Coach"]|["DRI"] 至少 1 个
  tag_source      TEXT             -- "auto" | "override"
  ai_involvement  TEXT             -- "L1"|"L2"|"L3"
  agent_autonomy  TEXT             -- "L1"..."L5"
  difficulty      TEXT             -- "routine"|"hard"
  decision_record JSON NULL        -- 仅 difficulty='hard' 或 tags⊇{DRI} 时必填
                                   --   {options[], chosen, prob_estimate, rationale}
  outcome         JSON NULL        -- 事后回填：{summary, matched_estimate}
  rework_count    INTEGER DEFAULT 0  -- 被 reject 次数
  escalated       BOOLEAN DEFAULT 0  -- agent 跑不动升级给人
  unit_id         TEXT NULL FK     -- 单元健康聚合用，不归因到个人

  status          TEXT             -- open|claimed|awaiting_review|closed
  created_by      TEXT
  claimed_by      TEXT NULL
  created_at, claimed_at, submitted_at, closed_at  TEXT
  version         INTEGER DEFAULT 0
```

### 2.2 events（事件日志，仪表盘原料）

```text
events
  id            TEXT PK (ulid)
  task_id       TEXT FK
  type          TEXT
  actor         TEXT
  payload       JSON
  created_at    TEXT
  delivery_failed BOOLEAN DEFAULT 0

  -- 快照字段（防 retag 污染历史聚合） --
  tags_snapshot         JSON
  ai_involvement_snap   TEXT
  agent_autonomy_snap   TEXT
  unit_id_snap          TEXT
```

事件类型集合（MVP）：

```
task.created / task.claimed / task.submitted / task.signed_off /
task.rejected / task.abandoned / task.cancelled / task.escalated /
task.retagged / task.outcome_recorded
question.asked / question.answered
```

`judgment.created` / `judgment.used` 推迟到 V2，与 §2.5 同步。

### 2.3 questions（反馈循环）

```text
questions
  id           TEXT PK (ulid)
  task_id      TEXT FK
  asked_by     TEXT
  question     TEXT
  ctx_summary  TEXT             -- ≤ 500B，CC 生成的"为啥问"一句话
  ctx_full     TEXT             -- ≤ 4KB，最近若干轮 transcript 原文
  answer       TEXT NULL
  answered_by  TEXT NULL
  status       TEXT             -- open|answered
  asked_at, answered_at  TEXT
```

分层设计动机：写入端（协作者）和阅读端（发布者）需求不同。Slack 通知与 inbox 列表只展示 `ctx_summary`，发布者展开后才看 `ctx_full`。

### 2.4 actors / units

```text
actors
  handle PK, display, onboarding_date, primary_unit_id NULL FK

units
  id PK, name, type ∈ {"squad","builder_fleet","engine"},
  coach_handle TEXT NULL FK, created_at
```

- `onboarding_date` 用于"新人两天缓冲"
- `units` 用于"单元健康聚合，不归因个人"

### 2.5 V2 预留（不在 MVP 实施）

```text
judgments              -- Coach 货币：可复用的判断
judgment_usages        -- 复用追踪：判定线的硬数据
```

V2 引入时，events 增加 `judgment.created` / `judgment.used` 两个 type，§4.5 映射表的 Coach 两行被点亮。

---

## 3. 状态机与生命周期

### 3.1 状态机

```
        publish              claim                submit
 (none) ────────→ open ─────────────→ claimed ─────────────→ awaiting_review
                   │ ▲                  │ │                      │ │
                   │ │ abandon          │ │ abandon              │ │ reject (回 claimed, rework_count+1)
                   │ └──────────────────┘ │                      │ │
                   │                      │                      │ │
                   │ cancel               │ cancel               │ │ sign_off
                   └──────────────────────┴──────────────────────┴─┴──→ closed
```

**非状态转移的旁路动作（不动 status，只改字段或写事件）**：

- `retag(task_id, new_tags, reason)`：任何时间可发，写 `task.retagged` event，`tag_source='override'`。仅 `created_by` 或单元 coach 有权
- `record_outcome(task_id, outcome)`：仅 `status=closed` 之后可发，写 `task.outcome_recorded` event，用于 DRI 校准事后回填

**状态转移的旁路（改 status）**：

- `cancel_task(task_id, reason)`：仅 `created_by` 发起；从 `open` 或 `claimed` 直接 → `closed`，写 `task.cancelled` event。`awaiting_review` 之后不可取消（应走 reject + abandon 路径）

### 3.2 上下文打包（publish 工作流）

publish 不是直接 dump，是协作式工作流：

1. CC 扫当前会话起草提案：title / description / context_summary / artifacts / 推断 tags / ai_involvement / agent_autonomy / difficulty
2. 推断规则：
   - **tags**：实现/构建 → IC 或 Builder；策略选择/方向拍板 → DRI；可复用判断/playbook → Coach
   - **difficulty**：不可逆、高风险、跨单元影响 → hard
   - **ai_involvement**：协作者预期"亲手写" L1 / "拆解+审" L2 / "只验收" L3
3. 发布者逐字段 review，CC 引导修改
4. 若 `difficulty='hard'`，CC 强制引导填 `decision_record`：
   ```
   options_considered: [...]
   chosen:             ...
   prob_estimate:      0.0-1.0
   rationale:          ...
   ```
5. 提交，平台落库

`artifacts` 类型集合：

```
{kind:"file", path:"..."}            -- 本地路径
{kind:"snippet", lang, body}         -- 代码片段
{kind:"link", url:"..."}             -- 外链
{kind:"transcript", body:"..."}      -- 会话片段
```

### 3.3 claim 时的上下文注入（双轨）

平台返回 payload 后，协作者 CC 同时做两件事：

- **当前会话注入**：context_summary + artifacts 摘要塞为 user 消息
- **落地文件**：写入 `./.ganren/task-<id>.md`（含完整 payload），跨 session 续干 / 人类查看

落地文件还作为协作者 CC 调用 `ask_question` 时引用 `ctx_full` 的来源。

### 3.4 反馈循环（不确定问题）

```
协作者 ─→ "帮我问发布者 X"
       ─→ CC ask_question(task_id, question, ctx_summary, ctx_full)
            │
            ▼
        questions 行 + Slack 通知发布者频道（只发 ctx_summary）
            │
发布者 CC inbox() 拉取 ──┘
            │
       发布者口述/CC 草拟 ─→ 确认 ─→ answer_question(qid, answer)
            │
            ▼
        Slack 通知协作者频道
            │
协作者 CC inbox() 拉取 ──┘
            │
       ─→ 把 answer 注入当前会话 ─→ 继续干
```

关键设计：
- `ctx_summary` ≤ 500B；`ctx_full` ≤ 4KB；CC 自动生成，协作者不直接打字
- inbox 是 pull-based，不依赖在线状态；Slack 只是 nudge
- 一个 task 可以有多个 open question，相互不阻塞

---

## 4. 操作集（MCP 与 HTTP 同源）

同一份 service 层，MCP 与 HTTP 各暴露一遍。

### 4.1 发布者侧

| 操作 | 入参 | 守卫 | 副作用 |
|---|---|---|---|
| `publish_task` | title, description, context_summary, **tags（必填）, ai_involvement（必填）, agent_autonomy（必填）, difficulty（必填）**, artifacts?, decision_record?, unit_id? | hard 或 DRI ⇒ decision_record 必填；tag_source='auto' | events.task.created + Slack 广播 |
| `retag_task` | task_id, new_tags, reason | actor=created_by 或 unit.coach | tag_source='override' + events.task.retagged |
| `cancel_task` | task_id, reason | actor=created_by 且 status∈{open,claimed} | status→closed + events.task.cancelled |
| `sign_off_task` | task_id, comment? | actor=created_by 且 status=awaiting_review | status→closed + events.task.signed_off |
| `reject_task` | task_id, reason, hints? | actor=created_by 且 status=awaiting_review | status→claimed + rework_count+1 + events.task.rejected |
| `record_outcome` | task_id, summary, matched_estimate? | status=closed | events.task.outcome_recorded |
| `answer_question` | question_id, answer | actor=对应 task 的 created_by | question.status→answered + events.question.answered |

### 4.2 协作者侧

| 操作 | 入参 | 守卫 | 副作用 |
|---|---|---|---|
| `list_open_tasks` | filter? {tags, ai_involvement, difficulty} | — | 返回精简视图：id/title/description/tags/ai/autonomy/difficulty/created_by。**不含 context_summary / artifacts** |
| `claim_task` | task_id | 原子 `UPDATE WHERE status='open' AND version=?` | 返回完整 payload（context_summary + artifacts + question_history）+ events.task.claimed |
| `abandon_task` | task_id, reason | actor=claimed_by 且 status=claimed | status→open + claimed_by=null + events.task.abandoned |
| `ask_question` | task_id, question, ctx_summary, ctx_full | actor=claimed_by | 新 questions 行 + events.question.asked + Slack 通知发布者 |
| `submit_for_review` | task_id, summary | actor=claimed_by 且 status=claimed | status→awaiting_review + events.task.submitted |
| `report_escalation` | task_id, note | actor=claimed_by | tasks.escalated=true + events.task.escalated |

### 4.3 通用

| 操作 | 用途 |
|---|---|
| `inbox()` | 按 actor 角色返回分组：`questions_to_answer` / `reviews_pending`（发布者视角）+ `answers_received` / `rejections_to_address`（协作者视角） |
| `get_task(task_id)` | 详情，权限按 actor 关系自动判 |
| `my_tasks(window)` | 我创建的 + 我认领的，含状态分布 |
| `unit_health(unit_id, window)` | 单元健康聚合，**不归因到个人** |

### 4.4 错误码

| 码 | 场景 |
|---|---|
| 400 missing_decision_record | hard 或 DRI 任务缺 decision_record |
| 400 invalid_tags | tags 为空或包含未知值 |
| 400 ctx_too_large | ctx_summary > 500B 或 ctx_full > 4KB |
| 403 not_allowed | retag/cancel/sign_off/reject 不是 created_by 或 coach |
| 404 task_not_found / question_not_found | — |
| 409 already_claimed | claim 时 status≠open |
| 409 invalid_state | 状态守卫失败（如 submit 一个 open 任务） |
| 409 version_conflict | 乐观锁冲突，建议客户端重读再试 |

### 4.5 考核框架 ⇆ 数据字段映射

| 框架要求 | 数据来源 |
|---|---|
| IC 一周不抛弃 = 没在认真探索 | `events.task.abandoned WHERE actor=X` 窗口聚合 |
| IC 向单元外求助逐周减少 | `questions WHERE asked_by=X` 窗口聚合 |
| IC delegate→review→own / 队列深度 | `tasks WHERE status='awaiting_review' AND created_by=X` |
| Builder 每周固定吞吐 | `events.task.signed_off WHERE tags⊇{Builder} AND claimed_by=X` |
| Builder 可插拔（context 没进脑子）| `tasks.context_summary` + `artifacts` 完整度审计 + 同类 task 是否只能某人 claim（聚合派生）|
| Coach 判断复用率 | V2 引入 `judgment_usages` 后：`COUNT GROUP BY judgment.created_by` |
| Coach 升级率下降 | V2 引入后：`COUNT(questions) GROUP BY scope_tags` 窗口趋势 |
| DRI 决策质量（事前）| `tasks.decision_record` 填写 + 内容审计 |
| DRI 校准（概率分布）| 跨多 closed task 的 `decision_record.prob_estimate × outcome.matched_estimate` 聚合 |
| DRI 担当 | 早暴露：questions.asked_at 早于 submitted_at；如实上报：outcome JSON 完整 |
| DRI 真用了权 | `tasks WHERE difficulty='hard' AND claimed_by=X` 周期聚合 |
| AI 介入度 L2+L3 占比 | `tasks.ai_involvement` 窗口聚合 |
| Agent 自主度 / 升级率 | `tasks.agent_autonomy` + `events.task.escalated` 比率 |
| 单元健康（不归因个人）| `tasks/events GROUP BY unit_id` |
| 新人两天缓冲 | `actors.onboarding_date` |
| 流动治理（切标签洗不掉低产）| `events.tags_snapshot` 各窗口分别累加 |

---

## 5. 一致性、并发、错误处理

### 5.1 事务边界

每个状态转移操作 = 单事务，事务里同时落 tasks 更新 + events 插入：

```python
with conn:
    rowcount = update_task(...)         # 带 WHERE 守卫
    if rowcount == 0: raise Conflict
    insert_event(...)                   # 同事务必然一起落
```

不能把 events 和 status 拆成两个事务，否则崩溃恢复时仪表盘聚合会错位。

### 5.2 并发控制

核心机制只有一条：所有 mutation 用 `UPDATE ... WHERE 守卫 + version` 然后看 rowcount。无锁乐观并发。

```sql
UPDATE tasks
SET status=:new, ..., version=version+1
WHERE id=:id AND status=:expected AND version=:expected_version;
-- cursor.rowcount == 1 才视为成功
```

边界用例：

| 场景 | 行为 |
|---|---|
| 两人同时 claim 同一 open task | 一成一败；败者 409 already_claimed |
| 协作者 abandon vs 发布者 cancel | 谁先到 SQLite 内部锁谁赢；另一方 409 invalid_state |
| 同一 task 重复 submit | 第二次 409 invalid_state |
| 多人 ask_question | 不互斥，追加表并行写无冲突 |

**SQLite 配置**：`journal_mode=WAL`、`synchronous=NORMAL`、`busy_timeout=5000ms`。

### 5.3 Slack 投递失败

webhook 不在事务里。事务 commit 后异步投递；失败仅在 `events.delivery_failed=true` 标记。MVP 不做重试；schema 留口子，未来可上 cron 扫表补发。

### 5.4 服务崩溃恢复

SQLite WAL + 单事务 → 拉起服务自然回到最后一致状态。不需要额外恢复流程。

---

## 6. 通知（Slack outbound）

**MVP 简化**：单 webhook 全部发同一频道。用户在 Slack 端按事件 emoji / 关键词订阅或筛选。多频道路由放 V2。

| 事件 | 模板（mention 仅作语义提示，MVP 不实际 @ 人）| 内容 |
|---|---|---|
| task.created | `📌 PUBLISH` | `#<id> <title> [tags] 由 <created_by> 发布` |
| task.claimed | `🙋 CLAIM` | `#<id> 被 <claimed_by> 接走` |
| task.submitted | `✅ REVIEW @<created_by>` | `#<id> 待 review` |
| task.signed_off | `🎉 CLOSE` | `#<id> 关闭` |
| task.rejected | `↩️ REJECT @<claimed_by>` | `#<id> 打回：<reason>` |
| task.abandoned | `🪂 ABANDON`（无 mention，减少面子压力）| `#<id> 回池` |
| task.cancelled | `🛑 CANCEL` | `#<id> 已取消` |
| question.asked | `❓ Q @<created_by>` | `#<task_id>: <ctx_summary>`（不发 ctx_full）|
| question.answered | `💬 A @<asked_by>` | `#<task_id> 已回复` |

实现：
- 单个 webhook URL：`SLACK_WEBHOOK_URL`
- `httpx.AsyncClient`，timeout=5s
- 失败标记 `events.delivery_failed=true`，不阻塞主流程

> 通道分流是文化决策。MVP 默认单通道避免配置爆炸；多频道路由（按事件类型路由到不同 webhook）放 V2。改成多通道只需改配置 + 一行 service 层映射，不动 schema。

---

## 7. 测试策略

| 层 | 工具 | 覆盖 |
|---|---|---|
| service 单测 | pytest | 状态机所有转移路径；权限守卫；hard 任务 decision_record 强制校验；retag 审计 |
| 并发测试 | pytest + threading | 两个 thread 同时 claim 同一 task，断言一成一败；abandon vs cancel 竞态 |
| HTTP 集成 | pytest + httpx AsyncClient | 完整 REST 路径；错误码契约 |
| MCP 集成 | mcp client SDK | 启动 server，跑工具列表/调用 |
| Slack 投递 | pytest + respx mock | 成功路径 + 失败标 delivery_failed |
| 端到端 | 两个真实 CC session 手动 | publish → claim → ask → answer → submit → sign_off 闭环 |

**测试纪律**：
- 不 mock SQLite（用临时文件，行为真实且快）
- 必须 mock Slack（外部依赖）
- 测试用例命名带状态机转移名称，方便回溯

---

## 8. 部署形态（MVP）

- 单二进制：`uv run python -m ganren_platform.main`
- SQLite 文件：`./data/ganren.db`（WAL 模式，启动自动 migrate）
- 配置文件：`.env`：
  ```
  BIND_ADDR=0.0.0.0:8787
  SLACK_WEBHOOK_URL=https://hooks.slack.com/...
  LOG_LEVEL=info
  ```
- HTTP + MCP streamable HTTP **同端口不同路径**：`/v1/...` vs `/mcp/...`
- CC 端配置：`.mcp.json` 写一条 server entry
- 日志：stdout JSON Lines

---

## 9. A2A 技术可行性探索（不进 MVP 实现）

| 路线 | 思路 | 与本平台兼容度 | 复杂度 |
|---|---|---|---|
| **A. Google A2A 协议** | 用 2024-2025 出的 A2A 标准；每个 agent 暴露 AgentCard | 中：task schema 要 map 成 A2A Task 对象；状态机对齐 A2A TaskState | 高 |
| **B. 双向 MCP** | 每个 CC 端跑轻量 MCP server 暴露 publish/answer；对方作 client 调用 | 高：本平台已是 MCP server，对称化即可 | 中 |
| **C. 共享消息总线** | NATS / Redis Streams + JSON envelope；每个 agent 订阅自己 channel | 中：相当于把"中心 DB"换成"消息流"；events 退化为 replay 视图 | 中 |
| **D. 复用本平台 HTTP REST 互调** | 每个 agent 跑 HTTP server，互相 webhook；本平台从"调度器"降级为"目录服务" | 高：完全复用 schema | 低 |

**建议演进路径**：MVP 跑稳后先试路线 D（复用 HTTP/JSON schema，验证去中心最小路径），再评估是否上 A（协议标准化）。B 留作 fallback。C 仅当并发量明显上来才考虑。

A2A 不影响 MVP 的数据模型设计 —— task/event/question schema 已足够通用，MVP 实现期间不引入任何 A2A 兼容层。

---

## 10. 范围切分（MVP vs V2）

**MVP（本设计文档涵盖）**：
- 单进程平台 + SQLite + WAL
- tasks / events / questions / actors / units 五张表
- §4.1–4.3 操作集
- Slack outbound 通知（§6 矩阵）
- 测试策略 §7
- 部署形态 §8

**V2（后续，本设计仅留接口）**：
- `judgments` + `judgment_usages` 两张表 + 对应 events 类型
- 考核仪表盘前端（读 events 表）
- A2A 实验（按 §9 建议路径走 D）
- Slack 失败补发 cron
- 多频道 / 多 webhook 路由的精细化

---

## 11. 开放问题（实施期再决）

1. `decision_record.options_considered` 用结构化 JSON 还是自由 markdown？影响 CC 引导难度
2. `record_outcome` 谁可以发起？默认 `created_by` + `coach`，但需要"任何 actor 看到关键结果后补一笔"吗？
3. `units` 由谁创建/维护？MVP 阶段是否手动写 seed 即可？
4. CC 端 skill 文件分多少个？候选拆分：`ganren-publish` / `ganren-collaborate` / `ganren-inbox` 三个
