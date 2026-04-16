# Problem

## 背景

见 `need.md`。PoCo 所有 backend 都通过 `subprocess.Popen(..., env=os.environ.copy())` 起子进程，env 来源完全由 PoCo 自身进程的环境决定。

## 相关需求

- 排障时能快速判断"某个环境变量有没有被 PoCo 继承到"
- 不引入新依赖，不改动 backend 启动方式

## 当前状态

- `/health` 只暴露 `feishu_enabled` / `agent_backend` / `agent_ready` 等运行时状态，不暴露环境变量
- `/debug/feishu` 只展示飞书相关的 inbound/outbound 活动
- `poco status` 也只展示服务是否运行
- 用户要查环境只能 ssh 到服务器 `cat /proc/<pid>/environ | tr '\0' '\n'`，成本高

## 问题定义

**PoCo 进程当前看到的、会传给 backend 子进程的"关键环境变量"，对外没有任何可观测入口。**

这导致：

- 首次部署 PoCo 到新机器时，每次都要盲调 10 分钟
- 任何"我明明 export 了但 PoCo 好像没看到"的怀疑都得靠外部工具验证
- 飞书里看到 task 卡住时，没有快捷路径区分是"环境继承问题"还是"backend 自身问题"

## 为什么这是个真实问题

- 已经出现了至少两次真实排障轮次（claude 慢 / codex MCP 启动失败）都卡在这个点
- 随着 backend 数量增加（已经四个），环境变量集合只会更多
- 一个新接入 bytedance 内网部署的用户会立刻踩
- 和 `purpose.md` 里"让用户在手机上能可靠判断 task 状态"直接相关：看不到环境就没法快速得出判断

## 不是什么问题

- 不是"PoCo 应该帮用户 source `.bashrc`" —— 那是更大的配置路径问题
- 不是"应该把所有环境变量暴露出来" —— 会泄漏密钥
- 不是"应该做一个完整的运维 dashboard" —— 超出当前阶段

## 证据

- `poco/agent/runner.py` 中四个 backend 的 subprocess 启动代码：
  - codex: `runner.py:795` `env=os.environ.copy()`
  - claude_code: `runner.py:1019` `env=env`（以 `os.environ.copy()` 为基础）
  - cursor_agent: 同样模式
  - coco: 同样模式
- `poco/main.py:237-293` `/health` 端点当前不含任何环境变量信息
- 2026-04-16 两次诊断会话中，最终都绕回"需要看 PoCo 进程的环境"
