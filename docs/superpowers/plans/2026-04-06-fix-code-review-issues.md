# 代码审查问题修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复全面代码审查发现的 28 个问题，包含 4 个沙箱安全漏洞、2 个功能 Bug、多个数据竞态和阻塞 IO 问题，以及若干规范违反。

**Architecture:** 按 P0（安全/功能必须）→ P1（稳定性/数据完整性）→ P2（质量/规范）三级优先级逐步修复，每个 Task 独立提交，确保 CI 在每步保持绿色。

**Tech Stack:** Python 3.12, FastAPI, asyncio, multiprocessing, SQLite, pandas, pytest

---

## Task 1：修复 stat_test.py description 与 enum 不一致（P0）

**Files:**
- Modify: `src/nini/tools/stat_test.py:46`

- [ ] **Step 1：定位问题行**

  文件 `src/nini/tools/stat_test.py` 第 46 行，`description` 中的 `anova` 与 `parameters.enum` 中的 `one_way_anova` 不一致。LLM 按 description 传 `anova` 时，`_delegates["anova"]` 不存在，工具直接报错。

- [ ] **Step 2：修改 description**

  将 `src/nini/tools/stat_test.py` 第 46 行：
  ```python
  "method：independent_t/paired_t/one_sample_t/mann_whitney/anova/kruskal_wallis/multiple_comparison_correction。"
  ```
  改为：
  ```python
  "method：independent_t/paired_t/one_sample_t/mann_whitney/one_way_anova/kruskal_wallis/multiple_comparison_correction。"
  ```

- [ ] **Step 3：验证测试**

  运行：`pytest tests/test_statistics_split.py tests/test_foundation_regression.py -q`
  预期：PASS

- [ ] **Step 4：提交**

  ```bash
  git add src/nini/tools/stat_test.py
  git commit -m "fix(tools): 修正 stat_test description 中 anova → one_way_anova 与 enum 保持一致"
  ```

---

## Task 2：修复 Anthropic provider tool 角色映射错误（P0）

**Files:**
- Modify: `src/nini/agent/providers/anthropic_provider.py:141-148`

- [ ] **Step 1：理解问题**

  `_convert_messages_for_anthropic` 方法（约 130 行）将 `role == "tool"` 的消息转为 `assistant` 角色。Anthropic API 要求工具结果必须以 `user` 角色发送（而非 `assistant`），否则多轮工具调用的对话结构被破坏。

- [ ] **Step 2：修改角色**

  将 `src/nini/agent/providers/anthropic_provider.py` 中：
  ```python
  if role == "tool":
      # Anthropic 不支持 tool 角色：转为 assistant 摘要，避免误判为用户输入。
      out.append(
          {
              "role": "assistant",
              "content": self._summarize_tool_context(msg.get("content")),
          }
      )
      continue
  ```
  改为：
  ```python
  if role == "tool":
      # Anthropic 不支持 tool 角色：转为 user 消息发送工具结果，
      # 保持对话的 user/assistant 合法交替结构。
      out.append(
          {
              "role": "user",
              "content": self._summarize_tool_context(msg.get("content")),
          }
      )
      continue
  ```

- [ ] **Step 3：验证测试**

  运行：`pytest tests/ -k "anthropic or provider" -q`
  预期：PASS（如无相关测试则继续）

- [ ] **Step 4：提交**

  ```bash
  git add src/nini/agent/providers/anthropic_provider.py
  git commit -m "fix(agent): Anthropic provider 工具结果角色从 assistant 改为 user"
  ```

---

## Task 3：沙箱策略—移除 `__class__` 双下划线白名单（P0）

**Files:**
- Modify: `src/nini/sandbox/policy.py:358`

- [ ] **Step 1：理解漏洞**

  `policy.py` 约 358 行，`_ALLOWED_DUNDERS = {"__name__", "__doc__", "__len__", "__class__"}`。
  `__class__` 是 Python 沙箱逃逸的经典入口，攻击者可通过 `obj.__class__` 配合 `type()` 遍历 MRO 找到系统调用。

- [ ] **Step 2：修改白名单**

  将：
  ```python
  _ALLOWED_DUNDERS = {"__name__", "__doc__", "__len__", "__class__"}
  ```
  改为：
  ```python
  _ALLOWED_DUNDERS = {"__name__", "__doc__", "__len__"}
  ```

- [ ] **Step 3：验证测试**

  运行：`pytest tests/test_phase3_run_code.py tests/test_sandbox_import_fix.py tests/test_security_hardening.py -q`
  预期：PASS（沙箱策略测试不依赖 `__class__` 访问）

- [ ] **Step 4：提交**

  ```bash
  git add src/nini/sandbox/policy.py
  git commit -m "fix(sandbox): 移除 __class__ 双下划线白名单，堵塞沙箱逃逸入口"
  ```

---

## Task 4：沙箱执行器—添加受限反序列化器防止 pickle RCE（P0）

**Files:**
- Modify: `src/nini/sandbox/executor.py:806-819`

- [ ] **Step 1：理解漏洞**

  父进程通过 `parent_conn.recv()`（底层 `pickle.loads()`）接收子进程数据。用户代码可向 `result` 变量赋一个含 `__reduce__` 的对象，父进程反序列化时执行任意命令。

