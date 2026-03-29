import json
import shlex
import time
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.widgets import Input, Static

from .. import __version__
from ..config import config_ready

POCO_ICON = """
 .-.
(###)
 '-'
""".strip("\n")

TUI_COMMANDS = [
    "/help",
    "/config",
    "/log",
    "/restart",
    "/quit",
]

CONFIG_SUBCOMMANDS = [
    "/config",
    "/config show",
]

COMMAND_ALIASES = {
    "/config": "/c",
    "/help": "/h",
    "/log": "/l",
    "/restart": "/r",
    "/quit": "/q",
}

CONFIG_MENU_OPTIONS = ["language", "feishu", "codex", "bridge"]
FEISHU_WIZARD_STEPS = [
    ("feishu.app_id", "Enter Feishu Bot App ID", "请输入 Feishu Bot App ID"),
    ("feishu.app_secret", "Enter Feishu Bot App Secret", "请输入 Feishu Bot App Secret"),
]
LANGUAGE_CHOICES = [("English", "en"), ("中文", "zh")]

STRINGS = {
    "app_title": {"en": "Pocket Coding for Feishu", "zh": "Feishu 口袋编程"},
    "dashboard": {"en": "Dashboard", "zh": "仪表盘"},
    "settings": {"en": "Config", "zh": "配置"},
    "language": {"en": "Language", "zh": "语言"},
    "logs": {"en": "Logs", "zh": "日志"},
    "help": {"en": "Help", "zh": "帮助"},
    "bridge": {"en": "Bridge", "zh": "桥接"},
    "running": {"en": "RUNNING", "zh": "运行中"},
    "stopped": {"en": "STOPPED", "zh": "已停止"},
    "ready": {"en": "READY", "zh": "已就绪"},
    "needs_config": {"en": "NEEDS CONFIG", "zh": "需要配置"},
    "current_dir": {"en": "Current dir", "zh": "当前目录"},
    "tips": {"en": "Tips for getting started", "zh": "开始使用提示"},
    "recent_activity": {"en": "Recent activity", "zh": "最近活动"},
    "runtime": {"en": "Runtime", "zh": "运行时"},
    "started_at": {"en": "started_at", "zh": "启动时间"},
    "last_error": {"en": "last_error", "zh": "最近错误"},
    "no_recent_activity": {"en": "No recent activity", "zh": "暂无最近活动"},
    "latest_logs": {"en": "Latest logs", "zh": "最新日志"},
    "no_logs": {"en": "No logs yet", "zh": "暂无日志"},
    "current_config": {"en": "Current config", "zh": "当前配置"},
    "commands": {"en": "Commands", "zh": "命令"},
    "help_body": {
        "en": "/help  (/h for short)\n/config  (/c for short)\n/log  (/l for short)\n/restart  (/r for short)\n/quit  (/q for short)",
        "zh": "/help  （/h 为缩写）\n/config  （/c 为缩写）\n/log  （/l 为缩写）\n/restart  （/r 为缩写）\n/quit  （/q 为缩写）",
    },
    "tip_help": {
        "en": "Use /help to show help. /h is the short form.",
        "zh": "使用 /help 查看帮助，/h 是缩写。",
    },
    "tip_config": {
        "en": "Use /config to enter config mode. /c is the short form.",
        "zh": "使用 /config 进入配置模式，/c 是缩写。",
    },
    "tip_quit": {
        "en": "Use /quit to exit. /q is the short form.",
        "zh": "使用 /quit 退出，/q 是缩写。",
    },
    "tip_restart": {
        "en": "Use /restart to restart. /r is the short form.",
        "zh": "使用 /restart 重启，/r 是缩写。",
    },
    "tip_logs": {
        "en": "Use /log to inspect recent runtime logs. /l is the short form.",
        "zh": "使用 /log 查看最近运行日志，/l 是缩写。",
    },
    "tip_config_show": {
        "en": "After typing /config, slash suggestions will show /config show.",
        "zh": "输入 /config 后，命令提示里会出现 /config show。",
    },
    "config_mode": {"en": "Config mode", "zh": "配置模式"},
    "pick_section": {"en": "Select a config section", "zh": "选择配置分类"},
    "pick_section_help": {
        "en": "Use ↑/↓ to move. Press Enter to continue. Type /quit (/q) to leave config mode.",
        "zh": "使用 ↑/↓ 选择，按回车继续；输入 /quit（或 /q）退出配置模式。",
    },
    "section": {"en": "Section", "zh": "当前分类"},
    "select_action": {"en": "Select an action", "zh": "选择动作"},
    "type_value": {
        "en": "Type the new value in the command line and press Enter.",
        "zh": "请在命令行输入新值并按回车。",
    },
    "collected_values": {"en": "Collected values", "zh": "已收集的值"},
    "new": {"en": "New", "zh": "新值"},
    "do_not_change": {"en": "Do not change ({current})", "zh": "不修改（{current}）"},
    "current_secret": {"en": "current secret", "zh": "当前密钥"},
    "empty": {"en": "empty", "zh": "空"},
    "unknown_interactive": {
        "en": "{section} interactive setup is not implemented yet. Select language or feishu, or type /quit.",
        "zh": "{section} 的交互式设置还没实现。请先选择 language 或 feishu，或输入 /quit。",
    },
    "config_placeholder": {
        "en": "",
        "zh": "",
    },
    "config_mode_placeholder": {
        "en": "Press Enter to select current section, or type /quit (/q)",
        "zh": "按回车进入当前分类，或输入 /quit（/q）",
    },
    "choice_placeholder": {
        "en": "Press Enter to confirm selection, or type /quit (/q)",
        "zh": "按回车确认选项，或输入 /quit（/q）",
    },
    "input_placeholder": {
        "en": "Enter new value and press Enter, or type /quit (/q)",
        "zh": "输入新值后按回车，或输入 /quit（/q）",
    },
    "config_required": {
        "en": "Config is incomplete. Enter /quit (/q) to leave config mode, then use /config to finish the setup.",
        "zh": "配置还不完整。先输入 /quit（或 /q）退出配置模式，再用 /config 完成配置。",
    },
    "bridge_started": {"en": "PoCo bridge is running.", "zh": "PoCo bridge 已启动。"},
    "bridge_already_running": {"en": "PoCo bridge is already running.", "zh": "PoCo bridge 已经在运行。"},
    "left_config": {"en": "Left config mode.", "zh": "已退出配置模式。"},
    "config_only_quit": {
        "en": "Config mode only accepts /quit (/q) here, or Enter to continue.",
        "zh": "当前处于配置模式，这里只接受 /quit（或 /q），或者直接按回车继续。",
    },
    "press_enter_choice": {
        "en": "Press Enter to confirm the current choice, or type /quit (/q) to leave.",
        "zh": "请直接按回车确认当前选项，或输入 /quit（或 /q）退出。",
    },
    "enter_value_or_quit": {
        "en": "Enter a value for the current field, or type /quit (/q) to leave config mode.",
        "zh": "请输入当前字段的值，或输入 /quit（或 /q）退出配置模式。",
    },
    "start_feishu": {
        "en": "Starting Feishu setup. First choose how to handle App ID.",
        "zh": "开始配置 Feishu。先选择 App ID 的处理方式。",
    },
    "start_language": {
        "en": "Starting language setup. Choose a language.",
        "zh": "开始配置语言。请选择一种语言。",
    },
    "language_done": {
        "en": "Language updated. It takes effect immediately.",
        "zh": "语言已更新，立即生效。",
    },
    "feishu_done": {
        "en": "Feishu config saved. Restart is required before it takes effect.",
        "zh": "Feishu 配置完成，但需要重启后才能生效。",
    },
    "next_choose": {
        "en": "{prompt}. Choose New or Do not change first.",
        "zh": "{prompt}。先选择 New 或 Do not change。",
    },
    "show_refreshed": {"en": "Current config refreshed.", "zh": "当前配置已刷新。"},
    "show_scroll": {"en": "Use ↑ / ↓ to scroll.", "zh": "使用 ↑ / ↓ 滚动。"},
    "commands_list": {
        "en": "Available commands: /help (/h) /config (/c) /log (/l) /restart (/r) /quit (/q)",
        "zh": "可用命令：/help（/h） /config（/c） /log（/l） /restart（/r） /quit（/q）",
    },
    "help_message": {
        "en": "Use /help (/h) /config (/c) /log (/l) /restart (/r) /quit (/q)",
        "zh": "输入 /help（/h） /config（/c） /log（/l） /restart（/r） /quit（/q）",
    },
    "unknown_command": {
        "en": "Unknown command. Use /help to see available commands.",
        "zh": "未知命令。输入 /help 查看可用命令。",
    },
    "slash_required": {
        "en": "TUI commands must start with /. Use /help to see available commands.",
        "zh": "TUI 命令需要以 / 开头。输入 /help 查看可用命令。",
    },
    "config_pick": {
        "en": "Choose a section with ↑/↓, press Enter to enter, type /quit (/q) to leave config mode.",
        "zh": "请用 ↑/↓ 选择分类，按回车进入；输入 /quit（或 /q）退出配置模式。",
    },
    "scroll_status": {
        "en": "lines {start}-{end} / {total}",
        "zh": "行 {start}-{end} / {total}",
    },
    "back_dashboard": {
        "en": "Back to dashboard.",
        "zh": "已回到 dashboard。",
    },
}


