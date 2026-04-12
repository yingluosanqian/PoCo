# AI Repo Workflow

本文件是 AI 在本 repo 内工作的执行手册。

AI 不应把这里当建议，而应把这里当默认工作协议。

## 修改代码前必须先读

最少读取：

- `development/README.md`
- `development/developer-docs/README.md`
- `development/layers/purpose.md`
- `development/layers/constraints.md`

如果任务不是纯局部修正，还必须读取：

- `development/layers/problems.md`
- `development/layers/decisions.md`
- `development/layers/plan.md`
- 相关 `records/`

如果任务涉及结构或抽象变化，还必须读取：

- `development/layers/design.md`

## 先判断任务属于哪一层

### 属于 needs

特征：

- 用户表达诉求
- 外部环境变化
- 新的输入信号出现

此时不能直接实现。

### 属于 problems

特征：

- 已经能说明“为什么当前状态阻碍项目目的”
- 已经区分问题和噪声

此时仍不能直接实现。

### 属于 decisions / plan / design

特征：

- 已经有明确问题
- 需要在多个方向之间做取舍
- 需要约束范围、预算、接口或模块结构

此时通常仍不应直接跳到实现。

### 属于 implementation

只有在以下条件满足时才成立：

- 问题边界清楚
- 本轮做什么和不做什么清楚
- 风险可接受
- 验收方式清楚

## 什么时候不能直接进入实现

出现以下任一情况时，不能直接写代码：

- 任务会改变项目目标解释
- 任务会触碰约束边界
- 任务会改变外部行为但尚未定义问题
- 任务存在多个明显可选方案但未形成决策
- 任务会跨多个模块扩张，但尚未定义范围
- 任务需要新抽象或新接口，但尚未形成设计说明

## 什么时候必须新建 record

出现以下任一情况时，必须在 `development/records/` 建目录：

- 新功能
- 对外行为变化
- 边界变化
- 中等以上范围 bug 修复
- 跨模块改动
- 新设计被采纳
- 明确的技术决策需要追溯

推荐目录名：

- `YYYY-MM-DD-short-topic/`

## 什么时候必须停止并等待审批或确认

出现以下任一情况时，AI 应停止继续扩大实现：

- 需要改变 `purpose` 或 `constraints`
- 需要接受更高复杂度路径
- 需要引入破坏性变更
- 需要删除或迁移重要数据
- 需求信号不足，问题定义不成立
- 当前任务边界不清，继续实现只会放大问题

## 实现时的硬约束

- 不得把需求直接翻译成代码
- 不得在实现阶段偷偷重定义问题
- 不得扩大批准范围
- 不得把设计层问题留给实现层临时发挥
- 不得把临时分析和 scratch 文件提交进 repo

临时内容应进入：

- `.tmp/`
- `.work/`
- `artifacts/local/`

## 修改后必须更新什么

### 始终需要

- 验证结论

### 视情况需要

- 相关 `record` 中的 `plan`
- 被采纳的 `design`
- 新的 `decision`
- `state` 相关描述所依赖的证据

## Commit 规范

提交信息统一使用：

- `[xxx] ...`

执行要求：

- `[]` 内写本次提交的类型或主题标签，如 `feat`、`fix`、`docs`、`refactor`
- `[]` 后必须有一个空格，再写本次提交的简洁说明
- 不要把多个无关改动塞进同一个 commit
- 若当前工作尚未形成清晰边界，应先继续整理，不要急于提交
- 若当前工作已形成清晰里程碑，应及时提交，不要持续堆积未提交改动

示例：

- `[feat] bootstrap PoCo feishu-first Python MVP scaffold`
- `[fix] handle waiting task approval correctly`
- `[docs] define repository commit message format`

## 最小执行顺序

1. 读 `purpose` 与 `constraints`
2. 判断当前任务层级
3. 必要时创建 `record`
4. 只在满足进入实现条件时编码
5. 及时更新 `record`、稳定层文档和验证结论
6. 当前轮形成清晰边界后及时提交
7. 若验证失败，返回上一层重审，不强行继续实现
