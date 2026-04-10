# Need

## 背景

群文本 `/run` 已经会继承当前 workspace workdir，但 card-first 主交互面还没有正式发任务入口。

## 需求信号

- group workspace 首卡已经存在
- 用户已经可以在群卡里切 workdir
- 如果发任务仍只能退回文本命令，card-first 交互就没有闭环

## 场景

- 用户在群工作区卡片上确认当前 workdir
- 直接在卡片里输入任务
- 提交后让任务异步进入执行，并继承当前 workdir

## 影响

这一步决定 PoCo 是否开始从“群卡片看状态 + 文本 fallback 发任务”进入真正的 card-first 工作流。
