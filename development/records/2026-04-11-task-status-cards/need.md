# Need

## 背景

group workspace card 已经能发起 task，但 task 进入等待确认或终态后，回推仍主要是文本。

## 需求信号

- 用户已经能在卡片里提交任务
- 如果 approval / result 仍主要通过文本回推，card-first 工作流会被打断

## 场景

- task 因 `confirm:` 进入等待确认
- 用户希望直接在卡片里点 `Approve` / `Reject`
- task 完成、失败或取消后，用户希望看到状态卡，而不是纯文本摘要

## 影响

这一步决定 PoCo 的 task 工作流是否开始从“卡片发起 + 文本回推”进入更完整的 card-first 交互。
