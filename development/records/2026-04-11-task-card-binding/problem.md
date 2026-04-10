# Problem

## 当前状态

- notifier 已能原位更新已有 task status card
- 但 `task.submit` 仍未把当前 card 的 message identity 主动绑定到 task flow
- workspace 首卡也缺少稳定的 latest task 入口

## 问题定义

PoCo 当前缺少一条从 `task_composer` 当前卡到 task status 主对象，以及从 workspace 到 latest task 的更紧更新链，导致 task 相关卡片仍然偏松散。

## 不是的问题

- 不是现在就实现完整 session timeline 的问题
- 不是现在就实现 workspace 首卡自动跟随 task 状态原位更新的问题
