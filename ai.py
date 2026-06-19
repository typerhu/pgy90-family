from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st


APP_TIMEZONE = ZoneInfo("Asia/Kuching")
OPENAI_TRANSIENT_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504, 520, 522, 524}

FOOD_ESTIMATES = {
    "雞胸": (165, 31, 0, 0, 3.6),
    "雞腿": (220, 24, 0, 0, 12),
    "牛肉": (250, 26, 0, 0, 15),
    "豬肉": (260, 24, 0, 0, 17),
    "魚": (150, 24, 0, 0, 5),
    "蛋": (78, 6, 0, 0.6, 5),
    "豆腐": (80, 8, 1, 2, 4),
    "飯": (130, 2.7, 0.4, 28, 0.3),
    "麵": (140, 5, 2, 25, 2),
    "麵包": (265, 9, 3, 49, 3.2),
    "燕麥": (389, 17, 10, 66, 7),
    "地瓜": (86, 1.6, 3, 20, 0.1),
    "蔬菜": (35, 2, 3, 6, 0.2),
    "沙拉": (45, 2, 3, 8, 1),
    "香蕉": (105, 1.3, 3, 27, 0.4),
    "蘋果": (95, 0.5, 4, 25, 0.3),
    "小番茄": (3, 0.1, 0.1, 0.7, 0),
    "小蕃茄": (3, 0.1, 0.1, 0.7, 0),
    "番茄": (22, 1, 1.5, 4.8, 0.2),
    "蕃茄": (22, 1, 1.5, 4.8, 0.2),
    "藍莓": (1, 0, 0.1, 0.2, 0),
    "牛奶": (60, 3.2, 0, 5, 3.3),
    "優格": (95, 9, 0, 6, 4),
    "拿鐵": (180, 9, 0, 18, 7),
    "咖啡": (5, 0, 0, 0, 0),
    "奶茶": (300, 4, 0, 45, 10),
    "海南雞飯": (780, 35, 3, 88, 28),
    "便當": (750, 35, 5, 90, 25),
    "火鍋": (650, 45, 8, 45, 25),
    "壽司": (520, 24, 3, 85, 8),
    "漢堡": (620, 28, 4, 55, 30),
    "炸雞": (700, 35, 2, 35, 45),
}

MEAL_KEYWORDS = {
    "早餐": ["早餐", "早上"],
    "午餐": ["午餐", "中午", "午飯"],
    "晚餐": ["晚餐", "晚上", "晚飯"],
    "點心": ["點心", "宵夜", "飲料", "下午茶"],
}

MEAL_TYPES = ["早餐", "午餐", "晚餐", "點心"]


def get_openai_api_key() -> str:
    try:
        api_key = st.secrets.get("OPENAI_API_KEY", "")
    except Exception:
        api_key = ""
    if api_key:
        return str(api_key)
    return os.environ.get("OPENAI_API_KEY", "")


def get_openai_model() -> str:
    try:
        model = st.secrets.get("OPENAI_MODEL", "")
    except Exception:
        model = ""
    if model:
        return str(model)
    return os.environ.get("OPENAI_MODEL", "gpt-5.5")


def meal_type_by_local_time(now: datetime | None = None) -> str:
    local_now = now or datetime.now(APP_TIMEZONE)
    if local_now.tzinfo is None:
        local_now = local_now.replace(tzinfo=APP_TIMEZONE)
    else:
        local_now = local_now.astimezone(APP_TIMEZONE)
    hour = local_now.hour
    if hour < 10:
        return "早餐"
    if hour < 15:
        return "午餐"
    if hour < 21:
        return "晚餐"
    return "點心"


def detect_meal_type(text: str) -> str:
    for meal_type, keywords in MEAL_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return meal_type
    return meal_type_by_local_time()


def quantity_multiplier(text: str) -> float:
    multipliers = {
        "半": 0.5,
        "一": 1,
        "1": 1,
        "兩": 2,
        "二": 2,
        "2": 2,
        "三": 3,
        "3": 3,
    }
    total = 0.0
    for token, value in multipliers.items():
        if re.search(rf"{token}\s*(份|碗|盤|個|顆|杯|片)", text):
            total += value
    return total if total else 1.0


