from __future__ import annotations

import sqlite3
import os
from datetime import date, datetime

import pandas as pd

from db import connect
from write_adapter import SupabaseWriteAdapter


MEAL_LOG_WRITE_BACKEND_ENV = "PGY90_MEAL_LOG_WRITE_BACKEND"


def _meal_write_backend() -> tuple[str, str | None]:
    backend = os.environ.get(MEAL_LOG_WRITE_BACKEND_ENV, "sqlite").strip().lower() or "sqlite"
    if backend in {"sqlite", "supabase"}:
        return backend, None
    return "sqlite", f"{MEAL_LOG_WRITE_BACKEND_ENV}={backend} 不支援，已改用 sqlite。"


def _readable_write_error(exc: Exception) -> str:
    message = str(exc)
    if "SUPABASE_URL" in message or "SUPABASE_SERVICE_ROLE_KEY" in message:
        return "Supabase backend selected but SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is missing."
    return message or exc.__class__.__name__


def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)


def _get_meal_by_id(meal_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM meal_logs WHERE id = ?", (meal_id,)).fetchone()
    return _row_to_dict(row)


def save_meal_log(values: dict) -> tuple[str, str | None]:
    created_at = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO meal_logs (
                person_name, log_date, meal_type, description, calories, protein_g,
                fiber_g, carbs_g, fat_g, confidence, created_at
            ) VALUES (
                :person_name, :log_date, :meal_type, :description, :calories, :protein_g,
                :fiber_g, :carbs_g, :fat_g, :confidence, :created_at
            )
            """,
            {**values, "created_at": created_at},
        )
        meal_id = int(cursor.lastrowid)
        saved_row = conn.execute("SELECT * FROM meal_logs WHERE id = ?", (meal_id,)).fetchone()
    backend, warning = _meal_write_backend()
    if backend != "supabase":
        return "sqlite", warning

    try:
        payload = _row_to_dict(saved_row) or {**values, "id": meal_id, "created_at": created_at}
        SupabaseWriteAdapter(require_env=True, dry_run=False).save_meal_log(payload)
        return "supabase", warning
    except Exception as exc:
        return (
            "sqlite",
            "餐食紀錄已保存到 SQLite；Supabase meal_logs write pilot 失敗，未影響本機保存："
            f"{_readable_write_error(exc)}",
        )


def update_meal_log(meal_id: int, values: dict) -> tuple[str, str | None]:
    with connect() as conn:
        conn.execute(
            """
            UPDATE meal_logs
            SET log_date = :log_date,
                meal_type = :meal_type,
                description = :description,
                calories = :calories,
                protein_g = :protein_g,
                fiber_g = :fiber_g,
                carbs_g = :carbs_g,
                fat_g = :fat_g,
                confidence = :confidence
            WHERE id = :id
            """,
            {**values, "id": meal_id},
        )
        saved_row = conn.execute("SELECT * FROM meal_logs WHERE id = ?", (meal_id,)).fetchone()
    backend, warning = _meal_write_backend()
    if backend != "supabase":
        return "sqlite", warning

    try:
        payload = _row_to_dict(saved_row)
        if not payload:
            return "sqlite", "餐食紀錄已更新 SQLite；Supabase meal_logs pilot 找不到可同步的本機 row。"
        SupabaseWriteAdapter(require_env=True, dry_run=False).update_meal_log(meal_id, payload)
        return "supabase", warning
    except Exception as exc:
        return (
            "sqlite",
            "餐食紀錄已更新 SQLite；Supabase meal_logs write pilot 失敗，未影響本機更新："
            f"{_readable_write_error(exc)}",
        )


def delete_meal_log(meal_id: int) -> tuple[str, str | None]:
    existing = _get_meal_by_id(meal_id)
    with connect() as conn:
        conn.execute("DELETE FROM meal_logs WHERE id = ?", (meal_id,))
    backend, warning = _meal_write_backend()
    if backend != "supabase":
        return "sqlite", warning

    try:
        person_name = existing.get("person_name") if existing else None
        SupabaseWriteAdapter(require_env=True, dry_run=False).delete_meal_log(meal_id, person_name)
        return "supabase", warning
    except Exception as exc:
        return (
            "sqlite",
            "餐食紀錄已從 SQLite 刪除；Supabase meal_logs write pilot 失敗，請稍後檢查同步狀態："
            f"{_readable_write_error(exc)}",
        )


def load_meals(person_name: str) -> pd.DataFrame:
    with connect() as conn:
        return pd.read_sql_query(
            "SELECT * FROM meal_logs WHERE person_name = ? ORDER BY log_date, id",
            conn,
            params=(person_name,),
            parse_dates=["log_date"],
        )


def daily_meal_totals(meals: pd.DataFrame, selected_date: date) -> dict:
    if meals.empty:
        return {"calories": 0, "protein_g": 0.0, "fiber_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    day = meals[meals["log_date"].dt.date == selected_date]
    if day.empty:
        return {"calories": 0, "protein_g": 0.0, "fiber_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    return {
        "calories": int(day["calories"].fillna(0).sum()),
        "protein_g": float(day["protein_g"].fillna(0).sum()),
        "fiber_g": float(day["fiber_g"].fillna(0).sum()),
        "carbs_g": float(day["carbs_g"].fillna(0).sum()),
        "fat_g": float(day["fat_g"].fillna(0).sum()),
    }


def coach_feedback(totals: dict, profile: sqlite3.Row | None) -> list[str]:
    if profile is None:
        return ["先設定你的目標和飲食偏好，我就能用更貼近你的方式給建議。"]
    feedback = []
    calorie_gap = profile["daily_calorie_target"] - totals["calories"]
    protein_gap = profile["protein_target_g"] - totals["protein_g"]
    fiber_gap = profile["fiber_target_g"] - totals["fiber_g"]
    if totals["calories"] == 0:
        feedback.append("今天還沒有飲食紀錄。先用一句話輸入早餐或午餐就可以。")
    elif calorie_gap > 350:
        feedback.append(f"目前熱量還有約 {int(calorie_gap)} kcal 空間，下一餐可以補高蛋白主食。")
    elif calorie_gap < -150:
        feedback.append(f"今天已超過目標約 {abs(int(calorie_gap))} kcal，晚點以清淡蛋白質和蔬菜收尾。")
    else:
        feedback.append("今天熱量接近目標，接下來重點放在蛋白質和纖維。")
    if protein_gap > 20:
        feedback.append(f"蛋白質還差約 {int(protein_gap)} g，可以考慮雞胸、魚、蛋、豆腐或希臘優格。")
    elif protein_gap <= 0:
        feedback.append("蛋白質已達標，對減脂和維持肌肉很加分。")
    if fiber_gap > 8:
        feedback.append(f"纖維還差約 {int(fiber_gap)} g，下一餐加一份蔬菜或水果會很划算。")
    return feedback
