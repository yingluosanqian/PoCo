# Plan

## 范围

- 在 project 模型中加入最小 `workdir_presets`
- 在 DM `Manage Dir Presets` 中支持新增 preset
- 在群 `Choose Preset` 中支持应用 preset
- 更新测试和最小文档

## 验收标准

- DM 中可新增 project-level preset
- 群中可看到 preset 列表并应用其中一项
- 应用成功后，workspace context 更新为 `source=preset`