- [ ] **Step 2：在文件顶部导入 io**

  检查文件顶部是否已有 `import io`；若没有，在已有 import 块中加入：
  ```python
  import io
  ```

- [ ] **Step 3：在 `_sandbox_worker` 函数上方添加受限反序列化器**

  在 `class SandboxExecutor:` 之前，添加以下代码：
  ```python
  class _RestrictedUnpickler(pickle.Unpickler):
      """受限反序列化器：仅允许沙箱结果中合法出现的类型，防止子进程发送恶意 __reduce__ payload。"""

      _SAFE: dict[str, set[str]] = {
          "builtins": {
              "dict", "list", "tuple", "set", "frozenset",
              "str", "int", "float", "bool", "bytes", "bytearray",
              "complex", "NoneType",
          },
          "pandas.core.frame": {"DataFrame"},
          "pandas.core.series": {"Series"},
          "pandas.core.indexes.base": {"Index"},
          "pandas.core.indexes.range": {"RangeIndex"},
          "pandas.core.indexes.multi": {"MultiIndex"},
          "pandas.core.indexes.datetimes": {"DatetimeIndex"},
          "numpy": {"ndarray", "dtype"},
          "numpy.core.multiarray": {"scalar", "_reconstruct"},
          "numpy.core._multiarray_umath": {"_reconstruct"},
          "_codecs": {"encode"},
          "datetime": {"datetime", "date", "time", "timedelta"},
          "collections": {"OrderedDict"},
      }

      def find_class(self, module: str, name: str) -> Any:
          if module in self._SAFE and name in self._SAFE[module]:
              return super().find_class(module, name)
          raise pickle.UnpicklingError(
              f"不允许从沙箱反序列化类型: {module}.{name}"
          )


  def _safe_recv(conn: Connection) -> Any:
      """使用受限反序列化器接收沙箱进程数据，防止 pickle RCE。"""
      raw = conn.recv_bytes()
      return _RestrictedUnpickler(io.BytesIO(raw)).load()
  ```

- [ ] **Step 4：替换两处 `parent_conn.recv()` 调用**

  在 `_execute_sync` 方法中（约 806-819 行），将所有 `parent_conn.recv()` 替换为 `_safe_recv(parent_conn)`：

  将：
  ```python
  if parent_conn.poll(min(0.05, remaining)):
      try:
          payload = parent_conn.recv()
      except EOFError:
          payload = None
      break

  if not process.is_alive():
      # 进程已退出但可能还有最后一条消息尚未被读取
      if parent_conn.poll(0.05):
          try:
              payload = parent_conn.recv()
          except EOFError:
              payload = None
      break
  ```
  改为：
  ```python
  if parent_conn.poll(min(0.05, remaining)):
      try:
          payload = _safe_recv(parent_conn)
      except EOFError:
          payload = None
      except pickle.UnpicklingError as exc:
          logger.warning("沙箱进程发送了不安全的 payload，已拒绝: %s", exc)
          payload = {"success": False, "error": "沙箱返回了不允许的数据类型", "stdout": "", "stderr": ""}
      break

  if not process.is_alive():
      # 进程已退出但可能还有最后一条消息尚未被读取
      if parent_conn.poll(0.05):
          try:
              payload = _safe_recv(parent_conn)
          except EOFError:
              payload = None
          except pickle.UnpicklingError as exc:
              logger.warning("沙箱进程发送了不安全的 payload，已拒绝: %s", exc)
              payload = {"success": False, "error": "沙箱返回了不允许的数据类型", "stdout": "", "stderr": ""}
      break
  ```

- [ ] **Step 5：确认 `pickle` 已导入**

  检查文件顶部是否已导入 `pickle`；若无则加入。

- [ ] **Step 6：验证测试**

  运行：`pytest tests/test_phase3_run_code.py tests/test_phase4_websocket_run_code.py -q`
  预期：PASS

- [ ] **Step 7：提交**

  ```bash
  git add src/nini/sandbox/executor.py
  git commit -m "fix(sandbox): 添加受限反序列化器，防止沙箱进程 pickle RCE"
  ```

---

## Task 5：修复 `_save_entries()` 非原子写入导致数据丢失风险（P0）

**Files:**
- Modify: `src/nini/memory/long_term_memory.py:136-142`

- [ ] **Step 1：理解问题**

  `_save_entries()` 使用 `write_text()` 直接截断再写入，进程崩溃时文件变为空，所有长期记忆丢失。

- [ ] **Step 2：确认 `os` 已导入**

  检查文件顶部是否已有 `import os`；若无则加入。

- [ ] **Step 3：修改 `_save_entries` 为原子写入**

  将：
  ```python
  def _save_entries(self) -> None:
      """保存所有记忆条目。"""
      entries_file = self._storage_dir / "entries.jsonl"
      lines = []
      for entry in self._entries.values():
          lines.append(json.dumps(entry.to_dict(), ensure_ascii=False))
      entries_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
  ```
  改为：
  ```python
  def _save_entries(self) -> None:
      """保存所有记忆条目（原子写入：先写临时文件再 rename，避免写入中途崩溃导致数据丢失）。"""
      entries_file = self._storage_dir / "entries.jsonl"
      tmp_file = entries_file.with_suffix(".jsonl.tmp")
      lines = [json.dumps(entry.to_dict(), ensure_ascii=False) for entry in self._entries.values()]
      tmp_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
      os.replace(tmp_file, entries_file)
  ```

