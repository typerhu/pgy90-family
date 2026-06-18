from __future__ import annotations

import hmac
import hashlib
import os
import sqlite3
import re
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st


APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "health.db"
DEFAULT_PERSON = "我"
APP_TIMEZONE = ZoneInfo("Asia/Kuching")
UTC_TIMEZONE = ZoneInfo("UTC")

PROFILE = {
    "height_cm": 181,
    "target_weight_kg": 75,
    "target_body_fat_min": 13,
    "target_body_fat_max": 15,
}

FOOD_CATEGORIES = ["均衡", "高蛋白", "外食", "應酬", "偏清淡", "偏油/甜", "其他"]
WORKOUT_TYPES = ["重訓", "有氧", "伸展", "球類", "步行", "休息", "其他"]
REHAB_TYPES = ["肩頸", "下背", "髖/腿", "膝蓋", "足踝", "全身活動度", "其他"]
GOALS = ["減脂", "增肌", "維持"]

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

DAILY_LOG_MIGRATIONS = {
    "breakfast_category": "TEXT",
    "breakfast_notes": "TEXT",
    "lunch_category": "TEXT",
    "lunch_notes": "TEXT",
    "dinner_category": "TEXT",
    "dinner_notes": "TEXT",
    "snack_notes": "TEXT",
    "avg_heart_rate": "INTEGER",
    "max_heart_rate": "INTEGER",
    "active_calories": "INTEGER",
    "distance_km": "REAL",
    "rpe": "INTEGER",
    "discomfort_notes": "TEXT",
}


@dataclass
class WeekWindow:
    start: date
    end: date


def get_app_password() -> str:
    try:
        secret_password = st.secrets.get("APP_PASSWORD", "")
    except Exception:
        secret_password = ""
    if secret_password:
        return str(secret_password)
    return os.environ.get("APP_PASSWORD", "")


def get_invite_code() -> str:
    try:
        invite_code = st.secrets.get("INVITE_CODE", "")
    except Exception:
        invite_code = ""
    if invite_code:
        return str(invite_code)
    return os.environ.get("INVITE_CODE", "")


def get_user_passwords() -> dict[str, str]:
    try:
        users = st.secrets.get("users", {})
    except Exception:
        users = {}
    if not users:
        return {}
    return {str(username): str(password) for username, password in dict(users).items()}


def get_admin_passwords() -> dict[str, str]:
    try:
        admins = st.secrets.get("admins", {})
    except Exception:
        admins = {}
    if not admins:
        return {}
    return {str(username): str(password) for username, password in dict(admins).items()}


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    password_salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        password_salt.encode("utf-8"),
        200_000,
    ).hex()
    return password_salt, digest


def create_account(person_name: str, password: str) -> None:
    salt, password_hash = hash_password(password)
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO app_users (person_name, password_salt, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (person_name, salt, password_hash, now),
        )
    add_person(person_name)


def set_account_password(person_name: str, password: str) -> None:
    salt, password_hash = hash_password(password)
    now = datetime.now().isoformat(timespec="seconds")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO app_users (person_name, password_salt, password_hash, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(person_name) DO UPDATE SET
                password_salt = excluded.password_salt,
                password_hash = excluded.password_hash
            """,
            (person_name, salt, password_hash, now),
        )
    add_person(person_name)


def delete_person_data(person_name: str) -> None:
    with connect() as conn:
        for table_name in [
            "daily_logs",
            "meal_logs",
            "weekly_reports",
            "coach_profiles",
            "app_users",
            "people",
        ]:
            conn.execute(f"DELETE FROM {table_name} WHERE person_name = ?", (person_name,))


def user_overview() -> pd.DataFrame:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                p.person_name,
                COALESCE(d.daily_count, 0) AS daily_logs,
                COALESCE(m.meal_count, 0) AS meal_logs,
                COALESCE(w.weekly_count, 0) AS weekly_reports,
                CASE WHEN u.person_name IS NULL THEN '否' ELSE '是' END AS has_login,
                p.created_at
            FROM people p
            LEFT JOIN (
                SELECT person_name, COUNT(*) AS daily_count
                FROM daily_logs
                GROUP BY person_name
            ) d ON d.person_name = p.person_name
            LEFT JOIN (
                SELECT person_name, COUNT(*) AS meal_count
                FROM meal_logs
                GROUP BY person_name
            ) m ON m.person_name = p.person_name
            LEFT JOIN (
                SELECT person_name, COUNT(*) AS weekly_count
                FROM weekly_reports
                GROUP BY person_name
            ) w ON w.person_name = p.person_name
            LEFT JOIN (
                SELECT person_name, COUNT(*) AS profile_count
                FROM coach_profiles
                GROUP BY person_name
            ) c ON c.person_name = p.person_name
            LEFT JOIN app_users u ON u.person_name = p.person_name
            WHERE NOT (
                p.person_name = ?
                AND COALESCE(d.daily_count, 0) = 0
                AND COALESCE(m.meal_count, 0) = 0
                AND COALESCE(w.weekly_count, 0) = 0
                AND COALESCE(c.profile_count, 0) = 0
            )
            ORDER BY p.created_at, p.person_name
            """,
            (DEFAULT_PERSON,),
        ).fetchall()
    df = pd.DataFrame([dict(row) for row in rows])
    if not df.empty and "created_at" in df:
        df["created_at"] = df["created_at"].apply(format_local_datetime)
    return df


def format_local_datetime(value: str | None) -> str:
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC_TIMEZONE)
    local_time = parsed.astimezone(APP_TIMEZONE)
    return local_time.strftime("%Y-%m-%d %H:%M:%S MYT")


def account_exists(person_name: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM app_users WHERE person_name = ?",
            (person_name,),
        ).fetchone()
    return row is not None


def registered_usernames() -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT person_name FROM app_users ORDER BY person_name"
        ).fetchall()
    return [row["person_name"] for row in rows]


def verify_account(person_name: str, password: str) -> bool:
    with connect() as conn:
        row = conn.execute(
            "SELECT password_salt, password_hash FROM app_users WHERE person_name = ?",
            (person_name,),
        ).fetchone()
    if not row:
        return False
    _, digest = hash_password(password, row["password_salt"])
    return hmac.compare_digest(digest, row["password_hash"])


