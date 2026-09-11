#!/usr/bin/env python3
"""One-command FoodArena launcher.

Starts the FastAPI backend and the Vite frontend together, opens the browser
and cleans both up on Ctrl+C.

Examples
--------
    python dev.py                # real provider (needs SILICONFLOW_API_KEY)
    python dev.py --mock         # deterministic offline provider
    python dev.py --no-browser   # don't auto-open the browser

Requirements: Python deps installed (`pip install -e ".[dev]"`) and, for the
frontend, `cd frontend && npm install` run at least once.
"""

from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / "Scripts" / "python.exe"
BACKEND_PORT = 8000
FRONTEND_PORT = 5173
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}/healthz"
FRONTEND_URL = f"http://localhost:{FRONTEND_PORT}"

# Marker used to decide whether the real SiliconFlow key is usable.
PLACEHOLDER_KEYS = {"", "replace-with-your-api-key"}


def _read_key() -> str:
    for path in (ROOT / ".env",):
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("SILICONFLOW_API_KEY="):
                return stripped.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _port_free(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def _wait_until(url: str, timeout: int = 30) -> bool:
    import urllib.request

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def _npm_command() -> list[str]:
    """npm is npm.cmd on Windows; bare 'npm' raises FileNotFoundError."""
    return ["npm.cmd"] if os.name == "nt" else ["npm"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mock",
        action="store_true",
        help="use the deterministic offline provider instead of the real model",
    )
    parser.add_argument(
        "--no-browser", action="store_true", help="do not open the browser"
    )
    args = parser.parse_args(argv)

    provider = "mock" if args.mock else "real"
    if provider == "real" and _read_key() in PLACEHOLDER_KEYS:
        print("⚠️  未检测到有效的 SILICONFLOW_API_KEY，已回退到 mock 离线模式。")
        print("   要使用真实模型：把 Key 填入 .env 后重试，或 python dev.py --mock")
        provider = "mock"

    if not VENV_PY.exists():
        print(f"❌ 找不到虚拟环境 Python：{VENV_PY}")
        print(
            "   请先运行：python -m venv .venv && "
            '.venv/Scripts/python -m pip install -e ".[dev]"'
        )
        return 1
    if not (ROOT / "frontend" / "node_modules").exists():
        print("❌ 前端依赖未安装。请先运行：cd frontend && npm install")
        return 1

    for port, name in ((BACKEND_PORT, "后端"), (FRONTEND_PORT, "前端")):
        if not _port_free(port):
            print(f"❌ 端口 {port} 已被占用（{name}）。请先停止占用该端口的进程。")
            return 1

    env = os.environ.copy()
    env["FOODARENA_PROVIDER"] = provider

    backend = subprocess.Popen(
        [
            str(VENV_PY),
            "-m",
            "uvicorn",
            "foodarena_ai.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(BACKEND_PORT),
        ],
        cwd=ROOT,
        env=env,
    )
    frontend = subprocess.Popen(
        [*_npm_command(), "run", "dev", "--", "--host", "127.0.0.1"],
        cwd=ROOT / "frontend",
        env=env,
    )

    def shutdown(_signum=None, _frame=None) -> None:
        print("\n正在停止服务…")
        backend.terminate()
        frontend.terminate()
        try:
            backend.wait(timeout=5)
            frontend.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend.kill()
            frontend.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"▶  提供方：{provider}")
    print(f"▶  后端: http://127.0.0.1:{BACKEND_PORT}/docs")
    print(f"▶  前端: {FRONTEND_URL}")
    print("▶  按 Ctrl+C 同时停止前后端。\n")

    backend_ok = _wait_until(BACKEND_URL)
    frontend_ok = _wait_until(FRONTEND_URL)

    if backend_ok and frontend_ok:
        print("✔ 后端与前端均已就绪。")
        if not args.no_browser:
            webbrowser.open(FRONTEND_URL)
    else:
        print("⚠️  服务启动超时。请查看上方日志；按 Ctrl+C 退出。")
        if not backend_ok:
            print(f"   - 后端健康检查失败: {BACKEND_URL}")
        if not frontend_ok:
            print(f"   - 前端未就绪: {FRONTEND_URL}")

    while True:
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main())
