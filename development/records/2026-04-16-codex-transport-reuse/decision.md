# Decision

## 待选问题/方案

- 方案 A：只做 idle 放宽（最小改动）
- 方案 B：只做 pre-warm（不动 idle）
- 方案 C：两个都做，idle 放宽到 30min + 增加 `warm()` API + 挂一两个 card 动作 hook 点
- 方案 D：做更激进的"进程级持久化 / 跨 PoCo 重启复用"（需要 codex CLI 支持，本轮范围外）

## 当前决策

采纳 **方案 C**。

### 改动点

#### 1. idle 可配置

- `poco/config.py::Settings` 新增 `codex_transport_idle_seconds: int`
  - 默认 **1800**（30 min），通过 `POCO_CODEX_TRANSPORT_IDLE_SECONDS` env 覆盖
- `poco/agent/factory.py::create_agent_runner` 新增同名参数，注入 `CodexAppServerRunner`
- `poco/main.py` 从 `settings` 读取并传入

#### 2. 后台 warm API

- `CodexAppServerRunner.warm(workdir, reasoning_effort)`：
  - 幂等：同 key 已有活 transport 或正在被 warm → 立即 return
  - 否则后台 daemon 线程内执行 `_start_transport`，完成后写入 cache
  - 完整吞掉失败（log INFO，不抛）
- `MultiAgentRunner.warm(backend, workdir, reasoning_effort)`：按 backend_key 分发；对不支持 warm 的 backend 是 no-op
- `TaskController.warm_runner_for_project(project)`：封装 project → (backend, workdir, reasoning_effort) 映射逻辑，给卡片层调用

#### 3. 挂 hook 点

**只挂一个**：`workspace.apply_agent`（card 中用户点 "Apply" 应用 agent 设置之后）。

理由：这是最强的"即将发起任务"信号，也正好是用户改了配置可能导致 cache key 变化的那一刻。再多挂会过度复杂化首轮。

### 不改的部分

- 其他 backend 的 runner 和 factory 参数
- codex protocol / codex CLI
- `_acquire_transport` / `_release_transport` 主链路（warm 不走这条路径，独立走后台 path）
- Settings 里其他字段

## 为什么这样选

- **方案 A 不够**：idle 拉长对"回头再用"有效，对"第一次"无效
- **方案 B 不够**：没 hook 也没用；而且 idle=300s 下 warm 完很快又被回收
- **方案 C 刚好**：一个参数 + 一个 API + 一个 hook，价值覆盖率最高
- **方案 D 本轮外**：跨进程持久化要改 codex CLI

## 为什么不选其他方案

- 方案 A/B 见上
- 方案 D：本轮范围外

## 风险

- **内存**：`idle=1800` 下每个活 project workdir 常驻一个 codex 进程（~30-50MB）。对日常 5-10 project 用户合计 150-500MB。可通过 env 降回 300 规避
- **并发竞争**：warm 启动 + 真实 task 的 `_acquire_transport` 并发时可能产生重复 start。用"后到的清理自己的副本"策略，语义不出错
- **hook 误发**：apply_agent 后用户不再发任务 → warm 浪费一次 cold start + 常驻 30min。成本可接受
- **线程模型**：warm 用 daemon Thread，进程退出时自动清理

## 后续影响

- 若后续 cursor / coco 也需要 pre-warm，`warm` API 已经是 `MultiAgentRunner` 级别的，直接扩展
- 若需要更多 hook 点（`task.open_composer` 等），加在 card_handlers 里即可，不动 API
