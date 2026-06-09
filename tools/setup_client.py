#!/usr/bin/env python3
"""
ganren 客户端配置脚本 —— 队友本机跑一次。

做的事（按顺序）：
  1. 检查 Claude Code 是否已装
  2. 收集 actor handle / 显示名 / 平台 URL
  3. 联通测试（健康检查 + MCP endpoint）
  4. 把 ganren 加进 user-scope MCP 配置
  5. 在全局 ~/.claude/CLAUDE.md 追加 actor 身份说明
  6. 验证 `claude mcp list` 真的看到了 ganren
  7. 给出"请管理员把我加进 actors 表"指令 + 后续验证步骤

重复跑也安全 —— 已经配过的会被检测到并跳过；可以当诊断脚本用。

跨平台（Windows / macOS / Linux），纯 stdlib，无外部依赖。

用法：
  python setup_client.py
"""
from __future__ import annotations

import json
import os
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
def info(s: str) -> None: print(s)
def ok(s: str) -> None: print(f"  ✓ {s}")
def warn(s: str) -> None: print(f"  ⚠ {s}")
def err(s: str) -> None: print(f"  ✗ {s}", file=sys.stderr)


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


def _opener_no_proxy():
    """显式不走系统代理 —— V2Ray/Clash 等本地代理常拦局域网请求"""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def test_healthz(mcp_url: str) -> bool:
    """探一下 /healthz 看 server 是否活着"""
    url = health_url_from_mcp(mcp_url)
    info(f"\n  GET {url}")
    try:
        with _opener_no_proxy().open(url, timeout=5) as r:
            body = r.read().decode("utf-8", errors="replace").strip()
            if r.status == 200 and '"ok"' in body:
                ok(f"healthz: {body}")
                return True
            warn(f"healthz 非预期回应：HTTP {r.status} {body}")
            return False
    except urllib.error.URLError as e:
        err(f"healthz 联通失败：{e}")
        return False
    except Exception as e:
        err(f"healthz 未预期错误：{e}")
        return False


def test_mcp_endpoint(mcp_url: str) -> bool:
    """探一下 /mcp/ 本身 —— 捕获 DNS rebinding (HTTP 421) 这类 server 端配置问题"""
    info(f"\n  POST {mcp_url} (MCP initialize)")
    payload = json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "ganren-setup", "version": "1.0"},
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        mcp_url, data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        method="POST",
    )
    try:
        with _opener_no_proxy().open(req, timeout=5) as r:
            ok(f"MCP endpoint 返回 HTTP {r.status}")
            return True
    except urllib.error.HTTPError as e:
        # MCP 协议层面可能返回 4xx，但只要不是 421（DNS rebinding 拦截）就 OK
        if e.code == 421:
            err(f"HTTP 421 Misdirected Request")
            info("    → 管理员的 server 版本太老，开了 DNS rebinding 保护拦了局域网 IP")
            info("    → 让管理员拉最新代码（commit eaeb2f5 起已修）+ 重启 server")
            return False
        ok(f"MCP endpoint 返回 HTTP {e.code}（不是 421，证明 server 能接局域网请求）")
        return True
    except urllib.error.URLError as e:
        err(f"MCP endpoint 联通失败：{e}")
        return False
    except Exception as e:
        err(f"MCP endpoint 未预期错误：{e}")
        return False


def diagnose_failure(mcp_url: str) -> None:
    """联通失败时列可能原因"""
    info("\n  常见原因排查（按可能性排序）：")
    info("    1. URL 拼错（末尾应是 /mcp/，注意斜杠）")
    info("    2. 你和 server 不在同一局域网 / VPN")
    info("    3. 管理员的 server 没启动 / 已关机")
    info("    4. 管理员机器 Windows 防火墙没放行 8787")
    info("    5. 你装了 V2Ray/Clash 等代理软件，拦了局域网请求")
    # 检测当前 shell 是否有代理环境变量
    proxy_envs = [v for v in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY")
                  if os.environ.get(v)]
    if proxy_envs:
        warn(f"    检测到代理变量：{', '.join(proxy_envs)}")
        info("    → 临时绕过：把目标 IP 加进代理软件的「直连」名单")
        info("       或开新 shell 跑：unset http_proxy https_proxy && python setup_client.py")


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
        ok("ganren 已在 user-scope MCP 配置里（跳过）")
        return True

    err(f"claude mcp add 失败：{errout or out}")
    info("\n  如果你想改 URL，先删了再重跑此脚本：")
    info("    claude mcp remove ganren -s user")
    return False


