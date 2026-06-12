# 给 Claude Code 看的协作者入网指引

> **目标读者**：你（Claude Code）。
> **触发**：当一个用户对你说类似 "帮我配 ganren" / "按 ONBOARDING_FOR_CLAUDE 给我配 ganren" / "我要加入 ganren 平台" 时，按这份文档一步步把他配好。
> 用户的目标：成为 ganren 协作者，能用自己的 CC 调 `ganren__*` 工具发布/认领/沟通任务。

---

## 你现在的位置

你正在用户**本机**的 Claude Code 会话里运行。用户刚 clone 了 ganren 仓库（或者只下载了几个文件），现在要请你帮他完成"成为 ganren 平台协作者"全过程。

**不要**自己起服务、自己装数据库、自己读 src/ 想自己实现。这个仓库的 `src/` 是平台代码，**管理员**在他的中心调度机上跑。你只是帮用户**连过去**。

---

## 入网四步（按顺序做，不要跳）

### Step 1 · 跟用户对话拿到三个信息

跟用户聊一下，问到这三件事：

| 问题 | 例子 | 用途 |
|---|---|---|
| 你的 actor handle（英文/数字/下划线）| `huangtang` | 你以后调任何 `ganren__*` 工具时 `actor=` 参数都用这个 |
| 显示名 | `黄唐` 或 `Huang Tang` | Slack 通知/报表上显示 |
| 管理员给你的 ganren 平台 URL | `http://192.168.22.56:8787/mcp/` | MCP 连接地址 |

**如果用户不知道 URL**：让他去管理员那里要。不要瞎猜（特别是不要用 `localhost:8787` —— 平台跑在管理员机器上，不在用户本机）。

### Step 2 · 跑配置脚本

在仓库根目录跑：

```bash
python tools/setup_client.py
```

这个脚本是**交互式**的，会问用户上面那三个问题。如果用户希望你（CC）代为输入答案，注意：

- 你需要用一个能向 stdin 喂数据的方式调用，例如 PowerShell 里用 echo 管道，bash 里用 here-doc
- 例（bash）：
  ```bash
  python tools/setup_client.py <<EOF
  huangtang
  黄唐
  http://192.168.22.56:8787/mcp/
  EOF
  ```

脚本会做这些事：
1. 检查 Claude Code CLI（`claude` 命令）是否存在
2. 测试网络联通（healthz + MCP endpoint 双探针，捕获 HTTP 421 这类 server 端配置问题）
3. 调 `claude mcp add --scope user --transport http ganren <URL>` 注册 MCP server
4. 在 `~/.claude/CLAUDE.md` 追加 actor 身份说明
5. 用 `claude mcp list` 验证配置生效
6. 输出"请管理员把我加进 actors 表"的指令

**重要的输出处理**：脚本结尾会打印一段框起来的指令，类似：

```
┌────────────────────────────────────────┐
│ 请把我加进 ganren actors 表，在仓库根目录跑：│
│                                            │
│ uv run python tools/add_actor.py           │
│   'huangtang' "黄唐"                       │
└────────────────────────────────────────┘
```

**你要把这条原样转告用户**，让他通过任何 IM/邮件发给管理员。说明：管理员收到后跑一下这条命令，才会真正把他加进 actors 表。

### Step 3 · 用户视角的关键告诫

跟用户清楚说明这两件事 —— 这是 V1 试用最容易踩的坑：

**告诫 A · 不要在 ganren 仓库目录里启动 Claude Code**

> 跑完 setup 后，请你 `cd ~` 或回到你自己的项目目录再启动 CC。
> 在 ganren 仓库目录里启 CC，CC 会看到周围的源码，可能误判为"要本地部署"而不去调远程 MCP。

**告诫 B · 重启 CC 让 MCP 配置生效**

setup_client.py 调了 `claude mcp add`，但**当前的 CC 会话**还没拿到新的 MCP 配置。让用户：

```bash
exit       # 退出当前 CC
cd ~       # 离开 ganren 仓库
claude     # 重新启动 CC
```

### Step 4 · 验证 + 第一次调用

在用户新启动的 CC 会话里，让他说：

> 用 ganren MCP 工具看下我的 inbox（actor 用 huangtang）

