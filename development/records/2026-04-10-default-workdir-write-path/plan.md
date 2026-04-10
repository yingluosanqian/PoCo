# Plan

## 范围

- 新增最小 `workspace context` 模型、store、controller
- 让 `workspace.open` / `workspace.refresh` 读取当前 context
- 让 `workspace.use_default_dir` 真正写入 context
- 更新测试和最小文档

## 验收标准

- 点击 `Use Default` 后，当前群工作面的 `active_workdir` 被更新
- 后续再次打开 workspace 或 switcher 时可看到新的 state
- 如果 project 没有 default workdir，会返回明确拒绝而不是静默成功
