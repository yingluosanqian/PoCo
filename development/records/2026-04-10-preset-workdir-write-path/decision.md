# Decision

## 当前决策

先落地最小 preset 写链：

- `project.add_dir_preset`
- `workspace.apply_preset_dir`

对应结构：

- preset 存在 `project.workdir_presets`
- 群工作面应用 preset 时，写回当前 in-memory workspace context，并标记 `source=preset`

## 为什么这样选

- 这直接连接 DM control plane 和 group workspace
- 它能验证 preset 是否真的是比 manual path 更自然的高频路径
- 范围仍然受控，不需要现在就做删除、排序和 recent 自动生成

## 风险

- 当前 preset 仍无删除和重命名能力
- preset 只存路径字符串，尚未引入更强语义
