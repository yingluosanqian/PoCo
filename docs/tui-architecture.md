# TUI 架构重构方案

## 目标

把当前 TUI 重构成一套更简单、更像产品本身的结构：

- 先绑定一个 bot
- 然后直接进入工作区
- 在一个统一的工作区界面里完成配置

重构的核心不是“继续优化菜单”，而是去掉现在这种多层菜单系统。

---

## 非目标

这次重构不解决以下问题：

- 不引入通用 UI DSL
- 不做插件系统
- 不做任意平台的动态扩展框架
- 不在本次里重写 relay / provider 层
- 不把 TUI 做成一套通用表单引擎

这份方案只解决：

- 启动绑定流
- 工作区配置流
- 状态与渲染边界

---

## 当前问题

现在的 TUI 能工作，但结构已经明显偏重了。

主要问题：

- 一个大的 `PoCoTui` 同时负责了太多事情
- 登录流、菜单流、配置流、渲染、service glue 都混在一起
- UI 状态太分散
  - `_view`
  - `_login_step`
  - `_root_selected`
  - `_config_stack`
  - `_show_scroll`
- 产品本质上是“设置型界面”，但当前实现更像老式终端菜单系统
- `menu -> section -> field -> sub-menu` 的层级太深

---

## 新的产品模型

新的 TUI 只保留两个顶层界面：

1. `Bind Bot`
2. `Workspace`

### Bind Bot

这是启动后的绑定流程。

用户流程：

- 先选平台
  - `Feishu`
  - `Slack`
  - `Discord`
- 如果平台还没实现
  - 显示 `Not implemented yet`
- 如果选择 `Feishu`
  - 先选一个已保存 bot
  - 或选择 `New Bot`
- 如果选择 `New Bot`
  - 输入 `APP ID`
  - 输入 `APP Secret`

绑定完成后：

- 当前工作区绑定到这个 bot
- 如有必要，保存凭据
- 直接进入 `Workspace`

### Workspace

这是唯一的主工作界面。

右侧不再先显示一个抽象的菜单页，而是直接显示当前 section 的内容。

建议保留这 4 个 section：

- `Agent & Model`
- `Bot`
- `PoCo`
- `Language`

用户直接在这些 section 之间切换，而不是先进菜单再点进去。

---

## Textual 集成策略

这里必须先拍板，否则后面一切设计都会摇摆。

本方案明确采用：

**Textual 只做渲染壳，不做业务状态源。**

也就是：

- `AppState` 是唯一业务状态源
- 键盘事件先转成 typed action
- reducer 产出新 state
- Textual widget 只读 state，不写业务状态
- Textual 的 reactive 只用于触发刷新，不保存业务状态

不要混成两套状态系统：

- 一套在 Textual reactive/watch 里
- 一套在 reducer/state tree 里

否则调试会非常痛苦。

更准确地说：

- Textual
  - 接收键盘事件
  - 管理布局和绘制
  - 管理组件生命周期
- state/reducer
  - 负责业务状态
  - 负责状态迁移
  - 不直接做渲染副作用

---

## 交互模型

### Bind Bot

- `↑ / ↓`：切换选项
- `Enter`：继续
- `Esc / q`：返回

### Workspace

- `← / →`：切换 section
- `↑ / ↓`：在当前 section 的字段中移动
- `Enter`：激活当前字段
- `Esc / q`：退出当前编辑态
- `Ctrl+R`：保存并重启 relay

这样可以直接去掉一整层“根菜单”。

---

## Enter 行为表

`Enter` 是这套 TUI 里最复杂的键，所以不能只写成一句“继续”或“打开字段”，必须显式建模。

### Bind Bot

- `Enter` on `platform`
  - 派发 `SelectPlatform(platform)`
- `Enter` on `saved_bot`
  - 派发 `BindExistingBot(app_id)`
- `Enter` on `new_bot`
  - 派发 `BeginNewBotBinding`
- `Enter` on `app_id`
  - 派发 `SubmitAppId(value)`
