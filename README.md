# PGY90 Health Coach / teofamilyhealth

這是一個給家人使用的健康管理 Web App。目前真實技術棧是：

- Python
- Streamlit
- SQLite
- OpenAI API

目前版本是先穩定 SQLite 版，資料庫檔案位於 `data/health.db`。這個 repo 目前不是 Supabase 版本，也不要假設已經有 Supabase 連線或 Supabase table。中期可以規劃 Supabase migration，但應該等 SQLite 版整理穩定、測試流程明確後再做。

## 目前功能

- 註冊 / 登入 / 邀請碼 / 管理員模式
- 記住我 30 天
- AI 文字飲食輸入
- AI 照片飲食輸入，支援上傳照片與需要時啟用相機
- 餐食保存、修改、重新估算、刪除
- 每日營養總覽
- 每日健康記錄
- 體重、體脂、腰圍、BMI、睡眠趨勢圖
- 每週報告
- 管理員後台

## 專案結構

```text
app.py              Streamlit 主程式，目前包含登入、資料庫、AI、UI 與管理後台
requirements.txt    Python 套件需求
README.md           專案說明
DEV_CHECKLIST.md    每次修改後的手動檢查清單
REFACTOR_PLAN.md    未來重構路線圖
data/health.db      SQLite 真實資料庫，不應提交到 Git
```

## 安裝與啟動

請先確認已安裝 Python 3.10 以上。

```bash
python3 --version
```

建立並啟用虛擬環境：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

安裝套件：

```bash
pip install -r requirements.txt
```

啟動 App：

```bash
streamlit run app.py
```

啟動後通常會開啟：

```text
http://localhost:8501
```

## 資料庫

第一次啟動時，App 會自動建立：

```text
data/health.db
```

這是目前正式使用的 SQLite 資料庫。請不要提交、刪除或移動真實資料庫檔案。若需要備份，請在 App 關閉後複製 `data/health.db` 到安全位置。

目前多人資料隔離主要依靠 `person_name`，不是穩定的 `user_id`。短期先維持現況以避免破壞既有資料；中期若要做 Supabase migration，建議改成以穩定 `user_id` 作為主要資料關聯。

## Secrets / Environment Variables

部署到 Streamlit Cloud 時，請到 App 的 Settings > Secrets 設定需要的值。

基本範例：

```toml
INVITE_CODE = "換成你的家庭邀請碼"
OPENAI_API_KEY = "換成你的 OpenAI API key"
REMEMBER_LOGIN_SECRET = "換成一串長一點的隨機文字"

[admins]
Teo = "換成你的管理員密碼"
```

可選設定：

```toml
OPENAI_MODEL = "gpt-5.5"

[users]
爸爸 = "爸爸的密碼"
媽媽 = "媽媽的密碼"
```

本機測試也可以暫時使用：

```bash
APP_PASSWORD="換成你的密碼" streamlit run app.py
```

設定說明：

- `INVITE_CODE`：家人註冊用邀請碼。
- `[admins]`：管理員帳號與密碼。
- `[users]`：可選，固定使用者帳號與密碼。
- `APP_PASSWORD`：可選，本機或簡易測試用共用密碼。
- `OPENAI_API_KEY`：AI 文字飲食與照片飲食估算使用。
- `OPENAI_MODEL`：可選，指定 OpenAI 模型；未設定時使用程式預設值。
- `REMEMBER_LOGIN_SECRET`：記住我 30 天的登入 token 簽章密鑰，正式部署建議一定設定。

如果沒有設定 `INVITE_CODE`、`[admins]`、`[users]` 或 `APP_PASSWORD`，App 會顯示設定提醒，不會進入健康資料頁面。

## Streamlit Cloud 部署

Streamlit Cloud 新增 App 時可設定：

```text
Repository: typerhu/pgy90-family
Branch: main
Main file path: app.py
```

部署後請確認 Secrets 已設定，尤其是 `INVITE_CODE`、`[admins]`、`OPENAI_API_KEY` 與 `REMEMBER_LOGIN_SECRET`。

## 使用建議

- 每位家人使用自己的帳號登入。
- 每日健康記錄可只填有記錄到的資料，不必每天完整填滿。
- 每餐飲食建議統一到「AI 飲食教練」記錄。
- AI 估算是健康追蹤用的近似值，必要時可以手動修正餐食營養。
- 管理員帳號可查看使用者、重設密碼或刪除使用者資料。
- 每次修改程式後，請依照 `DEV_CHECKLIST.md` 做基本手動檢查。

## 未來方向

短期目標是穩定目前 SQLite 版本，讓登入、AI 飲食、照片輸入、餐食保存與每日總覽維持可靠。中期再規劃 Supabase migration，並在遷移前先建立清楚的資料備份、測試與 `user_id` 資料模型。
