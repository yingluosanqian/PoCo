# Need

## 背景

`agent` 与 `working dir` 的 ownership 已经被定义，但用户还没有一套具体、低摩擦、卡片优先的操作面去完成这些选择。

## 需求信号

- 用户已经认可：
  - `agent` 更固定
  - `working dir` 更灵活
- 下一步需要把这个判断落成真实卡片信息架构

## 场景

- 用户在 DM 中进入某个 project，希望看到当前 agent、repo、default workdir，并能进入相应配置入口
- 用户在群里进入 workspace，希望快速确认当前 agent 和当前 workdir，并在不离开工作面时切换目录

## 影响

如果没有合适的卡片 IA，前一轮的 ownership 决策仍然只是抽象，而不是实际可用的产品行为。
