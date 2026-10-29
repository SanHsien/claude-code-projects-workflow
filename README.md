[English](README.en.md) | 中文版

# claude-code-projects-workflow

**多個 AI agent 平行改同一個 repo 時，派工前先抓出範圍重疊，合併前先預測衝突。**

一個零依賴的 Python 單檔工具 `worktree_tasks.py`，加上三份範本。適用 Claude Code、Codex 或任何能在
`git worktree` 裡工作的 agent，也適用人工分工。

## 解決什麼問題

把需求拆給多個 agent 平行做，最常見的失敗不是 agent 寫錯，而是：

- 兩個任務的範圍其實重疊，各自完成後合併才發現衝突
- agent 順手改了範圍外的檔案（README、設定檔、共用型別）
- 有人忘了提交，收尾時把未提交的工作連 worktree 一起刪掉

`worktree_tasks.py` 在每個關口各做一次機械檢查：

```text
plan.json ──lint──> up ──(agents 各自在 worktree 工作)──> check ──(你合併)──> down
            │        │                                      │                    │
       範圍重疊？  建 worktree＋分支              超出範圍？未提交？        有未提交的不刪
       id/目標/驗證  寫入任務說明檔                依計畫順序合併會衝突？    未合併的分支不刪
```

## 快速開始

需要 Python 3.10+ 與 git 2.38+（`git merge-tree --write-tree`）。不用安裝任何套件。

```bash
# 1. 寫計畫檔（或用 templates/coordinator-prompt.md 讓 agent 幫你寫）
cp templates/plan.example.json plan.json

# 2. 派工前檢查
python worktree_tasks.py --repo <你的 repo> lint plan.json

# 3. 建立 worktree；每個 worktree 會有一份 .parallel-task.md 寫著目標、可改路徑、不可碰的路徑
python worktree_tasks.py --repo <你的 repo> up plan.json

# 4. 在每個 worktree 啟動 agent，請它先讀 .parallel-task.md

# 5. 合併前檢查
python worktree_tasks.py --repo <你的 repo> check plan.json

# 6. 合併完收尾（只刪已合併的分支）
python worktree_tasks.py --repo <你的 repo> down plan.json --delete-merged
```

實際輸出（在暫存 repo 裡，故意讓 `api` 任務改了範圍外的 `README.md`）：

```text
$ python worktree_tasks.py check plan.json
ERROR: api: README.md is outside the task's paths
ERROR: ui: merging task/ui after the earlier tasks conflicts in: README.md
FAILED: 2 error(s), 0 warning(s)
```

結束碼：`0` 通過、`1` 檢查發現問題、`2` 用法或環境錯誤。可以直接放進腳本或 CI 當閘門。

`lint` 與 `check` 可加 `--json`，把結果輸出成結構化 JSON 給協調者或 CI 解析（結束碼不變）：

```bash
python worktree_tasks.py lint plan.json --json
```

```json
{
  "command": "lint",
  "ok": false,
  "errors": 1,
  "warnings": 0,
  "findings": [{"level": "error", "message": "src/api/server.py is claimed by tasks api, refactor"}],
  "message": null
}
```

## 計畫檔格式

```json
{
  "base": "main",
  "branch_prefix": "task/",
  "worktree_root": "",
  "context_file": "PROJECT_CONTEXT.md",
  "tasks": [
    {"id": "api-pagination", "goal": "…", "paths": ["src/api/**", "tests/api/**"], "verify": "python -m pytest tests/api -q"}
  ]
}
```

| 欄位 | 說明 |
|---|---|
| `base` | 從哪個分支開工、最後合併回哪裡。預設 `main` |
| `branch_prefix` | 任務分支名稱前綴。預設 `task/` |
| `worktree_root` | worktree 放哪。空白＝repo 旁邊的 `<repo>.worktrees/`；相對路徑以 repo 為基準 |
| `context_file` | 共享脈絡檔，任務說明檔會指向它 |
| `tasks[].id` | 小寫英數與 `-`，同時是分支與資料夾名稱 |
| `tasks[].paths` | 這個任務可以改的路徑。`*` 不跨目錄、`**` 跨任意層、結尾 `/` 代表整個目錄 |
| `tasks[].verify` | 驗證指令，會寫進任務說明檔；沒填會給警告 |

