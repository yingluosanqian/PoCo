# Decision

PoCo 收敛为：

- 一个 project 一个群
- 一个群一个稳定 session

因此：

- 移除显式 `New Session / Close Session`
- 不再把 session 设计成群内可切换生命周期对象
- `task` 持续挂到该群绑定的稳定 session

session 继续保留为运行态对象，但不再暴露为需要用户频繁管理的概念。
