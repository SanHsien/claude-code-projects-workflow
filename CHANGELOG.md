[English](CHANGELOG.en.md) | 中文版

# 變更紀錄

格式參考 [Keep a Changelog](https://keepachangelog.com/zh-TW/1.1.0/)，新的在上面。

## 2026-10-26

### 修正

- `worktree_tasks.py`：檔名含中文等非 ASCII 字元時，`lint` 看不出檔案被兩個任務同時認領、`check` 把範圍內的檔案誤報成「超出範圍」、未提交檔案以 `\346\226\207...` 跳脫字串回報。改用 `-z` 取得真實檔名。
- 任務 id 結尾帶換行（`"api\n"`）不再通過格式檢查；Windows 保留名稱（`con`、`nul`、`com1`…）會被擋下，不會等到 `up` 建資料夾時才失敗；`branch_prefix` 組出無效分支名稱時由 `lint`／`up` 報錯，不會建到一半才崩。

## 2026-10-25

### 修正

- `docs/background-notes.md`：對照 Claude Code Projects 與 worktrees 官方文件逐項校正。更正協調者只看得到 Thread 回報、共享記憶是專案指令加專案記憶（不是 repo 的 `MEMORY.md`）、雲端 Thread 只讀 `CLAUDE.md` 而不載入 skills／hooks／`.mcp.json`／`settings.json`；補上可改跑本機的 Thread、auto-fix、beta 與方案限制、`claude --worktree`。
- README 的「邊界」補一條：雲端 Thread 不在本機 worktree 裡，本工具檢查不到。

### 變更

- `.github/dependabot.yml` 加 `fleet-waiver: freshness`：本 repo 零依賴，沒有套件宣告可比對下限。

## 2026-10-24

### 修正

- `tools/dev_check.ps1`：`-BaseRef` 指向已不存在的 commit（例如 force push 之後）時，所有檢查都通過卻以結束碼 1 結束；改為明確 `exit 0`。

### 變更

- CI 的 actions 升到 `checkout` v7／`setup-python` v7 並釘 commit SHA，關閉 `persist-credentials`。
- 新增 `.github/dependabot.yml`（GitHub Actions，每週）與 CodeQL 掃描（Python、Actions）。

## 2026-10-19

### 新增

- `lint` 與 `check` 新增 `--json`：把結果輸出成結構化 JSON（`command`／`ok`／`errors`／`warnings`／`findings`／`message`）給協調者或 CI 解析，結束碼不變。

## 2026-10-16

### 新增

- `worktree_tasks.py`：`lint`／`up`／`check`／`down` 四個子指令。派工前檢查任務範圍重疊，建立 worktree 與任務說明檔，合併前檢查越界改動、未提交改動並依計畫順序預測合併衝突，收尾時保留未提交的 worktree 與未合併的分支。
- 範本：`templates/plan.example.json`、`templates/PROJECT_CONTEXT.md`、`templates/coordinator-prompt.md`。
- 測試（stdlib `unittest`，24 個）、`tools/dev_check.ps1`、GitHub Actions（Windows＋Ubuntu Python 3.10／3.13）。
- 雙語 README、MIT 授權、`.gitattributes`、`.editorconfig`。

### 修正

- `down --delete-merged`：目前 HEAD 不在 base 時，已合併的分支會被 `git branch -d` 誤拒並中斷收尾；改用已驗證過的 `--is-ancestor` 結果刪除。
- `down`：worktree 資料夾被手動刪掉時不再中斷，交給 `git worktree prune` 清除。
- 分支一律以 `refs/heads/` 指定：同名 tag 會讓「是否已合併」誤判，進而刪掉未合併的分支。
- `down` 先跑 `git worktree prune`，資料夾被手動刪掉時搭配 `--delete-merged` 也能刪分支。
- 被 `git worktree lock` 鎖住、資料夾又不見的 worktree：`down` 給警告並跳過，不再中斷其他任務的收尾。
- 計畫檔不是 UTF-8 時回報錯誤（結束碼 2），不再噴 traceback。

### 變更

- 原本的 Claude Code Projects 架構筆記搬到 `docs/background-notes.md`，開頭標明是閱讀筆記。
