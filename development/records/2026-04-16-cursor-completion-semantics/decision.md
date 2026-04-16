# Decision

## 待选问题/方案

方案 A：沿用 codex / claude 的 CompletionGate 模式，arm 信号定义为："收到 `assistant` event，该 event 没有产生新的 output_chunk（live_text 未改变），但能提出 final_text"。disarm 信号：任何产生新 output_chunk 的 event。

方案 B：用纯静默窗口（arm 每个事件，根据 tick + elapsed 判定）。

方案 C：什么都不做，依赖 `result` event + 进程退出 + 900s timeout。

## 当前决策

采纳 **方案 A**。

具体约束：

- `CursorAgentRunner.__init__` 新增 `completion_settle_seconds: float = 1.0`，factory 不改（类默认值，和 codex/claude 保持一致）
- `_execute_prompt` 内实例化 `CompletionGate`
- while-loop 顶部（timeout 判定之后、`select.select` 之前）调 `gate.tick(monotonic())`
- 对每个解析出的 event：
  - 先计算 `output_chunk, live_text = _extract_cursor_output_chunk(event, ...)`
  - 再计算 `extracted_final_text = _extract_cursor_final_text(event)`
  - **arm 条件**：`output_chunk is None` AND `extracted_final_text` 非空 AND 已有非空 `live_text`（避免在最早的零长度 assistant 上误 arm）
  - **disarm 条件**：`output_chunk` 非空（有新增流式内容）
  - `type=result` 强终态路径不变
- settle fire 时 yield 独立的 completed update 文本：`Task completed by the cursor_agent runner after the final assistant message settled.`
- arm / settle-fire / strong-terminal 三处加 INFO log

## 为什么这样选

- **arm 信号对应 cursor 真实行为**：summary assistant event（`_extract_cursor_output_chunk` 已经识别为 None delta）是 cursor CLI 现实中的"我这条回复完整了"标志
- **对齐 codex / claude 模板**：三个 backend 同一个 CompletionGate，降低心智负担
- **不依赖"静默窗口"**：方案 B 会在长 tool turn 的真实间隔里误 fire
- **降级保留**：方案 C 安全但继续让用户体验等 15 分钟

## 为什么不选其他方案

- **方案 B**：误 fire 风险高，不能接受
- **方案 C**：和前两轮 decision 的精神冲突，属于"放任问题"

## 风险

- **cursor 协议漂移**：如果未来 cursor CLI 不再发 summary assistant event，弱终态就不会触发 arm，退化到纯强终态 + timeout（即当前行为）。不会引入新 bug，只是失去兜底价值
- **误 arm**：如果有 `assistant` event 既没有新 delta 又携带 final_text，但其实是中间 tool-use 的某个子阶段，可能误 arm。用 disarm 规则（下一条带新 output_chunk 的 event 立即 disarm）兜底
- **现有 6 条 cursor tests 必须继续绿**

## 后续影响

- coco 之后按同模板再做一轮（第四个也是最后一个 backend）
- 若后续观察到 cursor 协议有更明确的终态信号（如官方加入 `stop_reason`），本文件是调整入口
