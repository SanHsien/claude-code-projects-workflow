# AGENTS.md

給所有 AI agent 的維護規則（單一真相源）。

## 這個 repo 是什麼

`worktree_tasks.py`：平行任務的 git worktree 派工前檢查、建立、合併前檢查與收尾。單檔、只用 Python 標準函式庫與 git。
`templates/` 是給使用者複製的範本；`docs/background-notes.md` 是閱讀筆記，不是規格。

## 規則

- **零依賴**：不新增任何第三方套件。需要 YAML、彩色輸出之類的功能，先問維護者。
- **不動使用者的 ref**：`check` 只能用 `git merge-tree`／`commit-tree` 做模擬；`down` 只能刪已合併的分支、只能移除乾淨的 worktree。這兩條有測試鎖住，不要為了方便放寬。
- 結束碼語意固定：`0` 通過、`1` 檢查發現問題、`2` 用法或環境錯誤。
- 改行為要同步：`README.md`、`README.en.md` 的「各檢查的判斷方式」表格，以及 `CHANGELOG.md`／`CHANGELOG.en.md`。
- 測試用 stdlib `unittest`，每個測試自己建暫存 repo。新增檢查條件時做突變驗證：故意弄壞條件，確認有測試會紅。

## 回覆

- 回覆用繁體中文，先結論後細節。
- 宣稱完成前附上驗證指令的實際輸出。

## 驗證

```bash
python -m unittest discover -s tests -v
python tools/check_links.py
```

Windows：`pwsh -File tools/dev_check.ps1`。驗證通過才提交（用 `&&` 串接，不要用 `;`）。

## 交付

直接提交並推到 `main`，不開分支、不開 PR。
