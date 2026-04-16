# Problem

## 背景

见 `need.md`。

## 相关需求

- 减少用户可感知的 codex 冷启动延迟
- 不破坏现有 transport 复用（cache key 为 `(workdir, reasoning_effort)`）语义

## 当前状态

### 冷启动路径（`CodexAppServerRunner._start_transport`）

```
subprocess.Popen([codex, app-server, --listen, stdio://])   # 启 codex 进程 + MCP servers
  ↓
_CodexAppServerSession.initialize()                         # JSON-RPC initialize 同步等响应
  ↓
_execute_prompt: thread/start (或 resume) → turn/start      # 另外两个同步 round-trip
```

主要延迟在前两步。第三步通常很快。

### 现有缓存机制

- `_transports: dict[(workdir, reasoning_effort), _CodexAppServerTransport]`
- `_acquire_transport`：同 key 活 transport → 直接复用；否则 `_start_transport`
- `_collect_idle_transports_locked`：扫描超过 `transport_idle_seconds=300`（硬编码）未用的 transport，回收
- 进程死亡检测：`process.poll() is not None` → 从 cache 剔除

### 两个具体缺口

1. **idle=300s 对多数用户过短**。PoCo 是消息驱动的异步工具，用户行为天然 bursty（发一批 → 等结果 → 再发一批）。5 分钟间隔 >> hot-path gap 的 5s，实际场景下"我刚才还在用，再回来又冷起了"频繁发生。

2. **首次任务没有预热**。对同一个项目，用户**第一次**发消息必然冷起。即使 idle 拉长，首次仍然挨打。典型任务路径里存在几个用户可观察的"意图信号"（选了 agent、打开 composer），在这些点启动后台预热，能把第一次任务的等待也消掉。

## 问题定义

**PoCo 当前的 codex 复用是被动的，只在已有 transport 的前提下受益；对 idle 超时和首次任务两类场景没有主动策略。**

## 为什么这是个真实问题

- 用户明确反馈
- 冷启动延迟 2-5s 乘以每天十几次的使用频率，合计分钟级的隐形成本
- 修改成本可控（不动协议、不动其他 backend、主要是本地 runner 层面）

## 不是什么问题

- 不是"codex 协议本身慢"：冷启动就是重量级，无法简化
- 不是"现有 transport 复用有 bug"：主链路已经工作
- 不是"要跨 backend 通用"：用户只点名 codex

## 证据

- `poco/agent/codex_app_server.py:65` `transport_idle_seconds: float = 300.0` 硬编码默认
- `poco/agent/codex_app_server.py:563-596` `_start_transport` 在 cache miss 时同步执行完整冷启动链
- 无任何主动预热机制
