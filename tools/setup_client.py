#!/usr/bin/env python3
"""
ganren 客户端配置脚本 —— 队友本机跑一次。

做的事：
  1. 检查 Claude Code 是否已装
  2. 测试到 ganren 平台的网络联通
  3. 用 `claude mcp add` 把 ganren 加入 user-scope MCP 配置
  4. 在全局 ~/.claude/CLAUDE.md 追加一段 actor handle 说明
  5. 给出"请管理员把我加进 actors 表"的指令

跨平台（Windows / macOS / Linux），纯 stdlib，无外部依赖。

用法：
  python setup_client.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

HOME = Path.home()
CLAUDE_MD = HOME / ".claude" / "CLAUDE.md"

CLAUDE_MD_MARKER = "## ganren 平台"
CLAUDE_MD_SECTION = """
## ganren 平台

我在 ganren 平台上的 actor handle 是 `{handle}`。
当我调用任何 `ganren__*` 工具时，actor 参数都用 `{handle}`。
"""


# ─── ui helpers ───
def info(s: str) -> None:
    print(s)


def ok(s: str) -> None:
    print(f"  ✓ {s}")


def warn(s: str) -> None:
    print(f"  ⚠ {s}")


def err(s: str) -> None:
    print(f"  ✗ {s}", file=sys.stderr)


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    val = input(f"  {prompt}{suffix}: ").strip()
    return val or default


def banner(title: str) -> None:
    line = "─" * 60
    print()
    print(line)
    print(f" {title}")
    print(line)


# ─── checks ───
def find_claude_cli() -> str | None:
    for name in ("claude", "claude.cmd", "claude.exe"):
        path = shutil.which(name)
        if path:
            return path
    return None


def health_url_from_mcp(mcp_url: str) -> str:
    base = mcp_url.rstrip("/")
    if base.endswith("/mcp"):
        base = base[: -len("/mcp")]
    return base + "/healthz"


def test_connection(mcp_url: str) -> bool:
    health = health_url_from_mcp(mcp_url)
    info(f"\n  GET {health}")
    try:
        # 显式不走系统代理（很多人开 V2Ray/Clash，会把局域网请求转去代理）
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(health, timeout=5) as r:
            body = r.read().decode("utf-8", errors="replace").strip()
            if r.status == 200 and '"ok"' in body:
                ok(f"平台回应：{body}")
                return True
            warn(f"非预期回应：HTTP {r.status} {body}")
            return False
    except urllib.error.URLError as e:
        err(f"联通失败：{e}")
        info("\n  常见原因：")
        info("    1. URL 拼错（末尾应是 /mcp/）")
        info("    2. 管理员的 server 没启动")
        info("    3. 你跟 server 不在同一局域网 / VPN")
        info("    4. 管理员机器防火墙没放行 8787")
        info("    5. 你装了 V2Ray/Clash 等代理软件，把局域网 IP 也拦了")
        info("       → 把目标 IP 加进代理的「直连」名单")
        return False
    except Exception as e:
        err(f"未预期错误：{e}")
        return False


# ─── steps ───
def step_mcp_add(claude_cli: str, mcp_url: str) -> bool:
    cmd = [claude_cli, "mcp", "add", "--transport", "http",
           "--scope", "user", "ganren", mcp_url]
    info(f"\n  $ {' '.join(cmd)}")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except FileNotFoundError:
        err("找不到 claude 命令")
        return False
    except subprocess.TimeoutExpired:
        err("claude mcp add 超时")
        return False

    out = (r.stdout or "").strip()
    errout = (r.stderr or "").strip()
    if r.returncode == 0:
        ok(out or "已加入 user-scope MCP servers")
        return True

    msg = (errout or out).lower()
    if "already exists" in msg or "already configured" in msg:
        warn("ganren 已存在 user-scope MCP 配置")
        info("  如需变更 URL，手动跑：")
        info(f"    claude mcp remove ganren -s user")
        info("  再重跑此脚本。")
        return True

    err(f"claude mcp add 失败：{errout or out}")
    return False


def step_claude_md(handle: str) -> bool:
    CLAUDE_MD.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if CLAUDE_MD.exists():
        try:
            existing = CLAUDE_MD.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            err(f"读 CLAUDE.md 失败：{e}")
            return False
        if CLAUDE_MD_MARKER in existing:
            ok("已有 ganren 配置 section，跳过（如需修改请手动编辑此文件）")
            return True
        # 备份
        backup = CLAUDE_MD.with_name(
            f"CLAUDE.md.bak.{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )
        try:
            shutil.copy2(CLAUDE_MD, backup)
            ok(f"已备份到 {backup.name}")
        except Exception as e:
            warn(f"备份失败：{e}（继续）")

    section = CLAUDE_MD_SECTION.format(handle=handle)
    new_content = (existing.rstrip() + "\n" + section) if existing else section.lstrip()
    try:
        CLAUDE_MD.write_text(new_content, encoding="utf-8")
        ok(f"已写入 {CLAUDE_MD}")
        return True
    except Exception as e:
        err(f"写 CLAUDE.md 失败：{e}")
        return False


def finish_message(handle: str, display: str) -> None:
    print()
    print("=" * 60)
    print(" 配置完成 🎉")
    print("=" * 60)
    print()
    print(" 还差一步 —— 让平台管理员把你加进 actors 表。")
    print(" 把下面这条消息发给管理员（任何 IM 都行）：")
    print()
    print(" ┌" + "─" * 56 + "┐")
    print(f" │  请把我加进 ganren 平台 actors 表，在仓库根目录跑： │")
    print(" │                                                        │")
    print(f' │  uv run python tools/add_actor.py {handle!r} "{display}"'.ljust(57) + "│")
    print(" └" + "─" * 56 + "┘")
    print()
    print(" 管理员跑完后：")
    print()
    print("   1. 重启你的 Claude Code（让它重读 MCP 配置）")
    print("   2. 跟 CC 说：「看下我在 ganren 上的 inbox」")
    print("   3. 第一次会弹工具权限提示，确认即可")
    print("   4. 返回空 inbox = 全通了")
    print()
    print(" 之后日常对话脚本看：")
    print(" https://github.com/chenjr-renlab-ai/ganren/blob/main/docs/USAGE.md")
    print()


# ─── main ───
def main() -> int:
    banner("ganren 客户端配置")
    info(
        "\n 这个脚本会引导你完成 3 件事："
        "\n   1. 测试到 ganren 平台的网络联通"
        "\n   2. 把 ganren 加进 Claude Code 的 user-scope MCP 配置"
        "\n   3. 在全局 CLAUDE.md 登记你的 actor handle"
    )

    # 第 0 步：检查 claude CLI
    banner("第 0 步 · 检查 Claude Code")
    claude_cli = find_claude_cli()
    if not claude_cli:
        err("找不到 `claude` 命令")
        info("\n  你需要先装 Claude Code（这个工具是基于 CC 的 MCP 协议工作的）")
        info("  装完后重跑此脚本。")
        info("  https://docs.claude.com/claude-code")
        return 1
    ok(f"Claude Code CLI 位置：{claude_cli}")

    # 第 1 步：收集输入
    banner("第 1 步 · 基本信息")
    try:
        handle = ask("你的 actor handle（英文/数字/下划线，如 bob）")
        while not handle or not handle.replace("_", "").isalnum():
            warn("handle 必须是英文字母/数字/下划线，不能为空")
            handle = ask("你的 actor handle")
        display = ask("显示名（用于通知与报表）", default=handle.title())
        url = ask(
            "ganren 平台 MCP URL（管理员告诉你）",
            default="http://192.168.22.56:8787/mcp/",
        )
        if not url.endswith("/"):
            url += "/"
        if "/mcp" not in url:
            warn("URL 看起来不对，通常以 /mcp/ 结尾")
            cont = ask("继续吗？（y/N）", default="N")
            if cont.lower() != "y":
                return 1
    except (KeyboardInterrupt, EOFError):
        print("\n  已取消")
        return 1

    # 第 2 步：测试联通
    banner("第 2 步 · 联通测试")
    if not test_connection(url):
        cont = ask("\n  联通失败。仍要继续写本地配置吗？（y/N）", default="N")
        if cont.lower() != "y":
            info("\n  已退出。请先排错，然后重跑此脚本。")
            return 1
        warn("强制继续（但 CC 实际调工具时会失败）")

    # 第 3 步：claude mcp add
    banner("第 3 步 · 注册 MCP server")
    if not step_mcp_add(claude_cli, url):
        return 1

    # 第 4 步：CLAUDE.md
    banner("第 4 步 · 登记 actor 身份")
    if not step_claude_md(handle):
        return 1

    finish_message(handle, display)
    return 0


if __name__ == "__main__":
    sys.exit(main())
