# ganren-platform

中心调度协作平台：CC 发布者把任务推上来，CC 协作者认领、干活、提问、提交 review；events 表对接 AI-Native 考核仪表盘。

## 快速开始

```bash
uv sync --extra dev
cp .env.example .env       # 编辑配置
uv run python -m ganren_platform.main
```

服务监听 `0.0.0.0:8787`。

- HTTP REST：`/v1/*`
- MCP streamable HTTP：`/mcp/*`
- Health：`/healthz`

## CC 端配置

参考 `.mcp.json.example`，把这段加到你的 `.mcp.json`：

```json
{
  "mcpServers": {
    "ganren": {
      "type": "http",
      "url": "http://localhost:8787/mcp/"
    }
  }
}
```

## 测试

```bash
uv run pytest -v
```

## 使用手册

- **完整使用手册（架平台 / 配 CC / 日常协作 / 故障排查）**：[`docs/USAGE.md`](docs/USAGE.md)
- **产品演示动画**：浏览器打开 `product-demo.html`

## Spec & Plan

- Spec：`docs/superpowers/specs/2026-06-05-ganren-collab-platform-design.md`
- Plan：`docs/superpowers/plans/2026-06-05-ganren-collab-platform.md`

## V2 已落

详见 [`docs/V2_BACKLOG.md`](docs/V2_BACKLOG.md)。第一波已实施：

- **#4 定时 Slack 日报 + 池快照** · [设计](docs/superpowers/specs/2026-06-10-scheduled-slack-digest-design.md) · [实施计划](docs/superpowers/plans/2026-06-10-scheduled-slack-digest.md)
