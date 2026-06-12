# V2 · 定时 Slack 日报 + 新任务池快照 设计文档

> 来源：V2_BACKLOG.md §4。第一波 V2 P0 项之一。
> 一句话：让 Slack 频道每天自动收到两条全组日报 + 每次有新任务时附带当前任务池快照，不再依赖人工跑脚本。

---

## 0. 上下文与约束

- **范围**：服务端调度 + Slack 推送渲染。**不**包括个人化 push、watch_inbox 工具、Block Kit 卡片等其他 V2 项。
- **使用场景**：单中心调度机持续运行 `python -m ganren_platform.main`。Slack webhook 单频道已配。
- **关联现状**：
  - V1 已有 `notifications/slack.py` 做实时事件推送（task.created/claimed/...），保留不变
  - 看板逻辑现在散落在临时 Python 脚本里，需要沉到 platform 模块内
  - `events` 表是真相源，所有摘要数字来自它

---

## 1. 架构

### 1.1 模块新增

```
src/ganren_platform/notifications/
├── slack.py                # 已有 · 实时事件推送，保留
├── digest.py               # 新 · 渲染日报 / 池快照
└── scheduler.py            # 新 · apscheduler 包装
```

`digest.py` 暴露 5 个函数（前 3 个纯函数无副作用、易测试；后 2 个负责推送 + 节流）：

- `render_pool_snapshot(conn, *, max_rows=50) -> str` — 渲染所有未关闭任务，等宽表格
- `render_morning_digest(conn, *, today: date) -> str` — 早 10:00 日报（前一个工作日活动 + 池快照）
- `render_evening_digest(conn, *, today: date) -> str` — 晚 18:00 日报（今天 0:00 → now 活动 + 池快照）
- `push_publish_snapshot(conn, webhook_url, new_task_id) -> None` — 在 publish_task 完成后调用，渲染池快照 + POST 到 webhook（遵从 `PUBLISH_INCLUDES_SNAPSHOT` 配置 + 节流）
- `should_push(kind: str) -> bool` — 模块级节流，60s 窗口

`scheduler.py` 暴露 2 个：

- `build_scheduler(cfg, db_path) -> BackgroundScheduler` — 装配 2 个 cron job（morning / evening）
- `start_scheduler_if_enabled(app, cfg, db_path) -> None` — `main.py` 启动时调用，封装 try/except 保证 scheduler 故障不阻塞 server

### 1.2 集成点

1. **`main.py`**：在 `uvicorn.run` 之前调 `start_scheduler_if_enabled(...)`
2. **`service/tasks.py publish_task`**：事务 commit 之后，schedule_slack 之外再调 `notifications.digest.push_publish_snapshot(...)`
3. **配置**：`config.py` 增加新字段，全部从 `.env` 读

### 1.3 数据流

```
                          [cron 10:00 / 18:00]
                                  │
                                  ▼
  ┌────────────────────────────────────────┐
  │      apscheduler BackgroundScheduler   │
  └──────────────┬─────────────────────────┘
                 │
                 ▼
        render_morning/evening_digest()
        ────────────────────────────
        │ ⓐ 查 events 拿活动摘要
        │ ⓑ 查 tasks 拿未关闭池
        │ ⓒ 渲染等宽表格
        ▼
        slack.post_to_webhook(...)
                 │
                 ▼
        Slack 频道


       [service.publish_task 完成]
                 │
                 ▼
        schedule_slack(task.created)  ← 现有，单条事件通知
                 +
        push_publish_snapshot()       ← 新增：紧接着一条池快照
```

---

## 2. 调度配置

`.env` 新增：

```dotenv
SCHEDULER_ENABLED=true               # 平台启动时是否启 scheduler（默认 true）
SCHEDULER_TZ=Asia/Shanghai           # cron 时区
MORNING_DIGEST_CRON=0 10 * * MON-FRI # 工作日早 10:00
EVENING_DIGEST_CRON=0 18 * * MON-FRI # 工作日晚 18:00
SLACK_DIGEST_WEBHOOK=                # 留空就复用 SLACK_WEBHOOK_URL
PUBLISH_INCLUDES_SNAPSHOT=true       # publish 时是否附池快照（默认 true）
SNAPSHOT_MAX=50                      # 单条消息池快照上限，超过尾部加省略
```

`config.py` 对应字段：

```python
@dataclass(frozen=True)
class Config:
    # ... 已有
    scheduler_enabled: bool
    scheduler_tz: str
    morning_digest_cron: str
    evening_digest_cron: str
    slack_digest_webhook: str | None  # None 时回落用 slack_webhook_url
    publish_includes_snapshot: bool
    snapshot_max: int
```

---

## 3. 内容渲染规则

### 3.1 时间窗口

