# Validation

## 验证方法

- `python3 -m unittest tests/test_card_gateway.py tests/test_feishu_gateway.py tests/test_demo_cards.py tests/test_debug_api.py`
- `python3 -m compileall poco tests`
- 本地模拟真实 card action 回调，点击 `project.create`

## 结果

- DM 首页卡片已包含真实 `callback` 按钮
- `project.create` 点击后会返回 `project_detail` 卡片
- `project.list` 已可作为返回动作使用
- callback 写操作已支持使用飞书顶层 `event_id` 做幂等
- 本地 click smoke 返回 `200`，并返回 `project_detail` card

## 是否通过

通过当前轮目标。

## 残留问题

- `project.create` 仍使用默认命名
- 建群、绑定群、完整 workspace 工作流仍待继续迭代