- [ ] **Step 4：运行测试**

  运行：`pytest tests/test_long_term_memory.py -q`
  预期：PASS

- [ ] **Step 5：提交**

  ```bash
  git add src/nini/memory/long_term_memory.py
  git commit -m "fix(memory): _save_entries 改为原子写入，防止崩溃导致 entries.jsonl 数据丢失"
  ```

---

## Task 6：修复 `_consolidating` 类级共享集合竞态条件（P0）

**Files:**
- Modify: `src/nini/memory/long_term_memory.py:107,273-289`

- [ ] **Step 1：理解问题**

  `_consolidating: set[str] = set()` 是类属性（所有实例共享），并发 `add_memory` 可绕过 `in` 检查，导致两个沉淀任务并发执行并竞争写入同一文件。此外若事件循环关闭时任务未执行，`discard` 永远不会被调用，session_id 泄漏。

- [ ] **Step 2：将类属性改为实例级 asyncio.Lock 字典**

  将类体顶部的：
  ```python
  # session 级 in-flight 锁，防止高重要性记忆触发的沉淀任务并发重复执行
  _consolidating: set[str] = set()
  ```
  改为：
  ```python
  # session 级 in-flight 锁（per-session asyncio.Lock），防止沉淀任务并发重复执行
  _consolidating_locks: dict[str, asyncio.Lock] = {}
  ```

  同时在文件顶部确认已导入 `asyncio`。

- [ ] **Step 3：修改 `add_memory` 中使用 lock 的部分**

  将（约 272-289 行）：
  ```python
  # 高重要性记忆自动触发沉淀（importance_score >= 0.8），使用 in-flight 锁防并发
  if importance_score >= 0.8 and source_session_id:
      if source_session_id not in LongTermMemoryStore._consolidating:
          LongTermMemoryStore._consolidating.add(source_session_id)

          async def _do_consolidate(sid: str) -> None:
              try:
                  await consolidate_session_memories(sid)
              finally:
                  LongTermMemoryStore._consolidating.discard(sid)

          consolidate_coro = _do_consolidate(source_session_id)
          try:
              from nini.utils.background_tasks import track_background_task

              track_background_task(consolidate_coro)
          except Exception:
              consolidate_coro.close()
              LongTermMemoryStore._consolidating.discard(source_session_id)
  ```
  改为：
  ```python
  # 高重要性记忆自动触发沉淀（importance_score >= 0.8），使用 per-session Lock 防并发
  if importance_score >= 0.8 and source_session_id:
      if source_session_id not in LongTermMemoryStore._consolidating_locks:
          LongTermMemoryStore._consolidating_locks[source_session_id] = asyncio.Lock()
      session_lock = LongTermMemoryStore._consolidating_locks[source_session_id]

      if not session_lock.locked():
          async def _do_consolidate(sid: str, lock: asyncio.Lock) -> None:
              async with lock:
                  try:
                      await consolidate_session_memories(sid)
                  finally:
                      # 锁释放后移除，避免 dict 无限增长
                      LongTermMemoryStore._consolidating_locks.pop(sid, None)

          consolidate_coro = _do_consolidate(source_session_id, session_lock)
          try:
              from nini.utils.background_tasks import track_background_task

              track_background_task(consolidate_coro)
          except Exception:
              consolidate_coro.close()
              LongTermMemoryStore._consolidating_locks.pop(source_session_id, None)
  ```

- [ ] **Step 4：在 `delete_memory` 中同样更新引用**

  搜索文件中其他使用 `_consolidating` 的地方，统一改为 `_consolidating_locks`。

- [ ] **Step 5：运行测试**

  运行：`pytest tests/test_long_term_memory.py tests/test_memory_consolidation.py -q`
  预期：PASS

- [ ] **Step 6：提交**

  ```bash
  git add src/nini/memory/long_term_memory.py
  git commit -m "fix(memory): _consolidating 类级集合改为 per-session asyncio.Lock，消除沉淀任务竞态"
  ```

---

## Task 7：R 沙箱—用 `source()` 替换 `eval(parse())` 并移除 `parallel` 包（P0）

**Files:**
- Modify: `src/nini/sandbox/r_executor.py:50-53,306`
- Modify: `src/nini/sandbox/r_policy.py:20`

### 7a：R wrapper 脚本改用 `source()`

