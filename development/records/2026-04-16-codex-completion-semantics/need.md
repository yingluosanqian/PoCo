PoCo 当前的 codex backend 已经是正式主链。

当用户在手机上查看 task card 时，最关键的前提不是“有 streaming”，而是：

- 不要在输出还没真正收口时就把 task 判成 `completed`
- 不要在输出明显已经结束后还长期停在 `running`

这轮需要把 codex app-server 的完成语义收紧成对用户可解释、对状态机可收口的最小稳定版本。
