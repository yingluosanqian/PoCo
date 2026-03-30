"""Static UI resources used by the PoCo TUI shell."""

POCO_ICON = """
██████╗  ██████╗  ██████╗ ██████╗
██╔══██╗██╔═══██╗██╔════╝██╔═══██╗
██████╔╝██║   ██║██║     ██║   ██║
██╔═══╝ ██║   ██║██║     ██║   ██║
██║     ╚██████╔╝╚██████╗╚██████╔╝
""".strip("\n")

TUI_CSS = """
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
    width: 40;
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
    height: 3;
    padding: 0 1;
}

#command_input {
    border: round #f97316;
    background: #0d1117;
    color: #e6edf3;
    height: 3;
    margin: 0;
}

#message_line {
    height: auto;
    margin-top: 1;
    padding: 0 1 1 1;
    color: #fb923c;
}
"""


STRINGS = {
    "app_title": {"en": "Pocket Coding for Feishu", "zh": "Feishu 口袋编程"},
    "bot": {"en": "Bot (feishu)", "zh": "机器人（飞书）"},
    "bot_binding": {"en": "Bot", "zh": "机器人"},
    "section": {"en": "Section", "zh": "分组"},
    "unbound": {"en": "unbound", "zh": "未绑定"},
    "agent": {"en": "Agent", "zh": "Agent"},
    "agent_summary": {"en": "Agent", "zh": "Agent"},
    "poco": {"en": "PoCo", "zh": "PoCo"},
    "language": {"en": "Language", "zh": "语言"},
    "relay": {"en": "Relay", "zh": "转发"},
    "running": {"en": "RUNNING", "zh": "运行中"},
    "stopped": {"en": "STOPPED", "zh": "已停止"},
    "ready": {"en": "READY", "zh": "已就绪"},
    "needs_config": {"en": "NEEDS CONFIG", "zh": "需要配置"},
    "current_config": {"en": "Current config", "zh": "当前配置"},
    "path": {"en": "Path", "zh": "路径"},
    "nav_hint_config": {
        "en": "↑/↓ to select | ←/→ to switch | Enter to open | Esc / q to back | Ctrl+R to restart",
        "zh": "↑/↓ 选择 | ←/→ 切换 | Enter 打开 | Esc / q 返回 | Ctrl+R 重启",
    },
    "nav_hint_login": {
        "en": "↑/↓ to select | Enter to continue | Esc / q to back",
        "zh": "↑/↓ 选择 | Enter 继续 | Esc / q 返回",
    },
    "nav_hint_bind_platform": {
        "en": "↑/↓ to select | Enter to continue | Esc / q to quit",
        "zh": "↑/↓ 选择 | Enter 继续 | Esc / q 退出",
    },
    "nav_hint_bind_account": {
        "en": "↑/↓ to select | Enter to continue | Esc / q to back",
        "zh": "↑/↓ 选择 | Enter 继续 | Esc / q 返回",
    },
    "nav_hint_workspace_view": {
        "en": "↑/↓ to select | ←/→ to switch | Esc / q to quit | Ctrl+R to restart",
        "zh": "↑/↓ 选择 | ←/→ 切换 | Esc / q 退出    Ctrl+R 重启",
    },
    "nav_hint_workspace_editable": {
        "en": "↑/↓ to select | ←/→ to switch | Enter to open | Esc / q to quit | Ctrl+R to restart",
        "zh": "↑/↓ 选择 | ←/→ 切换 | Enter 打开 | Esc / q 退出    Ctrl+R 重启",
    },
    "nav_hint_choice": {
        "en": "↑/↓ to select | Enter to apply | Esc / q to cancel",
        "zh": "↑/↓ 选择 | Enter 应用 | Esc / q 取消",
    },
    "nav_hint_input": {
        "en": "Type a value | Enter to save | Esc / q to cancel",
        "zh": "输入新值 | Enter 保存 | Esc / q 取消",
    },
    "nav_hint_subview": {
        "en": "↑/↓ to select | Enter to open | Esc / q to close",
        "zh": "↑/↓ 选择 | Enter 打开 | Esc / q 关闭",
    },
    "nav_hint_show_config": {
        "en": "↑/↓ to scroll | Esc / q to close",
        "zh": "↑/↓ 滚动 | Esc / q 关闭",
    },
    "login_title": {"en": "Connect a Bot", "zh": "连接机器人"},
    "login_platform": {"en": "Platform", "zh": "平台"},
    "login_platform_desc": {
        "en": "Choose the chat platform for this workspace.",
        "zh": "为当前工作区选择聊天平台。",
    },
    "login_saved_bots": {"en": "Saved Bots", "zh": "已保存机器人"},
    "login_saved_bots_desc": {
        "en": "Reuse a saved bot, or choose New Bot.",
        "zh": "复用已保存机器人，或选择 New Bot。",
    },
    "login_new_bot": {"en": "New Bot", "zh": "新机器人"},
    "login_current_bot": {"en": "current", "zh": "当前"},
    "login_feishu": {"en": "Feishu", "zh": "飞书"},
    "login_slack": {"en": "Slack", "zh": "Slack"},
    "login_discord": {"en": "Discord", "zh": "Discord"},
    "select_platform": {"en": "Choose a platform", "zh": "选择平台"},
    "select_saved_bot": {"en": "Choose a saved bot", "zh": "选择已保存机器人"},
    "login_enter_app_id": {
        "en": "Enter the Feishu APP ID for this workspace.",
        "zh": "请输入当前工作区的飞书 APP ID。",
    },
    "login_enter_app_secret": {
        "en": "Enter the Feishu APP Secret for this workspace.",
        "zh": "请输入当前工作区的飞书 APP Secret。",
    },
    "login_app_id": {"en": "APP ID", "zh": "APP ID"},
    "login_app_secret": {"en": "APP Secret", "zh": "APP Secret"},
    "workspace_title": {"en": "Workspace Settings", "zh": "工作区设置"},
    "workspace_help": {
        "en": "Use ←/→ to switch sections. Press Enter on a field to edit it.",
        "zh": "使用 ←/→ 切换 section。按 Enter 编辑字段。",
    },
    "field": {"en": "Field", "zh": "字段"},
    "type_value": {
        "en": "Type the new value in the command line and press Enter.",
        "zh": "请在底部输入新值并按 Enter。",
    },
    "current_value": {"en": "Current value", "zh": "当前值"},
    "secret_value": {"en": "(hidden)", "zh": "（已隐藏）"},
    "empty": {"en": "empty", "zh": "空"},
    "config_required": {
        "en": "This workspace is not ready. Finish Bot (feishu) first.",
        "zh": "当前工作区尚未就绪。请先完成 Bot (feishu) 配置。",
    },
    "config_missing": {
        "en": "Missing in this workspace binding (Bot (feishu)): {fields}",
        "zh": "当前工作区绑定的 Bot (feishu) 缺少：{fields}",
    },
    "missing_label": {"en": "Missing", "zh": "缺少"},
    "relay_started": {"en": "PoCo relay is running.", "zh": "PoCo relay 已启动。"},
    "relay_already_running": {"en": "PoCo relay is already running.", "zh": "PoCo relay 已经在运行。"},
    "enter_value_or_quit": {
        "en": "Enter a value, or press Esc to go back.",
        "zh": "请输入值，或按 Esc 返回。",
    },
    "value_saved": {"en": "{field} saved.", "zh": "{field} 已保存。"},
    "workspace_bound_bot": {"en": "Bound bot", "zh": "绑定机器人"},
    "workspace_config_file": {"en": "Config file", "zh": "配置文件"},
    "workspace_state_dir": {"en": "State dir", "zh": "状态目录"},
    "restart_relay": {"en": "Restart Relay", "zh": "重启 Relay"},
    "show_config": {"en": "Show Config", "zh": "查看配置"},
    "not_implemented": {"en": "{name} support is not implemented yet.", "zh": "{name} 支持暂未实现。"},
    "restart_required": {
        "en": "Saved. Press Ctrl+R to restart relay if needed.",
        "zh": "已保存。如有需要请按 Ctrl+R 重启 relay。",
    },
    "show_scroll": {"en": "Use ↑ / ↓ to scroll.", "zh": "使用 ↑ / ↓ 滚动。"},
    "scroll_status": {"en": "lines {start}-{end} / {total}", "zh": "行 {start}-{end} / {total}"},
}
