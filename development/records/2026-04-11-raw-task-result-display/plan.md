# Plan

本轮范围聚焦在结果展示主链。

## 范围

- 为 task 增加原始结果字段
- 调整 runner / controller，把完成结果写入 `raw_result`
- 调整 task card，默认展示原始结果
- 为超长结果增加最小分页
- 从 workspace 首卡移除 latest result preview

## 不在范围内

- richer timeline
- 真正的流式输出
- 多媒体结果展示
- 完整 session continuity

## 验收标准

- 完成态 task card 不再依赖 `result_summary` 作为主结果内容
- 超长原始结果能分页浏览
- workspace 首卡不再承担结果正文展示
