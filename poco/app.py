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
from .config import ConfigStore, bind_workspace, build_paths, ensure_dirs, get_nested, workspace_binding
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


def _env_flag(name: str) -> bool:
    value = os.getenv(name, "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _env_feishu_binding() -> tuple[str, str, str] | None:
    if not _env_flag("POCO_BIND_SKIP"):
        return None
    app_id = os.getenv("POCO_FEISHU_APP_ID", "").strip()
    app_secret = os.getenv("POCO_FEISHU_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        return None
    alias = os.getenv("POCO_FEISHU_ALIAS", "").strip()
    return app_id, app_secret, alias


def _apply_env_binding(workspace: Path, app_id: str, app_secret: str, alias: str) -> str:
    bind_workspace(workspace, app_id)
    paths = build_paths(app_id)
    ensure_dirs(paths)
    store = ConfigStore(paths.config_path, paths)
    config = store.load()
    feishu = config.setdefault("feishu", {})
    feishu["app_id"] = app_id
    feishu["app_secret"] = app_secret
    if alias:
        feishu["alias"] = alias
    store.save(config)
    return app_id


def main() -> None:
    args = parse_args()
    workspace = Path.cwd()
    env_binding = _env_feishu_binding()
    binding = workspace_binding(workspace)
    if env_binding is not None:
        binding = _apply_env_binding(workspace, *env_binding)
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, str(getattr(args, "log_level", "INFO")).upper(), logging.INFO))
    for handler in list(root_logger.handlers):
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            root_logger.removeHandler(handler)
    ring = RingLogHandler()
    ring.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger.addHandler(ring)
    file_handler: RotatingFileHandler | None = None

    def build_service_for(app_id: str | None) -> PoCoService:
        nonlocal file_handler
        paths = build_paths(app_id or "default")
        ensure_dirs(paths)
        if file_handler is not None:
            root_logger.removeHandler(file_handler)
            file_handler.close()
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
            app_id or "default",
        )
        store = ConfigStore(paths.config_path, paths)
        return PoCoService(store, ring, paths)

    service = build_service_for(binding)

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
    app = PoCoTui(
        service,
        service_factory=build_service_for,
        focus_config=args.command == "config",
        skip_bind_on_boot=env_binding is not None,
    )
    result = app.run()
    if result == "restart":
        os.execv(sys.executable, [sys.executable, *sys.argv])


if __name__ == "__main__":
    main()