- `Enter` on `app_secret`
  - 派发 `SubmitAppSecret(value)`

### Workspace

- `Enter` on section title
  - 无操作
  - section 切换只用 `← / →`
- `Enter` on `ReadOnly`
  - 无操作
- `Enter` on `SubviewOpen`
  - 派发 `OpenSubview(section, subview_id)`
- `Enter` on `ChoiceSelect`
  - 派发 `OpenChoiceEditor(field_key)`
- `Enter` on `TextInput`
  - 派发 `BeginInput(field_key)`
- `Enter` on `ActionTrigger`
  - 直接派发该字段绑定的 typed action

### 输入态

- `Enter` on input submitted
  - 派发 `CommitInput(field_key, value)`
- `Esc / q`
  - 派发 `CancelInput`

这张行为表应该先于 reducer 落地，避免 reducer 重新长成新的 if/else 泥潭。

---

## 状态模型

所有 TUI 状态都应该收口到一个统一的状态树里，不再散落在 `PoCoTui` 的私有字段里。

关键要求：

- business state 和 transient state 分层
- 每个状态对象的 lifetime 和 ownership 明确
- 草稿、已确认值、通知不要混在同一个 dataclass 里

对于当前项目规模，这里**暂时不强制**再拆一层 `DomainState / UiState`。  
这是后续可能的演化方向，但不是这次重构的前置条件。

```python
@dataclass
class AppState:
    screen: ScreenKind
    bind_bot: BindBotState
    workspace: WorkspaceState
    runtime: RuntimeState
    notification: Notification | None
```

```python
class ScreenKind(Enum):
    BIND_BOT = "bind_bot"
    WORKSPACE = "workspace"
```

```python
@dataclass
class BindBotState:
    step: BindBotStep
    selected_index: int
    platform: Platform | None
    saved_bots: list[BotAccount]
    draft: BindBotDraft | None
```

```python
@dataclass
class BindBotDraft:
    app_id: str = ""
    app_secret: str = ""
```

```python
@dataclass
class WorkspaceState:
    active_section: WorkspaceSection
    sections: dict[WorkspaceSection, SectionState]
    input_state: InputState | None
```

```python
@dataclass
class SectionState:
    selected_index: int
    scroll: int
    subview: SubviewId | None
```

```python
@dataclass
class InputState:
    field_key: str
    steps: list[str]
    current: int = 0
    buffer: str = ""
    draft: dict[str, str] = field(default_factory=dict)
```

```python
@dataclass
class Notification:
    message: str
    kind: Literal["info", "error"]
    ttl: int | None = None
```

这里 `InputState` 不应该只是 `str | None`，`step` 也不应该是一个无约束字符串。

原因是现在已经存在多步骤输入场景，例如：

- `extra_env_key`
- `extra_env_value`

如果值域是有限的，就不应该再退回字符串 dispatch。

这里建议两种实现里选一种：

- 用 per-flow enum
- 或者直接用 `steps + current index`

这份方案先采用第二种，因为它更通用：

- `steps=["key", "value"]`
- `current=0/1`

这样：

- reducer 不需要理解任意自由字符串
- 多步骤输入的顺序也变成显式数据

---

## 关键不变量

这部分是架构里的硬约束，不是建议。

- 任意时刻只能有一个 active screen
- `screen == WORKSPACE` 时，必须已经存在有效 bot binding
- `input_state is not None` 时，普通字段导航被冻结
- `subview is not None` 时，只允许子视图相关动作
- `selected_index` 必须始终落在当前字段列表合法范围内
- `workspace.active_section` 必须始终对应一个存在的 section
- screen 切换只能由顶层 reducer 或 system reducer 触发
- screen reducer 不得直接修改 `state.screen`

这些约束应该在 reducer 测试里直接验证，而不是靠 UI 手测兜底。

---

## Action 设计

这里不建议用字符串 dispatch。

这种写法是错误方向：

```python
FieldDef(on_enter="restart_relay")
```

因为它把类型信息降级成了字符串，后面 reducer 里还要再 match 一遍。