def require_login() -> str | None:
    init_db()
    admin_passwords = get_admin_passwords()
    user_passwords = get_user_passwords()
    registered_users = registered_usernames()
    password = get_app_password()
    invite_code = get_invite_code()
    if not registered_users and not user_passwords and not admin_passwords and not password and not invite_code:
        st.error("尚未設定登入方式。請先在 Streamlit Secrets 加上 INVITE_CODE 或 [admins]。")
        st.stop()

    if st.session_state.get("authenticated"):
        with st.sidebar:
            current_user = st.session_state.get("authenticated_person")
            if current_user:
                st.markdown(f"### {current_user}")
            if st.session_state.get("is_admin"):
                st.caption("管理員模式")
            if st.button("登出", use_container_width=True):
                st.session_state["authenticated"] = False
                st.session_state.pop("authenticated_person", None)
                st.session_state.pop("is_admin", None)
                st.rerun()
        return st.session_state.get("authenticated_person")

    st.title("家庭健康管理")
    st.caption("請先登入。")
    login_tab, register_tab = st.tabs(["登入", "註冊"])

    with login_tab:
        with st.form("login_form"):
            available_users = sorted(
                set(registered_users) | set(user_passwords.keys()) | set(admin_passwords.keys())
            )
            selected_user = None
            if available_users:
                selected_user = st.selectbox("使用者", available_users)
            entered_password = st.text_input("密碼", type="password")
            submitted = st.form_submit_button("登入", use_container_width=True)

        if submitted:
            if selected_user in admin_passwords and hmac.compare_digest(
                entered_password,
                admin_passwords.get(selected_user, ""),
            ):
                st.session_state["authenticated"] = True
                st.session_state["authenticated_person"] = selected_user
                st.session_state["is_admin"] = True
                st.rerun()
            elif selected_user and verify_account(selected_user, entered_password):
                st.session_state["authenticated"] = True
                st.session_state["authenticated_person"] = selected_user
                st.session_state["is_admin"] = False
                add_person(selected_user or "")
                st.rerun()
            elif user_passwords:
                expected_password = user_passwords.get(selected_user or "", "")
                if hmac.compare_digest(entered_password, expected_password):
                    st.session_state["authenticated"] = True
                    st.session_state["authenticated_person"] = selected_user
                    st.session_state["is_admin"] = False
                    add_person(selected_user or "")
                    st.rerun()
                else:
                    st.error("使用者或密碼不正確。")
            elif password and hmac.compare_digest(entered_password, password):
                st.session_state["authenticated"] = True
                st.session_state["is_admin"] = False
                st.rerun()
            else:
                st.error("使用者或密碼不正確。")

    with register_tab:
        if not invite_code:
            st.info("尚未開放自助註冊。請請管理者在 Secrets 設定 INVITE_CODE。")
        else:
            with st.form("register_form"):
                new_user = st.text_input("使用者名稱", placeholder="例：爸爸、媽媽、Ashley")
                new_password = st.text_input("設定密碼", type="password")
                confirm_password = st.text_input("再次輸入密碼", type="password")
                entered_invite = st.text_input("邀請碼", type="password")
                register_submitted = st.form_submit_button("建立帳號", use_container_width=True)

            if register_submitted:
                cleaned_user = new_user.strip()
                if not cleaned_user:
                    st.warning("請輸入使用者名稱。")
                elif cleaned_user == DEFAULT_PERSON:
                    st.warning("請輸入實際名字或稱呼，避免大家都用「我」。")
                elif account_exists(cleaned_user):
                    st.warning("這個使用者已經存在，請直接登入。")
                elif len(new_password) < 4:
                    st.warning("密碼至少需要 4 個字元。")
                elif new_password != confirm_password:
                    st.warning("兩次密碼不一致。")
                elif not hmac.compare_digest(entered_invite, invite_code):
                    st.warning("邀請碼不正確。")
                else:
                    create_account(cleaned_user, new_password)
                    st.success("帳號已建立，現在可以登入。")
    st.stop()


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    return [row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})")]


def ensure_family_schema(conn: sqlite3.Connection) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS people (
            person_name TEXT PRIMARY KEY,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_users (
            person_name TEXT PRIMARY KEY,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT OR IGNORE INTO people (person_name, created_at) VALUES (?, ?)",
        (DEFAULT_PERSON, now),
    )

    daily_columns = table_columns(conn, "daily_logs")
    if "person_name" not in daily_columns:
        conn.execute("ALTER TABLE daily_logs RENAME TO daily_logs_old")
        conn.execute(
            """
            CREATE TABLE daily_logs (
                person_name TEXT NOT NULL DEFAULT '我',
                log_date TEXT NOT NULL,
                weight_kg REAL,
                body_fat_percent REAL,
                waist_cm REAL,
                sleep_hours REAL,
                sleep_quality INTEGER,
                food_category TEXT,
                food_notes TEXT,
                breakfast_category TEXT,
                breakfast_notes TEXT,
                lunch_category TEXT,
                lunch_notes TEXT,
                dinner_category TEXT,
                dinner_notes TEXT,
                snack_notes TEXT,
                workout_type TEXT,
                workout_minutes INTEGER,
                avg_heart_rate INTEGER,
                max_heart_rate INTEGER,
                active_calories INTEGER,
                distance_km REAL,
                rpe INTEGER,
                discomfort_notes TEXT,
                workout_notes TEXT,
                rehab_done INTEGER DEFAULT 0,
                rehab_type TEXT,
                rehab_notes TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (person_name, log_date)
            )
            """
        )
        old_daily_columns = table_columns(conn, "daily_logs_old")
        copy_columns = [col for col in daily_columns if col in old_daily_columns]
        conn.execute(
            f"""
            INSERT INTO daily_logs (person_name, {", ".join(copy_columns)})
            SELECT ?, {", ".join(copy_columns)} FROM daily_logs_old
            """,
            (DEFAULT_PERSON,),
        )
        conn.execute("DROP TABLE daily_logs_old")

    weekly_columns = table_columns(conn, "weekly_reports")
    if "person_name" not in weekly_columns:
        conn.execute("ALTER TABLE weekly_reports RENAME TO weekly_reports_old")
        conn.execute(
            """
            CREATE TABLE weekly_reports (
                person_name TEXT NOT NULL DEFAULT '我',
                week_start TEXT NOT NULL,
                week_end TEXT NOT NULL,
                summary TEXT NOT NULL,
                generated_at TEXT NOT NULL,
                PRIMARY KEY (person_name, week_start)
            )
            """
        )
        conn.execute(
            """
            INSERT INTO weekly_reports (
                person_name, week_start, week_end, summary, generated_at
            )
            SELECT ?, week_start, week_end, summary, generated_at
            FROM weekly_reports_old
            """,
            (DEFAULT_PERSON,),
        )
        conn.execute("DROP TABLE weekly_reports_old")

    meal_columns = table_columns(conn, "meal_logs")
    if "person_name" not in meal_columns:
        conn.execute(
            f"ALTER TABLE meal_logs ADD COLUMN person_name TEXT NOT NULL DEFAULT '{DEFAULT_PERSON}'"
        )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS coach_profiles (
            person_name TEXT PRIMARY KEY,
            goal TEXT NOT NULL,
            current_weight_kg REAL,
            daily_calorie_target INTEGER,
            protein_target_g INTEGER,
            fiber_target_g INTEGER,
            preferences TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    old_profile = conn.execute("SELECT * FROM coach_profile WHERE id = 1").fetchone()
    if old_profile:
        conn.execute(
            """
            INSERT OR IGNORE INTO coach_profiles (
                person_name, goal, current_weight_kg, daily_calorie_target,
                protein_target_g, fiber_target_g, preferences, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                DEFAULT_PERSON,
                old_profile["goal"],
                old_profile["current_weight_kg"],
                old_profile["daily_calorie_target"],
                old_profile["protein_target_g"],
                old_profile["fiber_target_g"],
                old_profile["preferences"],
                old_profile["updated_at"],
            ),
        )


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_logs (
                log_date TEXT PRIMARY KEY,
                weight_kg REAL,
                body_fat_percent REAL,
                waist_cm REAL,
                sleep_hours REAL,
                sleep_quality INTEGER,
                food_category TEXT,
                food_notes TEXT,
                breakfast_category TEXT,
                breakfast_notes TEXT,
                lunch_category TEXT,
                lunch_notes TEXT,
                dinner_category TEXT,
                dinner_notes TEXT,
                snack_notes TEXT,
                workout_type TEXT,
                workout_minutes INTEGER,
                avg_heart_rate INTEGER,
                max_heart_rate INTEGER,
                active_calories INTEGER,
                distance_km REAL,
                rpe INTEGER,
                discomfort_notes TEXT,
                workout_notes TEXT,
                rehab_done INTEGER DEFAULT 0,
                rehab_type TEXT,
                rehab_notes TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        existing_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(daily_logs)").fetchall()
        }
        for column_name, column_type in DAILY_LOG_MIGRATIONS.items():
            if column_name not in existing_columns:
                conn.execute(
                    f"ALTER TABLE daily_logs ADD COLUMN {column_name} {column_type}"
                )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS weekly_reports (
                week_start TEXT PRIMARY KEY,
                week_end TEXT NOT NULL,
                summary TEXT NOT NULL,
                generated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS meal_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_date TEXT NOT NULL,
                meal_type TEXT NOT NULL,
                description TEXT NOT NULL,
                calories INTEGER,
                protein_g REAL,
                fiber_g REAL,
                carbs_g REAL,
                fat_g REAL,
                confidence TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS coach_profile (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                goal TEXT NOT NULL,
                current_weight_kg REAL,
                daily_calorie_target INTEGER,
                protein_target_g INTEGER,
                fiber_target_g INTEGER,
                preferences TEXT,
                updated_at TEXT NOT NULL
            )
            """
        )
        ensure_family_schema(conn)


def load_people() -> list[str]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT person_name FROM people ORDER BY created_at, person_name"
        ).fetchall()
    return [row["person_name"] for row in rows] or [DEFAULT_PERSON]


def add_person(person_name: str) -> None:
    cleaned = person_name.strip()
    if not cleaned:
        return
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO people (person_name, created_at) VALUES (?, ?)",
            (cleaned, datetime.now().isoformat(timespec="seconds")),
        )


