# Need

## 背景

经过多轮 card-first 设计收敛后，PoCo 已经具备进入代码实现的前置条件。此时最合理的第一步不是直接接飞书卡片回调，而是先落平台无关的交互协议骨架。

## 需求信号

- 需要开始实现 card-first 设计
- 需要先落稳定的数据结构和 dispatcher
- 需要避免一开始就把飞书平台细节写进核心逻辑

## 来源

- 前序多轮设计 record 已完成，且用户明确要求继续

## 场景

- 后续飞书卡片回调进入系统时，需要先转换成统一 `ActionIntent`
- handler 执行完后，需要返回统一 `IntentDispatchResult`
- 平台层需要消费统一 `PlatformRenderInstruction`

## 频率/影响

这一步是 card-first 实现的第一块真正代码基础，会影响后续所有卡片接入。

## 备注

当前目标是骨架，不是飞书卡片端到端可用。
