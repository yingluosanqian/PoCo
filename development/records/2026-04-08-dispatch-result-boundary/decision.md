# Decision

## 待选问题/方案

- 方案 A：handler 直接返回平台卡片结构
- 方案 B：handler 返回平台无关结果，平台层再把结果翻译成渲染指令
- 方案 C：平台层直接读取业务对象并自行决定如何渲染

## 当前决策

采用方案 B。

PoCo 的业务层返回平台无关的 `IntentDispatchResult`；平台适配层再基于该结果生成 `PlatformRenderInstruction`，最终由具体 renderer 输出飞书卡片。

## 为什么这样选

- 这最符合“薄平台适配 + 独立任务核心”原则
- 这让业务层不依赖飞书 schema
- 这为未来接入其他平台保留了结构空间

## 为什么不选其他方案

- 不选方案 A：会让平台 schema 直接污染 handler
- 不选方案 C：会把渲染决策偷偷塞进平台层，重新形成隐式业务逻辑

## 风险

- 如果 dispatch result 设计过于抽象，可能拖慢实现
- 如果 render instruction 太薄，平台层可能仍需要额外猜测

## 后续影响

- 下一轮实现应先落 `dispatcher -> result -> render instruction -> renderer` 链路
- view model 需要成为业务层的一等输出，而不是平台层临时拼装