- [ ] **Step 1：修改 `_build_wrapper_script` 中执行用户代码的方式**

  在 `r_executor.py` 约 304-308 行，将：
  ```r
  tryCatch({{
    user_code <- paste(readLines(user_code_path, warn = FALSE, encoding = "UTF-8"), collapse = "\\n")
    eval(parse(text = user_code), envir = .GlobalEnv)
  }}, error = function(e) {{
  ```
  改为：
  ```r
  tryCatch({{
    source({user_code_path_literal}, local = FALSE, encoding = "UTF-8")
  }}, error = function(e) {{
  ```

  其中 `user_code_path_literal` 已有对应的 Python 格式化变量（与 `{dataset_name_literal}` 相同模式），查找 `_build_wrapper_script` 函数签名中的参数并使用：
  ```python
  user_code_path_literal = repr(str(user_code_path)).replace("\\", "/")
  ```
  在 wrapper 字符串中将 `{user_code_path_literal}` 作为 `source()` 的路径参数（需加引号）。

  实际改为：
  ```r
  tryCatch({{
    source("{user_code_path_r}", local = FALSE, encoding = "UTF-8")
  }}, error = function(e) {{
  ```
  在 `_build_wrapper_script` 参数处计算：
  ```python
  user_code_path_r = str(user_code_path).replace("\\", "/")
  ```
  并在 wrapper f-string 中插入。

### 7b：移除 `parallel` 包

- [ ] **Step 2：从 `ALLOWED_R_PACKAGES` 移除 `parallel`**

  在 `src/nini/sandbox/r_policy.py` 第 20 行，删除：
  ```python
  "parallel",
  ```

- [ ] **Step 3：在 `BANNED_R_CALLS` 中添加并行函数**

  找到 `BANNED_R_CALLS` 集合，加入：
  ```python
  "mclapply", "mcfork", "makeCluster", "stopCluster", "clusterEvalQ",
  "clusterApply", "clusterCall", "clusterMap", "parLapply", "parSapply",
  ```

### 7c：修复 R 包提取正则不过滤注释

- [ ] **Step 4：在 `_extract_required_packages` 中先剥离注释**

  在 `r_executor.py` 中，将：
  ```python
  _PACKAGE_REF_RE = re.compile(
      r"\b(?:library|require|requireNamespace)\s*\(\s*['\"]?([A-Za-z][A-Za-z0-9._]*)['\"]?",
      flags=re.IGNORECASE,
  )
  ```
  保持正则不变，但在使用它的函数中先剥离注释。找到 `_extract_required_packages(code)` 函数，在 `re.findall` 之前添加：
  ```python
  # 剥离 R 单行注释（# 开头），防止注释触发自动安装
  code_no_comments = re.sub(r"#[^\n]*", "", code)
  ```
  然后将后续的 `_PACKAGE_REF_RE.findall(code)` 改为 `_PACKAGE_REF_RE.findall(code_no_comments)`。

- [ ] **Step 5：运行测试**

  运行：`pytest tests/test_r_code_exec.py tests/test_r_executor.py tests/test_r_policy.py -q`
  预期：PASS

- [ ] **Step 6：提交**

  ```bash
  git add src/nini/sandbox/r_executor.py src/nini/sandbox/r_policy.py
  git commit -m "fix(sandbox): R 沙箱用 source() 替换 eval(parse())，移除 parallel 包，过滤注释触发包安装"
  ```

---

## Task 8：沙箱执行器—`execute()` 改用 `asyncio.to_thread` 避免阻塞事件循环（P1）

**Files:**
- Modify: `src/nini/sandbox/executor.py:725-746`
- Modify: `src/nini/sandbox/r_executor.py:406-421`

- [ ] **Step 1：修改 Python 沙箱 `execute()` 方法**

  将 `SandboxExecutor.execute()` 中：
  ```python
  async def execute(
      self,
      *,
      code: str,
      session_id: str,
      datasets: dict[str, pd.DataFrame],
      dataset_name: str | None = None,
      persist_df: bool = False,
      extra_allowed_imports: Iterable[str] | None = None,
  ) -> dict[str, Any]:
      """异步执行入口。

      这里直接调用同步实现，避免在线程池里再启动 `spawn` 子进程时出现阻塞。
      """
      return self._execute_sync(
          code=code,
          session_id=session_id,
          datasets=datasets,
          dataset_name=dataset_name,
          persist_df=persist_df,
          extra_allowed_imports=extra_allowed_imports,
      )
  ```
  改为：
  ```python
  async def execute(
      self,
      *,
      code: str,
      session_id: str,
      datasets: dict[str, pd.DataFrame],
      dataset_name: str | None = None,
      persist_df: bool = False,
      extra_allowed_imports: Iterable[str] | None = None,
  ) -> dict[str, Any]:
      """异步执行入口：在线程池中运行同步逻辑，避免阻塞 asyncio 事件循环。"""
      import functools

      return await asyncio.to_thread(
          functools.partial(
              self._execute_sync,
              code=code,
              session_id=session_id,
              datasets=datasets,
              dataset_name=dataset_name,
              persist_df=persist_df,
              extra_allowed_imports=extra_allowed_imports,
          )
      )
  ```

- [ ] **Step 2：同样修改 R 沙箱 `execute()` 方法**

  在 `r_executor.py` 中，同理替换 `RExecutor.execute()`：
  ```python
  async def execute(
      self,
      *,
      code: str,
      session_id: str,
      datasets: dict[str, pd.DataFrame],
      dataset_name: str | None = None,
      persist_df: bool = False,
  ) -> dict[str, Any]:
      """异步执行入口：在线程池中运行同步逻辑，避免阻塞 asyncio 事件循环。"""
      import asyncio
      import functools

      return await asyncio.to_thread(
          functools.partial(
              self._execute_sync,
              code=code,
              session_id=session_id,
              datasets=datasets,
              dataset_name=dataset_name,
              persist_df=persist_df,
          )
      )
  ```

