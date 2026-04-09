# Validation

## 验证方法

- 检查 DM 与 Group 两张卡是否分别对应慢变量和快变量
- 检查 `agent` 是否没有重新掉回群内一级切换动作
- 检查 `working dir` 是否没有重新退化成 task 级裸输入主路径

## 结果

- `DM Project Config Card` 清楚承接了 project 级配置摘要和入口
- `Group Workdir Switcher Card` 清楚承接了 session 级目录切换
- 方案保持了 `DM control plane + group workspace` 的整体一致性

## 是否通过

通过当前轮 IA 设计目标。

## 残留问题

- `Configure Agent` 的二级确认卡仍需单独设计
- `Enter Path` 的校验、权限和安全边界仍需单独设计
- `Recent / Preset / Manual` 的优先级还可以继续微调
