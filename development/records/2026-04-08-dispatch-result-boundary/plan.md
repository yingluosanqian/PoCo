# Plan

## 目标

定义业务层到平台层之间的最小结果边界，为实现阶段保持平台解耦提供稳定接口。

## 范围

- 定义 `IntentDispatchResult`
- 定义 `PlatformRenderInstruction`
- 定义两者的关系
- 定义哪些信息属于业务层，哪些属于平台层

## 不在范围内的内容

- 具体飞书卡片 JSON
- 模板语言设计
- 具体 Python 模块命名

## 风险点

- 结果结构可能过于泛化
- 视图模型和渲染指令之间可能重复
- 平台层可能仍然残留业务判断

## 验收标准

- 已明确 dispatcher 返回什么
- 已明确平台层消费什么
- 已明确 view model 和 render instruction 的边界
- 可作为下一轮正式实现的输入

## 实施顺序

1. 固化 need/problem/decision
2. 形成 result boundary design
3. 回写稳定层 design 摘要
4. 下一轮进入实现层