## 各檢查的判斷方式

| 指令 | ERROR（結束碼 1） | WARNING |
|---|---|---|
| `lint` | 同一個**已存在**的檔案被兩個任務宣告；id 不合法、結尾帶換行、為 Windows 保留名稱或重複；`branch_prefix` 組出無效分支名；沒寫目標；路徑指向 repo 外；base 不存在 | 兩個任務的路徑**可能**產生同一個新檔案（比對萬用字元前的目錄）；沒寫驗證指令；context 檔不存在 |
| `check` | 分支改了範圍外的檔案；worktree 有未提交改動；依計畫順序合併回 base 會衝突 | 分支不存在或還沒有提交 |
| `down` | worktree 有未提交改動（保留不刪） | 分支還沒合併進 base（保留不刪） |

`check` 的合併預測用 `git merge-tree` 加暫時 commit 串接，不會移動任何分支、不碰工作區。

## 範本

| 檔案 | 用途 |
|---|---|
| [`templates/plan.example.json`](templates/plan.example.json) | 三個互不重疊任務的計畫檔範例 |
| [`templates/PROJECT_CONTEXT.md`](templates/PROJECT_CONTEXT.md) | 所有 worker 共用的脈絡檔骨架：技術棧、目錄地圖、硬邊界、標準指令、完成的定義 |
| [`templates/coordinator-prompt.md`](templates/coordinator-prompt.md) | 給規劃 agent 的提示詞，產出能直接過 `lint` 的計畫檔 |

## 邊界

- 檢查是**路徑層級**的。兩個任務改不同檔案但語意上互相依賴（例如一個改介面、一個改呼叫端），
  合併不會衝突，但可能一起壞掉——這要靠合併後跑完整測試。
- `lint` 的「可能重疊」是保守估計，會有誤報；它是警告，不擋 `up`。
- 不負責啟動 agent、不呼叫任何模型 API、不自動合併。
- 管的是**本機 worktree** 的平行工作。Claude Code Projects 的雲端 Thread 各自在雲端分支上跑，不在你本機的 worktree 裡，這個工具檢查不到；它們的分工邊界要寫進專案指令，合併前衝突由 PR 流程處理。

## 和其他工具的關係

- [agent-cortex](https://github.com/SanHsien/agent-cortex)：完整的多 agent 控制面（spec、派工、重試、審查、交付證據），
  其中也有「改動必須在 allowed_paths 內」的事後檢查。本工具是它的**輕量對照**：單檔、不需要常駐服務，
  多做了派工前的範圍重疊檢查與合併前的衝突預測。需要完整生命週期管理用 cortex；只想在現有流程加兩道閘門用這個。
- [agent-advisor](https://github.com/SanHsien/agent-advisor)：決定**要不要**派工、派給哪個模型。本工具處理派工之後的檔案範圍。
- Claude Code 內建的 worktree 隔離：負責「建立隔離環境」。本工具負責「隔離環境之間會不會互相踩到」。

背景閱讀：[`docs/background-notes.md`](docs/background-notes.md)（Claude Code Projects 架構的閱讀筆記）。

## 開發

```bash
python -m unittest discover -s tests -v
```

Windows 完整檢查：`pwsh -File tools/dev_check.ps1`。

## 多 Agent 流水線

本 repo 是 [agent-relay](https://github.com/SanHsien/agent-relay) 多 Agent 派工與驗收流水線的一環（角色：Worktree 派工前範圍檢查與衝突預測）。與 agent-relay 的整合規劃中（Phase 2）。協定規格與所有相關 repo 的總目錄見 agent-relay。

## 授權

[MIT](LICENSE)
