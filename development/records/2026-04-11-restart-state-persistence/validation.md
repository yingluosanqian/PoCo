# Validation

## 目标

验证 PoCo 在服务重启后，是否还能识别既有 project/group/workspace/task 最小状态。

## 方法

- 新增 sqlite store roundtrip 验证
- 新增 `create_app()` 跨重启恢复测试
- 回归现有 health/debug/demo/task/feishu 测试

## 结果

已通过：

- `tests/test_state_persistence.py`
- `tests/test_health.py`
- `tests/test_debug_api.py`
- `tests/test_demo_api.py`
- `tests/test_demo_cards.py`
- `tests/test_task_controller.py`
- `tests/test_feishu_gateway.py`
- `tests/test_card_gateway.py`
- `tests/test_task_notifier.py`
- `tests/test_feishu_client.py`

并通过：

- `python3 -m compileall poco tests`

## 结论

本轮已解决“服务重启后完全失去 group/project/workspace/task 最小跟踪”的问题。

## 残留问题

- 仍未实现完整 session continuity
- 仍未实现跨进程可恢复 worker
- 被重启打断的运行中 task 目前只会被标记为失败，不会断点续跑
