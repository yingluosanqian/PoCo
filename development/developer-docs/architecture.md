# Architecture

## 1. 当前产品结构

- `DM` 是 control plane
- `Group` 是 project workspace
- 一个 `project` 对应一个 Feishu 群
- 一个群就是一个稳定 `session`
- 群里的普通文本消息默认就是 task prompt

## 2. 运行主链

### 群消息 -> task

1. Feishu 消息进入 [`poco/main.py`](/Users/yihanc/project/PoCo/poco/main.py)
2. 转到 [`FeishuGateway`](/Users/yihanc/project/PoCo/poco/platform/feishu/gateway.py)
3. 转到 [`InteractionService`](/Users/yihanc/project/PoCo/poco/interaction/service.py)
4. 创建 [`TaskController`](/Users/yihanc/project/PoCo/poco/task/controller.py) 的 task
5. 若同 project 已有 active task，则进入 queue
6. 否则由 [`AsyncTaskDispatcher`](/Users/yihanc/project/PoCo/poco/task/dispatcher.py) 异步启动
7. runner 流式输出通过 [`FeishuTaskNotifier`](/Users/yihanc/project/PoCo/poco/task/notifier.py) 原位更新 task card

### DM 卡片 -> project 管理

1. Feishu 卡片 action 进入 [`/platform/feishu/card-actions`](/Users/yihanc/project/PoCo/poco/main.py)
2. 由 [`FeishuCardActionGateway`](/Users/yihanc/project/PoCo/poco/platform/feishu/card_gateway.py) 解析为 `ActionIntent`
3. 由 [`CardActionDispatcher`](/Users/yihanc/project/PoCo/poco/interaction/card_dispatcher.py) 分发到对应 handler
4. handler 产出平台无关 `IntentDispatchResult`
5. 再由 [`FeishuCardRenderer`](/Users/yihanc/project/PoCo/poco/platform/feishu/cards.py) 渲染成卡片

## 3. 核心模块分工

- [`poco/main.py`](/Users/yihanc/project/PoCo/poco/main.py)
  - 组装所有 controller / gateway / runner / notifier
  - 定义 HTTP endpoints
- [`poco/interaction/service.py`](/Users/yihanc/project/PoCo/poco/interaction/service.py)
  - 文本消息的主入口
  - 决定 DM 和 Group 的默认消息语义
- [`poco/interaction/card_handlers.py`](/Users/yihanc/project/PoCo/poco/interaction/card_handlers.py)
  - 所有 card intent 的实际业务处理
- [`poco/task/controller.py`](/Users/yihanc/project/PoCo/poco/task/controller.py)
  - task 生命周期
  - queue 查询与状态转换
- [`poco/task/dispatcher.py`](/Users/yihanc/project/PoCo/poco/task/dispatcher.py)
  - 后台异步启动 / resume / 自动推进 queue
- [`poco/task/notifier.py`](/Users/yihanc/project/PoCo/poco/task/notifier.py)
  - 将 task 状态变化同步回 Feishu task card / workspace card
- [`poco/agent/runner.py`](/Users/yihanc/project/PoCo/poco/agent/runner.py)
  - 多 backend runner
  - Codex / Claude Code / Cursor Agent 的真实执行实现
- [`poco/agent/catalog.py`](/Users/yihanc/project/PoCo/poco/agent/catalog.py)
  - backend descriptor
  - backend-specific config fields
  - backend model discovery
- [`poco/project/controller.py`](/Users/yihanc/project/PoCo/poco/project/controller.py)
  - project 增删改查
  - 删除 project 时本地级联清理
- [`poco/workspace/controller.py`](/Users/yihanc/project/PoCo/poco/workspace/controller.py)
  - 当前群 workspace 的 workdir 状态
- [`poco/session/controller.py`](/Users/yihanc/project/PoCo/poco/session/controller.py)
  - 群绑定的稳定 session
- [`poco/storage/sqlite.py`](/Users/yihanc/project/PoCo/poco/storage/sqlite.py)
  - 默认持久化后端

## 4. 当前卡片面

### DM

- 首页：`New / Manage`
- `New`：创建 project + group
- `Manage`：删除 project

### Group

- 主 workspace card
  - `Stop`
  - `Working Dir`
  - `Agent`
- task card
  - streaming running output
  - terminal result
  - `Stop`

## 5. 数据对象

### Project

- 群绑定
- backend 选择
- backend-specific config
- workspace card message id

### Session

- 一个群一个稳定 session
- 保存 `backend_session_id`
  - 例如 Codex thread id

### Task

- 当前 prompt
- queue / running / waiting / terminal 状态
- `effective_backend_config`
- `effective_workdir`
- `backend_session_id`
- task card message id

## 6. 当前设计边界

- 不支持在已有 project 上切 backend
- `DM` 不承载实际 task 对话
- `Group` 不再依赖 `/run` 命令作为正式入口
- browser-based 配置已被移除，配置交互保持在卡片内
