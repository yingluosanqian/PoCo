# TUI 架构设计

这份文档描述的是 **PoCo 当前 TUI 的实际架构**。

它不讲迁移计划，不讲阶段划分，也不讲“以后可能怎么做”。这里只回答三件事：

- TUI 现在是怎么组织的
- 为什么这样组织
- 改 UI 或加功能时应该遵守什么约束

---

## 1. 产品模型

当前 TUI 只有两个顶层阶段：

1. `Bind Bot`
2. `Workspace`

也就是说，PoCo 的 TUI 不是传统的“根菜单 -> 子菜单 -> 配置页”模型，而是：

- 先绑定一个 bot
- 然后进入统一的工作区设置界面

这和产品本质更一致。

### Bind Bot

用于：

- 选择平台
- 选择已保存 bot
- 或输入新的 `APP ID / APP Secret`

当前支持的平台入口有：

- `Feishu`
- `Slack`
- `Discord`

其中只有 `Feishu` 已实现，其他平台只展示占位提示。

### Workspace

这是唯一的主工作界面。

工作区内的配置通过 section 切换完成，目前有 4 个 section：

- `Agent`
- `Bot`
- `PoCo`
- `Language`

不再存在单独的“根菜单页”。

---

## 2. 代码结构

当前 TUI 的核心文件是：

- [poco/tui/app.py](/root/project/pocket_go/poco/tui/app.py)
- [poco/tui/state.py](/root/project/pocket_go/poco/tui/state.py)
- [poco/tui/sections.py](/root/project/pocket_go/poco/tui/sections.py)
- [poco/tui/resources.py](/root/project/pocket_go/poco/tui/resources.py)

它们的职责如下。

### `app.py`

这是 Textual 外壳，也是当前 TUI 的主控制器。

负责：

- 组装左右面板、输入框、footer
- 接收键盘事件
- 根据当前状态决定渲染什么
- 调用配置服务读写配置
- 在绑定 bot 后原地切换 service/store
- 管理 choice editor、input editor、subview 的进入与退出

不负责：

- 定义 section 字段 schema
- 定义状态数据结构
- 管理旧式多层菜单系统

### `state.py`

定义 TUI 运行时状态：

- 当前 screen
- bind-bot 流程状态
- workspace 状态
- choice editor 状态
- input editor 状态
- 各 section 的选中位置、滚动位置、subview

### `sections.py`

定义各 section 的字段模型和显示规则。

负责：

- 一个 section 应该有哪些字段
- 每个字段是什么交互类型
- 哪些字段是只读
- 哪些字段打开子视图
- Claude backend 相关的字段如何组织

### `resources.py`

负责静态资源：

- logo
- CSS
- 中英文字典

---

## 3. 当前状态模型

当前状态以 [poco/tui/state.py](/root/project/pocket_go/poco/tui/state.py) 为中心。

核心结构可以概括成：

```python
AppState
├── screen
├── bind_bot
├── workspace
└── runtime
```

### `AppState`

顶层状态对象。

当前包含：

- 当前 screen
- bind-bot 状态
- workspace 状态
- runtime 摘要状态

### `ScreenKind`

当前只有两个值：

- `BIND_BOT`
- `WORKSPACE`

这是一条硬约束：**顶层 screen 不再扩张。**

像：

- `show config`
- Claude backend 管理
- Bot advanced

都不属于新的顶层 screen，而是 `Workspace` 内部的子视图。

### `BindBotState`

描述绑定 bot 的流程状态。

当前主要包含：

- 当前步骤
- 当前列表选中项
- 当前平台
- 已保存 bot 列表
- 新 bot 输入草稿

### `WorkspaceState`

描述工作区内的导航和编辑状态。

当前主要包含：

- 当前激活的 section
- 每个 section 的 `SectionState`
- 当前 choice editor 状态
- 当前 input editor 状态

### `SectionState`

每个 section 一份。

当前包含：

- `selected_index`
- `scroll`
- `subview`

这里的 `subview` 是 `Workspace` 内部的右侧替换视图，不是顶层 screen。

### `InputState`

用于底部输入框编辑。

当前不是一个简单字符串，而是一个完整编辑会话，包含：

- 当前字段 key
- 当前 label
- placeholder
- 是否是 secret
- 当前 buffer/value
- 多步骤输入时的 `steps`
- 当前步骤索引
- draft

这样可以支撑：

- 普通单字段输入
- `New Claude Backend` 这类多步骤输入

### `ChoiceState`

用于 choice editor。

包含：

- 当前字段 key
- 标签
- 候选项
- 当前选中项