建议使用 typed action，也就是 sum type / dataclass action。

```python
@dataclass
class RestartRelay:
    pass

@dataclass
class CommitInput:
    field_key: str
    value: str

@dataclass
class OpenSubview:
    section: WorkspaceSection
    subview_id: SubviewId

AppAction = BindBotAction | WorkspaceAction | SystemAction
```

并且 action 也不应该全部平铺在一个文件里。  
更合理的是按 screen 分组：

- `BindBotAction`
- `WorkspaceAction`
- `SystemAction`

如果后面并不需要 replay / trace / log，也不必把 action 系统做得特别重。  
但 action 本身必须保持强类型，不应该退化成字符串名字。

---

## Reducer 设计

不能只有一个全局大 reducer。

否则只是把今天的 `if/else` 从 `PoCoTui` 挪到了另一个文件。

应该做成分层 reducer：

```python
def reduce_app(state: AppState, action: AppAction) -> AppState:
    state = reduce_system(state, action)
    match state.screen:
        case ScreenKind.BIND_BOT:
            return replace(state, bind_bot=reduce_bind_bot(state.bind_bot, action))
        case ScreenKind.WORKSPACE:
            return replace(state, workspace=reduce_workspace(state.workspace, action))
```

```python
def reduce_bind_bot(state: BindBotState, action: BindBotAction) -> BindBotState:
    ...
```

```python
def reduce_workspace(state: WorkspaceState, action: WorkspaceAction) -> WorkspaceState:
    ...
```

```python
def reduce_section(
    state: SectionState,
    action: SectionAction,
    fields: list[FieldDef],
) -> SectionState:
    ...
```

原则：

- `SystemAction` 先由 `reduce_system` 处理
- `reduce_system` 是唯一允许切换 `state.screen` 的地方
- screen reducer 不处理跨 screen 状态
- 顶层 reducer 只做路由
- screen reducer 只处理 screen 自己的状态
- section reducer 只处理 section 自己的导航和子视图

这里要特别强调一个实现约定：

- `reduce_system` 跑完之后，再读取一次 `state.screen`
- 顶层 reducer 只能根据**更新后的** `state.screen` 做路由
- `reduce_bind_bot` 和 `reduce_workspace` 不允许顺手改 `state.screen`

这样每一层都可以单独测试，不会线性膨胀。

---

## 副作用模型

reducer 必须保持纯函数。

像这些操作都不是纯状态迁移：

- 保存 bot 凭据
- 保存配置
- 读取已保存 bots
- 校验 `APP ID / APP Secret`
- 重启 relay
- 读取 runtime 状态

这些都应该通过 effect 层执行，而不是让 reducer 或 screen 直接调用 service。

建议最小闭环：

```python
AppAction -> reducer -> (AppState, list[AppEffect])
AppEffect -> effect runner -> EffectResultAction
EffectResultAction -> reducer -> AppState
```

这里不需要一开始就做很重的 effect 框架，但必须保证三件事：

- reducer 不直接做 IO
- effect 结果会回流成显式 action
- 失败也必须是显式结果，不允许静默吞掉

例如：

- `SubmitAppSecret` 触发 `ValidateBotCredentialsEffect`
- 校验成功后回流 `BotCredentialsValidated`
- 校验失败后回流 `BotCredentialsRejected`

---

## 建议的代码结构

```text
poco/tui/
  app.py
  state.py
  resources.py
  actions/
    bind_bot.py
    workspace.py
    system.py
  reducers/
    app.py
    bind_bot.py
    workspace.py
    section.py
  screens/
    bind_bot.py
    workspace.py
  sections/
    agent.py
    bot.py
    poco.py
    language.py
  widgets/
    layout.py
    summary.py
    footer.py
```

### 各层职责

#### `app.py`

只负责 Textual 外壳：

- 挂载 widgets
- 接收键盘事件
- 调 reducer
- 刷新 UI

#### `state.py`

定义所有状态 dataclass。

#### `actions/`

