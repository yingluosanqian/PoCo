# Plan

## 范围

- 在飞书卡片 JSON 2.0 中加入真实 callback 按钮
- 修正 callback 请求的 `event_id` 幂等读取
- 补测试与最小文档

## 验收标准

- DM 首页卡片包含真实 `callback` 按钮
- `Create Project` 点击后返回 project detail card
- 写操作按飞书顶层 `event_id` 幂等
