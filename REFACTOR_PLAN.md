# 未來重構地圖

目前不要一次大拆。PGY90 Health Coach 已經有登入、AI 文字飲食、AI 照片飲食、餐食保存、每日總覽、健康記錄、趨勢圖與管理員後台；重構時要保護這些既有功能。

## 原則

- 每拆一個模組，都要跑 `DEV_CHECKLIST.md`。
- 不要在拆模組時同時改 UI。
- 不要在拆模組時同時改 database schema。
- 不要在拆模組時同時遷移 Supabase。
- Supabase migration 是中期任務，必須等 SQLite 版整理穩定後再做。
- 目前資料隔離主要靠 `person_name`，未來遷移時再規劃穩定 `user_id`。

## 建議拆分方向

- `auth.py`：登入、註冊、密碼雜湊、管理員、記住我 cookie。
- `db.py`：SQLite 連線、初始化、schema migration。
- `ai.py`：OpenAI API 呼叫、文字與照片估算、JSON 解析。
- `meals.py`：餐食保存、讀取、修改、刪除、每日營養合計。
- `profiles.py`：個人目標、身高、體重、體脂目標、飲食偏好。
- `health_logs.py`：每日健康記錄、體重、體脂、腰圍、睡眠、運動。
- `reports.py`：每週報告產生、讀取與保存。
- `ui_helpers.py`：樣式、格式化、數字顯示、共用 UI helper。
- `pages/`：各頁 Streamlit 畫面，例如 AI 飲食教練、每日輸入、趨勢圖表、每週報告、管理員後台。

## 分階段路線

### 第 0 階段：理解與文件

只整理 README、檢查清單、重構地圖與現況註解，不改功能。

### 第 1 階段：低風險整理

補齊文件、保護 SQLite 真實資料、在 `app.py` 加清楚區塊標題。不要改函數名稱、不要改流程、不要拆檔。

### 第 2 階段：中風險模組拆分

一次只拆一個責任區，例如先拆 `ai.py`，確認行為不變後再拆下一個。每次拆完都跑 `DEV_CHECKLIST.md`。

### 第 3 階段：UI 資訊架構整理

等程式責任比較清楚後，再整理頁面層級。不要和資料庫 schema 或 Supabase migration 同時做。

### 第 4 階段：Supabase migration 規劃

SQLite 版穩定後，再設計 Supabase table、`user_id`、資料備份、資料遷移腳本與 rollback 方案。這是獨立專案，不應混在一般 UI 或模組拆分裡。
