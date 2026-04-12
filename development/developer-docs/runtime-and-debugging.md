# Runtime And Debugging

## 1. 启动

最常用启动方式：

```bash
poco start
```

常用管理命令：

```bash
poco config
poco status
poco shutdown
poco restart
```

当前默认 Feishu 入站模式就是 `longconn`，不需要再主动设置 `POCO_FEISHU_DELIVERY_MODE=longconn`。

如果 CLI 还没装好，再退回：

```bash
python3 -m pip install -e .
uvicorn poco.main:app --reload
```

## 2. 最先看的接口

### 健康检查

```bash
curl http://127.0.0.1:8000/health
```

看这些字段：

- `mode`
- `feishu_delivery_mode`
- `feishu_listener_ready`
- `state_backend`
- `agent_backend`
- `agent_ready`
- `missing`
- `warnings`

### Feishu 调试快照

```bash
curl http://127.0.0.1:8000/debug/feishu
```

重点看：

- `inbound_events`
- `outbound_attempts`
- `errors`
- `listener`

### 任务状态

```bash
curl http://127.0.0.1:8000/tasks
curl http://127.0.0.1:8000/tasks/<task_id>
```

## 3. 常见问题排查

### 群里发消息没有任何回复

先查：

1. `/health`
2. `/debug/feishu`
3. `/tasks`

判断路径：

- 没有 inbound event：问题在 Feishu 入站
- 有 inbound event，但没有 task：问题在 gateway / interaction
- 有 task，但没有 outbound：问题在 notifier / message client
- 有 outbound attempt，但卡片没更新：问题在 message id 绑定或 Feishu API

### 卡片点击没反应

先查：

1. `/debug/feishu` 是否记录到 card action
2. intent key 是否被 normalize
3. 旧卡片是否命中兼容映射

当前仍保留的旧 intent key 兼容：

- `workspace.choose_model -> workspace.choose_agent`
- `workspace.apply_model -> workspace.apply_agent`

### 任务卡停在 `[Created]`

先判断是不是旧进程没重启。

当前正确行为应该是：

- 任务开始后先切 `[Running]`
- 若暂时没正文 delta，则显示 `Waiting for agent output...`
- 有 delta 后再持续更新

### 终态卡被 running 卡覆盖

这类问题优先看 [`poco/task/notifier.py`](/Users/yihanc/project/PoCo/poco/task/notifier.py)。

当前设计是：

- notifier 更新前会取 freshest task
- terminal state 比旧 running 快照更权威

### stop 后没进入 `[Stopped]`

优先检查：

- runner 是否真的支持 `cancel`
- task 是否被后续旧快照覆盖

当前 `codex / claude / cursor` 都已实现最小 `cancel()`，但稳定性仍以 Codex 最好。

## 4. 当前主要 HTTP 接口

- `GET /health`
- `POST /platform/feishu/events`
- `POST /platform/feishu/card-actions`
- `POST /demo/command`
- `POST /demo/tasks/{task_id}/approve`
- `POST /demo/tasks/{task_id}/reject`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `GET /debug/feishu`
- `GET /demo/cards/dm/projects`
- `POST /demo/card-actions`

## 5. 默认存储

默认是 sqlite：

- 路径默认 `~/.poco/poco.db`

保存内容：

- projects
- sessions
- tasks
- workspace_contexts

删除 project 时，以上本地状态会一起清理。