def person_has_data(person_name: str) -> bool:
    with connect() as conn:
        checks = [
            ("daily_logs", "person_name = ?"),
            ("meal_logs", "person_name = ?"),
            ("weekly_reports", "person_name = ?"),
            ("coach_profiles", "person_name = ?"),
        ]
        for table_name, where_clause in checks:
            count = conn.execute(
                f"SELECT COUNT(*) AS total FROM {table_name} WHERE {where_clause}",
                (person_name,),
            ).fetchone()["total"]
            if count:
                return True
    return False


def get_daily_log(person_name: str, log_date: date) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM daily_logs WHERE person_name = ? AND log_date = ?",
            (person_name, log_date.isoformat()),
        ).fetchone()


def upsert_daily_log(values: dict) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    payload = {
        **values,
        "rehab_done": 1 if values["rehab_done"] else 0,
        "updated_at": now,
    }
    with connect() as conn:
        exists = conn.execute(
            "SELECT 1 FROM daily_logs WHERE person_name = ? AND log_date = ?",
            (payload["person_name"], payload["log_date"]),
        ).fetchone()
        if exists:
            conn.execute(
                """
                UPDATE daily_logs
                SET weight_kg = :weight_kg,
                    body_fat_percent = :body_fat_percent,
                    waist_cm = :waist_cm,
                    sleep_hours = :sleep_hours,
                    sleep_quality = :sleep_quality,
                    food_category = :food_category,
                    food_notes = :food_notes,
                    breakfast_category = :breakfast_category,
                    breakfast_notes = :breakfast_notes,
                    lunch_category = :lunch_category,
                    lunch_notes = :lunch_notes,
                    dinner_category = :dinner_category,
                    dinner_notes = :dinner_notes,
                    snack_notes = :snack_notes,
                    workout_type = :workout_type,
                    workout_minutes = :workout_minutes,
                    avg_heart_rate = :avg_heart_rate,
                    max_heart_rate = :max_heart_rate,
                    active_calories = :active_calories,
                    distance_km = :distance_km,
                    rpe = :rpe,
                    discomfort_notes = :discomfort_notes,
                    workout_notes = :workout_notes,
                    rehab_done = :rehab_done,
                    rehab_type = :rehab_type,
                    rehab_notes = :rehab_notes,
                    notes = :notes,
                    updated_at = :updated_at
                WHERE person_name = :person_name AND log_date = :log_date
                """,
                payload,
            )
        else:
            conn.execute(
                """
                INSERT INTO daily_logs (
                    person_name, log_date, weight_kg, body_fat_percent, waist_cm,
                    sleep_hours, sleep_quality, food_category, food_notes,
                    breakfast_category, breakfast_notes, lunch_category,
                    lunch_notes, dinner_category, dinner_notes, snack_notes,
                    workout_type, workout_minutes, avg_heart_rate,
                    max_heart_rate, active_calories, distance_km, rpe,
                    discomfort_notes, workout_notes,
                    rehab_done, rehab_type, rehab_notes, notes,
                    created_at, updated_at
                ) VALUES (
                    :person_name, :log_date, :weight_kg, :body_fat_percent, :waist_cm,
                    :sleep_hours, :sleep_quality, :food_category, :food_notes,
                    :breakfast_category, :breakfast_notes, :lunch_category,
                    :lunch_notes, :dinner_category, :dinner_notes, :snack_notes,
                    :workout_type, :workout_minutes, :avg_heart_rate,
                    :max_heart_rate, :active_calories, :distance_km, :rpe,
                    :discomfort_notes, :workout_notes,
                    :rehab_done, :rehab_type, :rehab_notes, :notes,
                    :created_at, :updated_at
                )
                """,
                {**payload, "created_at": now},
            )


