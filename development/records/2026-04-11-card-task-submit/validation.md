# Validation

## 验证方法

- `python3 -m unittest tests/test_card_dispatcher.py tests/test_card_gateway.py tests/test_demo_cards.py tests/test_feishu_client.py tests/test_feishu_gateway.py tests/test_feishu_longconn.py tests/test_health.py tests/test_debug_api.py tests/test_demo_api.py tests/test_task_controller.py tests/test_agent_runner.py`
- `python3 -m compileall poco tests`
- 单测验证 workspace overview 渲染出 `Run Task`
- 单测验证 `task.open_composer`
- 单测验证 `task.submit` 创建 task、继承 workdir、触发 dispatcher

## 结果

- 群工作区卡片已新增 `Run Task`
- 已存在最小 `task_composer` 卡片
- `task.submit` 已能创建 task，并继承当前 workspace 的 `active_workdir`
- `task.submit` 已能触发异步 `dispatch_start`

## 是否通过

通过当前轮目标。

## 残留问题

- task 终态和审批仍主要通过文本回推，而不是结果卡
- `Use Recent` 仍未接入真实写路径
- card-first 的 approval / reject / result cards 仍未落地
