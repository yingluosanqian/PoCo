# Problem

## 当前状态

- `Workdir Switcher Card` 已经存在
- 但其动作还没有真实写入路径

## 问题定义

PoCo 当前缺少第一条真正会修改群工作面 workdir 状态的路径，导致 `working dir = session stance` 虽然已经进入卡片交互，但还没有形成真实可写上下文。

## 不是的问题

- 不是现在就完成完整 session 模型的问题
- 不是现在就完成 preset / recent / manual path 全量写入的问题
