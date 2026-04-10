# Validation

## 验证方法

- `python3 -m unittest tests/test_card_dispatcher.py tests/test_card_gateway.py tests/test_demo_cards.py tests/test_feishu_client.py tests/test_feishu_gateway.py tests/test_feishu_longconn.py tests/test_health.py tests/test_debug_api.py tests/test_demo_api.py tests/test_task_controller.py`
- `python3 -m compileall poco tests`
- 单测模拟 `workspace.enter_path` 卡渲染
- 单测模拟 `workspace.apply_entered_path` 写入和空路径拒绝

## 结果

- `workspace_enter_path` 已包含输入框和 `Apply Path`
- `workspace.apply_entered_path` 已可写入 in-memory workspace context
- 空路径会返回明确 warning

## 是否通过

通过当前轮目标。

## 残留问题

- 真实执行链路仍未消费 `active_workdir`
- 路径合法性、权限和 repo-relative 语义仍需继续设计
- `Choose Preset / Use Recent` 仍未接真实写入
