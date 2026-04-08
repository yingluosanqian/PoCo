# Validation

## 验证方法

- `python3 -m unittest tests/test_feishu_longconn.py tests/test_card_gateway.py tests/test_feishu_gateway.py tests/test_health.py tests/test_debug_api.py`
- `python3 -m compileall poco tests`
- 检查 `/health` warning 是否已反映新事实

## 结果

- 长连接 listener 已注册 `p2.card.action.trigger`
- 自定义 ws client 已处理 `CARD` 帧，不再直接忽略
- `/health` 已显示长连接同时处理 message events 和 card callbacks
- 测试通过

## 是否通过

通过当前轮目标。

## 残留问题

- card callback 在 SDK 序列化后不保留顶层 `event_id`，长连接路径需要使用组合 request id 做幂等 fallback
- 仍需你在真实飞书里再点一次按钮完成端到端确认
