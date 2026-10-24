# 背景筆記：Claude Code Projects 架構整理

> **閱讀筆記，不是本 repo 的主體。** 整理自 Threads 討論串（原貼文者 `@bounce12340`）對 Claude Code Projects 發表內容的拆解，
> 內容是轉述，未逐項向官方文件查證。本 repo 實際提供的工具見 [README](../README.md)。


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

**Claude Code Projects** 將其升級為**「對話式幕僚長（Coordinator）+ 雲端平行工班（Parallel Cloud Threads）」**的 AI 研發團隊模式。你只需要提供高階業務目標，AI 會自動拆解任務並平行派發。

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
       │ Thread A    │  │ Thread B    │ │ Thread C    │ ... (平行雲端 VM)
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
   - 調度各個 Thread，監控執行進度，避免單一 Session context 過長導致幻覺。
2. **Parallel Cloud Threads（平行雲端執行緒）**：
   - 每個 Thread 在雲端獨立 VM 中執行，擁有自己的 Git 分支與 Repo 副本。
   - **離線背景執行**：即使筆電蓋上或手機關螢幕，雲端任務依然持續推進。
   - **自動化迴圈**：任務完成後自動提交 Commit、發起 Pull Request (PR)；CI 檢查失敗時會自動獲取 Log 並推進修正。
3. **Shared Memory & Library（共享專案記憶庫）**：
   - 統一由專案層級的記憶檔（如 `MEMORY.md`、`CLAUDE.md`）維護共用架構標準與規則，消除多 Session 間背景知識不一致的問題。

### 2. 開發者痛點與風險評估
- **Token 燃燒速度極快**：多個 Thread 同時開工代表 API / Subscription 配額會以數倍速度消耗。
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
在專案根目錄維護一個精簡的 `PROJECT_CONTEXT.md` 或 `CLAUDE.md`：
- **核心架構**：技術棧版本、目錄結構定義。
- **硬邊界規則**：禁止修改專案外路徑、敏感 Key 不得入 Code、禁止用假資料或吞例外過測。
- **標準指令**：專案專屬的 quick test、lint、build 指令。

### 4. Token 防護與非同步檢驗防線
- **限制單一 Worker 的 Blast Radius**：每次只授權修改 1~3 個特定檔案。
- **快速回饋閉環**：強制 Worker 優先執行 Focused Test，通過後才跑整體驗證，避免長時間無效重試燃燒額度。
