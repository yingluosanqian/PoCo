# Need

## 背景

DM 卡片里的 `Create Project` 已经可点击，但如果创建 project 后还要再手工拉群，正式工作流仍然割裂。

## 需求信号

- 用户明确希望创建 project 时顺便直接拉群
- `DM -> control plane` 已经成立，下一步自然应该把 project bootstrap 做完整

## 场景

- 用户在单聊里点击 `Create Project + Group`
- PoCo 创建 project
- PoCo 同步创建对应飞书群并绑定回 project

## 影响

这一步决定 project bootstrap 是不是从“登记对象”走向“可立即协作的工作区”。
