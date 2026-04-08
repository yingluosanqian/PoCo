# Decision

## 当前决策

不要求额外公网 HTTP callback。

在 PoCo 内包一层自定义 long-connection ws client，接住 `CARD` 帧，并将 `p2.card.action.trigger` 分发到现有 `FeishuCardActionGateway`。

## 为什么这样选

- 符合移动端 / to C 产品的接入模型
- 复用现有 card dispatcher 与 gateway，不重写业务层

## 风险

- 需要承接 SDK 内部实现细节
- SDK 后续升级时需要关注 `ws.client` 兼容性