- [ ] **Step 3：运行测试**

  运行：`pytest tests/test_phase3_run_code.py tests/test_r_code_exec.py -q`
  预期：PASS

- [ ] **Step 4：提交**

  ```bash
  git add src/nini/sandbox/executor.py src/nini/sandbox/r_executor.py
  git commit -m "fix(sandbox): execute() 改用 asyncio.to_thread，避免阻塞 FastAPI 事件循环"
  ```

---

## Task 9：修复 `conversation.py append()` 同步 IO 阻塞事件循环（P1）

**Files:**
- Modify: `src/nini/memory/conversation.py:286-313`

- [ ] **Step 1：理解问题**

  `ConversationMemory.append()` 是同步方法，内部有 `open(..., "a")` 同步文件写入，在 FastAPI asyncio 上下文中直接调用会阻塞事件循环。CLAUDE.md 明确要求"不写同步阻塞代码"。

- [ ] **Step 2：将 `append` 内的 JSONL 写入包装为异步**

  在 `ConversationMemory` 的 `__init__` 中添加写锁（如果尚不存在）：
  ```python
  self._write_lock = asyncio.Lock()
  ```
  确认文件顶部已导入 `asyncio`。

  然后将 `append` 方法从同步改为异步：
  ```python
  async def append(self, entry: dict[str, Any]) -> None:
      """追加一条记录，自动引用化大型数据。双写 JSONL + SQLite。"""
      self._ensure_dir()

      # 提取大型数据到单独文件
      entry_with_refs = self._extract_large_payloads(entry)

      # 添加时间戳
      entry_with_refs.setdefault("_ts", datetime.now(timezone.utc).isoformat())

      # 主路径：写入 JSONL（加锁确保并发安全）
      async with self._write_lock:
          await asyncio.to_thread(self._sync_write_jsonl, entry_with_refs)

      # 次路径：写入 SQLite
      try:
          from nini.memory.db import get_session_db, insert_message

          conn = get_session_db(self._dir, create=False)
          if conn is not None:
              try:
                  await asyncio.to_thread(insert_message, conn, entry_with_refs)
              except Exception as exc:
                  logger.debug("[Memory] SQLite 双写失败（不影响 JSONL）: %s", exc)
              finally:
                  conn.close()
      except Exception:
          logger.warning("[Memory] SQLite 连接获取失败", exc_info=True)

  def _sync_write_jsonl(self, entry: dict[str, Any]) -> None:
      """同步写入 JSONL 文件（在线程池中调用）。"""
      with open(self._path, "a", encoding="utf-8") as f:
          f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
  ```

- [ ] **Step 3：更新所有调用方**

  在整个代码库中搜索 `.append(` 调用（涉及 ConversationMemory 实例），确保调用方都用 `await memory.append(...)`。

  运行：`grep -rn "\.append(" src/nini/agent/ src/nini/api/ --include="*.py" | grep -v "__pycache__"`
  
  对每个调用方，确认它在 `async def` 函数中，并加上 `await`。

- [ ] **Step 4：修复 `InMemoryConversationMemory.append` 加锁**

  在 `InMemoryConversationMemory` 的 `__init__` 中加锁，并将 `append` 改为 async：
  ```python
  def __init__(self) -> None:
      self._entries: list[dict[str, Any]] = []
      self._write_lock = asyncio.Lock()

  async def append(self, entry: dict[str, Any]) -> None:
      """追加一条记录到内存（加锁防止并发追加导致迭代异常）。"""
      entry_copy = dict(entry)
      entry_copy.setdefault("_ts", datetime.now(timezone.utc).isoformat())
      async with self._write_lock:
          self._entries.append(entry_copy)
  ```

- [ ] **Step 5：运行测试**

  运行：`pytest tests/test_in_memory_conversation.py tests/test_context_memory_injection.py tests/test_compression_segments.py -q`
  预期：PASS

- [ ] **Step 6：提交**

  ```bash
  git add src/nini/memory/conversation.py
  git commit -m "fix(memory): conversation append() 改为 async，加锁防止并发写入冲突"
  ```

---

## Task 10：修复 DNS 重绑定 SSRF（P1）

**Files:**
- Modify: `src/nini/tools/fetch_url.py:210-260`

- [ ] **Step 1：理解问题**

  `_validate_url` 在发请求前解析 DNS，但 `socket.getaddrinfo` 和实际 HTTP 请求之间存在时间窗口。攻击者控制 DNS，验证时返回公有 IP，请求时切换到私有 IP（如 `169.254.169.254`），绕过 SSRF 防护。