class PoCoTui(App[None]):
    CSS = """
    Screen {
        layout: vertical;
        background: #0f1117;
        color: #e6edf3;
    }

    #main_panel {
        height: 1fr;
        padding: 1 1 0 1;
    }

    .card {
        border: round #f97316;
        background: #161b22;
        color: #e6edf3;
        padding: 1 2;
    }

    #left_card {
        width: 30;
        margin-right: 1;
    }

    #right_card {
        width: 1fr;
    }

    #left_text, #right_text {
        width: 100%;
        height: 100%;
    }

    #command_panel {
        height: auto;
        padding: 1;
    }

    #command_input {
        border: round #f97316;
        background: #0d1117;
        color: #e6edf3;
    }

    #command_suggestions {
        height: auto;
        padding: 0 1 1 1;
        color: #fdba74;
        border: round #fb923c;
        background: #161b22;
        margin-top: 1;
    }

    #command_suggestions.hidden {
        display: none;
    }

    #message_line {
        height: auto;
        padding: 0 1 1 1;
        color: #fb923c;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("up", "cursor_up", "Up"),
        Binding("down", "cursor_down", "Down"),
        Binding("tab", "complete_command", "Complete"),
        Binding("ctrl+r", "save_and_restart", "Save & Restart"),
    ]

    def __init__(self, service, *, focus_config: bool = False) -> None:
        super().__init__()
        self._service = service
        self._focus_config = focus_config
        self._view = "dashboard"
        self._current_suggestions: list[str] = []
        self._selected_suggestion = 0
        self._config_menu_active = False
        self._config_selected = 0
        self._config_flow: dict | None = None
        self._show_scroll = 0

    def _lang(self) -> str:
        config = self._service.load_config()
        lang = config.get("ui", {}).get("language", "en")
        return "zh" if lang == "zh" else "en"

    def _t(self, key: str, **kwargs) -> str:
        lang = self._lang()
        template = STRINGS[key][lang]
        return template.format(**kwargs)

    @staticmethod
    def _lookup_nested(config: dict, path: str) -> str:
        value = config
        for part in path.split("."):
            if not isinstance(value, dict):
                return ""
            value = value.get(part, "")
        return str(value or "")

    def compose(self) -> ComposeResult:
        with Horizontal(id="main_panel"):
            with Container(id="left_card", classes="card"):
                yield Static("", id="left_text")
            with Container(id="right_card", classes="card"):
                yield Static("", id="right_text")
        with Container(id="command_panel"):
            yield Input(id="command_input", placeholder=self._t("config_placeholder"))
            yield Static("", id="command_suggestions", classes="hidden")
        yield Static("", id="message_line")

    def on_mount(self) -> None:
        self.title = "PoCo"
        self.sub_title = self._t("app_title")
        self._refresh_runtime()
        self.set_interval(1.0, self._refresh_runtime)
        self.call_after_refresh(self._boot)

    def _boot(self) -> None:
        config = self._service.load_config()
        self.query_one("#command_input", Input).placeholder = self._t("config_placeholder")
        if self._focus_config or not config_ready(config):
            self._enter_config_mode()
            self._set_message(self._t("config_required"))
            self.query_one("#command_input", Input).focus()
            return
        self._service.start_bridge()
        self._set_message(self._t("bridge_started"))
        self.query_one("#command_input", Input).focus()

    def _refresh_runtime(self) -> None:
        config = self._service.load_config()
        bridge = self._service.bridge_status()
        self.sub_title = self._t("app_title")
        self.query_one("#left_text", Static).update(self._left_panel_text(config, bridge))
        self.query_one("#right_text", Static).update(self._right_panel_text(config, bridge))

    def _left_panel_text(self, config: dict, bridge: dict) -> str:
        bridge_status = self._t("running") if bridge["running"] else self._t("stopped")
        bridge_style = "#3fb950" if bridge["running"] else "#f85149"
        config_status = self._t("ready") if config_ready(config) else self._t("needs_config")
        config_style = "#3fb950" if config_ready(config) else "#f2cc60"
        view_name = self._current_view_name()
        return (
            f"[bold #fb923c]{POCO_ICON}[/]\n"
            f"[bold #fb923c]PoCo v{__version__}[/]\n"
            f"{view_name}\n\n"
            f"{self._t('bridge')}: [bold {bridge_style}]{bridge_status}[/]\n"
            f"{self._t('settings')}: [bold {config_style}]{config_status}[/]\n"
            f"[#8b949e]{self._t('current_dir')}[/]\n"
            f"[#8b949e]{Path.cwd()}[/]"
        )

    def _right_panel_text(self, config: dict, bridge: dict) -> str:
        if self._config_menu_active:
            if self._config_flow is not None:
                return self._config_flow_text(config)
            return self._config_menu_text(config)
        if self._view == "logs":
            return self._logs_text()
        if self._view == "show":
            return self._show_text()
        if self._view == "help":
            return f"[bold #fb923c]{self._t('commands')}[/]\n\n{self._t('help_body')}"
        recent = self._recent_activity_text()
        started_at = bridge["started_at"]
        started_display = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(started_at)) if started_at else "-"
        return (
            f"[bold #fb923c]{self._t('tips')}[/]\n"
            f"[#8b949e]{self._t('tip_help')}[/]\n"
            f"[#8b949e]{self._t('tip_config')}[/]\n"
            f"[#8b949e]{self._t('tip_logs')}[/]\n"
            f"[#8b949e]{self._t('tip_restart')}[/]\n"
            f"[#8b949e]{self._t('tip_config_show')}[/]\n"
            f"[#8b949e]{self._t('tip_quit')}[/]\n\n"
            f"[bold #fb923c]{self._t('recent_activity')}[/]\n"
            f"{recent}\n\n"
            f"[bold #fb923c]{self._t('runtime')}[/]\n"
            f"{self._t('started_at')}: {started_display}\n"
            f"{self._t('last_error')}: {bridge['last_error'] or '-'}"
        )

    def _config_menu_text(self, config: dict) -> str:
        section = CONFIG_MENU_OPTIONS[self._config_selected]
        if section == "language":
            current_body = json.dumps(
                {"language": self._language_label(config.get("ui", {}).get("language", "en"))},
                ensure_ascii=False,
                indent=2,
            )
        else:
            current_body = json.dumps(config.get(section, {}), ensure_ascii=False, indent=2)
        lines = [
            f"[bold #fb923c]{self._t('config_mode')}[/]",
            f"[#8b949e]{self._t('pick_section_help')}[/]",
            "",
            f"[bold #fb923c]{self._t('pick_section')}[/]",
        ]
        for index, option in enumerate(CONFIG_MENU_OPTIONS):
            label = self._setting_option_label(option)
            if index == self._config_selected:
                lines.append(f"[bold #0f1117 on #fb923c]  {label}  [/]")
            else:
                lines.append(f"  {label}")
        lines.extend(["", f"[bold #fb923c]{self._t('section')}: {self._setting_option_label(section)}[/]", current_body])
        return "\n".join(lines)

    def _config_flow_text(self, config: dict) -> str:
        assert self._config_flow is not None
        section = self._config_flow["section"]
        step_index = self._config_flow["step_index"]
        step_key, prompt_en, prompt_zh = self._config_flow["steps"][step_index]
        prompt = prompt_zh if self._lang() == "zh" else prompt_en
        collected = self._config_flow["values"]
        phase = self._config_flow["phase"]
        masked = {}
        for key, value in collected.items():
            masked[key] = "*" * max(8, len(value)) if "secret" in key else value
        lines = [
            f"[bold #fb923c]{self._t('config_mode')}[/]",
            f"[#8b949e]{self._t('section')}: {self._setting_option_label(section)}. /quit[/]",
            "",
            f"[bold #fb923c]{prompt}[/]",
            f"[#8b949e]{step_key}[/]",
        ]
        if phase == "choice":
            lines.extend(["", f"[bold #fb923c]{self._t('select_action')}[/]"])
            for index, choice in enumerate(self._flow_choices_for_step(config)):
                if index == self._config_flow["selected_choice"]:
                    lines.append(f"[bold #0f1117 on #fb923c]  {choice}  [/]")
                else:
                    lines.append(f"  {choice}")
        else:
            lines.extend(["", f"[#8b949e]{self._t('type_value')}[/]"])
        if masked:
            lines.extend(["", f"[bold #fb923c]{self._t('collected_values')}[/]", json.dumps(masked, ensure_ascii=False, indent=2)])
        return "\n".join(lines)

    def _logs_text(self) -> str:
        items = self._service.logs.snapshot(limit=12)
        if not items:
            return f"[bold #fb923c]{self._t('logs')}[/]\n\n[#8b949e]{self._t('no_logs')}[/]"
        lines = [f"[bold #fb923c]{self._t('latest_logs')}[/]", ""]
        for item in items:
            lines.append(item["message"])
        return "\n".join(lines)

    def _recent_activity_text(self) -> str:
        items = self._service.logs.snapshot(limit=3)
        if not items:
            return f"[#8b949e]{self._t('no_recent_activity')}[/]"
        return "\n".join(f"[#8b949e]- {item['message'][-90:]}[/]" for item in items[-3:])

    def _show_lines(self) -> list[str]:
        config_text = json.dumps(self._service.masked_config(), ensure_ascii=False, indent=2)
        return [self._t("current_config"), ""] + config_text.splitlines()

    def _show_window_height(self) -> int:
        try:
            height = self.query_one("#right_card", Container).size.height
        except Exception:
            height = 0
        return max(8, height - 4 if height else 18)

    def _show_max_scroll(self) -> int:
        lines = self._show_lines()
        return max(0, len(lines) - self._show_window_height())

    def _show_text(self) -> str:
        lines = self._show_lines()
        max_scroll = self._show_max_scroll()
        self._show_scroll = max(0, min(self._show_scroll, max_scroll))
        start = self._show_scroll
        end = min(len(lines), start + self._show_window_height())
        visible = lines[start:end]
        rendered = []
        for index, line in enumerate(visible):
            if start + index == 0:
                rendered.append(f"[bold #fb923c]{line}[/]")
            else:
                rendered.append(line)
        status = self._t("scroll_status", start=start + 1 if lines else 0, end=end, total=len(lines))
        rendered.extend(["", f"[#8b949e]{self._t('show_scroll')}[/]", f"[#8b949e]{status}[/]"])
        return "\n".join(rendered)

    def _current_view_name(self) -> str:
        if self._config_menu_active:
            return self._t("settings")
        if self._view == "logs":
            return self._t("logs")
        if self._view == "help":
            return self._t("help")
        if self._view == "show":
            return self._t("current_config")
        return self._t("dashboard")

    def _setting_option_label(self, option: str) -> str:
        labels = {
            "language": self._t("language"),
            "feishu": "feishu",
            "codex": "codex",
            "bridge": "bridge",
        }
        return labels.get(option, option)

    def _language_label(self, code: str) -> str:
        return "中文" if code == "zh" else "English"

    def action_save_and_restart(self) -> None:
        self.exit("restart")

    def action_cursor_up(self) -> None:
        if self._config_menu_active:
            if self._config_flow is not None and self._config_flow["phase"] == "choice":
                choices = self._flow_choices_for_step(self._service.load_config())
                self._config_flow["selected_choice"] = (self._config_flow["selected_choice"] - 1) % len(choices)
                self._refresh_runtime()
                return
            self._config_selected = (self._config_selected - 1) % len(CONFIG_MENU_OPTIONS)
            self._refresh_runtime()
            return
        if self._view == "show" and not self._current_suggestions:
            self._show_scroll = max(0, self._show_scroll - 1)
            self._refresh_runtime()
            return
        input_widget = self.query_one("#command_input", Input)
        if not input_widget.has_focus or not self._current_suggestions:
            return
        self._selected_suggestion = (self._selected_suggestion - 1) % len(self._current_suggestions)
        self._render_suggestions()

    def action_cursor_down(self) -> None:
        if self._config_menu_active:
            if self._config_flow is not None and self._config_flow["phase"] == "choice":
                choices = self._flow_choices_for_step(self._service.load_config())
                self._config_flow["selected_choice"] = (self._config_flow["selected_choice"] + 1) % len(choices)
                self._refresh_runtime()
                return
            self._config_selected = (self._config_selected + 1) % len(CONFIG_MENU_OPTIONS)
            self._refresh_runtime()
            return
        if self._view == "show" and not self._current_suggestions:
            self._show_scroll = min(self._show_max_scroll(), self._show_scroll + 1)
            self._refresh_runtime()
            return
        input_widget = self.query_one("#command_input", Input)
        if not input_widget.has_focus or not self._current_suggestions:
            return
        self._selected_suggestion = (self._selected_suggestion + 1) % len(self._current_suggestions)
        self._render_suggestions()

    def action_complete_command(self) -> None:
        if self._config_menu_active:
            return
        input_widget = self.query_one("#command_input", Input)
        if not input_widget.has_focus or not self._current_suggestions:
            return
        current = input_widget.value.strip()
        selected = self._current_suggestions[self._selected_suggestion]
        if not selected.startswith(current):
            return
        input_widget.value = selected + " "
        input_widget.cursor_position = len(input_widget.value)
        self._update_suggestions(input_widget.value.strip())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "command_input":
            return
        raw_command = event.value
        command = raw_command.strip()
        direct_aliases = {"/c", "/h", "/l", "/q", "/r"}
        if self._config_menu_active:
            event.input.value = ""
            self._hide_suggestions()
            if command in {"/q", "/quit", "/exit"}:
                self._exit_config_mode()
                self._set_message(self._t("left_config"))
                self._refresh_runtime()
                return
            if self._config_flow is None:
                if command:
                    self._set_message(self._t("config_only_quit"))
                else:
                    self._start_config_flow()
                return
            if self._config_flow["phase"] == "choice":
                if command:
                    self._set_message(self._t("press_enter_choice"))
                else:
                    self._accept_config_choice()
                return
            if not command:
                self._set_message(self._t("enter_value_or_quit"))
            else:
                self._advance_config_flow(command)
            return
        if (
            self._current_suggestions
            and command.startswith("/")
            and command not in direct_aliases
            and not raw_command.endswith(" ")
            and self._current_suggestions[self._selected_suggestion].startswith(command)
        ):
            selected = self._current_suggestions[self._selected_suggestion]
            event.input.value = selected + " "
            event.input.cursor_position = len(event.input.value)
            self._update_suggestions(event.input.value.strip())
            return
        event.input.value = ""
        self._hide_suggestions()
        if not command:
            return
        try:
            self._run_command(command)
        except ValueError as exc:
            self._set_message(str(exc))

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "command_input":
            return
        self._update_suggestions(event.value.strip())

    def _matching_commands(self, value: str) -> list[str]:
        if self._config_menu_active:
            if value.startswith("/q") or value == "/":
                return ["/quit"]
            return []
        if not value.startswith("/"):
            return []
        if value == "/":
            return TUI_COMMANDS
        if value.startswith("/c"):
            return ["/config"]
        if value.startswith("/h"):
            return ["/help"]
        if value.startswith("/l"):
            return ["/log"]
        if value.startswith("/q"):
            return ["/quit"]
        if value.startswith("/r"):
            return ["/restart"]
        if value == "/config" or value.startswith("/config "):
            return [command for command in CONFIG_SUBCOMMANDS if command.startswith(value)]
        prefix = value.split(" ", 1)[0]
        return [command for command in TUI_COMMANDS if command.startswith(prefix)]

    def _update_suggestions(self, value: str) -> None:
        suggestions = self._matching_commands(value)
        current_selected = None
        if self._current_suggestions and 0 <= self._selected_suggestion < len(self._current_suggestions):
            current_selected = self._current_suggestions[self._selected_suggestion]
        self._current_suggestions = suggestions
        if not suggestions:
            self._hide_suggestions()
            return
        self._selected_suggestion = suggestions.index(current_selected) if current_selected in suggestions else 0
        self._render_suggestions()

    def _render_suggestions(self) -> None:
        widget = self.query_one("#command_suggestions", Static)
        visible = self._current_suggestions[:6]
        selected = min(self._selected_suggestion, len(visible) - 1)
        lines = []
        for index, command in enumerate(visible):
            alias = COMMAND_ALIASES.get(command)
            display = f"{command}    ({alias})" if alias else command
            if index == selected:
                lines.append(f"[bold #0f1117 on #fb923c]  {display}  [/]")
            else:
                lines.append(f"  {display}")
        widget.update("\n".join(lines))
        widget.remove_class("hidden")

    def _hide_suggestions(self) -> None:
        self._current_suggestions = []
        self._selected_suggestion = 0
        widget = self.query_one("#command_suggestions", Static)
        widget.update("")
        widget.add_class("hidden")

    def _enter_config_mode(self) -> None:
        self._config_menu_active = True
        self._config_selected = 0
        self._config_flow = None
        self.query_one("#command_input", Input).placeholder = self._t("config_mode_placeholder")
        self._hide_suggestions()
        self._refresh_runtime()

    def _exit_config_mode(self) -> None:
        self._config_menu_active = False
        self._config_flow = None
        self._view = "dashboard"
        self.query_one("#command_input", Input).placeholder = self._t("config_placeholder")
        self._hide_suggestions()

    def _start_config_flow(self) -> None:
        section = CONFIG_MENU_OPTIONS[self._config_selected]
        if section == "language":
            self._config_flow = {
                "section": "language",
                "step_index": 0,
                "steps": [("ui.language", "Choose a language", "请选择一种语言")],
                "values": {},
                "phase": "choice",
                "selected_choice": 0,
            }
            self.query_one("#command_input", Input).placeholder = self._t("choice_placeholder")
            self._refresh_runtime()
            self._set_message(self._t("start_language"))
            return
        if section == "feishu":
            self._config_flow = {
                "section": "feishu",
                "step_index": 0,
                "steps": FEISHU_WIZARD_STEPS,
                "values": {},
                "phase": "choice",
                "selected_choice": 0,
            }
            self.query_one("#command_input", Input).placeholder = self._t("choice_placeholder")
            self._refresh_runtime()
            self._set_message(self._t("start_feishu"))
            return
        self._set_message(self._t("unknown_interactive", section=section))

    def _flow_choices_for_step(self, config: dict) -> list[str]:
        assert self._config_flow is not None
        section = self._config_flow["section"]
        if section == "language":
            return [label for label, _code in LANGUAGE_CHOICES]
        step_index = self._config_flow["step_index"]
        step_key, _prompt_en, _prompt_zh = self._config_flow["steps"][step_index]
        current = self._lookup_nested(config, step_key)
        if step_key == "feishu.app_secret":
            current_label = self._t("current_secret") if current else self._t("empty")
        else:
            current_label = current or self._t("empty")
        return [
            self._t("new"),
            self._t("do_not_change", current=current_label),
        ]

    def _accept_config_choice(self) -> None:
        assert self._config_flow is not None
        section = self._config_flow["section"]
        selected = self._config_flow["selected_choice"]
        if section == "language":
            _label, code = LANGUAGE_CHOICES[selected]
            self._service.set_config_value("ui.language", code)
            self._config_flow = None
            self.query_one("#command_input", Input).placeholder = self._t("config_mode_placeholder")
            self._refresh_runtime()
            self._set_message(self._t("language_done"))
            return
        if selected == 0:
            self._config_flow["phase"] = "input"
            self.query_one("#command_input", Input).placeholder = self._t("input_placeholder")
            self._refresh_runtime()
            step_index = self._config_flow["step_index"]
            _step_key, prompt_en, prompt_zh = self._config_flow["steps"][step_index]
            self._set_message(prompt_zh if self._lang() == "zh" else prompt_en)
            return
        self._advance_config_flow(None)

    def _advance_config_flow(self, value: str | None) -> None:
        assert self._config_flow is not None
        step_index = self._config_flow["step_index"]
        steps = self._config_flow["steps"]
        key, _prompt_en, _prompt_zh = steps[step_index]
        if value is not None:
            self._config_flow["values"][key] = value
        next_index = step_index + 1
        if next_index >= len(steps):
            for config_key, config_value in self._config_flow["values"].items():
                self._service.set_config_value(config_key, config_value)
            self._config_flow = None
            self.query_one("#command_input", Input).placeholder = self._t("config_mode_placeholder")
            self._refresh_runtime()
            self._set_message(self._t("feishu_done"))
            return
        self._config_flow["step_index"] = next_index
        self._config_flow["phase"] = "choice"
        self._config_flow["selected_choice"] = 0
        self.query_one("#command_input", Input).placeholder = self._t("choice_placeholder")
        self._refresh_runtime()
        _next_key, next_prompt_en, next_prompt_zh = steps[next_index]
        prompt = next_prompt_zh if self._lang() == "zh" else next_prompt_en
        self._set_message(self._t("next_choose", prompt=prompt))

    def _run_command(self, command: str) -> None:
        if not command.startswith("/"):
            raise ValueError(self._t("slash_required"))
        try:
            parts = shlex.split(command[1:])
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        if not parts:
            self._set_message(self._t("commands_list"))
            return
        name = parts[0].lower()
        args = parts[1:]
        if name in {"help", "h", "?"}:
            self._view = "help"
            self._refresh_runtime()
            self._set_message(self._t("help_message"))
            return
        if name in {"config", "c"}:
            if args and args[0].lower() == "show":
                self._view = "show"
                self._show_scroll = 0
                self._refresh_runtime()
                self._set_message(self._t("show_refreshed"))
                return
            self._enter_config_mode()
            self._set_message(self._t("config_pick"))
            return
        if name in {"log", "l"}:
            self._view = "logs"
            self._show_scroll = 0
            self._refresh_runtime()
            return
        if name in {"r", "restart"}:
            self.exit("restart")
            return
        if name in {"q", "quit", "exit"}:
            if self._view != "dashboard":
                self._view = "dashboard"
                self._show_scroll = 0
                self._refresh_runtime()
                self._set_message(self._t("back_dashboard"))
                return
            self.exit()
            return
        raise ValueError(self._t("unknown_command"))

    def _set_message(self, message: str) -> None:
        self.query_one("#message_line", Static).update(message)