def load_logs(person_name: str) -> pd.DataFrame:
    with connect() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM daily_logs WHERE person_name = ? ORDER BY log_date",
            conn,
            params=(person_name,),
            parse_dates=["log_date"],
        )
    if not df.empty:
        df["bmi"] = df["weight_kg"] / ((PROFILE["height_cm"] / 100) ** 2)
    return df


def get_coach_profile(person_name: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM coach_profiles WHERE person_name = ?",
            (person_name,),
        ).fetchone()


def save_coach_profile(person_name: str, values: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO coach_profiles (
                person_name, goal, current_weight_kg, daily_calorie_target,
                protein_target_g, fiber_target_g, preferences, updated_at
            ) VALUES (:person_name, :goal, :current_weight_kg, :daily_calorie_target,
                :protein_target_g, :fiber_target_g, :preferences, :updated_at)
            ON CONFLICT(person_name) DO UPDATE SET
                goal = excluded.goal,
                current_weight_kg = excluded.current_weight_kg,
                daily_calorie_target = excluded.daily_calorie_target,
                protein_target_g = excluded.protein_target_g,
                fiber_target_g = excluded.fiber_target_g,
                preferences = excluded.preferences,
                updated_at = excluded.updated_at
            """,
            {
                **values,
                "person_name": person_name,
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
        )


def latest_weight(df: pd.DataFrame) -> float:
    if df.empty or "weight_kg" not in df:
        return 75.0
    weights = df.dropna(subset=["weight_kg"]).sort_values("log_date")
    if weights.empty:
        return 75.0
    return float(weights.iloc[-1]["weight_kg"])


def default_targets(weight_kg: float, goal: str) -> tuple[int, int, int]:
    maintenance = int(round(weight_kg * 31))
    if goal == "減脂":
        calories = maintenance - 400
        protein = int(round(weight_kg * 1.8))
    elif goal == "增肌":
        calories = maintenance + 250
        protein = int(round(weight_kg * 1.7))
    else:
        calories = maintenance
        protein = int(round(weight_kg * 1.6))
    return max(calories, 1500), protein, 28


def detect_meal_type(text: str) -> str:
    for meal_type, keywords in MEAL_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return meal_type
    hour = datetime.now().hour
    if hour < 10:
        return "早餐"
    if hour < 15:
        return "午餐"
    if hour < 21:
        return "晚餐"
    return "點心"


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
    pattern = rf"({'|'.join(number_tokens.keys())})\s*(份|碗|盤|個|顆|杯|片)?\s*{re.escape(keyword)}"
    match = re.search(pattern, text)
    if match:
        return number_tokens[match.group(1)]
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


def save_meal_log(values: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO meal_logs (
                person_name, log_date, meal_type, description, calories, protein_g,
                fiber_g, carbs_g, fat_g, confidence, created_at
            ) VALUES (
                :person_name, :log_date, :meal_type, :description, :calories, :protein_g,
                :fiber_g, :carbs_g, :fat_g, :confidence, :created_at
            )
            """,
            {**values, "created_at": datetime.now().isoformat(timespec="seconds")},
        )


def update_meal_log(meal_id: int, values: dict) -> None:
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


def delete_meal_log(meal_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM meal_logs WHERE id = ?", (meal_id,))


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


def week_window(selected: date) -> WeekWindow:
    start = selected - timedelta(days=selected.weekday())
    return WeekWindow(start=start, end=start + timedelta(days=6))


def format_delta(current: float | None, previous: float | None, unit: str) -> str | None:
    if current is None or previous is None:
        return None
    delta = current - previous
    if abs(delta) < 0.01:
        return f"0 {unit}"
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.1f} {unit}"


def compact_number(value: float | None, digits: int = 1) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{value:.{digits}f}"


def split_sleep_time(total_hours: float | None) -> tuple[int, int]:
    if total_hours is None or pd.isna(total_hours):
        return 7, 0
    total_minutes = int(round(float(total_hours) * 60))
    return total_minutes // 60, total_minutes % 60


