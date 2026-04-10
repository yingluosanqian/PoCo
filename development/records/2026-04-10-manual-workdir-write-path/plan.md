# Plan

## 范围

- 给 `workspace_enter_path` 卡加入输入框和 `Apply Path` 按钮
- 新增 `workspace.apply_entered_path`
- 把输入路径写入 in-memory workspace context
- 更新测试和最小文档

## 验收标准

- `Enter Path` 卡包含输入框和 `Apply Path`
- 点击 `Apply Path` 后，当前群工作面的 `active_workdir` 变更为手工输入路径
- 空路径会被明确拒绝
