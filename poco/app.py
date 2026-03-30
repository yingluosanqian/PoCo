#!/usr/bin/env python3
import argparse
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from .runtime import (
    PoCoService,
    RingLogHandler,
)
from .config import ConfigStore, build_paths, ensure_dirs, get_nested, workspace_binding
from .tui import PoCoTui


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PoCo")
    parser.add_argument("--log-level", default="INFO")
    sub = parser.add_subparsers(dest="command")
    config_cmd = sub.add_parser("config", help="open PoCo and focus config tab")
    config_cmd.add_argument("--show", action="store_true", help="show masked config and exit")
    config_cmd.add_argument("key", nargs="?", help="config key, e.g. app_id or feishu.app_id")
    config_cmd.add_argument("value", nargs="?", help="config value")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(getattr(args, "log_level", "INFO")).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    workspace = Path.cwd()
    binding = workspace_binding(workspace)
    paths = build_paths(binding or "default")
    ensure_dirs(paths)
    root_logger = logging.getLogger()
    ring = RingLogHandler()
    ring.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger.addHandler(ring)
    file_handler = RotatingFileHandler(
        paths.log_path,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
        mode="w",
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger.addHandler(file_handler)
    logging.getLogger("poco").info(
        "Persistent log file enabled at %s (instance=%s)",
        paths.log_path,
        binding or "default",
    )

    store = ConfigStore(paths.config_path, paths)
    service = PoCoService(store, ring, paths)

    if args.command == "config" and args.show:
        print(json.dumps(service.masked_config(), ensure_ascii=False, indent=2))
        return
    if args.command == "config" and args.key:
        if args.value is None:
            raise SystemExit("usage: poco config <key> <value>")
        path, _ = service.set_config_value(args.key, args.value)
        current = get_nested(service.masked_config(), path)
        print(json.dumps({path: current}, ensure_ascii=False, indent=2))
        return
    skip_bind_once = os.environ.pop("POCO_SKIP_BIND_ONCE", "") == "1"
    app = PoCoTui(service, focus_config=args.command == "config", skip_bind_once=skip_bind_once)
    result = app.run()
    if result == "restart-bound":
        os.environ["POCO_SKIP_BIND_ONCE"] = "1"
        os.execv(sys.executable, [sys.executable, *sys.argv])
    if result == "restart":
        os.execv(sys.executable, [sys.executable, *sys.argv])


if __name__ == "__main__":
    main()
