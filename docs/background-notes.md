# 背景筆記：Claude Code Projects 架構整理

> **閱讀筆記，不是本 repo 的主體。** 整理自 Threads 討論串（原貼文者 `@bounce12340`）對 Claude Code Projects 發表內容的拆解，
> 內容原本是轉述；2026-10-25 已對照官方文件
> [Let Claude coordinate ongoing work with Projects](https://code.claude.com/docs/en/claude-projects)
> 與 [worktrees](https://code.claude.com/docs/en/worktrees) 逐項校正，與官方不符處已改；2026-10-25 改寫的段落都已查證。
> Projects 仍在 beta，行為會變，以官方文件為準。本 repo 實際提供的工具見 [README](../README.md)。


> 原始整理自 Threads 討論串（原貼文者：蔡忠栩 `@bounce12340`）對 Anthropic 官方開發者帳號（`@claudedevs`）釋出 **Claude Code Projects**（開放 Pro / Max 用戶）與 4 分鐘教學影片的深度拆解。

---

## 目錄
- [一、核心架構與概念](#一核心架構與概念)
  - [1. 什麼是 Claude Code Projects？](#1-什麼是-claude-code-projects)
  - [2. 架構運作流程](#2-架構運作流程)
- [二、關鍵特性與值得參考的資訊](#二關鍵特性與值得參考的資訊)
  - [1. 核心機制](#1-核心機制)
  - [2. 開發者痛點與風險評估](#2-開發者痛點與風險評估)
- [三、如何仿造落地的實戰手冊](#三如何仿造落地的實戰手冊)
  - [1. Coordinator + Worker 雙層工作流](#1-coordinator--worker-雙層工作流)
  - [2. 使用 Git Worktree 實現本地平行隔離](#2-使用-git-worktree-實現本地平行隔離)
  - [3. 建立專案共享記憶檔 (Single Source of Truth)](#3-建立專案共享記憶檔-single-source-of-truth)
  - [4. Token 防護與非同步檢驗防線](#4-token-防護與非同步檢驗防線)

---

## 一、核心架構與概念

### 1. 什麼是 Claude Code Projects？
過去的 AI Coding Agent（如單機 CLI 或一般 Chat）多半是**「單人、同步阻塞式」**的：由開發者在終端機輸入提示詞，看著 Agent 逐步讀檔、改檔、執行測試。

**Claude Code Projects** 將其升級為**「對話式幕僚長（Coordinator）+ 平行工班（Threads）」**的 AI 研發團隊模式。你只需要提供高階業務目標，AI 會自動拆解任務並平行派發。

官方現況：公開 beta，只開放 Pro / Max，逐步推出（Team / Enterprise 尚未提供）；入口在 Claude Code 網頁版與桌面版 Code 分頁的側邊欄（或 **More**），手機 App 也能用。單一小任務、每個任務都得用你本機環境的工作，官方建議改用一般雲端 session 或本機 session（見官方「When something else fits better」）。

### 2. 架構運作流程

```
                    ┌──────────────────────────────┐
                    │      使用者 / 開發者          │
                    │ (下達高階需求、最後 PR 審核)    │
                    └──────────────┬───────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │     Coordinator (協調者)     │
                    │  拆解任務、分配工作、監控進度    │
                    └──────┬───────────────┬───────┘
                           │ 派工          │ 派工
              ┌────────────┴───┐       ┌───┴────────────┐
              ▼                ▼       ▼                ▼
       ┌─────────────┐  ┌─────────────┐ ┌─────────────┐
       │ Thread A    │  │ Thread B    │ │ Thread C    │ ... (平行雲端 session)
       │ (獨立 Branch)│  │ (獨立 Branch)│ │ (獨立 Branch)│
       │ 自動跑測試   │  │ 處理 API   │ │ 重構前端    │
       └──────┬──────┘  └──────┬──────┘ └──────┬──────┘
              └────────────┬───┴───────────────┘
                           ▼
                    ┌──────────────────────────────┐
                    │ 統一匯總：開立 PR、跑 CI 修復 │
                    │ 共享：MEMORY.md / 專案上下文  │
                    └──────────────────────────────┘
```

---

## 二、關鍵特性與值得參考的資訊

### 1. 核心機制
1. **Coordinator（協調者模式）**：
   - 負責將複雜的 Epic 或大規模重構拆分為彼此解耦的子任務（Sub-tasks）。
   - 調度各個 Thread，追蹤每個 Thread 的狀態。官方：協調者只看得到 Thread 回報的結果，看不到每一步；每個 Thread 有自己的 context window，這也是避免單一 Session context 過長的原因。
2. **Parallel Cloud Threads（平行雲端執行緒）**：
   - 每個 Thread 通常是一個雲端 session（Claude Code 跑在雲端），擁有自己的 Git 分支與 Repo 副本。
   - 需要本機才有的東西（本機資料庫、內網）時，可以請 Claude 把該 Thread 改跑在自己的電腦上（透過 Remote Control）；這種 Thread 只在電腦醒著時跑。
   - **離線背景執行**：雲端 Thread 在你關掉筆電後仍繼續；可從手機查看與介入。
   - **自動化迴圈**：工作需要時 Thread 會開 Pull Request (PR)，開完後以 auto-fix 監看：CI 失敗會推修正、處理 review 意見、檢查通過後在 Thread 回報。
3. **Shared Memory & Library（共享專案記憶庫）**：
   - 官方的共享脈絡有兩層：**專案指令**（每個新 Thread 開工都會帶著）與**專案記憶**（Claude 記下的需求、決策、踩過的坑；Thread 開工讀索引檔 `MEMORY.md`，需要時再開其他檔）。兩者存在 Project settings，不是 repo 裡的檔案。
   - repo 裡雲端 Thread 只讀每個 repo 根目錄的 `CLAUDE.md`、`.claude/CLAUDE.md`、`.claude/rules/`；子目錄的 `CLAUDE.md` 與路徑限定規則不讀。**不會載入** repo 的 skills、agents、commands、`.mcp.json`、`.claude/settings.json`（權限、hooks、env 都不生效）。對應做法：skills 在 claude.ai 帳號啟用；plugins 加到 Project settings > Plugins；MCP 用帳號的 connector；環境變數與工具放雲端環境；agents、commands、hooks 只能讓 Thread 改跑本機。
   - `AGENTS.md`：Projects 頁的載入清單只列 `CLAUDE.md`；官方 memory 頁說 Claude Code v2.1.277 以上在沒有 `CLAUDE.md` 時會直接讀 `AGENTS.md`。雲端 Thread 是否適用，兩頁都沒明講、也沒實測。要確定就開一個 Thread 實測，或在 `CLAUDE.md` 用 `@AGENTS.md` 匯入。

### 2. 開發者痛點與風險評估
- **Token 燃燒速度極快**：多個 Thread 同時開工代表訂閱配額會以數倍速度消耗（官方：與一般 Claude Code session 共用額度，消耗更快）。可以直接對協調者說「同時最多跑兩個 Thread」「同領域的後續交給既有 Thread」。
- **分支衝突（Merge Conflicts）**：若 Coordinator 任務拆解邊界不清，多個 Thread 修改重疊檔案，最後在主幹合併時將面臨大量衝突。
- **人類把關不可省略（Human-in-the-Loop）**：AI 負責開工與測試，但最終的 Plan Review 與 PR Merge 仍需人類工程師親自裁決。

---

## 三、如何仿造落地的實戰手冊

在我們自己的開發環境（無論是本機 Terminal、Antigravity、Cursor 或 Claude Code CLI），皆可立即落地仿造以下實踐：

### 1. Coordinator + Worker 雙層工作流
**原則**：切勿直接丟給單一 Agent 大段模糊要求，請強制拆分為三階段：
1. **規劃階段（Coordinator）**：
   - Prompt：「先調研當前專案結構，輸出拆解計畫、相依性圖與各自預計修改的檔案清單，先不要動手改寫程式碼。」
2. **實作階段（Workers）**：
   - 依據無依賴或低依賴模組，分別派發獨立工作。
3. **驗證階段（Review & Verify）**：
   - 統一整合回測，跑 Focused Unit Tests 與 Integration Tests。

### 2. 使用 Git Worktree 實現本地平行隔離
這一節是**不用 Projects、在本機自己做**的版本。Claude Code 本身也有對應功能：`claude --worktree <名稱>` 開一個在獨立 worktree 的 session，自訂 subagent 可在 frontmatter 寫 `isolation: worktree`（見官方 worktrees 頁）。這些管的是「建立隔離」；隔離之間的任務範圍會不會重疊，由本 repo 的 `worktree_tasks.py` 檢查。手動做法：

若想在本地同時跑多個 AI 修改不同功能，可透過 `git worktree` 取代直接在同一個目錄切換分支：

```powershell
# 為不同的子任務建立獨立工作目錄與分支
git worktree add ../task-backend-api -b feature/backend-api
git worktree add ../task-frontend-ui -b feature/frontend-ui

# 在各目錄分別啟動 AI Agent 進行修改與測試
cd ../task-backend-api
# 任務完成後提交並發 PR
git push origin feature/backend-api
```

### 3. 建立專案共享記憶檔 (Single Source of Truth)
在專案根目錄維護一個精簡的 `PROJECT_CONTEXT.md`，並在 `CLAUDE.md`（或 `AGENTS.md`，視你的 agent 讀哪個）指向它：
- **核心架構**：技術棧版本、目錄結構定義。
- **硬邊界規則**：禁止修改專案外路徑、敏感 Key 不得入 Code、禁止用假資料或吞例外過測。
- **標準指令**：專案專屬的 quick test、lint、build 指令。

### 4. Token 防護與非同步檢驗防線
- **限制單一 Worker 的 Blast Radius**：每次只授權修改 1~3 個特定檔案。
- **快速回饋閉環**：強制 Worker 優先執行 Focused Test，通過後才跑整體驗證，避免長時間無效重試燃燒額度。
