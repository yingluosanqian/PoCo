# Setup Card Design

这份文档描述 Feishu `setup` 卡片的排版目标和当前设计。

## 1. 问题

旧版 `setup` 卡片主要问题是：

- 使用固定标签列宽
- 大量依赖横向 `column_set`
- 按钮和输入框按桌面宽度思路排布
- 在移动端会被动换行，导致布局零碎

这些规则在桌面端还能勉强工作，但不能保证移动端体验。

## 2. 设计目标

新的 `setup` 卡片需要同时兼顾移动端和桌面端：

- 移动端优先可读
- 桌面端保持整齐，不显得过于松散
- 主流程一眼可见
- 尽量减少横向布局依赖

## 3. 布局原则

### 3.1 单列优先

主表单采用单列结构：

- 上面是 label
- 下面是控件

不再使用：

- 左标签 + 右控件的固定两列布局

### 3.2 只有轻量选项保留横排

以下场景仍然允许横向按钮组：

- `Reply Mode`

原因是：

- 选项数量少
- 用户需要快速切换
- 即使换行也比“左列标签 + 右列控件”更自然

`Agent / Provider / Model` 统一改成紧凑的一行：

- 左侧是标签
- 右侧是下拉

这样可以压缩移动端高度，并让运行时配置区更像一个连续表单。

### 3.3 输入框永远满宽

以下字段始终采用满宽输入框：

- `Project ID`
- `Working Dir`

这是主流程里最重要的输入区，优先保证稳定性和清晰度。

### 3.4 主按钮和次按钮分行

操作区规则：

- `setup_card()` 仍然保持主次按钮分行
- `project_launch_card()` 的 `Start / Reset / Back` 合并为一行三列，缩短卡片高度

两张卡都保持单列主体结构，只在动作区按具体使用频率做差异化处理。

## 4. 信息结构

卡片结构分成两段：

### Runtime

- Agent
- Provider
- Model
- Reply Mode

### Project

- Project ID
- Working Dir
- Directory picker
- Start
- Reset

顶部再补一行轻量说明：

- `Choose agent, confirm project info, then start.`

## 5. 为什么这套方案同时适合移动端和桌面端

### 移动端

- 基本不依赖横向空间
- 输入区和下拉框都是自然的单列表单
- 只有少量按钮组做横排，风险可控

### 桌面端

- setup 本质上是配置表单，单列不会显得奇怪
- 分组和留白足够时，视觉上仍然清晰
- 比起旧版固定列宽布局，更不容易出现局部拥挤

## 6. 当前实现约束

这次改动重做了两张与启动项目直接相关的卡片：

- `setup_card()`
- `project_launch_card()`

两者都统一采用：

- 分组式单列结构
- `Agent / Reply Mode` 的轻量横排按钮
- `Agent / Provider / Model` 的紧凑单行下拉
- `Project ID / Working Dir` 的满宽输入
- `Start / Reset` 的分行动作区
- 低频的 session attach 信息单独分组

但仍然保留这些约束：

- 不重写全局 `_card_labeled_row`
- 不改变 DM console 的布局
- 不把 session attach 做成独立子卡流程
- 只在 `SetupCardController` 里引入 setup / project-launch 专用的单列表单 helper

## 7. Session Attach

`Attach to` / `Or paste ID` 在移动端不再与主流程字段混成同一层横排结构。

新的规则是：

- 仅在 `codex / cursor` 下显示
- 放在 `Working Dir` 之后
- `Recent Session` 使用单列下拉
- `Or paste ID` 使用单列输入

这样可以避免 session attach 抢到主流程顶部，同时仍然保留在启动动作之前。

## 8. Working Dir 目录选择

当前主方案仍然以手动输入 `Working Dir` 为主。

目录浏览器如果存在，应优先作为主卡里的辅助选择器出现，而不是再切到独立子卡。

当前验证策略是：

- `Working Dir` 输入框仍然是主入口
- 目录下拉放在主卡里、表单外
- 目录选择只负责辅助更新 `Working Dir`

这样可以减少它对 `Create Pocket Project` 主流程稳定性的影响。
