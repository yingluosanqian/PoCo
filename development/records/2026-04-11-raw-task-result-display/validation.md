# Validation

## 已验证

- `Task` 现在保存 `raw_result`，同时保留 `result_summary` 作为兼容性 preview
- `task_status` card 现在会优先渲染 `raw_result`
- 超长原始结果会在 card 中显示页码和 `Next Page` / `Previous Page`
- `workspace_overview` 已移除 latest result preview，仅保留 latest task 状态与入口
- 单测已覆盖：
  - task 完成态显示原始结果
  - 超长结果分页按钮渲染
  - notifier 发送完成态结果卡
  - workspace 首卡结构变更后的按钮位置

## 验证命令

- `python3 -m unittest tests/test_card_dispatcher.py tests/test_card_gateway.py tests/test_demo_cards.py tests/test_feishu_client.py tests/test_feishu_gateway.py tests/test_feishu_longconn.py tests/test_health.py tests/test_debug_api.py tests/test_demo_api.py tests/test_task_controller.py tests/test_agent_runner.py tests/test_task_dispatcher.py tests/test_task_notifier.py`
- `python3 -m compileall poco tests`
