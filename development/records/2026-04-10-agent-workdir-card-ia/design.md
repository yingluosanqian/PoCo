# Design

## 设计目标

让用户在最少跳转下完成两件不同性质的事：

- 在 DM 中理解并管理 project 的长期执行配置
- 在群中快速确认并切换当前工作目录

## 1. DM Project Config Card

### 首屏必须展示的信息

- `Project Name`
- `Agent`
- `Repo Root`
- `Default Workdir`
- `Workspace Group`

这五项中：

- `Agent` 是最重要的慢变量，必须放在标题区下方第一组
- `Repo Root` 与 `Default Workdir` 是执行环境基线，应紧随其后
- `Workspace Group` 用于确认 project 是否已绑定真实工作区

### 首屏一级动作

- `Open Workspace`
- `Configure Agent`
- `Configure Repo`
- `Configure Default Dir`
- `Manage Dir Presets`

### 二级信息或二级动作

- `Recent Sessions`
- `Recent Directories`
- `Advanced: Migrate Agent`

这些不应进入首屏一级区，因为：

- 它们不是每次都需要
- 其中有些动作风险较高

### 关键交互原则

- `Configure Agent` 不应呈现为普通下拉切换，而应进入带提示的独立配置卡
- 当 project 已经存在活跃 session 时，卡片应强调当前 agent 变更是高成本动作

## 2. Group Workdir Switcher Card

### 首屏必须展示的信息

- `Project Name`
- `Current Agent`
- `Current Workdir`
- `Source`
  - `default` / `preset` / `recent` / `manual`

这里最关键的是：

- `Current Agent` 需要显示，但不提供一级切换
- `Current Workdir` 必须成为首要视觉焦点

### 首屏一级动作

- `Use Default`
- `Choose Preset`
- `Use Recent`
- `Enter Path`
- `Back To Workspace`

### 二级动作

- `Pin As Default` 不应放在群首屏一级区
- `Edit Presets` 不应放在群里，应回到 DM

### 关键交互原则

- 群里允许“切换当前站位”，不允许“重定义 project 基线”
- `Enter Path` 应被视为高级 fallback，而不是主路径
- 主路径应优先走 `default / preset / recent`

## 3. 两张卡之间的关系

- DM card 负责定义“长期配置”
- Group card 负责定义“当前站位”

因此它们不应相互复制全部信息。

正确做法是：

- DM card 展示完整 project config 摘要
- Group card 只展示当前执行真正需要知道的信息

## 4. 最小实现含义

如果后续进入实现，建议顺序是：

1. 先做 DM Project Config Card 的只读摘要和入口按钮
2. 再做 Group Workdir Switcher Card 的只读展示
3. 最后再接入真实切换动作

而不是一上来就开放自由输入路径。
