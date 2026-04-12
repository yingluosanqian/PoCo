from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from getpass import getpass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from poco.config import DEFAULT_CONFIG_PATH, DEFAULT_RUNTIME_DIR, load_file_config


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
PID_PATH = Path(DEFAULT_RUNTIME_DIR) / "poco.pid"
LOG_PATH = Path(DEFAULT_RUNTIME_DIR) / "poco.log"


def _ensure_runtime_dir() -> None:
    Path(DEFAULT_RUNTIME_DIR).mkdir(parents=True, exist_ok=True)


def _config_path() -> Path:
    return Path(os.getenv("POCO_CONFIG_PATH", DEFAULT_CONFIG_PATH))


def _read_config() -> dict[str, object]:
    path = _config_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_config(data: dict[str, object]) -> None:
    _ensure_runtime_dir()
    path = _config_path()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _read_pid() -> int | None:
    if not PID_PATH.exists():
        return None
    try:
        return int(PID_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _clear_pid() -> None:
    try:
        PID_PATH.unlink()
    except FileNotFoundError:
        pass


def _write_pid(pid: int) -> None:
    _ensure_runtime_dir()
    PID_PATH.write_text(f"{pid}\n", encoding="utf-8")


def _mask(value: str | None) -> str:
    if not value:
        return "<not set>"
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}***{value[-2:]}"


def _prompt(label: str, current: str | None = None, *, secret: bool = False) -> str:
    suffix = ""
    if current:
        shown = _mask(current) if secret else current
        suffix = f" [{shown}]"
    prompt = f"{label}{suffix}: "
    value = getpass(prompt) if secret else input(prompt)
    value = value.strip()
    if value:
        return value
    return current or ""


def command_config(_: argparse.Namespace) -> int:
    current = _read_config()
    app_id = _prompt("Feishu App ID", str(current.get("POCO_FEISHU_APP_ID") or ""))
    app_secret = _prompt(
        "Feishu App Secret",
        str(current.get("POCO_FEISHU_APP_SECRET") or ""),
        secret=True,
    )
    data = current.copy()
    data["POCO_FEISHU_APP_ID"] = app_id
    data["POCO_FEISHU_APP_SECRET"] = app_secret
    _write_config(data)
    load_file_config.cache_clear()
    print(f"Saved config to {_config_path()}")
    return 0


def _server_command(host: str, port: int) -> list[str]:
    return [
        sys.executable,
        "-m",
        "uvicorn",
        "poco.main:app",
        "--host",
        host,
        "--port",
        str(port),
    ]


def _health_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/health"


def _fetch_health(host: str, port: int) -> dict[str, object] | None:
    try:
        with urlopen(_health_url(host, port), timeout=1.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def command_start(args: argparse.Namespace) -> int:
    existing = _read_pid()
    if existing and _is_running(existing):
        print(f"PoCo is already running (pid {existing}).")
        return 0
    if existing:
        _clear_pid()

    _ensure_runtime_dir()
    log_file = LOG_PATH.open("a", encoding="utf-8")
    process = subprocess.Popen(
        _server_command(args.host, args.port),
        cwd=Path(__file__).resolve().parents[1],
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log_file.close()
    _write_pid(process.pid)
    time.sleep(0.5)
    if process.poll() is not None:
        _clear_pid()
        print("PoCo failed to start. Check log:")
        print(LOG_PATH)
        return 1
    print(f"PoCo started in background (pid {process.pid}).")
    print(f"Log: {LOG_PATH}")
    return 0


def command_shutdown(_: argparse.Namespace) -> int:
    pid = _read_pid()
    if pid is None:
        print("PoCo is not running.")
        return 0
    if not _is_running(pid):
        _clear_pid()
        print("Removed stale pid file.")
        return 0
    os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 5
    while time.time() < deadline:
        if not _is_running(pid):
            _clear_pid()
            print("PoCo stopped.")
            return 0
        time.sleep(0.1)
    os.kill(pid, signal.SIGKILL)
    _clear_pid()
    print("PoCo stopped.")
    return 0


def command_restart(args: argparse.Namespace) -> int:
    command_shutdown(args)
    return command_start(args)


def command_status(args: argparse.Namespace) -> int:
    pid = _read_pid()
    config = _read_config()
    if pid is None:
        print("PoCo status: stopped")
        print(f"Config: {_config_path()}")
        print(f"Feishu App ID: {_mask(str(config.get('POCO_FEISHU_APP_ID') or ''))}")
        print("PID: <not running>")
        print(f"Log: {LOG_PATH}")
        return 0

    running = _is_running(pid)
    if not running:
        print("PoCo status: stale pid")
        print(f"Config: {_config_path()}")
        print(f"Feishu App ID: {_mask(str(config.get('POCO_FEISHU_APP_ID') or ''))}")
        print(f"PID: {pid} (not running)")
        print(f"Log: {LOG_PATH}")
        return 0

    print("PoCo status: running")
    print(f"Config: {_config_path()}")
    print(f"Feishu App ID: {_mask(str(config.get('POCO_FEISHU_APP_ID') or ''))}")
    print(f"PID: {pid}")
    print(f"Log: {LOG_PATH}")

    health = _fetch_health(args.host, args.port)
    if health is None:
        print(f"Health: unavailable at {_health_url(args.host, args.port)}")
        return 0

    print(
        "Health: "
        f"mode={health.get('mode')} "
        f"delivery={health.get('feishu_delivery_mode')} "
        f"listener_ready={health.get('feishu_listener_ready')} "
        f"agent={health.get('agent_backend')} "
        f"agent_ready={health.get('agent_ready')}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poco")
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_parser = subparsers.add_parser("config", help="Configure Feishu credentials.")
    config_parser.set_defaults(func=command_config)

    start_parser = subparsers.add_parser("start", help="Start PoCo in the background.")
    start_parser.add_argument("--host", default=DEFAULT_HOST)
    start_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    start_parser.set_defaults(func=command_start)

    shutdown_parser = subparsers.add_parser("shutdown", help="Stop the background PoCo process.")
    shutdown_parser.set_defaults(func=command_shutdown)

    status_parser = subparsers.add_parser("status", help="Show PoCo runtime status.")
    status_parser.add_argument("--host", default=DEFAULT_HOST)
    status_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    status_parser.set_defaults(func=command_status)

    restart_parser = subparsers.add_parser("restart", help="Restart the background PoCo process.")
    restart_parser.add_argument("--host", default=DEFAULT_HOST)
    restart_parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    restart_parser.set_defaults(func=command_restart)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
