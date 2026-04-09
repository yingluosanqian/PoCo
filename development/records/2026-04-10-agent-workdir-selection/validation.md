# Validation

## 验证方法

- 对照当前已批准的 `DM control plane + group workspace` 模型做一致性检查
- 对照当前 card-first 方向检查交互面是否清晰分层
- 手工审查 `agent` 与 `working dir` 是否被赋予不同 ownership 和切换规则

## 结果

- `agent` 被收敛为 project 级慢变量
- `working dir` 被收敛为 session 级快变量
- DM 与群的交互职责边界清楚，没有重新混合管理面和工作面
- 方案为后续 `session` 和 workspace card 设计提供了稳定方向

## 是否通过

通过当前轮设计目标。

## 残留问题

- session 模型还未落地到代码
- `agent migration` 的告警与交互仍需单独设计
- `workdir presets` 的具体卡片信息架构仍需下一轮细化
