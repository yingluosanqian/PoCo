# Problem

## 背景

PoCo 当前虽已有 card gateway 和 renderer，但它们只停留在 demo / callback 层，没有接入真实飞书消息发送链路。

## 当前状态

- Feishu HTTP client 只能发送文本消息
- DM 消息入口仍然走文本回复
- renderer 产出的是内部调试结构，不是可直接发送的飞书卡片 JSON 2.0

## 问题定义

PoCo 当前缺少从 DM 消息事件到真实 Feishu interactive card 发送的闭环，导致用户在飞书单聊里无法看到 card-first 入口。

## 为什么这是个真实问题

- 看不到真实卡片，就无法验证 card-first 是否真的进入正式交互面
- 用户会误判为服务没有更新或飞书接入仍不可用

## 不是什么问题

- 不是完整群工作区 card 体系没做完的问题
- 不是卡片所有交互按钮必须同时完成的问题
