# 家庭健康管理 Web App

這是一個使用 Python、Streamlit、SQLite 製作的家庭健康管理工具。它可以讓家人共用同一個 App，並把每個人的體重、體脂、腰圍、睡眠、飲食、運動、復健與備註分開記錄。

## 功能

- 家人試用：登入後可在側邊欄選擇或新增家人，每個人的資料獨立保存
- 每日輸入：體重、體脂、可選腰圍、睡眠小時與分鐘、睡眠品質百分比、當日飲食總評、Apple Watch 運動摘要、復健、備註
- AI 飲食教練：用一句話記錄餐食，估算熱量、蛋白質、纖維、碳水與脂肪，並依照每日目標給建議
- 餐食修正：已輸入的餐食可以編輯、重新估算或刪除
- 登入密碼：部署到 Streamlit Cloud 後，必須先輸入密碼才能使用
- 飲食偏好記憶：儲存減脂、增肌或維持目標，以及熱量、蛋白質、纖維與飲食偏好
- 趨勢圖表：查看體重、體脂、腰圍、睡眠與運動量變化
- 每週報告：依照指定週期自動產生健康總結與下週建議
- SQLite 本機資料庫：資料儲存在 `data/health.db`

## Mac 安裝方式

請先確認 Mac 已安裝 Python 3.10 以上。

```bash
python3 --version
```

如果 macOS 提示需要安裝 Command Line Tools，可以先執行：

```bash
xcode-select --install
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

啟動後，瀏覽器會開啟本機網址，通常是：

```text
http://localhost:8501
```

## 手機連線

如果要用手機開啟，Mac 必須保持開機、不要睡眠，而且手機和 Mac 要連同一個 Wi-Fi。

使用 `outputs/啟動健康管理App.command` 啟動時，終端機會顯示手機網址，例如：

```text
http://192.168.x.x:8501
```

手機請輸入終端機顯示的網址。不要在手機輸入 `127.0.0.1:8501`，因為那代表手機自己，不是你的 Mac。

## 登入帳號

App 會從 Streamlit Secrets 讀取家人帳號。部署到 Streamlit Cloud 後，到 app 的 Settings > Secrets 加上：

```toml
[users]
爸爸 = "爸爸的密碼"
媽媽 = "媽媽的密碼"
孩子 = "孩子的密碼"
```

每個人登入後只能看到自己的資料。帳號名稱會直接成為該使用者的記錄名稱。

如果只是本機測試，也可以暫時使用共用密碼：

```bash
APP_PASSWORD="換成你的密碼" streamlit run app.py
```

如果沒有設定 `[users]` 或 `APP_PASSWORD`，App 會停止在設定提醒頁，不會顯示健康資料。

## 部署家人版

這個版本建議部署成獨立 Streamlit app。

Streamlit Cloud 新增 app 時設定：

```text
Repository: typerhu/pgy90-family
Branch: main
Main file path: app.py
```

部署後，請設定家人帳號密碼，不要沿用個人版密碼。

## 資料庫

第一次啟動時會自動建立：

```text
data/health.db
```

不需要手動建立資料庫。若未來想重新開始，可以先關閉 App，再刪除 `data/health.db`，下次啟動會重新建立空資料庫。

## 使用建議

- 每天記錄即可，不需要精準計算熱量
- 每個人用自己的帳號登入，不需要再手動選擇使用者
- 腰圍不需要每天量，有測量時再勾選並填寫即可
- 每餐飲食統一到「AI 飲食教練」記錄；「每日輸入」只保留當日飲食總評
- 運動可以照 Apple Watch 填入運動分鐘、平均心率、最高心率、活動熱量與距離
- RPE 是主觀強度，0 代表休息，10 代表極限強度
- 每週到「每週報告」頁面按下產生總結，保存當週摘要
- 中期目標設定為 75kg、體脂 13-15%
- 到「AI 飲食教練」頁面可以輸入例如「午餐吃海南雞飯加一顆蛋，喝無糖拿鐵」
- 如果不小心重複輸入餐食，到「今日餐食」展開該筆紀錄，勾選確認後即可刪除；也可以直接修改內容或重新估算
- 目前餐食營養是本機規則估算，適合日常追蹤方向；若要像 Welling 一樣看照片估算，可再接上圖片 AI
