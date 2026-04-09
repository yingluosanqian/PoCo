# Validation

## 验证方法

- `python3 -m unittest tests/test_feishu_client.py tests/test_card_gateway.py tests/test_demo_cards.py tests/test_feishu_gateway.py tests/test_feishu_longconn.py tests/test_health.py tests/test_debug_api.py tests/test_demo_api.py tests/test_task_controller.py`
- `python3 -m compileall poco tests`
- 单测模拟 project bootstrap 后的 workspace 首卡投递
- 单测验证 group surface 被正确写回 workspace 卡片按钮

## 结果

- 新建 project 群后，PoCo 会 best-effort 投递第一张 workspace overview card
- workspace 卡片在群里渲染时，按钮会带 `surface=group`
- 首卡投递是附加步骤，不会影响已成功创建的 project 和群

## 是否通过

通过当前轮目标。

## 残留问题

- 群首卡还没有真正的 task composer 和执行动作
- 首卡失败后的补发和可视化仍待继续完善
