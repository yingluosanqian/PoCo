# Need

## 背景

`Use Default` 和 `Enter Path` 已经成为真实写路径，但 `Choose Preset` 仍然缺少最小 preset 存储与应用链。

## 需求信号

- 群里的 `Choose Preset` 已经有入口
- 如果没有 project-level preset 存储，它仍然只是空壳

## 场景

- 用户在 DM 中管理某个 project 的常用目录
- 用户在群里从这些 preset 中选择一个并应用到当前 workspace context

## 影响

这一步决定 PoCo 的 workdir 切换是否从“默认 / 手输”扩展为更可复用的 project-level 目录集合。