- [ ] **Step 2：实现在连接时重验证 IP 的自定义 httpx transport**

  在 `fetch_url.py` 顶部，在已有导入之后添加：
  ```python
  import ssl
  ```

  在 `FetchURLTool` 类内或文件中添加辅助类：
  ```python
  class _SSRFGuardTransport(httpx.AsyncHTTPTransport):
      """自定义 transport：在建立 TCP 连接后二次验证目标 IP，防止 DNS 重绑定 SSRF。"""

      async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
          host = request.url.host
          # 对非 IP 域名做连接时 IP 验证
          try:
              addr_info = socket.getaddrinfo(host, None, socket.AF_UNSPEC)
              for _, _, _, _, sockaddr in addr_info:
                  resolved_ip = ipaddress.ip_address(sockaddr[0])
                  if (
                      resolved_ip.is_private
                      or resolved_ip.is_loopback
                      or resolved_ip.is_link_local
                      or resolved_ip.is_reserved
                  ):
                      raise httpx.ConnectError(
                          f"连接时检测到目标 IP {resolved_ip} 为私有地址，拒绝连接（DNS 重绑定防护）"
                      )
          except (socket.gaierror, ValueError):
              pass  # IP 地址或解析失败，由上层 _validate_url 处理
          return await super().handle_async_request(request)
  ```

- [ ] **Step 3：在 `_fetch` 的 httpx 请求中使用该 transport**

  找到 `_fetch` 方法中类似 `async with httpx.AsyncClient() as client:` 的代码，改为：
  ```python
  async with httpx.AsyncClient(transport=_SSRFGuardTransport(), timeout=_TIMEOUT) as client:
  ```
  （保持其他参数不变）

- [ ] **Step 4：运行测试**

  运行：`pytest tests/test_fetch_url_skill.py -q`
  预期：PASS

- [ ] **Step 5：提交**

  ```bash
  git add src/nini/tools/fetch_url.py
  git commit -m "fix(tools): fetch_url 添加连接时 IP 二次验证，防止 DNS 重绑定 SSRF"
  ```

---

## Task 11：修复 `long_term_memory` 中 `asyncio.create_task` 同步调用和 `search()` 不持久化访问统计（P1）

**Files:**
- Modify: `src/nini/memory/long_term_memory.py:250-267,358-371`

### 11a：`asyncio.create_task` 在同步方法中

- [ ] **Step 1：修复 `add_memory` 中的 `asyncio.create_task`**

  在 `add_memory`（同步方法）中，约 250-267 行，将：
  ```python
  if self._vector_store and self._vector_store._initialized:
      try:
          import asyncio

          asyncio.create_task(
              self._vector_store.add_document(...)
          )
      except Exception as e:
          logger.warning(f"添加记忆到向量索引失败: {e}")
  ```
  改为：
  ```python
  if self._vector_store and self._vector_store._initialized:
      try:
          loop = asyncio.get_running_loop()
          loop.create_task(
              self._vector_store.add_document(
                  doc_id=entry.id,
                  content=f"{entry.summary}\n{entry.content}",
                  metadata={
                      "memory_type": entry.memory_type,
                      "analysis_type": entry.analysis_type,
                      "tags": entry.tags,
                  },
              )
          )
      except RuntimeError:
          # 无运行中的事件循环（如测试环境）：跳过向量索引，不影响主路径
          logger.debug("无运行中事件循环，跳过向量索引更新")
      except Exception as e:
          logger.warning(f"添加记忆到向量索引失败: {e}")
  ```

### 11b：`search()` 不持久化访问统计

- [ ] **Step 2：在 `search()` 末尾添加持久化调用**

  在 `search()` 方法（约 348-387 行）的末尾，`return results[:top_k]` 之前，添加：
  ```python
  # 持久化访问统计更新（仅在有结果时，避免无效写入）
  if results:
      self._save_entries()
  ```

- [ ] **Step 3：运行测试**

  运行：`pytest tests/test_long_term_memory.py -q`
  预期：PASS

- [ ] **Step 4：提交**

  ```bash
  git add src/nini/memory/long_term_memory.py
  git commit -m "fix(memory): 修复 create_task 同步调用，search() 持久化访问统计"
  ```

---

## Task 12：修复 `asyncio.get_event_loop()` 已废弃（P2）

**Files:**
- Modify: `src/nini/knowledge/hybrid_retriever.py:260`

- [ ] **Step 1：替换废弃调用**

  将：
  ```python
  _, bm25_raw = await asyncio.get_event_loop().run_in_executor(
      None, self._bm25_retriever.search, query, top_k * 2
  )
  ```
  改为：
  ```python
  _, bm25_raw = await asyncio.get_running_loop().run_in_executor(
      None, self._bm25_retriever.search, query, top_k * 2
  )
  ```

- [ ] **Step 2：运行测试**

  运行：`pytest tests/test_hybrid_retriever.py tests/test_semantic_retrieval.py -q`
  预期：PASS

- [ ] **Step 3：提交**

  ```bash
  git add src/nini/knowledge/hybrid_retriever.py
  git commit -m "fix(knowledge): 替换已废弃的 get_event_loop()，改用 get_running_loop()"
  ```

---

## Task 13：将 `_resolve_dataset_name` 提取到 `Tool` 基类消除重复（P2）

**Files:**
- Modify: `src/nini/tools/base.py`
- Modify: `src/nini/tools/stat_test.py:289-316`
- Modify: `src/nini/tools/stat_model.py:150-177`

