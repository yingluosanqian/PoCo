# Problem

## 当前状态

- `Enter Path` 已经有卡片入口
- 但还不能把用户输入真正写回当前群工作面的 workdir 上下文

## 问题定义

PoCo 当前缺少第二条真实 workdir 写路径，导致用户虽然已经能看到 `Enter Path`，却仍不能把手工目录真正应用到当前 workspace context。

## 不是的问题

- 不是现在就实现完整路径校验和权限模型的问题
- 不是现在就处理 preset / recent 同步写入的问题
