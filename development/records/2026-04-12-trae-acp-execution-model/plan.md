# Plan

## 范围

- 为 `coco` 建立清晰的 ACP 执行模型
- 将 `Trae ACP` 协议适配从 `CocoRunner` 中拆出
- 明确当前 task 的输出归属与完成规则
- 修正子进程生命周期管理
- 用测试覆盖历史串台、完成收口、资源清理

## 不在范围内

- ACP 重连
- project 级常驻 server 复用
- 多 task 并发复用同一 ACP transport
- 改动其他 backend 的外部行为

## 主要风险

- Trae ACP 对“当前 prompt”的显式标识可能不足
- 若协议无法提供可靠 turn 边界，PoCo 必须采用更保守的展示策略
- 需要避免为了补 `coco` 而破坏已有 codex/claude/cursor runner

## 验收标准

- `coco` task 的输出只来自当前 prompt 对应的有效 update
- 已完整输出的 task 能可靠进入 `completed` 或 `failed`
- 运行多个 `coco` task 后，PoCo 不再因 runner 泄漏出现 `Too many open files`
- `stop` 仍可中断当前 task
- 相关测试能覆盖上述边界

## 实施顺序

1. 固化设计记录并更新 backend 文档中的现状描述
2. 抽出 `TraeAcpClient` 级别的协议与进程管理
3. 重新实现 `CocoRunner` 的 task 边界判定
4. 补单测与回归测试
5. 用真实本地 PoCo 进程验证 health、task 收口与群卡片更新

