# Problem

## 背景

前面的设计已经完成，但如果没有先把平台无关的协议对象和 dispatcher 骨架写出来，后续飞书卡片接入很容易直接耦合到平台实现里。

## 相关需求

- 平台无关的卡片交互协议
- 稳定的 dispatcher 骨架
- 最小幂等缓存

## 当前状态

- 当前系统已有文本命令交互，但没有 card-first 协议代码
- 当前还没有 `ActionIntent`、`IntentDispatchResult`、`PlatformRenderInstruction`
- 当前没有 `CardActionDispatcher`

## 问题定义

PoCo 当前缺少 card-first 交互的最小平台无关代码骨架，导致前面的设计无法进入受控实现。

## 为什么这是个真实问题

- 没有骨架，后续只能直接把卡片回调写进飞书适配层
- 没有 dispatcher，handler 边界无法通过代码验证
- 没有最小幂等缓存，重复点击和回调重试无法演练

## 不是什么问题

- 不是“马上把卡片端到端跑起来”的问题
- 不是“完成所有 handler 实现”的问题
- 不是“替换现有文本命令入口”的问题

## 证据

- 当前代码树中不存在 card-first 核心对象和 dispatcher
- 前序设计 record 已经把这些对象定义为下一步实现起点
