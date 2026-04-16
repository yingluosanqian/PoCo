# Validation

## 验证方法

- `uv run --extra dev pytest -q tests/test_session_controller.py`
- `uv run --extra dev pytest -q tests/test_task_controller.py`
- `uv run --extra dev pytest -q tests/test_card_gateway.py`
- `uv run --extra dev pytest -q tests/test_card_dispatcher.py`
- `uv run --extra dev pytest tests/test_agent_runner.py tests/test_completion_gate.py tests/test_task_controller.py tests/test_task_dispatcher.py tests/test_task_notifier.py tests/test_debug_api.py tests/test_health.py tests/test_card_gateway.py tests/test_feishu_client.py tests/test_config.py tests/test_session_controller.py tests/test_card_dispatcher.py`

## 结果

- `tests/test_session_controller.py`: 5 passed (新增 3 个: attach 创建 / 覆盖 / 清空)
- `tests/test_task_controller.py`: 27 passed (新增 6 个: empty / single / dedupe / recency / backend 过滤 / 无 backend_session_id 跳过)
- `tests/test_card_gateway.py`: 50 passed (新增 7 个: choose history / choose empty / apply / enter prefilled / apply entered / clear / overview Session 按钮)
- `tests/test_card_dispatcher.py`: 6 passed
- 宽扫测试集: 211 passed, 10 warnings (warnings 为既有 daemon-thread 资源告警, 非本轮引入)

## 新增行为

- workspace overview card (GROUP surface, 无 running task) 出现 `Session` 按钮, 行为 → `workspace.choose_session`
- `workspace.choose_session` 打开下拉 + "Enter ID" / "Start Fresh" / "Cancel" 的 chooser 卡; 历史为空时显示 empty-state markdown
- `workspace.apply_session` / `workspace.apply_entered_session_id` / `workspace.clear_session` 均走 `SessionController.attach_backend_session` 覆盖 active session 的 `backend_session_id`, 然后返回 workspace overview
- `workspace.enter_session_id` 打开手输卡; 预填当前 active 的 `backend_session_id`

## 是否通过

通过当前轮目标。

## 残留问题 / 预先忽略

- `tests/test_demo_cards.py` 里 4 个既有 daemon-thread race failing test 与本轮无关, 按指示不修不计入
- 未加 backend id 活性校验 (仍依赖 task 失败后换 id 兜底, 与 decision.md 一致)
- 未加历史下拉分页 (用户明确要求不设上限)