| 触发 | 窗口（本地时区）| 算法 |
|---|---|---|
| 早 10:00 | 前一个工作日 00:00 → 23:59:59 | `previous_workday(today)`：周一→上周五；其他→昨天 |
| 晚 18:00 | 今天 00:00 → 当前 | 直接取今天 0 点 |
| publish 触发 | 不限窗口 | 直接拿当前快照 |

`previous_workday()` 算法：

```python
from datetime import date, timedelta

def previous_workday(today: date) -> date:
    """周一 → 上周五；周二-周五 → 昨天。
    cron 限定 MON-FRI 触发，所以 today 总是工作日。
    节假日不特殊处理：如果上一个日历日是节假日（无活动），
    日报里"上一个工作日摘要"会全是 0，这是可接受的，
    不会出错也不会推空消息（仍含池快照）。"""
    if today.weekday() == 0:  # Monday
        return today - timedelta(days=3)
    return today - timedelta(days=1)
```

### 3.2 早 10:00 日报样本

````
🌅 ganren 日报 · 2026-06-10 早 10:00
上一个工作日（2026-06-09）摘要：
```
📌 发布  🙋 认领  🎉 关闭  ↩ 打回  ❓ 提问  💬 回答
   3       2       1       0       2       1
```
当前任务池（共 8 条 active）：
```
状态        ID         标题                              负责人     停留
──────────────────────────────────────────────────────────────────────
🟢 open     #t_AB12    试用 ganren 平台                  -          2d
🟢 open     #t_BC34    把首页响应时间从 2.1s 压到 800ms   -          3d
🟢 open     #t_CD56    webhook 链路迁移                  -          1d
🟢 open     #t_DE78    主备策略评估 [DRI]                -          4d
🟡 claimed  #t_EF90    优化 logs 检索                    bob        1h
🟡 claimed  #t_FG12    试用任务                          HuangTang  3h
🟡 claimed  #t_GH34    重构通知队列                      alice      5h
🔵 review   #t_HI56    改造支付链路                      alice 等   2h
```
````

### 3.3 晚 18:00 日报样本

格式同早报，差异：
- 标题：`🌆 ganren 日报 · 2026-06-10 晚 18:00`
- 摘要文案：`今日（00:00 至 18:00）：`

### 3.4 新任务推送样本

````
📌 PUBLISH #t_XY99 优化登录页 [Builder] 由 alice 发布
```
当前池：🟢 open 5 · 🟡 claimed 3 · 🔵 review 1
```
```
状态        ID         标题                负责人     停留
──────────────────────────────────────────────────────
🟢 open     #t_XY99    优化登录页 ← 新     -          刚才
🟢 open     #t_BC34    LCP 优化            -          3d
🟢 open     #t_AB12    试用 ganren         -          2d
🟡 claimed  #t_EF90    logs 检索           bob        1h
... 还有 5 条
```
````

> 注：这是**继 `📌 PUBLISH` 单条事件消息之后的第二条**。两条消息会紧挨着出现。可以是同一个 webhook 调用里 N=2 个块，或两次连续 POST。实现选后者更简单。

### 3.5 列定义

| 列 | 内容 | 宽度 |
|---|---|---|
| 状态 | emoji + 状态名简写（`🟢 open` / `🟡 claimed` / `🔵 review`）；`review` 是 `awaiting_review` 的展示简写 | 10 字符 |
| ID | `#t_XXXXXX`（ULID 后 6 字符前缀 `#t_`）| 10 字符 |
| 标题 | task.title，超长用 `...` 截断 | 32 字符 |
| 负责人 | claimed_by；open=`-`；review=`<creator> 等` | 10 字符 |
| 停留 | 当前状态下停留时长，`Xh` / `Xd`，<1h 用 `<1h` | 6 字符 |

「停留」计算：

```python
def state_dwell(row: sqlite3.Row, now: datetime) -> str:
    """当前状态从何时开始算起的时长。"""
    if row["status"] == "open":
        # open 状态下的"停留"指从最近一次回到 open 的时间起
        # 简化：用 created_at（abandon 回 open 极少发生）
        anchor = row["created_at"]
    elif row["status"] == "claimed":
        anchor = row["claimed_at"]
    elif row["status"] == "awaiting_review":
        anchor = row["submitted_at"]
    delta = now - datetime.fromisoformat(anchor)
    if delta.total_seconds() < 3600:
        return "<1h"
    if delta.days >= 1:
        return f"{delta.days}d"
    return f"{int(delta.total_seconds() / 3600)}h"
```

### 3.6 上限保护

`render_pool_snapshot(conn, max_rows=50)`：

- 查询带 `LIMIT max_rows`，按 `(status, created_at DESC)` 排序确保 open 在前
- 真实数 > max_rows 时，表格末尾追加：
  ```
  ... 还有 N 条（open A · claimed B · review C）
  ```