定义 typed action，按 screen 分组。

#### `reducers/`

定义分层 reducer，按 screen / section 分组。

#### `screens/`

顶层 screen 逻辑：

- `BindBotScreen`
- `WorkspaceScreen`

#### `sections/`

每个 section 一个模块。

每个 section 负责：

- 字段定义
- 文案
- 编辑行为
- 子视图

#### `widgets/`

纯渲染组件：

- 左侧摘要面板
- 底部栏
- 通用布局块

---

## 依赖规则

目录结构不是重点，依赖方向才是重点。

这里至少要写死这些禁止项：

- renderer 不得 import service
- reducer 不得触发 IO
- `state.py` 不得引用 Textual 类型
- section schema 不得依赖 widget
- action 定义不得依赖 service 实例

允许的依赖方向应该尽量简单：

```text
actions -> state
reducers -> actions, state
screens -> reducers, actions, state
widgets -> state
app -> screens, widgets, reducers, state
effect runner -> services, state, actions
```

如果后面出现层间倒灌，就优先修依赖方向，而不是继续增加 helper。

---

## Workspace 左侧摘要面板

左侧摘要不应该重复 section 菜单本身，否则和直接切换 section 没有区别。

建议左侧固定展示这些内容：

- Logo
- 当前 bot 显示名
  - `alias > app_name > app_id`
- Relay 状态
  - `RUNNING / STOPPED`
- 当前 section 名
- 当前 workspace 绑定状态

它的作用是：

- 给用户稳定上下文
- 让右侧专心做 section 内容

它不应该承担“再来一套导航系统”的职责。

---

## 字段模型

这里不要再用不正交的：

- `input`
- `choice`
- `action`
- `readonly`

因为它混了两个维度：

- 可编辑性
- 交互类型

更合理的是用一个正交的 `interaction` 模型：

```python
@dataclass
class FieldDef:
    key: str
    label: str
    interaction: FieldInteraction
```

```python
@dataclass
class TextInput:
    secret: bool = False
    validator: "Validator | None" = None

@dataclass
class ChoiceSelect:
    choices: list[str]

@dataclass
class ActionTrigger:
    action: AppAction

@dataclass
class SubviewOpen:
    subview_id: SubviewId

@dataclass
class ReadOnly:
    pass

class SubviewId(Enum):
    SHOW_CONFIG = "show_config"
    CHOICE_EDITOR = "choice_editor"

FieldInteraction = (
    TextInput
    | ChoiceSelect
    | ActionTrigger
    | SubviewOpen
    | ReadOnly
)
```

```python
Validator = Callable[[str], str | None]
```

约定：

- 返回 `None`
  - 表示校验通过
- 返回错误字符串
  - 表示校验失败，并把这条字符串显示给用户

这样每种交互类型的参数是内聚的：

- `ChoiceSelect`
  - 只有 choice 相关信息
- `TextInput`
  - 只有输入相关信息
- `ActionTrigger`
  - 直接带 typed action
- `SubviewOpen`
  - 明确表示这不是编辑，而是打开一个子视图

`ChoiceSelect` 的当前选中值不应存在 `SectionState` 里。  
它应该始终来自当前的 **committed config snapshot**：

- 渲染时：从 config snapshot 读取当前值
- 打开 choice editor 时：用该值初始化 editor 的选中位置
- 提交时：再写回 config snapshot

这样可以避免 UI 层额外维护一份“当前值”副本。

---

## Section 设计

### Agent & Model

包含：

- `codex`
- `claude code`
- model choices
- provider / backend choices
- approval / sandbox 相关字段

### Bot

包含：

- `alias`
- `app_name`（只读）
- `app_id`
- `app_secret`
- Feishu 相关配置

### PoCo

包含：

- relay / runtime 参数
- `show config`
- 本地高级设置

这里的 `show config` 不应该被当作普通可编辑字段，它更像一个特殊子视图。

建议明确区分：

- `field`
  - 普通可编辑项
- `subview`
  - 像 `show config` 这种只读滚动视图

