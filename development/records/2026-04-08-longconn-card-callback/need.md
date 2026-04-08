# Need

## 背景

PoCo 已使用 Feishu 长连接接收入站消息，但卡片点击仍失败。

## 需求信号

- 用户明确要求长连接模式
- 对 C 产品不能要求额外公网 callback 地址

## 场景

- 用户在 Feishu 单聊中点击 DM 首页卡片按钮
- PoCo 应在同一条长连接链路内收到 card callback

## 影响

如果卡片点击还依赖公网 HTTP callback，PoCo 的移动端接入模型就不成立。
