#!/usr/bin/env python3
import argparse
import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from .bootstrap import run_feishu_bootstrap_cli
from .runtime import (
    PoCoService,
    RingLogHandler,
)
from .config import CONFIG_PATH, LOG_PATH, ConfigStore, ensure_dirs, get_nested
from .tui import PoCoTui


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PoCo")
    parser.add_argument("--log-level", default="INFO")
    sub = parser.add_subparsers(dest="command")
    config_cmd = sub.add_parser("config", help="open PoCo and focus config tab")
    config_cmd.add_argument("--show", action="store_true", help="show masked config and exit")
    config_cmd.add_argument("key", nargs="?", help="config key, e.g. app_id or feishu.app_id")
    config_cmd.add_argument("value", nargs="?", help="config value")
    sub.add_parser("feishu-bootstrap", help="configure a Feishu self-built app for PoCo")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, str(getattr(args, "log_level", "INFO")).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    ensure_dirs()
    root_logger = logging.getLogger()
    ring = RingLogHandler()
    ring.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger.addHandler(ring)
    file_handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=2_000_000,
        backupCount=3,
        encoding="utf-8",
        mode="w",
    )
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger.addHandler(file_handler)
    logging.getLogger("poco").info("Persistent log file enabled at %s", LOG_PATH)

    store = ConfigStore(CONFIG_PATH)
    service = PoCoService(store, ring)

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
    if args.command == "feishu-bootstrap":
        raise SystemExit(run_feishu_bootstrap_cli(store))

    app = PoCoTui(service, focus_config=args.command == "config")
    result = app.run()
    if result == "restart":
        os.execv(sys.executable, [sys.executable, *sys.argv])


if __name__ == "__main__":
    main()
