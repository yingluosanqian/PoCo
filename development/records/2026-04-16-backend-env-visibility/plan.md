# Plan

## 目标

排障时能通过 HTTP 端点直接看到"PoCo 进程有哪些关键环境变量被继承到了"，不需要 ssh 进机器查 `/proc`。

## 范围

- 新增 `GET /debug/env` 端点
- 定义白名单（当前四个 backend 相关 + 通用代理变量）
- 响应结构只含：key / present（bool）/ length（int）/ source_hint（可选，如 "from os.environ"）
- `/health` 的 warnings 里加一行文字提示 `/debug/env` 存在
- 加单测覆盖端点行为（白名单过滤、不泄漏 value）

## 不在范围内的内容

- 不做 `poco status` CLI 侧的展示
- 不做鉴权
- 不做 `.bashrc` 自动 source
- 不做"per-project env 注入"配置（单独 record）
- 不修改任何 backend 子进程启动代码

## 风险点

- 白名单定义必须精确。不该把诸如 `PATH` / `HOME` 这类通用系统变量都列进去，避免噪声。
- 单测要覆盖"value 不会被返回"这个硬边界。
- 白名单数据结构要放在易修改的位置，避免未来加 backend 时忘更新。

## 验收标准

- `curl http://127.0.0.1:8000/debug/env` 返回 JSON，结构包含 `variables` 数组，每项至少 `key` / `present` / `length`
- 无论环境中设置的变量值是什么，响应里绝不出现 value 明文
- 响应不会出现白名单之外的变量
- `/health` 的 warnings 至少包含一条引导到 `/debug/env` 的提示
- 新增单测通过，现有 `pytest` 全绿

## 实施顺序

1. 在 `poco/main.py`（或拆一个小 helper）里实现白名单 + endpoint
2. 在 `/health` warnings 里加提示
3. 写单测：白名单命中、未命中、value 不泄漏
4. 跑 `pytest -q`，更新 validation.md