- [ ] **Step 1：在 `Tool` 基类中添加 `_resolve_dataset_name`**

  在 `src/nini/tools/base.py` 中，在 `Tool` 抽象基类内添加（在 `name` 属性之后）：
  ```python
  def _resolve_dataset_name(
      self,
      session: "Session",
      params: dict[str, Any],
  ) -> "str | ToolResult | None":
      """从参数中解析数据集名称，支持多种别名，自动推断单数据集场景。"""
      dataset_name = str(params.get("dataset_name", "")).strip()
      if dataset_name:
          return dataset_name

      for alias in ("dataset", "dataset_id", "input_dataset", "source_dataset"):
          value = params.get(alias)
          if isinstance(value, str) and value.strip():
              return value.strip()

      dataset_names = [
          name for name in session.datasets.keys() if isinstance(name, str) and name.strip()
      ]
      if len(dataset_names) == 1:
          return dataset_names[0]
      if not dataset_names:
          return ToolResult(success=False, message="缺少 dataset_name，且当前会话没有可用数据集")

      preview = ", ".join(dataset_names[:5])
      suffix = "..." if len(dataset_names) > 5 else ""
      return ToolResult(
          success=False,
          message=f"缺少 dataset_name，当前会话存在多个数据集，请明确指定（可选: {preview}{suffix}）",
      )
  ```

  同时在 `base.py` 文件顶部确认 `TYPE_CHECKING` 块中已有 `Session` 的导入，或在 `if TYPE_CHECKING:` 块中加入：
  ```python
  from nini.agent.session import Session
  ```

- [ ] **Step 2：删除 `stat_test.py` 中的重复方法**

  删除 `src/nini/tools/stat_test.py` 中 `StatTestTool._resolve_dataset_name` 方法（约 289-316 行）。

- [ ] **Step 3：删除 `stat_model.py` 中的重复方法**

  删除 `src/nini/tools/stat_model.py` 中 `StatModelTool._resolve_dataset_name` 方法（约 150-177 行）。

- [ ] **Step 4：运行测试**

  运行：`pytest tests/test_foundation_tools.py tests/test_statistics_split.py -q`
  预期：PASS

- [ ] **Step 5：提交**

  ```bash
  git add src/nini/tools/base.py src/nini/tools/stat_test.py src/nini/tools/stat_model.py
  git commit -m "refactor(tools): 提取 _resolve_dataset_name 到 Tool 基类，消除 stat_test/stat_model 重复代码"
  ```

---

## Task 14：修复 `tool_executor.py` 英文 docstring（P2）

**Files:**
- Modify: `src/nini/agent/components/tool_executor.py`

- [ ] **Step 1：翻译模块级注释**

  将文件开头：
  ```python
  """Tool execution logic for AgentRunner.

  Handles tool invocation, result serialization, and related utilities.
  """
  ```
  改为：
  ```python
  """AgentRunner 的工具执行逻辑。

  处理工具调用、结果序列化及相关工具函数。
  """
  ```

- [ ] **Step 2：翻译函数级英文 docstring**

  将 `execute_tool` 的 Args 部分翻译：
  ```python
  async def execute_tool(...) -> Any:
      """通过工具注册中心执行工具调用。

      Args:
          tool_registry: 工具注册中心，用于执行工具调用。
          session: 当前会话上下文。
          name: 要执行的工具/函数名称。
          arguments: JSON 编码的参数字符串。

      Returns:
          工具执行结果，失败时返回错误字典。
      """
  ```

  将 `parse_tool_arguments` 的英文 docstring 翻译：
  ```python
  def parse_tool_arguments(arguments: str) -> dict[str, Any]:
      """解析工具参数 JSON，解析失败时返回空字典。

      Args:
          arguments: JSON 编码的参数字符串。

      Returns:
          解析后的字典，解析失败返回空字典。
      """
  ```

  将 `serialize_tool_result_for_memory` 中英文部分翻译：
  ```python
  def serialize_tool_result_for_memory(result: Any, *, tool_name: str = "") -> str:
      """将工具结果序列化以存储到会话记忆。

      Args:
          result: 要序列化的工具执行结果。
          tool_name: 工具名称，用于对特定工具结果做额外结构化提取。

      Returns:
          结果的 JSON 字符串表示。
      """
  ```

  对文件中其余含英文 Args/Returns 的函数做同样翻译处理。

- [ ] **Step 3：运行测试**

  运行：`pytest tests/ -q --co -q 2>&1 | head -5`（仅验证文件可被导入，无语法错误）
  预期：无 ImportError/SyntaxError

- [ ] **Step 4：提交**

  ```bash
  git add src/nini/agent/components/tool_executor.py
  git commit -m "docs(agent): 翻译 tool_executor.py 英文注释为中文，符合 CLAUDE.md 语言要求"
  ```

---

## Task 15：修复 auth cookie 签名缺少 nonce（P2）

**Files:**
- Modify: `src/nini/api/auth_utils.py`

- [ ] **Step 1：理解问题**

  `_build_cookie_signature(api_key, issued_at_ts)` 的 HMAC payload 仅有时间戳，若 API Key 泄露，攻击者可枚举 8 小时窗口内所有有效 cookie。加入随机 nonce 后，即使 API Key 泄露也无法伪造 cookie。

