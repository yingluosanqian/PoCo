# Need

## 背景

PoCo 已经开始具备 `DM -> create project -> create group -> workspace card` 的主链路，但用户还没有被正式赋予“如何选择 agent、如何选择 working dir”的可用交互。

## 需求信号

- 用户明确提出需要设计 `working dir` 和 `agent` 的选择方式
- 用户已经判断这两者性质不同：
  - `agent` 更固定，切换后容易丢失上下文
  - `working dir` 相对灵活

## 场景

- 用户创建一个新 project 时，需要决定默认使用哪个 agent
- 用户在群里推进某一轮工作时，需要决定当前在什么目录下工作
- 用户后续可能需要切换目录，但不应轻易切换 agent

## 影响

这一步决定 PoCo 的执行上下文配置是清晰、连续、低摩擦，还是会把管理面和工作面重新搅混。
