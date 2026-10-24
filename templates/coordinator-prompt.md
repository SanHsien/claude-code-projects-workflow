# 協調者提示詞：產生平行任務計畫

把下面整段貼給負責規劃的 agent（Claude Code、Codex 等）。它只規劃、不改程式碼，產出可以直接交給
`worktree_tasks.py lint` 檢查的計畫檔。

---

先閱讀專案結構與 `PROJECT_CONTEXT.md`，**不要修改任何檔案**。把下面的需求拆成可以平行進行的子任務：

<需求寫在這裡>

拆分規則：

1. 每個子任務只負責一組**互不重疊**的路徑。兩個任務需要改同一個檔案，就合併成一個任務，或排成先後兩輪。
2. 每個子任務都要有一條能在本機跑完的驗證指令。
3. 共用的型別、介面、設定檔，交給單一任務負責，其他任務只讀不改。
4. 有先後依賴的工作不要放進同一輪；在回覆中列出「下一輪」要做什麼。

輸出一個 JSON 檔，格式如下（`id` 只能用小寫英數與 `-`）：

```json
{
  "base": "main",
  "context_file": "PROJECT_CONTEXT.md",
  "tasks": [
    {"id": "short-name", "goal": "一到兩句：要做什麼、怎樣算完成", "paths": ["src/x/**"], "verify": "指令"}
  ]
}
```

輸出後我會跑 `python worktree_tasks.py lint plan.json`；有 ERROR 你要修正計畫，有 WARNING 你要說明為什麼可以接受。
