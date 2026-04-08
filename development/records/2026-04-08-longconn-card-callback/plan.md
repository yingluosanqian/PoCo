# Plan

## 范围

- 自定义 long-connection ws client 处理 `CARD` 帧
- 注册 `p2.card.action.trigger`
- 将 card callback 路由到 `FeishuCardActionGateway`
- 补测试与最小文档

## 验收标准

- 长连接 listener 可处理消息事件和 card callback
- 测试通过
- README 与运行态 warning 不再声称卡片回调只能走 HTTP
