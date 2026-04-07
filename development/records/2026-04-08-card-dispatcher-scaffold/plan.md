# Plan

## 目标

实现 card-first 交互的最小平台无关代码骨架。

## 范围

- 新增 `ActionIntent` 等数据结构
- 新增 `CardActionDispatcher`
- 新增最小幂等缓存
- 新增 render instruction builder
- 新增最小自动化测试

## 不在范围内的内容

- 飞书卡片回调接入
- project/session/task 真实 handler 实现
- renderer 真实输出飞书卡片

## 风险点

- 结构过度抽象
- 测试只验证骨架，不验证真实平台行为

## 验收标准

- 平台无关协议对象已落地
- dispatcher 能路由、缓存写操作结果、拒绝未知 intent
- render instruction builder 能把业务结果转成平台指令
- 测试通过

## 实施顺序

1. 落数据结构
2. 落 dispatcher 与幂等缓存
3. 落 render instruction builder
4. 补测试和验证
