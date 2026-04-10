# Validation Layer

## 本层定义

本层负责判断这次变更是否真的让系统更接近项目目的。

验证不等于只跑测试。测试只是验证手段之一。

## 本层关注的问题

- 变更是否达到了本轮目标
- 风险是否真的被控制住
- 残留问题是什么
- 是否需要回滚、补做或继续迭代

## 输入

- 计划中的验收标准
- 实现结果
- 测试结果
- 运行观察
- 手工检查结论

## 输出

- 验证结论
- 是否通过
- 残留问题
- 是否需要继续迭代或回滚

## 禁止事项

- 不要把“代码已写完”当作验证通过
- 不要把测试通过等同于目标达成
- 不要忽略未验证区域
- 不要在验证失败时假装进入完成状态

## 进入下一层的条件

本层通常输出回流到 `state`，并为下一轮 `needs/problems` 提供事实基础。

只有在以下条件满足时，才可视为本轮闭环：

- 已给出明确结论
- 已说明是否通过
- 已记录残留问题
- 已说明下一步是结束、继续迭代还是回滚

## 测试和验证的区别

- 测试关注某个实现是否按预期运行
- 验证关注这次变更是否真的解决了本轮要解决的问题

测试可以通过，而验证仍然失败。

## 应记录的最少结论

- 验证目标
- 验证方法
- 结果
- 是否通过
- 残留问题
- 是否需要回滚或继续迭代

## PoCo 当前验证方向

### 当前轮验证重点

- Python MVP 骨架是否与已批准设计一致
- 最小任务状态流是否可执行
- 人工确认闭环是否至少在 stub 层成立
- 飞书 callback 校验与文本消息回发链路是否已经具备真实接入第一层能力
- Codex-first 执行器是否已经具备最小真实调用能力
- 后台调度与关键状态主动回推是否已经成立
- 本地 demo 联调入口是否足以支撑脱离飞书的反复验证
- card-first 的最小平台无关骨架与 DM card 链路是否已经成立
- DM 消息事件是否已经能触发真实 interactive card 下发
- DM 首页卡片上的真实 callback 动作是否已经成立
- `project.create` 是否已经能在真实飞书模式下同步建群并完成失败回滚
- 建群成功后是否已经能向新群投递第一张 workspace overview card
- DM `Project Config Card` 是否已经替代旧 detail 视图，并提供只读配置入口
- Group `Workdir Switcher Card` 是否已经从 workspace 首卡进入，并提供只读目录切换入口
- `workspace.use_default_dir` 是否已经成为第一条真实可写的群侧 workdir 路径
- `workspace.apply_entered_path` 是否已经成为第二条真实可写的群侧 workdir 路径
- `project.add_dir_preset` / `workspace.apply_preset_dir` 是否已经形成最小 preset 写链路
- group 文本 `/run` 是否已经把当前 workspace context 固化到 task 的 `effective_workdir`
- 已绑定 project 的 group 普通文本消息是否也已经默认创建 task
- Codex runner 是否已经优先使用 task 级 workdir
- group workspace card 是否已经具备 `Run Task` 入口
- `task.submit` 是否已经继承当前 workspace workdir 并触发异步派发
- notifier 是否已经发送 `task_status` interactive card
- `task.approve` / `task.reject` 是否已经接入 card callback 主链
- notifier 是否已经优先原位更新已有 task status card
- `task.submit` 是否已经直接替换当前 composer card 为 `task_status`
- workspace 是否已经提供 latest task 入口
- task 状态变化时 workspace latest task 区块是否也会同步刷新
- task status 是否已经优先展示原始结果而不是摘要
- 超长原始结果是否已经支持分页

### 当前轮已知未验证区域

- 真实飞书客户端是否已稳定看到 DM 首屏卡片
- 飞书卡片回调更新与完整 renderer 工作流
- 真实飞书环境里的建群权限、群名称策略和群内 workspace bootstrap
- 群内 workdir switcher card 与真实目录切换
- workspace / composer / task card 之间更完整的更新策略与 richer result 视图
- 群工作区卡片与 project/session/task 完整 handlers
- 飞书加密事件体
- 真实网络条件下的飞书端到端联调
- 真实 agent 执行与长任务管理
- 服务重启后的后台任务恢复
