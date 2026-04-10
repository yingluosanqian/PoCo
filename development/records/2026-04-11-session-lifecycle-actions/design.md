# Design

## 入口

仅在 group workspace 首卡上提供 session lifecycle 动作。

原因：

- session 是 group workspace 下的连续工作流对象
- DM 仍负责 project 级控制面

## 动作语义

### New Session

- 关闭旧 active session
- 创建新 active session
- 刷新当前 workspace card

### Close Session

- 关闭当前 active session
- 刷新当前 workspace card
- 不创建 replacement session

## 与现有消息语义的关系

- group 普通文本消息仍是主 prompt 入口
- 若当前无 active session，下一条 prompt 自动创建新的 active session