def apply_ui_style() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 760px;
            padding-top: 1.5rem;
            padding-left: 1rem;
            padding-right: 1rem;
        }
        div[data-testid="stMetric"] {
            border-bottom: 1px solid rgba(49, 51, 63, 0.15);
            padding-bottom: 0.75rem;
        }
        div[data-testid="stForm"] {
            border: 0;
            padding: 0;
        }
        h4 {
            margin-top: 1.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def generate_weekly_summary(week_df: pd.DataFrame, window: WeekWindow) -> str:
    if week_df.empty:
        return (
            f"{window.start.isoformat()} 至 {window.end.isoformat()} 尚無紀錄。"
            "本週先以建立連續記錄習慣為主。"
        )

    recorded_days = len(week_df)
    latest = week_df.sort_values("log_date").iloc[-1]
    weight_avg = week_df["weight_kg"].dropna().mean()
    body_fat_avg = week_df["body_fat_percent"].dropna().mean()
    waist_avg = week_df["waist_cm"].dropna().mean()
    sleep_avg = week_df["sleep_hours"].dropna().mean()
    workout_total = int(week_df["workout_minutes"].fillna(0).sum())
    active_calories_total = int(week_df["active_calories"].fillna(0).sum())
    avg_heart_rate = week_df["avg_heart_rate"].dropna().mean()
    avg_rpe = week_df["rpe"].dropna().mean()
    rehab_days = int(week_df["rehab_done"].fillna(0).sum())
    food_counts = week_df["food_category"].dropna().value_counts()
    main_food = food_counts.index[0] if not food_counts.empty else "未分類"

    weight_gap = None
    if pd.notna(latest.get("weight_kg")):
        weight_gap = latest["weight_kg"] - PROFILE["target_weight_kg"]

    highlights = [
        f"本週記錄 {recorded_days} 天。",
        f"平均體重 {compact_number(weight_avg)} kg，平均體脂 {compact_number(body_fat_avg)}%。",
        f"平均腰圍 {compact_number(waist_avg)} cm，平均睡眠 {compact_number(sleep_avg)} 小時。",
        f"運動總量 {workout_total} 分鐘，復健完成 {rehab_days} 天。",
        f"Apple Watch 運動摘要：活動熱量 {active_calories_total} kcal，平均心率 {compact_number(avg_heart_rate, 0)} bpm，平均 RPE {compact_number(avg_rpe)}。",
        f"飲食型態以「{main_food}」為主。",
    ]

    recommendations = []
    if weight_gap is not None:
        if weight_gap > 2:
            recommendations.append("體重仍高於 75kg 目標，先維持高蛋白、減少高油甜與應酬頻率。")
        elif weight_gap < -1:
            recommendations.append("體重已低於目標附近，建議確認精神、訓練表現與恢復狀態。")
        else:
            recommendations.append("體重接近 75kg 目標，可把注意力轉到腰圍、睡眠和訓練穩定度。")
    if pd.notna(body_fat_avg):
        if body_fat_avg > PROFILE["target_body_fat_max"]:
            recommendations.append("體脂仍高於 13-15% 目標區間，建議下週增加 1-2 次低強度活動。")
        elif PROFILE["target_body_fat_min"] <= body_fat_avg <= PROFILE["target_body_fat_max"]:
            recommendations.append("體脂落在目標區間，維持即可，避免過度節食。")
    if pd.notna(sleep_avg) and sleep_avg < 7:
        recommendations.append("睡眠平均低於 7 小時，恢復可能是下週最值得優先改善的指標。")
    if workout_total < 120:
        recommendations.append("運動量偏少，下週可先安排 2 次 45-60 分鐘訓練。")
    if rehab_days < 3:
        recommendations.append("復健頻率偏低，建議用短時間、低門檻方式累積到每週至少 3 天。")

    if not recommendations:
        recommendations.append("本週節奏穩定，下週延續同樣記錄密度並觀察腰圍與體脂變化。")

    return "\n".join(
        [
            f"週期：{window.start.isoformat()} 至 {window.end.isoformat()}",
            "",
            "本週摘要：",
            *[f"- {item}" for item in highlights],
            "",
            "下週建議：",
            *[f"- {item}" for item in recommendations],
        ]
    )


def save_weekly_report(person_name: str, window: WeekWindow, summary: str) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO weekly_reports (
                person_name, week_start, week_end, summary, generated_at
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(person_name, week_start) DO UPDATE SET
                week_end = excluded.week_end,
                summary = excluded.summary,
                generated_at = excluded.generated_at
            """,
            (
                person_name,
                window.start.isoformat(),
                window.end.isoformat(),
                summary,
                datetime.now().isoformat(timespec="seconds"),
            ),
        )


def get_saved_report(person_name: str, window: WeekWindow) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM weekly_reports WHERE person_name = ? AND week_start = ?",
            (person_name, window.start.isoformat()),
        ).fetchone()


def metric_cards(df: pd.DataFrame) -> None:
    sorted_df = df.sort_values("log_date") if not df.empty else df

    def latest_pair(column: str) -> tuple[float | None, float | None]:
        if sorted_df.empty:
            return None, None
        values = sorted_df.dropna(subset=[column])
        if values.empty:
            return None, None
        current = values.iloc[-1][column]
        previous = values.iloc[-2][column] if len(values) >= 2 else None
        return current, previous

    weight, prev_weight = latest_pair("weight_kg")
    body_fat, prev_body_fat = latest_pair("body_fat_percent")
    waist, prev_waist = latest_pair("waist_cm")
    bmi, _ = latest_pair("bmi")

    st.dataframe(
        pd.DataFrame(
            [
                ["最新體重", f"{compact_number(weight)} kg", format_delta(weight, prev_weight, "kg") or "-"],
                ["最新體脂", f"{compact_number(body_fat)}%", format_delta(body_fat, prev_body_fat, "%") or "-"],
                ["最新腰圍", f"{compact_number(waist)} cm", format_delta(waist, prev_waist, "cm") or "-"],
                ["BMI", compact_number(bmi), "181 cm"],
            ],
            columns=["指標", "目前", "變化"],
        ),
        use_container_width=True,
        hide_index=True,
    )


def daily_input_page(person_name: str) -> None:
    st.subheader(f"{person_name}｜每日輸入")
    selected_date = st.date_input("日期", value=date.today())
    existing = get_daily_log(person_name, selected_date)

    def existing_value(key: str, fallback):
        if existing is None or existing[key] is None:
            return fallback
        return existing[key]

    with st.form("daily_log_form"):
        st.markdown("#### 身體指標")
        weight = st.number_input(
            "體重 kg",
            min_value=30.0,
            max_value=180.0,
            value=float(existing_value("weight_kg", 75.0)),
            step=0.1,
            format="%.1f",
            width=120,
        )
        body_fat = st.number_input(
            "體脂 %",
            min_value=3.0,
            max_value=45.0,
            value=float(existing_value("body_fat_percent", 15.0)),
            step=0.1,
            format="%.1f",
            width=120,
        )
        existing_waist = existing_value("waist_cm", None)
        waist_measured = st.checkbox("今天有量腰圍", value=existing_waist is not None)
        waist = None
        if waist_measured:
            waist = st.number_input(
                "腰圍 cm",
                min_value=50.0,
                max_value=150.0,
                value=float(existing_waist if existing_waist is not None else 82.0),
                step=0.1,
                format="%.1f",
                width=120,
            )

        st.markdown("#### 睡眠")
        current_sleep_hours, current_sleep_minutes = split_sleep_time(
            existing_value("sleep_hours", 7.0)
        )
        sleep_hour_part = st.number_input(
            "小時",
            min_value=0,
            max_value=14,
            value=current_sleep_hours,
            step=1,
            width=90,
        )
        sleep_minute_part = st.number_input(
            "分鐘",
            min_value=0,
            max_value=59,
            value=current_sleep_minutes,
            step=1,
            width=90,
        )
        sleep_quality = st.slider(
            "睡眠品質 %",
            min_value=0,
            max_value=100,
            value=int(existing_value("sleep_quality", 75)),
            step=1,
        )

        st.markdown("#### 飲食")
        food_category = st.selectbox(
            "當日總評",
            FOOD_CATEGORIES,
            index=FOOD_CATEGORIES.index(existing_value("food_category", "均衡"))
            if existing_value("food_category", "均衡") in FOOD_CATEGORIES
            else 0,
        )
        breakfast_category = existing_value("breakfast_category", "")
        breakfast_notes = existing_value("breakfast_notes", "")
        lunch_category = existing_value("lunch_category", "")
        lunch_notes = existing_value("lunch_notes", "")
        dinner_category = existing_value("dinner_category", "")
        dinner_notes = existing_value("dinner_notes", "")
        snack_notes = existing_value("snack_notes", "")
        food_notes = existing_value("food_notes", "")

        st.markdown("#### 運動")

        workout_type = st.selectbox(
            "運動類型",
            WORKOUT_TYPES,
            index=WORKOUT_TYPES.index(existing_value("workout_type", "休息"))
            if existing_value("workout_type", "休息") in WORKOUT_TYPES
            else 0,
        )
        workout_minutes = st.number_input(
            "運動分鐘",
            min_value=0,
            max_value=300,
            value=int(existing_value("workout_minutes", 0)),
            step=5,
            width=110,
        )
        avg_heart_rate = st.number_input(
            "平均心率 bpm",
            min_value=0,
            max_value=230,
            value=int(existing_value("avg_heart_rate", 0)),
            step=1,
            width=110,
        )
        max_heart_rate = st.number_input(
            "最高心率 bpm",
            min_value=0,
            max_value=230,
            value=int(existing_value("max_heart_rate", 0)),
            step=1,
            width=110,
        )
        active_calories = st.number_input(
            "活動熱量 kcal",
            min_value=0,
            max_value=3000,
            value=int(existing_value("active_calories", 0)),
            step=10,
            width=120,
        )

        distance_km = st.number_input(
            "距離 km",
            min_value=0.0,
            max_value=100.0,
            value=float(existing_value("distance_km", 0.0)),
            step=0.1,
            format="%.1f",
            width=110,
        )
        rpe = st.slider(
            "主觀強度 RPE",
            min_value=0,
            max_value=10,
            value=int(existing_value("rpe", 0)),
            step=1,
        )

        workout_notes = st.text_area("運動內容", value=existing_value("workout_notes", ""), height=80)
        discomfort_notes = st.text_area(
            "疼痛 / 不適 / 疲勞",
            value=existing_value("discomfort_notes", ""),
            height=70,
        )

        rehab_done = st.checkbox("今天有做復健 / 活動度訓練", value=bool(existing_value("rehab_done", 0)))
        rehab_type = st.selectbox(
            "復健分類",
            REHAB_TYPES,
            index=REHAB_TYPES.index(existing_value("rehab_type", "全身活動度"))
            if existing_value("rehab_type", "全身活動度") in REHAB_TYPES
            else 0,
        )
        rehab_notes = st.text_area("復健記錄", value=existing_value("rehab_notes", ""), height=70)
        notes = st.text_area("備註", value=existing_value("notes", ""), height=80)

        submitted = st.form_submit_button("儲存今日紀錄", use_container_width=True)

    if submitted:
        upsert_daily_log(
            {
                "person_name": person_name,
                "log_date": selected_date.isoformat(),
                "weight_kg": weight,
                "body_fat_percent": body_fat,
                "waist_cm": waist if waist_measured else None,
                "sleep_hours": sleep_hour_part + (sleep_minute_part / 60),
                "sleep_quality": sleep_quality,
                "food_category": food_category,
                "breakfast_category": breakfast_category,
                "breakfast_notes": str(breakfast_notes).strip(),
                "lunch_category": lunch_category,
                "lunch_notes": str(lunch_notes).strip(),
                "dinner_category": dinner_category,
                "dinner_notes": str(dinner_notes).strip(),
                "snack_notes": str(snack_notes).strip(),
                "food_notes": str(food_notes).strip(),
                "workout_type": workout_type,
                "workout_minutes": workout_minutes,
                "avg_heart_rate": avg_heart_rate or None,
                "max_heart_rate": max_heart_rate or None,
                "active_calories": active_calories or None,
                "distance_km": distance_km or None,
                "rpe": rpe or None,
                "discomfort_notes": discomfort_notes.strip(),
                "workout_notes": workout_notes.strip(),
                "rehab_done": rehab_done,
                "rehab_type": rehab_type if rehab_done else "",
                "rehab_notes": rehab_notes.strip(),
                "notes": notes.strip(),
            }
        )
        st.success("已儲存。")
        st.rerun()


def trend_page(df: pd.DataFrame) -> None:
    st.subheader("趨勢圖表")
    if df.empty:
        st.info("還沒有資料。先到每日輸入新增第一筆紀錄。")
        return

    metric_cards(df)

    days = st.slider("顯示最近幾天", 7, 180, 60, step=7)
    cutoff = pd.Timestamp(date.today() - timedelta(days=days - 1))
    recent = df[df["log_date"] >= cutoff]

    st.line_chart(
        recent.set_index("log_date")[["weight_kg", "body_fat_percent", "waist_cm"]],
        height=320,
    )

    st.caption("睡眠")
    st.bar_chart(recent.set_index("log_date")[["sleep_hours"]], height=220)

    st.caption("運動分鐘")
    st.bar_chart(recent.set_index("log_date")[["workout_minutes"]], height=220)

    st.caption("平均心率")
    st.line_chart(recent.set_index("log_date")[["avg_heart_rate"]], height=220)

    st.caption("活動熱量")
    st.bar_chart(recent.set_index("log_date")[["active_calories"]], height=220)

    table_cols = [
        "log_date",
        "weight_kg",
        "body_fat_percent",
        "waist_cm",
        "sleep_hours",
        "food_category",
        "workout_type",
        "workout_minutes",
        "avg_heart_rate",
        "max_heart_rate",
        "active_calories",
        "distance_km",
        "rpe",
        "rehab_done",
        "discomfort_notes",
        "notes",
    ]
    st.dataframe(
        recent[table_cols].sort_values("log_date", ascending=False),
        use_container_width=True,
        hide_index=True,
    )


def weekly_report_page(df: pd.DataFrame, person_name: str) -> None:
    st.subheader(f"{person_name}｜每週報告")
    selected = st.date_input("選擇週內任一天", value=date.today(), key="weekly_date")
    window = week_window(selected)
    st.caption(f"週期：{window.start.isoformat()} 至 {window.end.isoformat()}")

    if df.empty:
        week_df = df
    else:
        week_df = df[
            (df["log_date"].dt.date >= window.start)
            & (df["log_date"].dt.date <= window.end)
        ]

    summary = generate_weekly_summary(week_df, window)
    saved = get_saved_report(person_name, window)

    if st.button("產生 / 更新本週總結", use_container_width=True):
        save_weekly_report(person_name, window, summary)
        st.success("已更新本週總結。")
        st.rerun()
    if saved:
        st.info(f"已儲存：{saved['generated_at']}")
    else:
        st.warning("尚未儲存本週總結。")

    st.text_area(
        "健康總結",
        value=saved["summary"] if saved else summary,
        height=320,
    )

    if not week_df.empty:
        st.markdown("#### 本週資料")
        st.dataframe(
            week_df.sort_values("log_date", ascending=False),
            use_container_width=True,
            hide_index=True,
        )


def coach_page(df: pd.DataFrame, person_name: str) -> None:
    st.subheader(f"{person_name}｜AI飲食教練")
    profile = get_coach_profile(person_name)
    current_weight = latest_weight(df)
    default_calories, default_protein, default_fiber = default_targets(current_weight, "減脂")

    if profile is not None:
        current_goal = profile["goal"]
        current_weight = float(profile["current_weight_kg"] or current_weight)
        default_calories = int(profile["daily_calorie_target"] or default_calories)
        default_protein = int(profile["protein_target_g"] or default_protein)
        default_fiber = int(profile["fiber_target_g"] or default_fiber)
        current_preferences = profile["preferences"] or ""
    else:
        current_goal = "減脂"
        current_preferences = "高蛋白、少油炸、外食可執行、亞洲食物優先"

    with st.expander("個人目標與飲食偏好", expanded=profile is None):
        with st.form("coach_profile_form"):
            goal = st.selectbox(
                "目前目標",
                GOALS,
                index=GOALS.index(current_goal) if current_goal in GOALS else 0,
            )
            weight = st.number_input(
                "目前體重 kg",
                min_value=30.0,
                max_value=180.0,
                value=float(current_weight),
                step=0.1,
                format="%.1f",
                width=120,
            )
            suggested_calories, suggested_protein, suggested_fiber = default_targets(weight, goal)
            calorie_target = st.number_input(
                "每日熱量目標 kcal",
                min_value=1000,
                max_value=5000,
                value=int(default_calories if profile is not None else suggested_calories),
                step=50,
                width=140,
            )
            protein_target = st.number_input(
                "每日蛋白質目標 g",
                min_value=40,
                max_value=300,
                value=int(default_protein if profile is not None else suggested_protein),
                step=5,
                width=120,
            )
            fiber_target = st.number_input(
                "每日纖維目標 g",
                min_value=10,
                max_value=80,
                value=int(default_fiber if profile is not None else suggested_fiber),
                step=1,
                width=120,
            )
            preferences = st.text_area(
                "飲食偏好 / 禁忌 / 身體狀況",
                value=current_preferences,
                height=90,
            )
            if st.form_submit_button("儲存偏好", use_container_width=True):
                save_coach_profile(
                    person_name,
                    {
                        "goal": goal,
                        "current_weight_kg": weight,
                        "daily_calorie_target": calorie_target,
                        "protein_target_g": protein_target,
                        "fiber_target_g": fiber_target,
                        "preferences": preferences.strip(),
                    }
                )
                st.success("已儲存你的飲食偏好。")
                st.rerun()

    selected_date = st.date_input("記錄日期", value=date.today(), key="coach_date")
    meals = load_meals(person_name)
    totals = daily_meal_totals(meals, selected_date)
    profile = get_coach_profile(person_name)

    target_calories = profile["daily_calorie_target"] if profile else default_calories
    target_protein = profile["protein_target_g"] if profile else default_protein
    target_fiber = profile["fiber_target_g"] if profile else default_fiber

    st.dataframe(
        pd.DataFrame(
            [
                ["熱量", f"{totals['calories']} / {target_calories} kcal", f"{int(target_calories - totals['calories'])} kcal"],
                ["蛋白質", f"{totals['protein_g']:.1f} / {target_protein} g", f"{target_protein - totals['protein_g']:.1f} g"],
                ["纖維", f"{totals['fiber_g']:.1f} / {target_fiber} g", f"{target_fiber - totals['fiber_g']:.1f} g"],
                ["碳水 / 脂肪", f"{totals['carbs_g']:.1f} g / {totals['fat_g']:.1f} g", "估算值"],
            ],
            columns=["項目", "今日進度", "剩餘"],
        ),
        use_container_width=True,
        hide_index=True,
    )

    for item in coach_feedback(totals, profile):
        st.info(item)

    with st.form("chat_food_form"):
        text = st.text_area(
            "用一句話記錄飲食",
            placeholder="例：午餐吃海南雞飯加一顆蛋，喝無糖拿鐵",
            height=110,
        )
        meal_type_override = st.selectbox("餐別", ["自動判斷", "早餐", "午餐", "晚餐", "點心"])
        submitted = st.form_submit_button("估算並加入今日紀錄", use_container_width=True)

    if submitted:
        cleaned = text.strip()
        if not cleaned:
            st.warning("先輸入一段飲食內容。")
        else:
            estimate = estimate_nutrition(cleaned)
            meal_type = detect_meal_type(cleaned) if meal_type_override == "自動判斷" else meal_type_override
            save_meal_log(
                {
                    "person_name": person_name,
                    "log_date": selected_date.isoformat(),
                    "meal_type": meal_type,
                    "description": cleaned,
                    "calories": estimate["calories"],
                    "protein_g": estimate["protein_g"],
                    "fiber_g": estimate["fiber_g"],
                    "carbs_g": estimate["carbs_g"],
                    "fat_g": estimate["fat_g"],
                    "confidence": estimate["confidence"],
                }
            )
            st.success(
                "已加入："
                f"{estimate['calories']} kcal，蛋白質 {estimate['protein_g']} g，"
                f"纖維 {estimate['fiber_g']} g。辨識：{estimate['matched']}。"
            )
            st.rerun()

    st.markdown("#### 今日餐食")
    if meals.empty:
        st.caption("還沒有餐食紀錄。")
    else:
        day_meals = meals[meals["log_date"].dt.date == selected_date].sort_values("id", ascending=False)
        if day_meals.empty:
            st.caption("這一天還沒有餐食紀錄。")
        else:
            for _, meal in day_meals.iterrows():
                meal_id = int(meal["id"])
                title = (
                    f"{meal['meal_type']}｜{meal['calories']} kcal｜"
                    f"{str(meal['description'])[:28]}"
                )
                with st.expander(title):
                    with st.form(f"edit_meal_{meal_id}"):
                        edited_date = st.date_input(
                            "日期",
                            value=meal["log_date"].date(),
                            key=f"meal_date_{meal_id}",
                        )
                        edited_meal_type = st.selectbox(
                            "餐別",
                            MEAL_TYPES,
                            index=MEAL_TYPES.index(meal["meal_type"])
                            if meal["meal_type"] in MEAL_TYPES
                            else 0,
                            key=f"meal_type_{meal_id}",
                        )
                        edited_description = st.text_area(
                            "內容",
                            value=meal["description"],
                            height=80,
                            key=f"meal_description_{meal_id}",
                        )
                        edited_calories = st.number_input(
                            "熱量 kcal",
                            min_value=0,
                            max_value=5000,
                            value=int(meal["calories"] or 0),
                            step=10,
                            key=f"meal_calories_{meal_id}",
                        )
                        edited_protein = st.number_input(
                            "蛋白質 g",
                            min_value=0.0,
                            max_value=300.0,
                            value=float(meal["protein_g"] or 0),
                            step=0.5,
                            key=f"meal_protein_{meal_id}",
                        )
                        edited_fiber = st.number_input(
                            "纖維 g",
                            min_value=0.0,
                            max_value=100.0,
                            value=float(meal["fiber_g"] or 0),
                            step=0.5,
                            key=f"meal_fiber_{meal_id}",
                        )
                        edited_carbs = st.number_input(
                            "碳水 g",
                            min_value=0.0,
                            max_value=500.0,
                            value=float(meal["carbs_g"] or 0),
                            step=0.5,
                            key=f"meal_carbs_{meal_id}",
                        )
                        edited_fat = st.number_input(
                            "脂肪 g",
                            min_value=0.0,
                            max_value=300.0,
                            value=float(meal["fat_g"] or 0),
                            step=0.5,
                            key=f"meal_fat_{meal_id}",
                        )
                        save_edit = st.form_submit_button("更新這筆紀錄", use_container_width=True)
                        reestimate_edit = st.form_submit_button("重新估算並更新", use_container_width=True)

                    if save_edit or reestimate_edit:
                        cleaned_description = edited_description.strip()
                        if not cleaned_description:
                            st.warning("餐食內容不能空白。")
                        else:
                            if reestimate_edit:
                                estimate = estimate_nutrition(cleaned_description)
                                update_values = {
                                    "log_date": edited_date.isoformat(),
                                    "meal_type": edited_meal_type,
                                    "description": cleaned_description,
                                    "calories": estimate["calories"],
                                    "protein_g": estimate["protein_g"],
                                    "fiber_g": estimate["fiber_g"],
                                    "carbs_g": estimate["carbs_g"],
                                    "fat_g": estimate["fat_g"],
                                    "confidence": estimate["confidence"],
                                }
                            else:
                                update_values = {
                                    "log_date": edited_date.isoformat(),
                                    "meal_type": edited_meal_type,
                                    "description": cleaned_description,
                                    "calories": edited_calories,
                                    "protein_g": edited_protein,
                                    "fiber_g": edited_fiber,
                                    "carbs_g": edited_carbs,
                                    "fat_g": edited_fat,
                                    "confidence": "手動",
                                }
                            update_meal_log(meal_id, update_values)
                            st.success("已更新。")
                            st.rerun()

                    confirm_delete = st.checkbox("確認刪除這筆", key=f"confirm_delete_meal_{meal_id}")
                    if st.button(
                        "刪除這筆紀錄",
                        key=f"delete_meal_{meal_id}",
                        disabled=not confirm_delete,
                        use_container_width=True,
                    ):
                        delete_meal_log(meal_id)
                        st.success("已刪除。")
                        st.rerun()

    st.markdown("#### 最近飲食趨勢")
    if not meals.empty:
        recent = meals[meals["log_date"] >= pd.Timestamp(date.today() - timedelta(days=13))]
        if not recent.empty:
            daily = recent.groupby("log_date", as_index=False)[
                ["calories", "protein_g", "fiber_g"]
            ].sum()
            st.line_chart(daily.set_index("log_date"), height=260)


def person_selector() -> str:
    people = [
        person
        for person in load_people()
        if person != DEFAULT_PERSON or person_has_data(person)
    ]
    with st.sidebar:
        st.markdown("### 使用者")
        if not people:
            st.info("請先新增第一位家人，再開始記錄。")
            with st.form("first_person_form"):
                first_person = st.text_input("家人名稱", placeholder="例：爸爸、媽媽、Ashley")
                submitted = st.form_submit_button("新增使用者", use_container_width=True)
            if submitted:
                cleaned = first_person.strip()
                if not cleaned:
                    st.warning("請輸入名稱。")
                elif cleaned == DEFAULT_PERSON:
                    st.warning("請輸入實際名字或稱呼，避免大家都用「我」。")
                else:
                    add_person(cleaned)
                    st.success(f"已新增 {cleaned}。")
                    st.rerun()
            st.stop()

        selected = st.selectbox("目前記錄", people)
        with st.expander("新增家人"):
            with st.form("add_person_form"):
                new_person = st.text_input("名稱", placeholder="例：爸爸、媽媽")
                submitted = st.form_submit_button("新增", use_container_width=True)
            if submitted:
                cleaned = new_person.strip()
                if not cleaned:
                    st.warning("請輸入名稱。")
                elif cleaned == DEFAULT_PERSON:
                    st.warning("請輸入實際名字或稱呼，避免大家都用「我」。")
                else:
                    add_person(cleaned)
                    st.success(f"已新增 {cleaned}。")
                    st.rerun()
    return selected


def admin_panel() -> str | None:
    st.sidebar.markdown("### 管理")
    mode = st.sidebar.radio(
        "管理模式",
        ["查看使用者", "管理使用者"],
        label_visibility="collapsed",
    )
    people = [
        person
        for person in load_people()
        if person != DEFAULT_PERSON or person_has_data(person)
    ]

    if mode == "管理使用者":
        st.title("管理員後台")
        overview = user_overview()
        if overview.empty:
            st.info("目前還沒有使用者資料。")
        else:
            st.dataframe(overview, use_container_width=True, hide_index=True)

        st.markdown("#### 重設密碼")
        with st.form("admin_reset_password_form"):
            reset_user = st.selectbox("使用者", people, key="reset_user") if people else ""
            reset_password = st.text_input("新密碼", type="password")
            reset_submitted = st.form_submit_button("重設密碼", use_container_width=True)
        if reset_submitted:
            if not reset_user:
                st.warning("目前沒有可重設的使用者。")
            elif len(reset_password) < 4:
                st.warning("密碼至少需要 4 個字元。")
            else:
                set_account_password(reset_user, reset_password)
                st.success(f"已重設 {reset_user} 的密碼。")

        st.markdown("#### 刪除使用者")
        with st.form("admin_delete_user_form"):
            delete_user = st.selectbox("使用者", people, key="delete_user") if people else ""
            confirm_name = st.text_input("輸入使用者名稱確認刪除")
            delete_submitted = st.form_submit_button("刪除使用者與所有資料", use_container_width=True)
        if delete_submitted:
            if not delete_user:
                st.warning("目前沒有可刪除的使用者。")
            elif confirm_name != delete_user:
                st.warning("確認名稱不一致，未刪除。")
            else:
                delete_person_data(delete_user)
                st.success(f"已刪除 {delete_user} 與所有資料。")
                st.rerun()
        st.stop()

    if not people:
        st.info("目前還沒有使用者資料。")
        st.stop()
    return st.sidebar.selectbox("查看使用者", people)


def app() -> None:
    st.set_page_config(page_title="個人健康管理", layout="centered")
    apply_ui_style()
    authenticated_person = require_login()
    init_db()
    if st.session_state.get("is_admin"):
        selected_person = admin_panel()
    elif authenticated_person:
        add_person(authenticated_person)
        selected_person = authenticated_person
    else:
        selected_person = person_selector()

    st.title("家庭健康管理")
    st.caption(f"目前使用者：{selected_person}")

    df = load_logs(selected_person)
    metric_cards(df)

    st.markdown(
        f"目標：{PROFILE['target_weight_kg']} kg，體脂 "
        f"{PROFILE['target_body_fat_min']}-{PROFILE['target_body_fat_max']}%。"
    )

    tab_coach, tab_daily, tab_trends, tab_weekly = st.tabs(
        ["AI飲食教練", "每日輸入", "趨勢圖表", "每週報告"]
    )
    with tab_coach:
        coach_page(load_logs(selected_person), selected_person)
    with tab_daily:
        daily_input_page(selected_person)
    with tab_trends:
        trend_page(load_logs(selected_person))
    with tab_weekly:
        weekly_report_page(load_logs(selected_person), selected_person)


if __name__ == "__main__":
    app()
