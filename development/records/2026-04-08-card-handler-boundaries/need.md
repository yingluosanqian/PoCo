# Need

## 背景

统一 action intent 和 refresh mode 已经确定，但还没有回答更接近实现的问题：

- `ActionIntent` 的最小 payload 到底长什么样
- 哪类动作该由哪个 handler 处理
- 卡片回调的幂等和重复提交如何约束

## 需求信号

- 需要继续推进卡片实现前设计
- 需要把 action intent 从概念变成最小 payload
- 需要把 project、session、task 的 handler 边界写清楚

## 来源

- 当前 card action record 的残留问题

## 场景

- 用户重复点击 `Approve`
- 网络抖动导致飞书回调重试
- 同一张卡片上的不同按钮分别落到 project 或 task 相关逻辑

## 频率/影响

这一步会直接影响实现层的可维护性和正确性，尤其是审批类动作和重复回调处理。

## 备注

本轮仍然是实现前设计，不定义具体 Python 文件结构。