def item_multiplier(text: str, keyword: str) -> float:
    number_tokens = {"半": 0.5, "一": 1, "1": 1, "兩": 2, "二": 2, "2": 2, "三": 3, "3": 3}
    pattern = rf"(\d+(?:\.\d+)?|{'|'.join(number_tokens.keys())})\s*(份|碗|盤|個|顆|杯|片)?\s*{re.escape(keyword)}"
    match = re.search(pattern, text)
    if match:
        token = match.group(1)
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            return float(token)
        return number_tokens[token]
    if keyword in {"飯", "麵", "麵包", "燕麥", "地瓜"}:
        return quantity_multiplier(text)
    return 1.0


def estimate_nutrition(description: str) -> dict:
    text = description.strip()
    remaining_text = text
    matched = []
    totals = {"calories": 0, "protein_g": 0.0, "fiber_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}

    for keyword, values in sorted(FOOD_ESTIMATES.items(), key=lambda item: len(item[0]), reverse=True):
        if keyword in remaining_text:
            matched.append(keyword)
            calories, protein, fiber, carbs, fat = values
            multiplier = item_multiplier(text, keyword)
            totals["calories"] += calories * multiplier
            totals["protein_g"] += protein * multiplier
            totals["fiber_g"] += fiber * multiplier
            totals["carbs_g"] += carbs * multiplier
            totals["fat_g"] += fat * multiplier
            remaining_text = remaining_text.replace(keyword, "", 1)

    if not matched:
        totals = {"calories": 550, "protein_g": 25.0, "fiber_g": 4.0, "carbs_g": 65.0, "fat_g": 18.0}
        confidence = "低"
    elif len(matched) == 1:
        confidence = "中"
    else:
        confidence = "中高"

    return {
        "calories": int(round(totals["calories"])),
        "protein_g": round(totals["protein_g"], 1),
        "fiber_g": round(totals["fiber_g"], 1),
        "carbs_g": round(totals["carbs_g"], 1),
        "fat_g": round(totals["fat_g"], 1),
        "confidence": confidence,
        "matched": "、".join(matched) if matched else "未辨識食物，以一般外食估算",
    }


def extract_response_text(response: dict) -> str:
    if response.get("output_text"):
        return str(response["output_text"])

    parts = []
    for output_item in response.get("output", []):
        for content_item in output_item.get("content", []):
            text = content_item.get("text")
            if text:
                parts.append(str(text))
    return "\n".join(parts).strip()


def parse_meal_ai_result(raw_text: str, fallback_description: str) -> dict:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    data = json.loads(cleaned)
    result = {
        "description": str(data.get("description") or fallback_description),
        "meal_type": str(data.get("meal_type") or "點心"),
        "calories": int(round(float(data.get("calories") or 0))),
        "protein_g": round(float(data.get("protein_g") or 0), 1),
        "fiber_g": round(float(data.get("fiber_g") or 0), 1),
        "carbs_g": round(float(data.get("carbs_g") or 0), 1),
        "fat_g": round(float(data.get("fat_g") or 0), 1),
        "confidence": str(data.get("confidence") or "低"),
        "matched": str(data.get("matched") or data.get("description") or "照片辨識"),
    }
    for optional_key in ("coach_note", "next_meal_suggestion", "warning_note"):
        if data.get(optional_key):
            result[optional_key] = str(data[optional_key])
    return result


def format_meal_context(coach_context: dict | None) -> str:
    if not coach_context:
        return ""
    labels = [
        ("person_name", "使用者"),
        ("gender", "性別"),
        ("birth_year", "出生年份"),
        ("activity_level", "活動量"),
        ("goal", "目前目標"),
        ("height_cm", "身高 cm"),
        ("current_weight_kg", "目前體重 kg"),
        ("target_weight_kg", "目標體重 kg"),
        ("target_body_fat_range", "目標體脂範圍"),
        ("daily_calorie_target", "每日熱量目標 kcal"),
        ("protein_target_g", "每日蛋白質目標 g"),
        ("fiber_target_g", "每日纖維目標 g"),
        ("today_calories", "今日已攝取熱量 kcal"),
        ("today_protein_g", "今日已攝取蛋白質 g"),
        ("today_fiber_g", "今日已攝取纖維 g"),
        ("today_carbs_g", "今日已攝取碳水 g"),
        ("today_fat_g", "今日已攝取脂肪 g"),
        ("remaining_calories", "今日剩餘熱量 kcal"),
        ("remaining_protein_g", "今日剩餘蛋白質 g"),
        ("remaining_fiber_g", "今日剩餘纖維 g"),
        ("total_meals_count", "今日已記錄餐食總數"),
        ("breakfast_count", "今日早餐數量"),
        ("lunch_count", "今日午餐數量"),
        ("dinner_count", "今日晚餐數量"),
        ("snack_count", "今日點心數量"),
        ("has_breakfast", "今日是否已有早餐"),
        ("has_lunch", "今日是否已有午餐"),
        ("has_dinner", "今日是否已有晚餐"),
        ("has_three_meals", "今日是否三餐完整"),
        ("has_multiple_snacks", "今日是否已有多次點心"),
        ("is_calorie_near_target", "今日熱量是否接近目標"),
        ("is_calorie_over_target", "今日熱量是否超過目標"),
        ("is_fat_high", "今日脂肪是否偏高"),
        ("is_wind_down_mode", "今日是否進入收尾模式"),
        ("wind_down_reasons", "收尾模式原因"),
        ("preferences", "飲食偏好 / 禁忌 / 身體狀況"),
    ]
    lines = []
    for key, label in labels:
        value = coach_context.get(key)
        if value is not None and value != "":
            if isinstance(value, bool):
                value = "是" if value else "否"
            lines.append(f"- {label}: {value}")
    if not lines:
        return ""
    return "\n\n目前使用者與今日營養 context：\n" + "\n".join(lines)


def request_openai_json(prompt: str, image_url: str | None = None) -> dict:
    content = [{"type": "input_text", "text": prompt}]
    if image_url:
        content.append({"type": "input_image", "image_url": image_url, "detail": "low"})
    request_body = {
        "model": get_openai_model(),
        "input": [{"role": "user", "content": content}],
    }
    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {get_openai_api_key()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def request_openai_text(prompt: str, image_url: str | None = None) -> str:
    response_data = request_openai_json(prompt, image_url)
    result = extract_response_text(response_data)
    if not result:
        raise RuntimeError("AI 沒有回傳可讀取的分析內容。")
    return result


def format_openai_http_error(error: urllib.error.HTTPError, action: str) -> str:
    details = error.read().decode("utf-8", errors="replace").strip()
    if error.code in OPENAI_TRANSIENT_STATUS_CODES:
        return (
            f"{action}暫時失敗（HTTP {error.code}）。"
            "這通常是 AI 服務暫時忙碌、圖片太大或連線中斷；請稍後重試，"
            "或先改用文字描述選項。"
        )
    if details:
        return f"{action}失敗：{details}"
    return f"{action}失敗（HTTP {error.code}）。"


def build_pre_meal_prompt(description: str, coach_context: dict | None, source_label: str) -> str:
    prompt = f"""
你是家庭健康管理 App 的餐前決策助手。使用者還沒吃這一餐，請根據{source_label}、今日營養進度、個人目標、活動量、飲食偏好與健康限制，建議這一餐怎麼選比較合理。

請用繁體中文清楚輸出，不要回傳 JSON。輸出必須先給 5 秒內可讀完的短結論，再給詳細分析。

請嚴格使用以下格式與順序：

### 快速結論
1. 最推薦：用很短的一句話寫最適合的選擇
2. 控制份量：用很短的一句話寫需要控制的項目
3. 少吃 / 避開：用很短的一句話寫今天較不建議的項目

### 一句話理由
不超過 40 字，直接說明最重要原因。

### 建議吃法
* 主食：建議份量或替代選擇
* 蛋白質：優先選擇
* 蔬菜 / 纖維：補足方式
* 湯 / 飲料：建議選擇
* 醬料 / 油脂：控制方式

### 如果想吃高熱量食物
給一個可執行折衷方案，不要說絕對不能吃。

### 後面一餐是否需要修正
說明後面一餐要不要清淡、補蛋白質或補纖維。

### 詳細分析
補充原因，但不要寫成冗長報告。

### 信心等級
高 / 中 / 低

信心等級只能是：高 / 中 / 低。
如果文字或圖片資訊不足，請提出最少量追問，或降低信心等級。
如果不確定份量，請說明是估算，不要假裝精準。
不要把食物分成絕對好壞；不要羞辱、恐嚇或製造焦慮；不要鼓勵極端節食或過度克制；不要做醫療診斷。
建議要可執行，並尊重使用者的飲食偏好、禁忌與身體狀況。
快速結論每一點都要短，適合排隊點餐時快速閱讀；不要一開始就輸出長篇分析。
如果今日熱量剩餘不多，請在快速結論直接提醒控制主食、油脂或含糖飲料。
如果蛋白質不足，優先推薦雞肉、魚、蛋、豆腐、瘦肉或希臘優格等選項。
如果纖維不足，提醒補蔬菜、水果、豆類或菇類。
如果今日脂肪偏高，提醒避開炸物、肥肉、奶茶、重醬或濃湯，並給可執行替代方案。

請務必同時判斷今日餐次狀態：
- 如果今日尚未吃正餐，可以正常建議如何選餐。
- 如果今日已經三餐完整但點心不多，請提醒這已經不是主要補正餐，而是判斷是否真的需要加餐；若真的餓，選小份高蛋白、低油、低糖食物；若只是嘴饞，建議不吃或改喝水 / 無糖茶。
- 如果今日已經三餐完整且點心 >= 2，快速結論要明確進入「收尾模式」：今天已經三餐加多次點心，現在不是再安排一餐，而是收尾。
- 收尾模式時，如果不是明顯飢餓，建議停止進食，改喝水、無糖茶，或提早休息；如果真的餓，只選小份高蛋白低油食物，不再加主食、炸物、甜飲、奶茶或重醬。
- 如果今日熱量還沒超標但脂肪已偏高，不要說「熱量偏高」；請說「今天熱量仍有空間，但脂肪已偏高」，並提醒避開炸物、肥肉、奶茶、濃湯、重醬。
- 只有今日熱量接近目標時，才說「今天熱量空間不多」並建議控制份量。
- 只有今日熱量已超過目標時，才說「今天熱量已超過目標」並建議進入收尾模式。
- 如果蛋白質不足但今日已經三餐完整、熱量接近/超過目標或脂肪偏高，不要建議再吃完整正餐；請建議小份高蛋白低脂選項，例如水煮蛋白、無糖高蛋白飲、清湯豆腐、少油魚肉或少量雞胸肉。
- 如果纖維不足但今日已經三餐完整，可以建議小份水果、水煮青菜、菇類或清燙蔬菜，但不要鼓勵再吃一大餐。
- 可以直接說「今天已經三餐加多次點心，建議進入收尾模式」，但不要羞辱、責備或製造焦慮。

使用者餐前輸入：
{description}
"""
    prompt += format_meal_context(coach_context)
    return prompt


def analyze_pre_meal_text(description: str, coach_context: dict | None = None) -> str:
    if not get_openai_api_key():
        raise RuntimeError("尚未設定 OPENAI_API_KEY，無法使用餐前 AI 分析。")
    prompt = build_pre_meal_prompt(description, coach_context, "使用者輸入的餐前文字")
    try:
        return request_openai_text(prompt)
    except json.JSONDecodeError as error:
        raise RuntimeError("餐前文字分析回傳格式無法讀取，請稍後再試。") from error
    except urllib.error.HTTPError as error:
        raise RuntimeError(format_openai_http_error(error, "餐前文字分析")) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"餐前文字分析連線失敗：{error.reason}") from error


def analyze_pre_meal_photo(
    image_bytes: bytes,
    mime_type: str,
    coach_context: dict | None = None,
    description: str = "請根據照片中的菜單、餐檯或食物選項提供餐前建議。",
) -> str:
    if not get_openai_api_key():
        raise RuntimeError("尚未設定 OPENAI_API_KEY，無法使用餐前圖片分析。")
    image_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"
    prompt = build_pre_meal_prompt(description, coach_context, "圖片中的餐前選項")
    try:
        return request_openai_text(prompt, image_url)
    except json.JSONDecodeError as error:
        raise RuntimeError("餐前圖片分析回傳格式無法讀取，請稍後再試。") from error
    except urllib.error.HTTPError as error:
        raise RuntimeError(format_openai_http_error(error, "餐前圖片分析")) from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"餐前圖片分析連線失敗：{error.reason}") from error


