# Decision

## 待选问题/方案

- 方案 A：实现时按卡片各自携带字段，各自找 handler
- 方案 B：定义统一 payload 包装层，明确 handler ownership，并对写操作设幂等约束
- 方案 C：先实现 happy path，再补幂等和边界

## 当前决策

采用方案 B。

PoCo 的卡片回调在实现层应遵守三条原则：

- 使用统一 payload 包装层
- 使用明确的 handler ownership
- 对会改变状态的动作默认要求幂等

## 为什么这样选

- 这最符合当前已经建立的结构化交互方向
- 这能提前压住审批、重复提交和回调重试的风险
- 这避免在实现时再把 project、session、task 搅成一层

## 为什么不选其他方案

- 不选方案 A：最终会变成按卡片散落协议
- 不选方案 C：会把高风险行为留到代码已扩散后再修

## 风险

- payload 包装层若设计过重，会拖慢实现
- 某些只读动作的幂等要求可能显得多余，需要区分读写级别

## 后续影响

- 下一轮实现应从 card action dispatcher 和 intent handler registry 入手
- task 类写操作需要默认幂等检查
- 读动作和导航动作可走轻量路径
