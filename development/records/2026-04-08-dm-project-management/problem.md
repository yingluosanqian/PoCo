# Problem

## 背景

PoCo 需要同时支持 project 的长期管理和 project 内任务的持续执行。

上一轮“一个 project 一个群”解决了执行空间混乱的问题，但还没有定义 project 的管理动作应该落在哪个交互入口，导致用户在正式模型里仍缺少清晰的 control plane。

## 相关需求

- 在单聊里管理 project
- 在单聊里触发建群
- 在群里承接执行与协作

## 当前状态

- 当前 record 已把群定义为 project 的正式执行容器
- 当前系统尚未定义 project 的管理入口
- 当前设计还没有把单聊明确成 control plane

## 问题定义

PoCo 当前缺少一套清晰的“管理入口与执行空间分离”的交互模型，导致 project 的创建、建群、绑定和执行之间缺乏稳定分工。

## 为什么这是个真实问题

- 若没有独立的管理入口，用户仍需依赖手工流程去创建或记忆 project 绑定关系
- 若把管理动作也放进 project 群，会污染正式执行空间
- 这会直接影响后续 project lifecycle、group binding 和 session 归属设计

## 不是什么问题

- 不是“单聊是不是正式执行主路径”的问题
- 不是“立刻做完整 project UI 后台”的问题
- 不是“取消 project 群工作区”的问题

## 证据

- 发起人明确表达“我希望单聊管理项目，建群”
- 当前稳定层和上一轮 record 还没有定义单聊作为 control plane 的职责
- 当前系统代码中也还不存在 project 管理与 group 绑定模型
