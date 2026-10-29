# 路線圖

> 本 repo 後續工作的單一真相源。做完一項，就在同一個 commit 刪掉那一列；新工作只加在這裡。
> 現況段的數字是 2026-10-29 依 `main` `d61bf8d0d36d` 查的快照，開工前先重查 GitHub。

## 現況

public、非 fork 的單檔工具 `worktree_tasks.py`（只用 Python 標準函式庫與 git）：平行 AI 任務的 git worktree 派工前範圍檢查與合併前衝突預測，另附範本與 `docs/background-notes.md` 閱讀筆記。健康：2026-10-29 查到 open issue 0、open PR 0、Dependabot 與 Code scanning 告警各 0，`CI`、`CodeQL` 在 `main` 最近一次皆 success；沒有 release（2026-10-29 `gh` 查詢）。2026-10-26 的深度掃描修復已全部在 `main`，本 repo 沒有等不到條件就卡住的項目，近期剩下 `check_links.py` 大小寫檢查，其餘為等外部條件的工作。

## 近期：可以直接動手
| 項目 | 為什麼 | 驗收方式 | 建議執行者 | 證據 |
| --- | --- | --- | --- | --- |
| `tools/check_links.py` 抓出大小寫錯誤的連結 | Windows 大小寫不分，`readme.md` 這類連結本機通過、GitHub 上 404 | `tests/` 新增測試：大小寫不符的連結回報失敗，正確大小寫仍通過；`python -m unittest discover -s tests -v` 與 `python tools/check_links.py` 綠 | Claude Sonnet | `tools/check_links.py:78`（以 `exists()` 判斷）；深掃報告（2026-10-26）「刻意不修」 |

## 中期：等條件成立再做
| 項目 | 觸發條件 | 驗收方式 | 建議執行者 | 證據 |
| --- | --- | --- | --- | --- |
| 實測雲端 Projects Thread 是否讀取 `AGENTS.md` 並更新 `docs/background-notes.md` | 維護者想確定這點（需要開一個 Projects Thread，不在本 repo 自動化範圍） | 維護者在 Thread 內放含暗號的 `AGENTS.md` 驗證，結果與日期寫進 `docs/background-notes.md`，取代 `docs/background-notes.md:83`「沒明講、也沒實測」的措辭 | 維護者 | 接續開發報告「刻意不做」；`docs/background-notes.md:83` |
| 重新對照官方 Projects／worktrees／memory 文件校正 `docs/background-notes.md` | 官方文件發布 Projects 相關變更（beta 轉正式、方案限制改變），或維護者要引用其中結論對外 | 每個與官方有關的陳述附官方頁面連結與查證日期；`python tools/check_links.py` 綠；README 中英「邊界」段同步 | Claude Sonnet | `0c7866e`（上次校正）；接續開發報告「做了什麼」 |
| 為 `main` 設分支保護 | 維護者放棄「個人開發、直推 main」慣例（例如開始有外部協作者） | `gh api repos/SanHsien/claude-code-projects-workflow/branches/main/protection` 回傳規則而非 404；CI 為必要檢查；`AGENTS.md`「交付」段改為 PR 流程 | 維護者 | 接續開發報告「需要維護者決定」；`AGENTS.md`「交付」 |

## 刻意不做
| 不做什麼 | 理由 | 什麼情況下重新考慮 |
| --- | --- | --- |
| 新增第三方依賴（YAML 解析、彩色輸出等） | `AGENTS.md` 規定零依賴；已用 `fleet-waiver: freshness` 登記 | 維護者明確同意某個依賴 |
| 放寬 `check` 與 `down` 的唯讀／只刪已合併保證 | 兩條有測試鎖住，是工具對使用者 ref 的安全承諾 | 不重新考慮 |
| 為含 tab、雙引號、反斜線的路徑消除 git 加引號的訊息外觀 | 只影響訊息外觀且極少見 | 實際有使用者回報誤判 |
| 為 `worktree list --porcelain` 改用 `-z` | 只在路徑含換行時有問題 | 出現含換行路徑的真實案例 |

## 維護方式

自有 repo，在 `main` 直推，無 release 節奏；改行為時同步 `README.md`、`README.en.md` 與 `CHANGELOG.md`、`CHANGELOG.en.md`，並跑 `python -m unittest discover -s tests -v` 與 `python tools/check_links.py`（CI 相同，另在 Windows 跑 `tools/dev_check.ps1`）。GitHub Actions 版本由 Dependabot 追蹤。
