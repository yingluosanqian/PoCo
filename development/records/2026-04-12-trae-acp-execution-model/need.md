# Need

用户需要：

- 在 `Trae CLI` project 中稳定发起 task
- 在群里看到真实、连续、不过期的 running 输出
- task 在完成后可靠收口，而不是停在 `running`
- bot 在长任务期间保持可用，不因为 backend 接入方式导致整体服务失效

这不是“再多支持一个 backend”这么简单。

真正的外部压力是：

- `traecli` 旧的 `-p --json` 路径不满足流式需求
- 当前 ACP 接入已暴露出输出串台、完成语义不稳、资源泄漏导致服务 unavailable 的问题

