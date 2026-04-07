# Problem

## 背景

只有协议对象和 dispatcher 还不够，PoCo 仍然缺少最小业务链路去证明 card-first 设计能真正驱动 project 管理动作。

## 相关需求

- 最小 DM card project 管理链路
- 最小 Feishu card gateway
- 最小 renderer

## 当前状态

- 已有平台无关协议对象和 dispatcher
- 尚无 project 领域模型、card handlers、renderer 和 card action gateway

## 问题定义

PoCo 当前缺少一条最小 DM card 业务链路，导致 card-first 实现仍停留在协议层，无法验证 project 管理交互是否真的成立。

## 为什么这是个真实问题

- 没有最小链路，就无法判断设计是否真的能走通
- 飞书平台适配和业务 handler 的边界还没有在代码中被验证

## 不是什么问题

- 不是完整 project lifecycle 全实现的问题
- 不是群工作区全部打通的问题

## 证据

- 当前代码中还没有 project controller、renderer、card gateway
