# Plan

## 范围

- 为飞书客户端补 `im/v1/chats` 建群调用
- 在 `project.create` 里接入 project bootstrapper
- 失败时回滚 project 创建
- 更新卡片文案、测试和最小文档

## 验收标准

- `Create Project + Group` 点击后，project 会带上 `group_chat_id`
- 建群失败时，不留下 project 脏数据
- demo/local 模式保持可运行
