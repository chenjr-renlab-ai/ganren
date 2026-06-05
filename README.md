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

## Spec & Plan

- Spec：`docs/superpowers/specs/2026-06-05-ganren-collab-platform-design.md`
- Plan：`docs/superpowers/plans/2026-06-05-ganren-collab-platform.md`
