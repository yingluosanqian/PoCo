# Plan

## 目标

把 PoCo 的正式交互模型修正为“单聊管理 project，群承载 project 执行”，为后续 project lifecycle 和 group binding 实现提供清晰边界。

## 范围

- 定义 DM 与群聊的职责分工
- 定义 project 创建、建群、绑定在交互模型中的位置
- 定义与 `project -> session -> task` 的衔接关系

## 不在范围内的内容

- 完整 project 后台界面
- 复杂 project 权限系统
- 立即实现全部 project 管理命令
- 取消群作为正式执行空间

## 风险点

- 若 DM 命令面铺得太大，会重新引入复杂度
- 若建群与绑定流程定义不清，正式模型仍然无法落地
- 若没有明确单聊与群聊的默认行为，后续实现会出现入口漂移

## 验收标准

- 已明确 DM 是 control plane，群是 project workspace
- 已明确 project 创建与 group binding 属于 DM 流程
- 已明确正式执行动作默认发生在 project 群中
- 稳定层已同步到这一轮修正后的交互模型

## 实施顺序

1. 固化 need/problem/decision
2. 形成最小设计说明
3. 回写稳定层中的决策、设计、计划、状态
4. 后续进入 project lifecycle 和 binding 的具体设计
