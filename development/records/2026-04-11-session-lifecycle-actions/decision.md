# Decision

在 group workspace 首卡上增加最小 session lifecycle 动作：

- `New Session`
- `Close Session`

规则：

- `New Session` 会关闭旧 active session，并创建新的 active session
- `Close Session` 只关闭当前 active session，不自动开启新的
- 关闭后，下一条 group prompt 仍可自动创建新的 active session