### `RuntimeState`

用于左侧摘要栏。

当前主要反映：

- relay 是否运行
- relay 上次错误

---

## 4. section 设计

section schema 定义在 [poco/tui/sections.py](/root/project/pocket_go/poco/tui/sections.py)。

当前共有四个 section。

### Agent

当前分成两组：

- `Codex`
- `Claude`

#### Codex 组

包含：

- `Bin`
- `App Server Args`
- `Model`
- `Reasoning`
- `Approval Policy`
- `Sandbox`

#### Claude 组

包含：

- `Bin`
- `App Server Args`
- `Approval Policy`
- `Sandbox`
- `Manage Backends`
- `Backend Settings`

这里特别注意：

- `Manage Backends`
  - 是入口，用来切换 / 新增 backend
- `Backend Settings`
  - 是当前 backend 的配置入口

而像：

- `Base URL`
- `Auth Token`
- `Model`
- `Extra Env`

这些并不直接混在主列表中，而是在 `Backend Settings` 子视图里编辑。

### Bot

当前优先展示核心字段：

- `APP ID`
- `APP Secret`
- `App Name`
- `Alias`
- `Allow All Users`

如果 `Allow All Users = false`，才显示：

- `Allowed Open IDs`

高级字段放进：

- `Advanced`

当前高级项包括：

- `Encrypt Key`
- `Verification Token`
- `Card Template ID`

### PoCo

包含本地运行时相关设置：

- `Message Limit`
- `Initial Update Seconds`
- `Max Update Seconds`
- `Max Message Edits`
- `Show Config`
- `Restart Relay`

其中：

- `Show Config`
  - 是只读子视图
- `Restart Relay`
  - 是动作，不是配置值

### Language

当前只有：

- `Language`

---

## 5. 字段交互模型

字段并不是简单地靠“类型名字”区分，而是靠交互语义区分。

当前字段模型是：

```python
FieldDef(
    key: str,
    label: str,
    interaction: FieldInteraction,
)
```

`FieldInteraction` 当前有 5 种：

- `TextInput`
- `ChoiceSelect`
- `ActionTrigger`
- `SubviewOpen`
- `ReadOnly`

### `TextInput`

表示按 Enter 后进入底部输入框编辑。

支持：

- `secret`
- `validator`
- `placeholder`

### `ChoiceSelect`

表示按 Enter 后进入 choice editor。

用于：

- model
- language
- allow_all_users
- reasoning_effort

### `ActionTrigger`

表示按 Enter 后立刻触发动作。

用于：

- `Restart Relay`
- `Delete Current Backend`

### `SubviewOpen`

表示按 Enter 后打开右侧子视图。

用于：

- `Show Config`
- `Manage Backends`
- `Backend Settings`
- `Advanced`

### `ReadOnly`

表示该字段可见但不可编辑。

用于：

- 分组标题
- `App Name`
- 某些摘要字段

当前实现里，**只读字段默认不参与焦点**。

这是重要的交互约束：  
用户不会再落到一个“看起来可操作，实际上不能输入”的字段上。

---

## 6. 子视图模型

当前所有子视图都在 `Workspace` 内部完成，不会创建新的顶层 screen。

也就是说：

- 顶层仍然只有 `Bind Bot` 和 `Workspace`
- 子视图只是右侧面板内容替换

当前使用的子视图包括：

- `SHOW_CONFIG`
- `CLAUDE_BACKENDS`
- `CLAUDE_BACKEND_SETTINGS`
- `BOT_ADVANCED`

这个约束很重要，因为它保证：

- 顶层模型稳定
- 导航深度不会再次失控
- `Esc / q` 的语义始终可控

---

## 7. 左侧面板设计

左侧面板当前已经统一成同一套渲染入口，而不是 `Bind Bot` 和 `Workspace` 各自硬编码一份。

左侧内容由三部分组成：

1. 品牌区
2. 状态区
3. 装饰区

对应 helper：

- `_left_panel_brand_lines()`
- `_left_panel_status_lines(...)`
- `_left_panel_decor_lines()`

这样做的目的是：

- 避免改左栏 UI 时只改了一半
- `Bind Bot` 和 `Workspace` 保持一致风格
- 让装饰和真实状态分离

### 品牌区

当前包含：

- 大 logo
- 版本号

### 状态区

当前固定显示：

- `Bot`
- `Section`
- `Relay`
- `PoCo`

其中 bot 显示规则是：

- `alias`
- 否则 `app_name`
- 否则截断后的 `app_id`

### 装饰区

当前使用一个低对比度字符画：

