# Plan

## 范围

- 把 `project.open` 的 view 升级为 `project_config`
- 更新 Feishu renderer
- 接入四个只读配置子卡
- 更新测试和最小文档

## 验收标准

- DM 打开 project 时返回 `Project Config Card`
- 首屏包含 `Agent`、`Repo Root`、`Default Workdir`、`Workspace Group`
- 配置按钮可进入对应只读子卡并能返回
