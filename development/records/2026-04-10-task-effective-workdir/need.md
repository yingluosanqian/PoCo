# Need

## 背景

`Use Default`、`Enter Path` 和 `Choose Preset` 都已经成为真实写路径，但这些变更还只停留在 in-memory workspace context。

## 需求信号

- 用户已经能在群里切换当前 workdir
- 如果 task 执行仍只使用全局 `POCO_CODEX_WORKDIR`，这些切换就只是 UI 状态

## 场景

- 用户在 project 群里把当前工作面切到某个目录
- 随后在同一个群里发起 `/run ...`
- 期望 server-side agent 真正在这个目录下执行

## 影响

这一步决定 PoCo 的 workdir 交互是否从“能选”变成“真的会影响执行”。
