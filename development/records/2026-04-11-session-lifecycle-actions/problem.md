# Problem

PoCo 当前虽已自动创建 active session，但用户无法显式：

- 开启一个新的 session
- 关闭当前 session

这意味着：

- “我想重新开始一条新工作流”没有直接动作
- “我想结束当前工作流”没有明确边界

产品上会继续显得 session 是隐式实现细节，而不是可理解的对象。
