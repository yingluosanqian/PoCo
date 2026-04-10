# Decision

采纳“群消息默认即 prompt”的交互决策。

具体为：

- `DM` 仍然是 control plane，不默认把普通消息当成 task prompt
- 已绑定 project 的 `Group` 里，普通文本消息默认按 task prompt 处理
- 显式斜杠命令保留给少数操作语义，例如帮助、查看状态、确认或拒绝
- `Run Task` 卡片不再是正式主入口，而是辅助入口或降级入口

## 影响判断

这轮影响是中等，不是底层重写。

原因：

- 现有 `FeishuGateway -> InteractionService -> TaskController -> Dispatcher` 文本链已经存在
- 群消息当前已经能通过 `/run ...` 直接发任务
- 主要变化集中在“文本如何被解释”，而不是任务状态机、调度器或 agent runner

之所以仍需要设计记录，是因为它会改变正式交互模型中的默认语义：

- Group 从“卡片驱动发任务”转向“对话驱动发任务”
- Card-first 从“卡片承载主输入”调整为“卡片承载管理、状态和确认”

## 当前明确不做

- 不把 DM 普通消息也默认当成 prompt
- 不取消所有斜杠命令
- 不把卡片完全删除
- 不把群内所有消息类型都当成 prompt，当前仅限普通文本消息
