# Problem

## 当前状态

- project 已有 group 绑定
- workspace card 已有 latest task 摘要
- task notifier 已能更新 task status card
- 但 workspace card 本身还没有进入同一条更新链

## 问题定义

PoCo 当前缺少一条从 task 状态变化到 workspace latest task 区块更新的最小同步链，导致 workspace card 仍需要依赖手动 refresh 才能接近实时状态。

## 不是的问题

- 不是现在就实现整个 workspace card 的全面实时同步问题
- 不是现在就实现多 workspace card 去重的问题