```text
/̴/̴_̴p̴o̴c̴o̴_̴/̴/̴
  ░▒▓ · · ▓▒░
  [̲̅$̲̅] relay on/off
```

并且最后一行颜色跟 relay 状态联动。

这块的定位是：

- 填充左栏空白
- 提供轻量品牌感
- 但不承担配置信息本身

---

## 8. 右侧面板设计

右侧面板由三层组成：

1. 标题
2. section tabs
3. 当前 section 或子视图内容

### section tabs

当前 tab 是平级切换：

- `Agent`
- `Bot`
- `PoCo`
- `Language`

不再经过根菜单中转。

### 分组显示

`Agent` section 当前会显示：

- `CODEX`
- `CLAUDE`

作为轻量分组标题。

分组标题本身是只读、不可选中的。

### action / subview 的视觉语言

当前区分原则是：

- 普通字段：
  - `Label: value`
- action / subview：
  - `Label →`
  - 或 `Label: summary →`

例如：

- `Manage Backends: minimax →`
- `Backend Settings: minimax · MiniMax-M2.7 →`

这样可以把“入口”与“配置值”分开。

---

## 9. 底部输入区与 footer

底部不是一个混合区，而是两块：

1. 输入区
2. footer

### 输入区

底部输入框只在以下场景启用：

- `Bind Bot` 输入 `APP ID`
- `Bind Bot` 输入 `APP Secret`
- `Workspace` 中的 `TextInput`

否则输入框是 disabled 状态。

### footer

footer 当前是上下文感知的，不再是一条静态提示。

例如：

- Bind Bot 平台页
- Bind Bot 账户页
- 输入态
- choice editor
- subview
- show config
- Workspace 顶层可编辑字段
- Workspace 顶层只读字段

显示的 hint 都不同。

这解决了两个问题：

- `Esc / q to back` 不会在顶层 workspace 误导用户
- `Enter to open` 不会在只读字段上出现

---

## 10. 键盘模型

### Bind Bot

- `↑ / ↓`
  - 切换选项
- `Enter`
  - 继续
- `Esc / q`
  - 返回或退出

### Workspace

- `← / →`
  - 切换 section
- `↑ / ↓`
  - 移动当前字段焦点
- `Enter`
  - 打开 / 编辑 / 执行动作
- `Esc / q`
  - 关闭输入态、choice editor、subview，或退出 workspace
- `Ctrl+R`
  - 重启 relay

---

## 11. 配置与 service 的关系

TUI 自己不直接管理配置文件路径，而是通过 service 访问配置。

当前关键对象链是：

- `ConfigStore`
- `PoCoService`
- `PoCoTui`

其中：

- store 负责具体配置落盘
- service 提供统一接口
- TUI 只通过 service 读写

当用户在 `Bind Bot` 里：

- 选择已有 bot
- 或输入新的 `APP ID / APP Secret`

TUI 不会重启整个进程，而是：

1. 绑定当前 workspace 到新 bot
2. 重新创建对应的 service/store
3. 原地进入 `Workspace`

所以当前设计已经不是“绑定 bot 后强制重启 PoCo”的模型。

---

## 12. 当前的重要约束

这些约束是当前实现里必须保持的。

### 顶层 screen 约束

顶层永远只有：

- `Bind Bot`
- `Workspace`

不要再引入第三个顶层 screen 去解决局部问题。

### 只读字段约束

只读字段默认不参与焦点。

否则用户会遇到：

- 能选中
- 但按 Enter 没反应
- 打字也无效

这种假交互。

### section 约束

section 是平级切换，不是菜单钻入。

不要重新引入：

- 根菜单
- 二级菜单
- 根菜单里的 section launcher

### 子视图约束

子视图只替换右侧内容，不改变顶层 screen。

### 左栏统一入口约束

左栏 UI 必须通过统一 helper 生成。

不要让：

- `Bind Bot`
- `Workspace`

各自单独拼左栏，否则很容易改一边忘一边。

---

## 13. 当前设计的取舍

这套 TUI 不是最“理论完美”的架构，但它是当前项目规模下比较合适的折中。

### 它优先解决的事情

- 去掉旧菜单系统
- 降低导航深度
- 统一 bot 绑定流
- 让 section 成为一等概念
- 让 UI 改动集中在少量入口

### 它没有追求的事情

- 通用 UI DSL
- 插件式 section 系统
- 纯 reducer / effect 框架
- 任意平台动态扩展

所以这份设计的核心不是“抽象最多”，而是：

**把 TUI 变成一套结构清晰、足够稳定、便于继续迭代的工作界面。**