- 不输出 `closed` 任务

---

## 4. 节流

`digest.py` 模块级 dict：

```python
import time

_last_push: dict[str, float] = {}
_THROTTLE_SECONDS = 60

def should_push(kind: str) -> bool:
    now = time.time()
    if now - _last_push.get(kind, 0) < _THROTTLE_SECONDS:
        return False
    _last_push[kind] = now
    return True
```

`kind` 取值：
- `"morning_digest"`
- `"evening_digest"`
- `"publish_snapshot"`

**适用场景**：
- 短时间内有多个 task.created 时，只有第一个的 publish_snapshot 推出去
- 重启平台后内存清零，第一次推送总能成功

**不适用**：
- 实时事件推送（task.claimed/.../question.*）不走节流，每条都推

---

## 5. 错误处理

| 故障 | 处理 |
|---|---|
| `apscheduler` 启动失败 | log.error，web server 继续起 |
| cron 表达式无效 | 启动时校验，无效就 log.error + 该 job 不装；server 继续 |
| `render_*` 渲染异常 | log.warning + 该次推送跳过，下次 cron 正常 |
| Slack POST 失败 | log.warning，不重试（同现有 §5.3） |
| 数据库连接失败 | 当前 SQLite 进程内，几乎不会发生；如果发生，归类到上一条渲染异常 |

**fail-safe 原则**：notifications 永远不阻塞业务流程，scheduler 永远不阻塞 web server。

---

## 6. 测试策略

| 层 | 工具 | 覆盖 |
|---|---|---|
| digest 单测 | pytest + 临时 sqlite | 给定固定 events/tasks，断言渲染输出含三桶 + 摘要数字正确 + 「停留」列计算正确 |
| 时间窗口单测 | pytest, freezegun | `previous_workday` 周一→上周五；其他→昨天 |
| 节流单测 | pytest | 调 2 次 `should_push("x")` 间隔 < 60s，第二次返回 False；间隔 ≥ 60s 第二次返回 True |
| 上限保护单测 | pytest | 插 60 条 active task，断言渲染只含 50 条 + `... 还有 10 条` |
| scheduler 单测 | apscheduler 测试模式 | 装载两个 job，触发后 callback 被调一次 |
| Slack 集成 | pytest + respx | 触发 morning_digest，断言 webhook 被 POST 一次，body 含「ganren 日报」 |
| 端到端 | pytest + httpx AsyncClient | 启 platform + mock Slack，POST /v1/tasks 发布任务，断言收到 ≥ 2 条 Slack 消息 |

**测试纪律**：
- 时间相关一律 freezegun
- 不真发 Slack
- digest 函数纯查询，可以用临时 sqlite 喂固定状态

---

## 7. 部署 / 迁移

- **依赖新增**：`apscheduler>=3.10`、`freezegun>=1.5`（dev only）
- **schema 变更**：无
- **运维迁移**：升级流程不变（`git pull && uv sync && 重启 platform`）
- **回滚**：`SCHEDULER_ENABLED=false` + 重启
- **多实例部署**（未来）：不支持。`should_push` 节流在内存里，多个 platform 进程会各自节流，每个进程都会重复推。当前 MVP 是单实例，不考虑

---

## 8. 与现有系统的关系

| 现有 | 关系 |
|---|---|
| `notifications/slack.py` | 不动，继续负责实时事件推送 |
| `service/tasks.publish_task` | 末尾追加调用 `digest.push_publish_snapshot(...)`，**事务外**调用 |
| `events` 表 | 唯一真相源，digest 计算"过去 24h 摘要"全靠它 |
| `config.py` | 增加 7 个新字段 |
| `main.py` | 启 server 前先启 scheduler |

---

## 9. 不在范围

下列 V2 项另立 spec：
- 异步问答 push（V2 #1）—— 个人级 webhook 路由 / watch_inbox
- 非开发者看板（V2 #3）—— Block Kit、个人视角
- self-register endpoint（V2 #2 服务端部分）
- list_open_tasks 重复检测（V2 #5）

---

## 10. 开放问题（实施期再决）

1. 节流是否要持久化？目前在内存里。重启平台后内存清零，下一次 cron 触发会正常推。MVP 接受。
2. cron 表达式校验用哪个库？apscheduler 自带 CronTrigger 解析，无效直接抛 ValueError，我们 catch 即可。
3. 「停留」列 emoji 化？目前纯文本（`3d` / `5h` / `<1h`）。MVP 不动；觉得太朴素再加 ⏱ 类装饰。
4. 摘要表头里的 emoji 跟 Slack mrkdwn 排版关系：等宽字体里 emoji 宽度可能不一致，导致对齐错位。实施时实测，必要时把 emoji 移到列头之外。