**"用 ganren MCP 工具"和"actor 用 X"这两句话很关键** —— 强化意图，防止 CC 瞎猜（试图本地读代码 / 用错 actor）。第一次会弹工具权限提示，选"允许"。

预期：返回空 inbox（`{questions_to_answer:[], reviews_pending:[], answers_received:[], rejections_to_address:[]}`）= 全通了。

---

## 排错决策树

如果某一步失败，按这个决策树排查：

### setup_client.py 在 Step 2「联通测试」失败

让脚本完整输出诊断（脚本会自动列原因）。最常见三类：

| 错误码 | 含义 | 行动 |
|---|---|---|
| connection refused | server 没起 | 找管理员，让他跑 `uv run python -m ganren_platform.main` |
| HTTP 421 | server 端 DNS rebinding 拦了 | 让管理员 `git pull && uv sync` 升级到 commit `eaeb2f5` 之后再重启 |
| timeout | 不在同一局域网 / 管理员防火墙没放 / 用户开了代理 | 三选一排查：1) 让管理员发自己的 LAN IP；2) 让管理员检查 8787 是否在 Windows Defender 的 Private profile 放行；3) 让用户检查 V2Ray/Clash 之类代理，把目标 IP 加进直连列表 |

### setup_client.py 报"找不到 claude 命令"

用户还没装 Claude Code。给他链接：<https://docs.claude.com/claude-code>。装完重跑 setup。

### Step 4 调 `ganren__inbox` 失败 (Error: tool not found / actor 错误)

按顺序排查：

1. `claude mcp list` 输出有没有 `ganren - http://...`？
   - 没有 → setup 没真生效，重跑 `python tools/setup_client.py`
2. 有 `ganren` 但 URL 是 localhost？
   - setup 时输错了，重跑改 URL
3. URL 对但 inbox 调用 `not found`？
   - 用户没重启 CC。退出 CC，cd 出仓库，再启动
4. inbox 返回 200 但是 `not_allowed` / `actor_not_found`？
   - 管理员还没加你 actor。让用户找管理员跑 add_actor.py 那条命令

---

## 用户后续可能问你的事

入网完毕后，用户可能跟你说这些 —— 你要直接调对应的工具：

| 用户说 | 你调 |
|---|---|
| "看下 ganren 池子有什么活" | `ganren__list_open_tasks` |
| "接 #t_01" | `ganren__claim_task` |
| "帮我问发布者 X" | `ganren__ask_question`（自动抽 ctx_summary ≤500B + ctx_full ≤4KB）|
| "看下我 ganren inbox" | `ganren__inbox` |
| "我干完了，提交 review" | `ganren__submit_for_review`（写清楚 summary："我做了什么/我决定了什么/还剩什么"）|
| "lgtm 通过" | `ganren__sign_off_task` |
| "打回让他改" | `ganren__reject_task`（reason + hints）|

**提示用户的注意事项**：

- 求助每次都被记一笔（events.questions），不扣分，但 IC 货币里**逐周减少 = 加分项**（"你在变自主"）。能查文档先查文档
- 被打回（reject）不扣个人分，rework_count 挂在任务上不挂在 actor 上
- 发布 hard / DRI 任务时会强制让你填 decision_record（选项/最终选择/估计成功概率/理由）—— 这是考核框架的"下注质量"要求

---

## 你（CC）要做的不要做的

- ✅ 帮用户跑 setup_client.py 并解析输出
- ✅ 帮用户把"请管理员加我"指令转给他复制
- ✅ 在排错时按上面决策树定位问题
- ✅ 用户后续真正用 ganren 时，直接调 `ganren__*` 工具
- ❌ 不要尝试本地起 server（这是远程平台）
- ❌ 不要去读 src/ganren_platform/ 想自己实现什么
- ❌ 不要在 ganren 仓库目录里劝用户长期工作 —— 提醒他离开

---

## 完成报告

入网完成后，跟用户说一句：

> ganren 配置完成。
> - actor: `huangtang`
> - MCP server: `ganren`（已加进 user-scope）
> - 待管理员把我加进 actors 表后即可使用
> - 跑完 setup 后请退出 CC，离开 ganren 仓库目录，重新启动 CC
> - 重启后说"用 ganren MCP 工具看下我的 inbox（actor 用 huangtang）"试连

然后等用户行动。
