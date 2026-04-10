# Validation

## 目标

验证 session 已不只是后台状态，而是用户可见、可操作的对象。

## 方法

- 检查 workspace card 是否展示 `New Session`
- 在 active session 存在时检查是否展示 `Close Session`
- 验证 `session.new` 会切换 active session
- 验证 `session.close` 会清空 active session 展示
- 回归 card gateway / gateway / task / session 测试

## 结果

通过：

- `tests/test_card_gateway.py`
- `tests/test_feishu_gateway.py`
- `tests/test_session_controller.py`
- `tests/test_task_controller.py`
- 以及相关回归

## 结论

PoCo 现在已具备最小可见的 session lifecycle 动作。
