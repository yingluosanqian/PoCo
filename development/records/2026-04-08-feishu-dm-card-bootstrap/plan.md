# Plan

## 目标

让真实飞书单聊收到首页卡片。

## 范围

- Feishu HTTP client 增加 interactive card 发送
- Feishu renderer 改为真实 card JSON 2.0
- DM 消息入口在单聊中主动回 project list card
- 自动化测试
- 最小 README / state / validation 更新

## 不在范围内的内容

- 完整 project lifecycle card 动作
- 群工作区完整 card 交互
- 真实飞书端到端人工联调结论

## 验收标准

- DM 消息事件可走 interactive card 发送分支
- renderer 输出真实飞书 card JSON 2.0
- 群聊文本 fallback 不被打坏
- 相关测试通过