也就是说，`show config` 属于 `PoCo` section，但不是一个普通 field 的同类物。

### 子视图渲染策略

这里建议明确采用：

- **不 push 新的顶层 screen**
- **只在右侧面板内部替换内容**

也就是说：

- 顶层 screen 永远只有：
  - `Bind Bot`
  - `Workspace`
- `show config`
- choice editor
- 某些只读详情页

这些都属于 `Workspace` 内部的 `subview`，只替换右侧主体，不改变整个应用级 screen。

这样可以避免重新回到老的“嵌套菜单/嵌套 screen”模型。

### Language

包含：

- UI 语言切换

---

## 渲染原则

renderer 不应该拥有业务逻辑。

它只负责把：

- `AppState`
- 当前 config snapshot

转换成：

- 左侧面板文本
- 右侧主体文本
- 底部提示文本

这些决策不应该放在 renderer 里：

- `Enter` 按下后发生什么
- 某个字段能不能编辑
- 某个跳转是否允许

这些都应该放到 reducer / screen 层里。

---

## 错误语义

失败行为必须统一，不要在不同 section 各搞一套。

最少先统一这些规则：

- bot 绑定失败
  - 保留当前输入 draft
  - 显示 error notification
- 凭据校验失败
  - 不落盘
  - 不改变当前 binding
- relay restart 失败
  - config 仍视为已提交
  - runtime 状态改成失败态
- subview 打开失败
  - 回到当前 section 主视图

这里只定义语义，不要求一开始就做复杂的错误恢复系统。

---

## 为什么这会更好

相比当前结构，这套设计会：

- 去掉“根菜单”这个没有产品价值的中间层
- 降低导航深度
- 让 bind-bot 流程成为一等公民
- 把状态集中起来
- 降低单类复杂度
- 更容易测试
- 更适合以后支持 Slack 和 Discord

---

## 迁移顺序

建议分阶段做，但 Stage 1 和 Stage 2 不应该切得太碎。

### Stage 1

一起做两件事：

- 引入新的 `AppState`
- 去掉 root menu

结果是：

- `menu` 消失
- `workspace.active_section` 成为主导航模型

如果把这两件事硬拆开，Stage 1 引入的中间状态反而可能成为负担。

这一阶段完成后，不要立刻继续大拆。  
应该先实际使用一段时间，验证：

- section 切换是否真的比 root menu 更顺
- 用户是否能自然理解新的导航方式
- 左右布局是否真的更清晰

确认体验正确后，再继续后面的模块拆分。

### Stage 1.5

在旧代码完全删除之前，保留一个兼容开关。

建议做法：

- 新旧路径同时存在
- 用一个内部 feature flag 控制：
  - `legacy_tui`
  - `new_tui`
- 验证稳定后，再删旧路径

否则会遇到一个典型问题：

- 旧的 `_config_stack / _view` 还在
- 新的 `AppState` 也在
- 但谁才是 source of truth 不明确

兼容期必须保证：

- 旧路径用旧状态
- 新路径用新状态
- 不允许两套状态互相写入

这一阶段不要求复杂的 action trace / 产品监控。  
但至少要有最小可观测性：

- screen transition log
- config commit log
- relay restart result

### Stage 2

把每个 section 拆成独立模块：

- `agent.py`
- `bot.py`
- `poco.py`
- `language.py`

### Stage 3

删除旧的 `menus/config/*` 栈式导航逻辑，并把剩余 screen 完全迁移到：

- `screens/`
- `reducers/`
- `sections/`

到这一步，新架构就成为唯一实现。

---

## 最终建议

不要继续在当前嵌套菜单模型上堆功能。

更合理的长期结构是：

- `Bind Bot`
- `Workspace`

并且配套：

- 明确 lifetime 的状态树
- 强类型 action
- 分层 reducer
- Textual 仅做渲染壳
- section 级导航

这比“终端菜单系统”更符合 PoCo 现在真实的产品形态，也更适合作为长期架构继续演进。
