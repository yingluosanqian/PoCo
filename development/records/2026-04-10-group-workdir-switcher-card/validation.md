# Validation

## 验证方法

- `python3 -m unittest tests/test_card_dispatcher.py tests/test_card_gateway.py tests/test_demo_cards.py tests/test_feishu_client.py tests/test_feishu_gateway.py tests/test_feishu_longconn.py tests/test_health.py tests/test_debug_api.py tests/test_demo_api.py tests/test_task_controller.py`
- `python3 -m compileall poco tests`
- 本地 card action 模拟 `workspace.open_workdir_switcher` 和 `workspace.enter_path`

## 结果

- 群里的 workspace overview card 已可进入 `Workdir Switcher Card`
- switcher card 已展示 current agent、current workdir、source
- 只读子卡已可返回 switcher card

## 是否通过

通过当前轮目标。

## 残留问题

- 真实 session workdir 切换仍未接入
- `Choose Preset / Use Recent / Enter Path` 仍未接真实数据与写入
