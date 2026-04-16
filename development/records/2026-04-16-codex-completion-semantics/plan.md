# Plan

- 为 `CodexAppServerRunner` 补最小完成状态机，区分显式终态、候选终态、长静默兜底
- 新增回归测试覆盖：
  - `idle` 后仍有后续输出时不能提前完成
  - 只有 delta 且没有 terminal event 时也能最终收口
- 跑相关 runner / controller / dispatcher 测试
- 根据结果补 validation
