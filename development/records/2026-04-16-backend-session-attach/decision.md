# Decision

## 待选问题/方案

- A：只支持文本输入（粘贴 backend_session_id）
- B：只支持下拉（从历史选）
- **C：下拉 + 手动输入 fallback**（用户明确偏好）
- D：不做，靠命令行 attach

## 当前决策

采纳 **方案 C**。

## 设计细节（已经和用户对齐的）

### 数据层

1. **数据源**：跨 project 的 task history，取 `backend_session_id` 非空的记录去重
2. **按 backend 过滤**：只列和当前 project 同 backend 的 session（codex thread_id 和 claude session_id 不兼容）
3. **排序**：按该 session 最近一次被使用的 task 时间倒序
4. **条目标签**：`<project name> · '<first prompt 前 50 字>' · <相对时间>`；没有 prompt 兜底 `session_id` 前 12 字符
5. **条目上限**：**不设上限**（用户明确要求）
6. **attach 语义**：覆盖当前 project 的 active session 的 `backend_session_id`。不新建 PoCo session

### UX intent 链

参照 workdir 的两段式：

- workspace 卡新增按钮 "Session" → `workspace.choose_session`
- choose 卡：下拉列出"所有与当前 backend 匹配的历史 session"（无上限）+ 按钮 "Enter ID" + 按钮 "Start Fresh"
  - 下拉 apply → `workspace.apply_session`（payload 带 `backend_session_id`）→ 覆盖 active session → 返回 workspace overview
  - "Enter ID" → `workspace.enter_session_id` 打开手输卡
  - "Start Fresh" → `workspace.clear_session`（把 active session 的 `backend_session_id` 清成 None，下次 task 自然 `thread/start`）
- enter 卡：文本输入 `backend_session_id` + Apply → `workspace.apply_entered_session_id` → 同样覆盖 → 返回 workspace overview

### 关键不变量

- PoCo session 对象依然 1-per-project，不为 attach 新建
- Task history 里所有 task 的 `backend_session_id` 不会被修改
- "Start Fresh" 不删除任何历史，只清当前 active session 的 id

## 为什么这样选

- 用户已经在 workdir 习惯这种"下拉 + 手输"模式，零学习成本
- 覆盖 active session 而非新建 session 最小化模型复杂度
- 按 backend 过滤避免跨 backend id 混乱
- 不设上限是用户明确需求；实际使用下历史 session 总数不会爆炸

## 为什么不选其他方案

- 方案 A：失去"不用记 id"的便利
- 方案 B：无法接完全外部的 id
- 方案 D：违反移动端优先，且 CLI 和手机不在一起

## 风险

- **历史 session 数量膨胀** → 下拉超长。但用户明确要求不设上限；后续若真的爆炸再加分页
- **选中已死 thread** → 下次 task 走 `thread/resume` 会失败。依赖现有 completion 语义兜底（task 会失败，用户看到错误再换 id）
- **跨 project attach 混淆所有权** → PoCo 现有模型里 session 本来就是 project 的属性，attach 只改 id，所有权没变。没有新增风险

## 后续影响

- 若将来支持 per-task session override，complementary 工作量小（task 层加一个 effective_session_id 字段，task.submit 时覆盖）
- 若将来要做"session 历史视图"，本轮的 `list_known_backend_sessions` helper 可以直接复用
