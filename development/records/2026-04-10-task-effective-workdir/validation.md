# Validation

## 验证方法

- `python3 -m unittest tests/test_card_dispatcher.py tests/test_card_gateway.py tests/test_demo_cards.py tests/test_feishu_client.py tests/test_feishu_gateway.py tests/test_feishu_longconn.py tests/test_health.py tests/test_debug_api.py tests/test_demo_api.py tests/test_task_controller.py tests/test_agent_runner.py`
- `python3 -m compileall poco tests`
- 单测模拟绑定到 group 的 project 收到 `/run ...` 消息
- 单测验证 Codex runner 优先使用 `task.effective_workdir`

## 结果

- 群消息入口现在会按 `chat_id` 解析 project
- task 创建时会固化 `project_id` 和 `effective_workdir`
- task 文本回执已可显示 `effective_workdir`
- Codex runner 执行时会优先使用 task 上的目录，而不是只依赖全局默认目录

## 是否通过

通过当前轮目标。

## 残留问题

- 当前只覆盖群文本 fallback 的 task 创建路径
- `Use Recent` 仍未接入真实写路径
- `project.backend` 仍未真正驱动多 runner 选择
