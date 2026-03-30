"""Static UI resources used by the PoCo TUI shell."""

POCO_ICON = """
┌─────┐
│ ~ ~ │
│  v  │
│/>_  │
└──●──┘
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
    width: 24;
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

#message_line {
    height: auto;
    padding: 0 1 1 1;
    color: #fb923c;
}
"""


STRINGS = {
    "app_title": {"en": "Pocket Coding for Feishu", "zh": "Feishu 口袋编程"},
    "dashboard": {"en": "Menu", "zh": "菜单"},
    "settings": {"en": "Config", "zh": "配置"},
    "bot": {"en": "Bot (feishu)", "zh": "机器人（飞书）"},
    "bot_binding": {"en": "Bot", "zh": "机器人"},
    "unbound": {"en": "unbound", "zh": "未绑定"},
    "agent": {"en": "Agent & Model", "zh": "Agent 与模型"},
    "poco": {"en": "PoCo", "zh": "PoCo"},
    "language": {"en": "Language", "zh": "语言"},
    "relay": {"en": "Relay", "zh": "转发"},
    "running": {"en": "RUNNING", "zh": "运行中"},
    "stopped": {"en": "STOPPED", "zh": "已停止"},
    "ready": {"en": "READY", "zh": "已就绪"},
    "needs_config": {"en": "NEEDS CONFIG", "zh": "需要配置"},
    "current_config": {"en": "Current config", "zh": "当前配置"},
    "commands": {"en": "Commands", "zh": "命令"},
    "path": {"en": "Path", "zh": "路径"},
    "nav_hint_title": {"en": "Hints", "zh": "提示"},
    "nav_hint_menu": {
        "en": "↑/↓ to select | Enter to open | Ctrl+R to restart",
        "zh": "↑/↓ 选择 | Enter 打开 | Ctrl+R 重启",
    },
    "nav_hint_config": {
        "en": "↑/↓ to select | Enter to open | Esc / q to back | Ctrl+R to restart",
        "zh": "↑/↓ 选择 | Enter 打开 | Esc / q 返回 | Ctrl+R 重启",
    },
    "nav_hint_login": {
        "en": "↑/↓ to select | Enter to continue | Esc / q to back",
        "zh": "↑/↓ 选择 | Enter 继续 | Esc / q 返回",
    },
    "login_title": {"en": "Connect a Bot", "zh": "连接机器人"},
    "login_platform": {"en": "Platform", "zh": "平台"},
    "login_platform_desc": {
        "en": "Choose the chat platform for this workspace first.",
        "zh": "先为当前工作区选择聊天平台。",
    },
    "login_saved_bots": {"en": "Saved Bots", "zh": "已保存机器人"},
    "login_saved_bots_desc": {
        "en": "Reuse a bot already configured on this machine, or choose New Bot.",
        "zh": "复用这台机器上已配置的机器人，或选择 New Bot。",
    },
    "login_new_bot": {"en": "New Bot", "zh": "新机器人"},
    "login_current_bot": {"en": "current", "zh": "当前"},
    "login_not_implemented": {
        "en": "{platform} support is not implemented yet.",
        "zh": "{platform} 支持暂未实现。",
    },
    "login_feishu": {"en": "Feishu", "zh": "飞书"},
    "login_slack": {"en": "Slack", "zh": "Slack"},
    "login_discord": {"en": "Discord", "zh": "Discord"},
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
    "config_mode": {"en": "Config mode", "zh": "配置模式"},
    "pick_section": {"en": "Select a config section", "zh": "选择配置分类"},
    "pick_section_help": {
        "en": "Use ↑/↓ to move, Enter to continue, Esc to go back.",
        "zh": "使用 ↑/↓ 选择，回车进入，Esc 返回。",
    },
    "section": {"en": "Section", "zh": "当前分类"},
    "backend": {"en": "Backend", "zh": "后端"},
    "field": {"en": "Field", "zh": "字段"},
    "type_value": {
        "en": "Type the new value in the command line and press Enter.",
        "zh": "请在命令行输入新值并按回车。",
    },
    "input_placeholder": {"en": "", "zh": ""},
    "current_secret": {"en": "current secret", "zh": "当前密钥"},
    "empty": {"en": "empty", "zh": "空"},
    "config_required": {
        "en": "This workspace is not ready. Run `poco feishu-bootstrap` here, then finish Bot (feishu).",
        "zh": "当前工作区尚未就绪。请先在这里运行 `poco feishu-bootstrap`，再完成 Bot (feishu) 配置。",
    },
    "config_missing": {
        "en": "Missing in this workspace binding (Bot (feishu)): {fields}",
        "zh": "当前工作区绑定的 Bot (feishu) 缺少：{fields}",
    },
    "missing_label": {"en": "Missing", "zh": "缺少"},
    "relay_started": {"en": "PoCo relay is running.", "zh": "PoCo relay 已启动。"},
    "relay_already_running": {"en": "PoCo relay is already running.", "zh": "PoCo relay 已经在运行。"},
    "left_config": {"en": "Left config mode.", "zh": "已退出配置模式。"},
    "enter_value_or_quit": {
        "en": "Enter a value, or press Esc to go back.",
        "zh": "请输入值，或按 Esc 返回。",
    },
    "language_done": {
        "en": "Language updated. It takes effect immediately.",
        "zh": "语言已更新，立即生效。",
    },
    "feishu_done": {
        "en": "Feishu config saved. Restart is required before it takes effect.",
        "zh": "Feishu 配置完成，但需要重启后才能生效。",
    },
    "agent_done": {
        "en": "{section} config saved. Restart is required before it takes effect.",
        "zh": "{section} 配置完成，但需要重启后才能生效。",
    },
    "show_refreshed": {"en": "Current config refreshed.", "zh": "当前配置已刷新。"},
    "show_scroll": {"en": "Use ↑ / ↓ to scroll.", "zh": "使用 ↑ / ↓ 滚动。"},
    "config_pick": {
        "en": "Choose a section with ↑/↓, press Enter to enter, press Esc to go back.",
        "zh": "请用 ↑/↓ 选择分类，按回车进入，Esc 返回。",
    },
    "scroll_status": {
        "en": "lines {start}-{end} / {total}",
        "zh": "行 {start}-{end} / {total}",
    },
    "back_dashboard": {
        "en": "Back to menu.",
        "zh": "已回到菜单。",
    },
    "back_config_section": {
        "en": "Back to config section list.",
        "zh": "已回到配置分类列表。",
    },
    "back_config_fields": {
        "en": "Back to field list.",
        "zh": "已回到字段列表。",
    },
    "field_list_help": {
        "en": "Use ↑/↓ to move, Enter to edit, Esc to go back.",
        "zh": "使用 ↑/↓ 选择，回车编辑，Esc 返回。",
    },
    "value_choices_help": {
        "en": "Use ↑/↓ to choose, Enter to save, Esc to go back.",
        "zh": "使用 ↑/↓ 选择，回车保存，Esc 返回。",
    },
    "current_value": {"en": "Current value", "zh": "当前值"},
    "secret_value": {"en": "(hidden)", "zh": "（已隐藏）"},
    "editing_field": {"en": "Editing {field}", "zh": "正在编辑 {field}"},
    "value_saved": {"en": "{field} saved.", "zh": "{field} 已保存。"},
    "restart_required": {
        "en": "Restart is required before it takes effect.",
        "zh": "需要重启后才能生效。",
    },
    "menu": {"en": "Menu", "zh": "菜单"},
    "root_menu_help": {
        "en": "Use ↑/↓ to move, Enter to open.",
        "zh": "使用 ↑/↓ 选择，回车进入。",
    },
    "menu_agent_desc": {
        "en": "Edit agent runtimes, providers, models, and Claude backends.",
        "zh": "编辑 Agent 运行时、provider、模型和 Claude 后端。",
    },
    "menu_bot_desc": {
        "en": "Configure the Feishu bot bound to this workspace.",
        "zh": "配置当前工作区绑定的飞书机器人。",
    },
    "workspace_bound_bot": {"en": "Bound bot", "zh": "绑定机器人"},
    "workspace_config_file": {"en": "Config file", "zh": "配置文件"},
    "workspace_state_dir": {"en": "State dir", "zh": "状态目录"},
    "menu_poco_desc": {
        "en": "Adjust PoCo local runtime behavior and advanced options.",
        "zh": "调整 PoCo 本地运行行为和高级选项。",
    },
    "menu_language_desc": {
        "en": "Change the TUI display language.",
        "zh": "修改 TUI 显示语言。",
    },
    "menu_quit_desc": {"en": "Exit the TUI application.", "zh": "退出 TUI 应用。"},
    "config_show_desc": {
        "en": "Inspect the current config file in a scrollable view.",
        "zh": "在可滚动视图中查看当前配置文件。",
    },
    "default_backend": {"en": "Default backend", "zh": "默认后端"},
    "claude_backend_help": {
        "en": "Use ↑/↓ to choose a backend, Enter to open it, Esc to go back.",
        "zh": "使用 ↑/↓ 选择后端，回车进入，Esc 返回。",
    },
    "claude_backend_fields_help": {
        "en": "Use ↑/↓ to choose a field, Enter to edit or run the action, Esc to go back.",
        "zh": "使用 ↑/↓ 选择字段，回车编辑或执行动作，Esc 返回。",
    },
    "set_as_default": {"en": "set_as_default", "zh": "设为默认"},
    "set_default_done": {
        "en": "{backend} is now the default Claude backend.",
        "zh": "{backend} 已设为默认 Claude 后端。",
    },
    "set_default_model_done": {
        "en": "{model} is now the default model for {backend}.",
        "zh": "{model} 已设为 {backend} 的默认模型。",
    },
    "true": {"en": "true", "zh": "true"},
    "false": {"en": "false", "zh": "false"},
    "extra_env": {"en": "extra_env", "zh": "额外环境变量"},
    "extra_env_help": {
        "en": "Use ↑/↓ to choose an env item, Enter to open it, Esc to go back.",
        "zh": "使用 ↑/↓ 选择环境变量，回车进入，Esc 返回。",
    },
    "extra_env_actions_help": {
        "en": "Choose an action for the selected env item.",
        "zh": "为当前环境变量选择一个动作。",
    },
    "add_custom_backend": {"en": "add new custom", "zh": "新增自定义后端"},
    "confirm": {"en": "confirm", "zh": "确认"},
    "delete": {"en": "delete", "zh": "删除"},
    "claude_custom_add_help": {
        "en": "Fill the fields, then select confirm to add the backend.",
        "zh": "请先填写字段，再选择 confirm 添加后端。",
    },
    "claude_custom_required": {
        "en": "name, base_url, auth_token, and model are required before confirm.",
        "zh": "name、base_url、auth_token、model 都需要填写后才能 confirm。",
    },
    "claude_custom_name_invalid": {
        "en": "Custom backend name can only contain letters, numbers, '-' and '_'.",
        "zh": "自定义后端名称只能包含字母、数字、- 和 _。",
    },
    "claude_custom_exists": {"en": "That backend name already exists.", "zh": "这个后端名称已经存在。"},
    "claude_custom_added": {"en": "Custom backend {backend} added.", "zh": "自定义后端 {backend} 已添加。"},
    "claude_backend_deleted": {"en": "Custom backend {backend} deleted.", "zh": "自定义后端 {backend} 已删除。"},
    "add_env": {"en": "add", "zh": "新增"},
    "edit_value": {"en": "edit_value", "zh": "修改值"},
    "remove": {"en": "remove", "zh": "删除"},
    "extra_env_empty": {"en": "No extra env variables.", "zh": "暂无额外环境变量。"},
    "env_key_prompt": {
        "en": "Type a new env key in the command line and press Enter.",
        "zh": "请在输入栏输入新的环境变量 key 并回车。",
    },
    "env_value_prompt": {
        "en": "Type the env value in the command line and press Enter.",
        "zh": "请在输入栏输入环境变量 value 并回车。",
    },
    "env_key_exists": {"en": "That env key already exists.", "zh": "这个环境变量 key 已存在。"},
    "env_key_saved": {
        "en": "Env key {key} created. Now enter its value.",
        "zh": "环境变量 {key} 已创建，请继续输入它的值。",
    },
    "env_saved": {"en": "Env variable {key} saved.", "zh": "环境变量 {key} 已保存。"},
    "env_removed": {"en": "Env variable {key} removed.", "zh": "环境变量 {key} 已删除。"},
    "model": {"en": "model", "zh": "模型"},
    "claude_model_help": {
        "en": "Use ↑/↓ to choose a model, Enter to continue, Esc to go back.",
        "zh": "使用 ↑/↓ 选择模型，回车进入，Esc 返回。",
    },
    "claude_model_action_help": {
        "en": "Press Enter to apply the action, Esc to go back.",
        "zh": "按回车执行动作，Esc 返回。",
    },
    "input_disabled": {
        "en": "Input is only enabled when a config field is being edited.",
        "zh": "只有在编辑配置字段时才启用输入框。",
    },
}
