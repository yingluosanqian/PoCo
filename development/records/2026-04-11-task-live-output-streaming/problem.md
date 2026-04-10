# Problem

PoCo 当前虽然已经有 task status card，但运行中的状态仍然过于粗粒度。

用户主要只能看到：

- created
- running
- waiting_for_confirmation
- completed / failed

这会让运行期体验接近黑箱等待。

真正的问题不是“有没有 running 状态”，而是：

系统还没有把 agent 运行中的增量输出传到用户面前。