def analyze_meal_text(description: str, meal_type_override: str, coach_context: dict | None = None) -> dict:
    if not get_openai_api_key():
        raise RuntimeError("尚未設定 OPENAI_API_KEY。")

    local_now = datetime.now(APP_TIMEZONE)
    default_meal_type = meal_type_by_local_time(local_now)
    prompt = f"""
你是家庭健康管理 App 的飲食紀錄助手。請根據使用者輸入的文字估算餐食營養。
請只回傳 JSON，不要加 Markdown。欄位：
description: 繁體中文餐食描述，保留重點份量
meal_type: 早餐、午餐、晚餐、點心之一
calories: 整數 kcal
protein_g, fiber_g, carbs_g, fat_g: 數字
confidence: 高、中、低之一
matched: 簡短說明辨識到的主要食物或估算依據
可選欄位：
coach_note: 根據今日進度與使用者偏好的簡短提醒
next_meal_suggestion: 下一餐可執行建議
warning_note: 只有在熱量接近或超過目標、或資訊不足時才回傳，語氣必須溫和
使用者輸入：{description}
營養只是估算；份量不確定時請保守估算並降低 confidence。
請根據今日剩餘熱量、蛋白質、纖維與飲食偏好調整建議。
若蛋白質不足，提醒補高蛋白食物；若纖維不足，提醒補蔬菜、水果或豆類。
若熱量接近或超過目標，提醒後續餐食清淡、控制油脂與份量。
不要使用羞辱、恐嚇、焦慮式語氣；不要鼓勵極端節食或過度限制；不要做醫療診斷。
"""
    prompt += format_meal_context(coach_context)
    if meal_type_override != "自動判斷":
        prompt += f"\n使用者指定餐別為「{meal_type_override}」，meal_type 請使用這個值。"
    else:
        prompt += (
            "\n使用者選擇自動判斷餐別。"
            f"目前馬來西亞時間是 {local_now.strftime('%Y-%m-%d %H:%M')}，"
            f"若文字沒有明確餐別，meal_type 請使用「{default_meal_type}」。"
        )

    try:
        response_data = request_openai_json(prompt)
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI 文字估算失敗：{details}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"AI 文字估算連線失敗：{error.reason}") from error

    result = parse_meal_ai_result(extract_response_text(response_data), description)
    if meal_type_override != "自動判斷":
        result["meal_type"] = meal_type_override
    if result["meal_type"] not in MEAL_TYPES:
        result["meal_type"] = default_meal_type
    return result


