# Handoff

## 1. 接手人最先要知道的事

- 这个项目不是“聊天 bot 平台”
- 它的核心是：手机消息入口控制服务器侧 agent
- 当前正式主链是：
  - DM 创建 / 管理 project
  - Group 直接发消息作为 prompt
  - task card 流式更新

## 2. 当前最关键的代码入口

- 服务组装: [`poco/main.py`](/Users/yihanc/project/PoCo/poco/main.py)
- 文本消息入口: [`poco/interaction/service.py`](/Users/yihanc/project/PoCo/poco/interaction/service.py)
- 卡片业务入口: [`poco/interaction/card_handlers.py`](/Users/yihanc/project/PoCo/poco/interaction/card_handlers.py)
- 多 backend 执行: [`poco/agent/runner.py`](/Users/yihanc/project/PoCo/poco/agent/runner.py)
- backend 配置能力: [`poco/agent/catalog.py`](/Users/yihanc/project/PoCo/poco/agent/catalog.py)
- Feishu 卡片渲染: [`poco/platform/feishu/cards.py`](/Users/yihanc/project/PoCo/poco/platform/feishu/cards.py)

## 3. 现在故意保留的兼容逻辑

- 旧卡片 intent 兼容：
  - `workspace.choose_model -> workspace.choose_agent`
  - `workspace.apply_model -> workspace.apply_agent`

这层兼容是故意留的，不要随手删。删之前要确认旧卡片都已失效。

## 4. 当前已知债务

- 测试全量通过，但仍有两条旧 `ResourceWarning`
- `Claude Code` 没做运行时模型发现，这是故意的
- 仍有一些历史 subcard 入口只是保留兼容，不是正式主路径
- `development/records/` 很完整，但不适合直接拿来当运行手册

## 5. 建议的接手顺序

1. 先用 `codex` 在真实群里跑通一轮
2. 再分别 smoke test `claude_code` 和 `cursor_agent`
3. 再决定是做产品功能，还是继续收技术债

## 6. 不建议的做法

- 不要把 backend-specific 配置重新抬回通用层
- 不要重新引入 browser-based 配置页
- 不要在已有 project 上开放 backend 切换
- 不要把队列、workspace、task 三张卡重新拆成多套互不联动的状态面
