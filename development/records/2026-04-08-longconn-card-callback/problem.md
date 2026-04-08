# Problem

## 当前状态

- Feishu 消息事件已走长连接
- 但卡片点击没有进入 PoCo

## 根因

- 当前使用的 Python SDK 在 ws client 中对 `MessageType.CARD` 直接返回，未进入事件处理链
- 因此 `p2.card.action.trigger` 没有被分发到 PoCo 的 card gateway

## 问题定义

PoCo 当前的长连接实现只完整支持消息事件，不完整支持 card callback，导致 card-first 交互在真实飞书里中断。