def analyze_meal_photo(
    image_bytes: bytes,
    mime_type: str,
    meal_type_override: str,
    coach_context: dict | None = None,
) -> dict:
    api_key = get_openai_api_key()
    if not api_key:
        raise RuntimeError("尚未設定 OPENAI_API_KEY。")

    image_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"
    local_now = datetime.now(APP_TIMEZONE)
    default_meal_type = meal_type_by_local_time(local_now)
    prompt = """
你是家庭健康管理 App 的飲食紀錄助手。請根據照片辨識餐點並估算營養。
請只回傳 JSON，不要加 Markdown。欄位：
description: 繁體中文餐食描述，包含可見份量推測
meal_type: 早餐、午餐、晚餐、點心之一
calories: 整數 kcal
protein_g, fiber_g, carbs_g, fat_g: 數字
confidence: 高、中、低之一
matched: 簡短說明辨識到的主要食物；如果不確定，說明不確定原因
可選欄位：
coach_note: 根據今日進度與使用者偏好的簡短提醒
next_meal_suggestion: 下一餐可執行建議
warning_note: 只有在熱量接近或超過目標、或資訊不足時才回傳，語氣必須溫和
營養只是估算；看不清楚或份量不確定時請保守估算並降低 confidence。
請根據今日剩餘熱量、蛋白質、纖維與飲食偏好調整建議。
若蛋白質不足，提醒補高蛋白食物；若纖維不足，提醒補蔬菜、水果或豆類。
若熱量接近或超過目標，提醒後續餐食清淡、控制油脂與份量。
不要使用羞辱、恐嚇、焦慮式語氣；不要鼓勵極端節食或過度限制；不要做醫療診斷。
"""
    prompt += format_meal_context(coach_context)
    if meal_type_override != "自動判斷":
        prompt += f"\n使用者指定餐別為「{meal_type_override}」，meal_type 請使用這個值。"
    else:
        prompt += (
            "\n使用者選擇自動判斷餐別。"
            f"目前馬來西亞時間是 {local_now.strftime('%Y-%m-%d %H:%M')}，"
            f"若照片本身無法明確判斷餐別，meal_type 請使用「{default_meal_type}」。"
        )

    try:
        response_data = request_openai_json(prompt, image_url)
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"照片辨識失敗：{details}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"照片辨識連線失敗：{error.reason}") from error

    result = parse_meal_ai_result(extract_response_text(response_data), "照片餐食")
    if meal_type_override != "自動判斷":
        result["meal_type"] = meal_type_override
    if result["meal_type"] not in MEAL_TYPES:
        result["meal_type"] = default_meal_type
    return result