def step_verify_mcp_list(claude_cli: str, expected_url: str) -> bool:
    """跑 claude mcp list 看 ganren 真的在里面 + URL 匹配"""
    info(f"\n  $ {claude_cli} mcp list")
    try:
        r = subprocess.run([claude_cli, "mcp", "list"], capture_output=True, text=True, timeout=10)
    except Exception as e:
        warn(f"调用 claude mcp list 失败：{e}（不致命，继续）")
        return True
    out = r.stdout or ""
    if "ganren" not in out.lower():
        err("claude mcp list 输出里看不到 ganren —— 配置可能没生效")
        return False
    if expected_url.rstrip("/") in out:
        ok(f"已确认 ganren 在 MCP servers 列表里，URL 匹配")
    else:
        warn(f"ganren 在列表里，但 URL 看起来跟你刚填的不一样")
        info("  list 输出：")
        for line in out.splitlines():
            if "ganren" in line.lower():
                info(f"    {line}")
        info(f"  你填的：{expected_url}")
    return True


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
            ok("已有 ganren 配置 section，跳过（要改 handle 请手动编辑此文件）")
            return True
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


def in_ganren_repo() -> bool:
    """检测当前 cwd 是否在 ganren 仓库里 —— 队友在仓库里启 CC 会让 CC 误以为要本地部署"""
    cwd = Path.cwd()
    return (cwd / "src" / "ganren_platform" / "main.py").exists()


def finish_message(handle: str, display: str) -> None:
    print()
    print("=" * 60)
    print(" 配置完成 🎉")
    print("=" * 60)
    print()
    print(" 接下来 3 步：")
    print()
    print(" ─── 步骤 1：让管理员把你加进 actors 表 ───")
    print()
    print("  把下面这条消息发给管理员（任何 IM 都行）：")
    print()
    print(" ┌" + "─" * 56 + "┐")
    print(f" │ 请把我加进 ganren actors 表，在仓库根目录跑：           │")
    print(" │                                                        │")
    print(f' │ uv run python tools/add_actor.py {handle!r} "{display}"'.ljust(57) + "│")
    print(" └" + "─" * 56 + "┘")
    print()
    print(" ─── 步骤 2：在「不是 ganren 仓库」的目录启 CC ───")
    print()
    print("  ⚠ 这一点很关键：如果你在 ganren 仓库目录里启动 Claude Code，")
    print("    CC 会看到周围的源码，误以为是要本地部署，不去调远程 MCP。")
    print()
    print("  正确做法：")
    print("    cd ~            # 或你自己的项目目录")
    print("    claude          # 启动 Claude Code")
    print()
    print(" ─── 步骤 3：在 CC 里明确说「用 ganren 工具」───")
    print()
    print("  跟 CC 说：")
    print()
    print(f"    用 ganren MCP 工具看下我的 inbox（actor 用 {handle}）")
    print()
    print("  「ganren MCP 工具」几个字很关键 —— 强化意图，防止 CC 瞎猜。")
    print("  第一次会弹工具权限确认，选「允许」。")
    print("  返回空 inbox（所有列表都是 []）= 全通了。")
    print()
    print(" ─── 出问题再跑一次这个脚本 ───")
    print()
    print(" 已配过的话脚本会跳过写入，只跑联通测试和验证 —— 可以当诊断器用。")
    print(" 完整手册：")
    print(" https://github.com/chenjr-renlab-ai/ganren/blob/main/docs/USAGE.md")
    print()


# ─── main ───
def main() -> int:
    banner("ganren 客户端配置")
    info(
        "\n 这个脚本会引导你完成连入 ganren 平台的全部配置 + 诊断。"
        "\n 已经配过的部分会被检测到并跳过 —— 重跑也安全。"
    )

    # 第 0 步：检查 claude CLI
    banner("第 0 步 · 检查 Claude Code")
    claude_cli = find_claude_cli()
    if not claude_cli:
        err("找不到 `claude` 命令")
        info("\n  你需要先装 Claude Code（这个工具基于 CC 的 MCP 协议工作）")
        info("  装完后重跑此脚本。")
        info("  https://docs.claude.com/claude-code")
        return 1
    ok(f"Claude Code CLI：{claude_cli}")
    if in_ganren_repo():
        warn("检测到你正在 ganren 仓库目录里跑这个脚本 —— 这没问题，")
        warn("但 setup 完成后启动 CC 时要 cd 出去（详见结尾的步骤 2）")

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

    # 第 2 步：联通测试（双探针：healthz + MCP endpoint）
    banner("第 2 步 · 联通测试")
    healthz_ok = test_healthz(url)
    mcp_ok = test_mcp_endpoint(url) if healthz_ok else False
    if not (healthz_ok and mcp_ok):
        diagnose_failure(url)
        cont = ask("\n  联通失败。仍要继续写本地配置吗？（y/N）", default="N")
        if cont.lower() != "y":
            info("\n  已退出。请先排错（或让管理员排），然后重跑此脚本。")
            return 1
        warn("强制继续（但 CC 实际调工具时会失败）")

    # 第 3 步：注册 MCP server
    banner("第 3 步 · 注册 MCP server")
    if not step_mcp_add(claude_cli, url):
        return 1

    # 第 4 步：登记 actor 身份
    banner("第 4 步 · 登记 actor 身份")
    if not step_claude_md(handle):
        return 1

    # 第 5 步：验证 MCP list 真的看到 ganren
    banner("第 5 步 · 验证 MCP 配置生效")
    step_verify_mcp_list(claude_cli, url)

    finish_message(handle, display)
    return 0


if __name__ == "__main__":
    sys.exit(main())
