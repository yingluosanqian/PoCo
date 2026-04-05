# Records

`records/` 用于保存每一次值得追溯的演进实例。

## 组织方法

每一轮值得追溯的变更，应建立独立目录。

推荐命名方式：

- `YYYY-MM-DD-short-topic/`

例如：

- `2026-04-05-bootstrap-governance/`
- `2026-04-12-auth-session-model/`

## 一个 record 目录通常包含

- `need.md`
- `problem.md`
- `decision.md`
- `plan.md`
- `design.md`
- `validation.md`

并不是每次都必须六个文件齐全，但至少应保留足以追溯本轮选择的最小集合。

## 什么内容应进入 records

- 被采纳的问题定义
- 被采纳的决策
- 本轮计划
- 被采纳的设计
- 验证结论

## 什么内容不应进入 records

- AI scratch
- 临时草稿
- 候选废案
- 一次性运行日志
- 原始运行产物
- 中间分析文件

这些内容应进入本地临时目录：

- `.tmp/`
- `.work/`
- `artifacts/local/`

## 使用建议

建立 record 时，先从模板复制：

- `development/templates/*.template.md`

记录要尽量短，但必须足以回答：

- 为什么这一轮值得做
- 做了什么选择
- 为什么这样选
- 最后验证结果如何
