# Validation

## 验证方法

- `python3 -m unittest tests/test_feishu_client.py tests/test_card_gateway.py tests/test_demo_cards.py tests/test_feishu_gateway.py tests/test_feishu_longconn.py tests/test_health.py tests/test_debug_api.py tests/test_demo_api.py tests/test_task_controller.py`
- `python3 -m compileall poco tests`
- 本地 card action 模拟 `project.create`
- 单测模拟飞书建群成功和失败回滚

## 结果

- 飞书客户端已具备 `im/v1/chats` 建群调用
- `project.create` 在接入 bootstrapper 后可把 `group_chat_id` 绑定回 project
- 建群失败时会回滚 project 创建，不留下半成品 project
- demo/local 模式下仍可继续创建不带群的 project

## 是否通过

通过当前轮目标。

## 残留问题

- 真实飞书环境中的建群权限和 owner 行为还需要继续联调
- 当前还没有在新建群里主动推 workspace 卡片
