# Need

## 背景

`Use Default` 已经成为第一条真实 workdir 写路径，但群工作面的 fallback 路径 `Enter Path` 还只是只读卡。

## 需求信号

- 上一轮之后，最自然的下一步就是把 `Enter Path` 也变成真实写路径
- 这比先做 `Preset` 或 `Recent` 更直接，也更能验证群侧 workdir 切换是否真的可用

## 场景

- 用户在 `Workdir Switcher Card` 中点击 `Enter Path`
- 输入一个目录
- 当前群工作面的 workdir 状态被更新为手工指定路径

## 影响

这一步决定群工作面的 fallback workdir 路径是否真正成立。