- [ ] **Step 2：修改签名函数和 cookie 构建逻辑**

  在文件顶部已有 `import hmac, hashlib`，添加 `import secrets`（如无）。

  将：
  ```python
  def _build_cookie_signature(api_key: str, issued_at_ts: int) -> str:
      payload = f"{issued_at_ts}".encode("utf-8")
      secret = api_key.encode("utf-8")
      return hmac.new(secret, payload, hashlib.sha256).hexdigest()


  def build_auth_session_cookie_value(api_key: str, now: datetime | None = None) -> str:
      """生成 HttpOnly 鉴权 Cookie 值。"""
      current = now or datetime.now(timezone.utc)
      issued_at_ts = int(current.timestamp())
      signature = _build_cookie_signature(api_key, issued_at_ts)
      return f"{issued_at_ts}.{signature}"
  ```
  改为：
  ```python
  def _build_cookie_signature(api_key: str, issued_at_ts: int, nonce: str) -> str:
      """生成包含 nonce 的 HMAC 签名，防止时间戳枚举攻击。"""
      payload = f"{issued_at_ts}.{nonce}".encode("utf-8")
      secret = api_key.encode("utf-8")
      return hmac.new(secret, payload, hashlib.sha256).hexdigest()


  def build_auth_session_cookie_value(api_key: str, now: datetime | None = None) -> str:
      """生成 HttpOnly 鉴权 Cookie 值（含随机 nonce）。"""
      current = now or datetime.now(timezone.utc)
      issued_at_ts = int(current.timestamp())
      nonce = secrets.token_hex(16)
      signature = _build_cookie_signature(api_key, issued_at_ts, nonce)
      return f"{issued_at_ts}.{nonce}.{signature}"
  ```

- [ ] **Step 3：修改验证函数以解析新格式**

  将 `is_valid_auth_session_cookie` 中：
  ```python
  try:
      issued_at_raw, signature = cookie_value.split(".", 1)
      issued_at_ts = int(issued_at_raw)
  except (ValueError, TypeError):
      return False
  ...
  expected = _build_cookie_signature(normalized_key, issued_at_ts)
  ```
  改为：
  ```python
  try:
      parts = cookie_value.split(".", 2)
      if len(parts) == 3:
          # 新格式：issued_at.nonce.signature
          issued_at_raw, nonce, signature = parts
      elif len(parts) == 2:
          # 旧格式兼容（无 nonce）：issued_at.signature — 仍验证，逐步淘汰
          issued_at_raw, signature = parts
          nonce = ""
      else:
          return False
      issued_at_ts = int(issued_at_raw)
  except (ValueError, TypeError):
      return False
  ...
  expected = _build_cookie_signature(normalized_key, issued_at_ts, nonce)
  ```

- [ ] **Step 4：运行测试**

  运行：`pytest tests/test_api_auth.py -q`
  预期：PASS（需检查测试是否用旧格式构建 cookie，若有需同步更新）

- [ ] **Step 5：提交**

  ```bash
  git add src/nini/api/auth_utils.py
  git commit -m "fix(api): cookie 签名加入随机 nonce，防止时间戳枚举攻击"
  ```

---

## Task 16：修复 `r_auto_install_packages` 默认为 True（P2）

**Files:**
- Modify: `src/nini/config.py:263`

- [ ] **Step 1：修改默认值**

  在 `config.py` 中，找到：
  ```python
  r_auto_install_packages: bool = True
  ```
  改为：
  ```python
  r_auto_install_packages: bool = False
  ```

- [ ] **Step 2：更新 `.env.example` 或 `nini init` 模板中的说明**

  在相关模板/注释中添加提示：启用 R 包自动安装需手动设置 `NINI_R_AUTO_INSTALL_PACKAGES=true`。

- [ ] **Step 3：运行测试**

  运行：`pytest tests/test_r_code_exec.py -q`
  预期：PASS（测试应能处理包不可用的情况）

- [ ] **Step 4：提交**

  ```bash
  git add src/nini/config.py
  git commit -m "fix(config): r_auto_install_packages 默认改为 False，需显式启用以避免 DoS 风险"
  ```

---

## Task 17：修复 `knowledge/vector_store.py` 注释哈希算法不一致（P2）

**Files:**
- Modify: `src/nini/knowledge/vector_store.py`

- [ ] **Step 1：修正注释**

  在 `vector_store.py` 文件头部或 `_compute_file_hashes` 方法的注释中，将"MD5"相关描述改为"SHA-256"，与实现一致。具体找到注释中提及"MD5"的行，替换为"SHA-256"。

- [ ] **Step 2：提交**

  ```bash
  git add src/nini/knowledge/vector_store.py
  git commit -m "docs(knowledge): 修正 vector_store 注释中 MD5 → SHA-256，与实现一致"
  ```

---

## 最终验证

- [ ] **运行完整测试套件**

  ```bash
  python scripts/check_event_schema_consistency.py && pytest -q --tb=short 2>&1 | tail -20
  ```
  预期：全部通过，无新增失败。

- [ ] **类型检查**

  ```bash
  mypy src/nini
  ```
  预期：无新增错误。
