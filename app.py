from __future__ import annotations

import base64
import hmac
import hashlib
import inspect
import json
import os
import sqlite3
import secrets
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import extra_streamlit_components as stx
import streamlit as st

import ai as meal_ai
from db import DB_PATH, DATA_DIR, connect, table_columns
from meals import (
    coach_feedback,
    daily_meal_totals,
    delete_meal_log,
    load_meals,
    save_meal_log,
    update_meal_log,
)


# Imports / Config

MEAL_TYPES = getattr(meal_ai, "MEAL_TYPES", ["早餐", "午餐", "晚餐", "點心"])
analyze_meal_photo = meal_ai.analyze_meal_photo
analyze_meal_text = meal_ai.analyze_meal_text
detect_meal_type = meal_ai.detect_meal_type
estimate_nutrition = meal_ai.estimate_nutrition
get_openai_api_key = meal_ai.get_openai_api_key


def _missing_ai_feature(feature_name: str):
    def fallback(*_args, **_kwargs):
        raise RuntimeError(f"AI 模組尚未提供 {feature_name}，請重新部署最新版本後再試。")

    return fallback


analyze_pre_meal_photo = getattr(
    meal_ai,
    "analyze_pre_meal_photo",
    _missing_ai_feature("餐前圖片分析"),
)
analyze_pre_meal_text = getattr(
    meal_ai,
    "analyze_pre_meal_text",
    _missing_ai_feature("餐前文字分析"),
)

DEFAULT_PERSON = "我"
APP_VERSION = "Ver. PGY90-G1-260620-0932-R14"
APP_TIMEZONE = ZoneInfo("Asia/Kuala_Lumpur")
UTC_TIMEZONE = ZoneInfo("UTC")
REMEMBER_COOKIE_NAME = "pgy90_family_remember"
REMEMBER_DAYS = 30
REMEMBER_DISABLED_KEY = "remember_login_disabled"
REMEMBER_CLEAR_PENDING_KEY = "remember_cookie_clear_pending"
REGISTRATION_SUCCESS_KEY = "registration_success_message"


def get_local_today() -> date:
    return datetime.now(APP_TIMEZONE).date()


def prepare_local_date_input_state(date_key: str) -> date:
    local_today = get_local_today()
    today_state_key = f"{date_key}_local_today"

    if today_state_key not in st.session_state:
        st.session_state[today_state_key] = local_today
    if date_key not in st.session_state:
        st.session_state[date_key] = local_today

    previous_today = st.session_state[today_state_key]
    if previous_today != local_today:
        if st.session_state.get(date_key) == previous_today:
            st.session_state[date_key] = local_today
        st.session_state[today_state_key] = local_today

    return local_today


# Constants / Defaults

PROFILE = {
    "height_cm": 181,
    "target_weight_kg": 75,
    "target_body_fat_min": 13,
    "target_body_fat_max": 15,
}

FOOD_CATEGORIES = ["均衡", "高蛋白", "外食", "應酬", "偏清淡", "偏油/甜", "其他"]
WORKOUT_TYPES = [
    "休息 Rest",
    "重訓 Strength Training",
    "有氧 Cardio",
    "飛輪 Spinning",
    "乒乓 Table Tennis",
    "步行 Walking",
    "伸展 Mobility",
    "復健 Rehab",
    "其他 Other",
]
WORKOUT_TYPE_LABELS = {
    "休息": "休息 Rest",
    "重訓": "重訓 Strength Training",
    "有氧": "有氧 Cardio",
    "球類": "乒乓 Table Tennis",
    "步行": "步行 Walking",
    "伸展": "伸展 Mobility",
    "復健": "復健 Rehab",
    "其他": "其他 Other",
}
REHAB_TYPES = ["肩頸", "下背", "髖/腿", "膝蓋", "足踝", "全身活動度", "其他"]
GOALS = ["減脂", "增肌", "維持"]
BODY_SHAPE_GOALS = ["健康減脂", "精實有線條", "增肌維持"]
GENDERS = ["男", "女", "不指定"]
ACTIVITY_LEVELS = ["低活動", "一般活動", "較高活動"]
PRE_MEAL_IMAGE_MAX_MB = 8
ACTIVITY_CALORIE_MULTIPLIERS = {
    "低活動": 28,
    "一般活動": 31,
    "較高活動": 34,
}

RESERVED_SECRET_NAMES = {
    "APP_PASSWORD",
    "INVITE_CODE",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "REMEMBER_LOGIN_SECRET",
}

DAILY_LOG_MIGRATIONS = {
    "systolic_bp": "INTEGER",
    "diastolic_bp": "INTEGER",
    "pulse_bpm": "INTEGER",
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


# Authentication and secrets

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
    return {
        str(username): str(password)
        for username, password in dict(users).items()
        if str(username) not in RESERVED_SECRET_NAMES
    }


def get_admin_passwords() -> dict[str, str]:
    try:
        admins = st.secrets.get("admins", {})
    except Exception:
        admins = {}
    if not admins:
        return {}
    return {
        str(username): str(password)
        for username, password in dict(admins).items()
        if str(username) not in RESERVED_SECRET_NAMES
    }


def get_remember_login_secret() -> str:
    try:
        cookie_secret = st.secrets.get("REMEMBER_LOGIN_SECRET", "")
    except Exception:
        cookie_secret = ""
    if cookie_secret:
        return str(cookie_secret)
    env_secret = os.environ.get("REMEMBER_LOGIN_SECRET", "")
    if env_secret:
        return env_secret
    secret_parts = [
        get_app_password(),
        get_invite_code(),
        *get_admin_passwords().values(),
        *get_user_passwords().values(),
    ]
    combined = "|".join(part for part in secret_parts if part)
    return combined or "pgy90-family-local-remember-login"


def sign_remember_payload(payload: str) -> str:
    secret_key = get_remember_login_secret().encode("utf-8")
    return hmac.new(secret_key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def make_remember_token(person_name: str, is_admin: bool) -> str:
    expires_at = int((datetime.now(UTC_TIMEZONE) + timedelta(days=REMEMBER_DAYS)).timestamp())
    payload = f"{person_name}|{1 if is_admin else 0}|{expires_at}"
    encoded_payload = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{encoded_payload}.{sign_remember_payload(payload)}"


def parse_remember_token(token: str) -> tuple[str, bool] | None:
    parts = str(token or "").split(".", 1)
    if len(parts) != 2:
        return None
    encoded_payload, signature = parts
    padding = "=" * (-len(encoded_payload) % 4)
    try:
        payload = base64.urlsafe_b64decode(f"{encoded_payload}{padding}").decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if not hmac.compare_digest(signature, sign_remember_payload(payload)):
        return None
    payload_parts = payload.split("|")
    if len(payload_parts) != 3:
        return None
    person_name, is_admin_value, expires_at_value = payload_parts
    try:
        expires_at = int(expires_at_value)
    except ValueError:
        return None
    if datetime.now(UTC_TIMEZONE).timestamp() > expires_at:
        return None
    return person_name, is_admin_value == "1"


def remember_user_exists(person_name: str, is_admin: bool) -> bool:
    if is_admin:
        return person_name in get_admin_passwords()
    return (
        person_name in registered_usernames()
        or person_name in get_user_passwords()
        or bool(get_app_password())
    )


def get_cookie_manager():
    return stx.CookieManager(key="remember_cookie_manager")


def get_remember_cookie() -> str:
    cookie_manager = get_cookie_manager()
    token = cookie_manager.get(cookie=REMEMBER_COOKIE_NAME)
    if token:
        return str(token)
    return str(st.context.cookies.get(REMEMBER_COOKIE_NAME, ""))


def apply_remembered_login() -> None:
    if st.session_state.get("authenticated"):
        return
    if st.session_state.get(REMEMBER_DISABLED_KEY):
        return
    token = get_remember_cookie()
    remembered = parse_remember_token(token)
    if remembered is None:
        return
    person_name, is_admin = remembered
    if not remember_user_exists(person_name, is_admin):
        return
    st.session_state["authenticated"] = True
    st.session_state["authenticated_person"] = person_name
    st.session_state["is_admin"] = is_admin


def set_remember_cookie(token: str) -> None:
    get_cookie_manager().set(
        cookie=REMEMBER_COOKIE_NAME,
        val=token,
        expires_at=datetime.now(UTC_TIMEZONE) + timedelta(days=REMEMBER_DAYS),
    )


def clear_remember_cookie() -> None:
    get_cookie_manager().delete(cookie=REMEMBER_COOKIE_NAME)


def request_logout() -> None:
    st.session_state["authenticated"] = False
    st.session_state[REMEMBER_DISABLED_KEY] = True
    st.session_state[REMEMBER_CLEAR_PENDING_KEY] = True
    st.session_state.pop("authenticated_person", None)
    st.session_state.pop("is_admin", None)
    st.session_state.pop("remember_token_to_set", None)


def finish_login(person_name: str | None, is_admin: bool, remember_me: bool) -> None:
    st.session_state["authenticated"] = True
    st.session_state["is_admin"] = is_admin
    st.session_state.pop(REMEMBER_DISABLED_KEY, None)
    if person_name:
        st.session_state["authenticated_person"] = person_name
    if remember_me and person_name:
        st.session_state["remember_token_to_set"] = make_remember_token(person_name, is_admin)
    st.rerun()


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

    if st.session_state.pop(REMEMBER_CLEAR_PENDING_KEY, False):
        clear_remember_cookie()

    apply_remembered_login()

    if st.session_state.get("authenticated"):
        remember_token = st.session_state.pop("remember_token_to_set", None)
        if remember_token:
            set_remember_cookie(remember_token)
        with st.sidebar:
            current_user = st.session_state.get("authenticated_person")
            if current_user:
                st.markdown(f"### {current_user}")
            if st.session_state.get("is_admin"):
                st.caption("管理員模式")
            st.button("登出", use_container_width=True, on_click=request_logout)
        return st.session_state.get("authenticated_person")

    st.title("家庭健康管理")
    st.caption("請先登入。")
    registration_success = st.session_state.pop(REGISTRATION_SUCCESS_KEY, None)
    if registration_success:
        st.success(registration_success)
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
            remember_me = st.checkbox(f"記住我 {REMEMBER_DAYS} 天", value=True)
            submitted = st.form_submit_button("登入", use_container_width=True)

        if submitted:
            if selected_user in admin_passwords and hmac.compare_digest(
                entered_password,
                admin_passwords.get(selected_user, ""),
            ):
                finish_login(selected_user, True, remember_me)
            elif selected_user and verify_account(selected_user, entered_password):
                add_person(selected_user or "")
                finish_login(selected_user, False, remember_me)
            elif user_passwords:
                expected_password = user_passwords.get(selected_user or "", "")
                if hmac.compare_digest(entered_password, expected_password):
                    add_person(selected_user or "")
                    finish_login(selected_user, False, remember_me)
                else:
                    st.error("使用者或密碼不正確。")
            elif password and hmac.compare_digest(entered_password, password):
                finish_login(DEFAULT_PERSON, False, remember_me)
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
                    st.session_state[REGISTRATION_SUCCESS_KEY] = "帳號已建立，現在可以登入。"
                    st.rerun()
    st.stop()


# Schema migration

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
                systolic_bp INTEGER,
                diastolic_bp INTEGER,
                pulse_bpm INTEGER,
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
            height_cm REAL,
            target_weight_kg REAL,
            target_body_fat_min REAL,
            target_body_fat_max REAL,
            current_weight_kg REAL,
            gender TEXT,
            birth_year INTEGER,
            activity_level TEXT,
            daily_calorie_target INTEGER,
            protein_target_g INTEGER,
            fiber_target_g INTEGER,
            preferences TEXT,
            health_limitations TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    coach_profile_columns = table_columns(conn, "coach_profiles")
    if "height_cm" not in coach_profile_columns:
        conn.execute("ALTER TABLE coach_profiles ADD COLUMN height_cm REAL")
    if "target_weight_kg" not in coach_profile_columns:
        conn.execute("ALTER TABLE coach_profiles ADD COLUMN target_weight_kg REAL")
    if "target_body_fat_min" not in coach_profile_columns:
        conn.execute("ALTER TABLE coach_profiles ADD COLUMN target_body_fat_min REAL")
    if "target_body_fat_max" not in coach_profile_columns:
        conn.execute("ALTER TABLE coach_profiles ADD COLUMN target_body_fat_max REAL")
    if "gender" not in coach_profile_columns:
        conn.execute("ALTER TABLE coach_profiles ADD COLUMN gender TEXT")
    if "birth_year" not in coach_profile_columns:
        conn.execute("ALTER TABLE coach_profiles ADD COLUMN birth_year INTEGER")
    if "activity_level" not in coach_profile_columns:
        conn.execute("ALTER TABLE coach_profiles ADD COLUMN activity_level TEXT")
    if "health_limitations" not in coach_profile_columns:
        conn.execute("ALTER TABLE coach_profiles ADD COLUMN health_limitations TEXT")

    old_profile = conn.execute("SELECT * FROM coach_profile WHERE id = 1").fetchone()
    if old_profile:
        conn.execute(
            """
            INSERT OR IGNORE INTO coach_profiles (
                person_name, goal, height_cm, target_weight_kg, target_body_fat_min,
                target_body_fat_max, current_weight_kg, daily_calorie_target,
                protein_target_g, fiber_target_g, preferences, health_limitations,
                gender, activity_level, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                DEFAULT_PERSON,
                old_profile["goal"],
                PROFILE["height_cm"],
                PROFILE["target_weight_kg"],
                PROFILE["target_body_fat_min"],
                PROFILE["target_body_fat_max"],
                old_profile["current_weight_kg"],
                old_profile["daily_calorie_target"],
                old_profile["protein_target_g"],
                old_profile["fiber_target_g"],
                old_profile["preferences"],
                "",
                "不指定",
                "一般活動",
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
                systolic_bp INTEGER,
                diastolic_bp INTEGER,
                pulse_bpm INTEGER,
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


# User / profile functions and daily health logs

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
                    systolic_bp = :systolic_bp,
                    diastolic_bp = :diastolic_bp,
                    pulse_bpm = :pulse_bpm,
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
                    systolic_bp, diastolic_bp, pulse_bpm,
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
                    :systolic_bp, :diastolic_bp, :pulse_bpm,
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
    height_cm = get_person_height_cm(person_name)
    with connect() as conn:
        df = pd.read_sql_query(
            "SELECT * FROM daily_logs WHERE person_name = ? ORDER BY log_date",
            conn,
            params=(person_name,),
            parse_dates=["log_date"],
        )
    if not df.empty:
        df["bmi"] = df["weight_kg"] / ((height_cm / 100) ** 2)
    return df


def get_coach_profile(person_name: str) -> sqlite3.Row | None:
    with connect() as conn:
        return conn.execute(
            "SELECT * FROM coach_profiles WHERE person_name = ?",
            (person_name,),
        ).fetchone()


def get_person_height_cm(person_name: str) -> float:
    profile = get_coach_profile(person_name)
    if profile is None:
        return float(PROFILE["height_cm"])
    return float(profile["height_cm"] or PROFILE["height_cm"])


def get_person_targets(person_name: str) -> dict[str, float]:
    profile = get_coach_profile(person_name)
    if profile is None:
        return {
            "target_weight_kg": float(PROFILE["target_weight_kg"]),
            "target_body_fat_min": float(PROFILE["target_body_fat_min"]),
            "target_body_fat_max": float(PROFILE["target_body_fat_max"]),
        }
    return {
        "target_weight_kg": float(profile["target_weight_kg"] or PROFILE["target_weight_kg"]),
        "target_body_fat_min": float(profile["target_body_fat_min"] or PROFILE["target_body_fat_min"]),
        "target_body_fat_max": float(profile["target_body_fat_max"] or PROFILE["target_body_fat_max"]),
    }


def save_coach_profile(person_name: str, values: dict) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO coach_profiles (
                person_name, goal, height_cm, target_weight_kg, target_body_fat_min,
                target_body_fat_max, current_weight_kg, daily_calorie_target,
                protein_target_g, fiber_target_g, preferences, gender, birth_year,
                activity_level, health_limitations, updated_at
            ) VALUES (:person_name, :goal, :height_cm, :target_weight_kg, :target_body_fat_min,
                :target_body_fat_max, :current_weight_kg, :daily_calorie_target,
                :protein_target_g, :fiber_target_g, :preferences, :gender, :birth_year,
                :activity_level, :health_limitations, :updated_at)
            ON CONFLICT(person_name) DO UPDATE SET
                goal = excluded.goal,
                height_cm = excluded.height_cm,
                target_weight_kg = excluded.target_weight_kg,
                target_body_fat_min = excluded.target_body_fat_min,
                target_body_fat_max = excluded.target_body_fat_max,
                current_weight_kg = excluded.current_weight_kg,
                daily_calorie_target = excluded.daily_calorie_target,
                protein_target_g = excluded.protein_target_g,
                fiber_target_g = excluded.fiber_target_g,
                preferences = excluded.preferences,
                gender = excluded.gender,
                birth_year = excluded.birth_year,
                activity_level = excluded.activity_level,
                health_limitations = excluded.health_limitations,
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


def latest_weight_from_logs(df: pd.DataFrame) -> float | None:
    if df.empty or "weight_kg" not in df:
        return None
    weights = df.dropna(subset=["weight_kg"]).sort_values("log_date")
    if weights.empty:
        return None
    return float(weights.iloc[-1]["weight_kg"])


def average_weight_last_days(df: pd.DataFrame, days: int = 7) -> float | None:
    if df.empty or "weight_kg" not in df or "log_date" not in df:
        return None
    cutoff = pd.Timestamp(get_local_today() - timedelta(days=days - 1))
    recent = df[df["log_date"] >= cutoff].dropna(subset=["weight_kg"])
    if recent.empty:
        return None
    return float(recent["weight_kg"].mean())


def maintenance_calories(weight_kg: float, activity_level: str) -> int:
    multiplier = ACTIVITY_CALORIE_MULTIPLIERS.get(activity_level, ACTIVITY_CALORIE_MULTIPLIERS["一般活動"])
    return int(round(weight_kg * multiplier))


def default_targets(weight_kg: float, goal: str, activity_level: str = "一般活動") -> tuple[int, int, int]:
    maintenance = maintenance_calories(weight_kg, activity_level)
    if goal == "減脂":
        calories = maintenance - min(int(round(maintenance * 0.15)), 500)
        protein = int(round(weight_kg * 1.8))
    elif goal == "增肌":
        calories = maintenance + min(int(round(maintenance * 0.10)), 350)
        protein = int(round(weight_kg * 1.7))
    else:
        calories = maintenance
        protein = int(round(weight_kg * 1.6))
    return max(calories, 1500), protein, 30


def recommended_body_targets(height_cm: float, body_shape_goal: str) -> dict[str, float]:
    height_m = height_cm / 100
    if body_shape_goal == "精實有線條":
        bmi_target = 21.5
        body_fat_min = 13.0
        body_fat_max = 16.0
    elif body_shape_goal == "增肌維持":
        bmi_target = 23.0
        body_fat_min = 15.0
        body_fat_max = 20.0
    else:
        bmi_target = 22.5
        body_fat_min = 15.0
        body_fat_max = 18.0

    healthy_min = 18.5 * height_m * height_m
    healthy_max = 24.9 * height_m * height_m
    target_weight = bmi_target * height_m * height_m
    target_weight = min(max(target_weight, healthy_min), healthy_max)
    return {
        "target_weight_kg": round(target_weight, 1),
        "target_body_fat_min": body_fat_min,
        "target_body_fat_max": body_fat_max,
        "healthy_weight_min": round(healthy_min, 1),
        "healthy_weight_max": round(healthy_max, 1),
    }


def build_meal_ai_context(
    person_name: str,
    profile: sqlite3.Row | None,
    current_weight: float,
    targets: dict[str, float],
    nutrition_targets: dict[str, float],
    totals: dict,
) -> dict:
    preferences = profile["preferences"] if profile else ""
    health_limitations = profile["health_limitations"] if profile else ""
    goal = profile["goal"] if profile else "減脂"
    return {
        "person_name": person_name,
        "gender": profile["gender"] if profile and profile["gender"] else "不指定",
        "birth_year": profile["birth_year"] if profile and profile["birth_year"] else "",
        "activity_level": profile["activity_level"] if profile and profile["activity_level"] else "一般活動",
        "goal": goal,
        "height_cm": round(float(get_person_height_cm(person_name)), 1),
        "current_weight_kg": round(float(current_weight), 1),
        "target_weight_kg": round(float(targets["target_weight_kg"]), 1),
        "target_body_fat_range": (
            f"{compact_number(targets['target_body_fat_min'])}-"
            f"{compact_number(targets['target_body_fat_max'])}%"
        ),
        "daily_calorie_target": int(nutrition_targets["calories"]),
        "protein_target_g": round(float(nutrition_targets["protein_g"]), 1),
        "fiber_target_g": round(float(nutrition_targets["fiber_g"]), 1),
        "today_calories": int(totals["calories"]),
        "today_protein_g": round(float(totals["protein_g"]), 1),
        "today_fiber_g": round(float(totals["fiber_g"]), 1),
        "today_carbs_g": round(float(totals["carbs_g"]), 1),
        "today_fat_g": round(float(totals["fat_g"]), 1),
        "remaining_calories": int(nutrition_targets["calories"] - totals["calories"]),
        "remaining_protein_g": round(float(nutrition_targets["protein_g"] - totals["protein_g"]), 1),
        "remaining_fiber_g": round(float(nutrition_targets["fiber_g"] - totals["fiber_g"]), 1),
        "preferences": preferences,
        "health_limitations": health_limitations,
    }


def build_today_meal_status_context(
    meals: pd.DataFrame,
    selected_date: date,
    totals: dict,
    nutrition_targets: dict[str, float],
) -> dict:
    if meals.empty:
        day_meals = meals
    else:
        day_meals = meals[meals["log_date"].dt.date == selected_date]

    meal_counts = {meal_type: 0 for meal_type in MEAL_TYPES}
    if not day_meals.empty:
        for meal_type, count in day_meals["meal_type"].fillna("").value_counts().items():
            if meal_type in meal_counts:
                meal_counts[str(meal_type)] = int(count)

    breakfast_count = meal_counts["早餐"]
    lunch_count = meal_counts["午餐"]
    dinner_count = meal_counts["晚餐"]
    snack_count = meal_counts["點心"]
    total_meals_count = int(sum(meal_counts.values()))
    has_three_meals = breakfast_count > 0 and lunch_count > 0 and dinner_count > 0
    has_multiple_snacks = snack_count >= 2

    target_calories = float(nutrition_targets["calories"] or 0)
    remaining_calories = target_calories - float(totals["calories"])
    is_calorie_near_target = target_calories > 0 and remaining_calories <= max(200, target_calories * 0.10)
    is_calorie_over_target = target_calories > 0 and remaining_calories < 0
    is_fat_high = target_calories > 0 and float(totals["fat_g"]) * 9 >= target_calories * 0.35

    wind_down_reasons = []
    if has_three_meals:
        wind_down_reasons.append("今日三餐已完整")
    if has_three_meals and snack_count >= 1:
        wind_down_reasons.append("三餐完整且已有點心")
    if has_multiple_snacks:
        wind_down_reasons.append("點心已達 2 次以上")
    if is_calorie_near_target and not is_calorie_over_target:
        wind_down_reasons.append("今日熱量已接近目標")
    if is_calorie_over_target:
        wind_down_reasons.append("今日熱量已超過目標")
    if is_fat_high:
        wind_down_reasons.append("今日脂肪比例偏高")

    is_wind_down_mode = bool(
        has_three_meals
        or (has_three_meals and snack_count >= 1)
        or (has_three_meals and is_calorie_near_target)
        or is_calorie_over_target
        or is_fat_high
    )

    return {
        "total_meals_count": total_meals_count,
        "breakfast_count": breakfast_count,
        "lunch_count": lunch_count,
        "dinner_count": dinner_count,
        "snack_count": snack_count,
        "has_breakfast": breakfast_count > 0,
        "has_lunch": lunch_count > 0,
        "has_dinner": dinner_count > 0,
        "has_three_meals": has_three_meals,
        "has_multiple_snacks": has_multiple_snacks,
        "is_calorie_near_target": is_calorie_near_target,
        "is_calorie_over_target": is_calorie_over_target,
        "is_fat_high": is_fat_high,
        "is_wind_down_mode": is_wind_down_mode,
        "wind_down_reasons": "、".join(wind_down_reasons),
    }


def extract_post_meal_draft_from_pre_meal_analysis(analysis_text: str) -> str:
    fields = {
        "主食": "",
        "蛋白質": "",
        "蔬菜 / 纖維": "",
        "湯 / 飲料": "",
        "醬料 / 油脂": "",
    }
    in_suggestion_section = False

    for raw_line in analysis_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        heading = line.lstrip("#").strip()
        if heading == "建議吃法":
            in_suggestion_section = True
            continue
        if in_suggestion_section and line.startswith("#"):
            break
        if not in_suggestion_section:
            continue

        cleaned = line.lstrip("*-0123456789. ").strip().strip("*")
        if "：" in cleaned:
            label, value = cleaned.split("：", 1)
        elif ":" in cleaned:
            label, value = cleaned.split(":", 1)
        else:
            continue
        normalized_label = label.strip().replace("／", "/").replace(" ", "")
        for field in fields:
            if normalized_label.startswith(field.replace(" ", "")):
                fields[field] = value.strip()
                break

    parsed_any = any(fields.values())
    lines = ["今天實際吃了："]
    lines.extend(f"{field}：{value}" for field, value in fields.items())
    if parsed_any:
        lines.append("備註：由餐前分析轉入，請依實際吃的內容修改後再估算。")
    else:
        summary_lines = []
        for raw_line in analysis_text.splitlines():
            line = raw_line.strip().lstrip("#").strip()
            if line:
                summary_lines.append(line)
            if len(summary_lines) >= 6:
                break
        summary = " / ".join(summary_lines)
        lines.append(
            "備註：由餐前分析轉入，但未能完整解析建議吃法；"
            "請依實際吃的內容修改後再估算。"
        )
        if summary:
            lines.append(f"餐前分析摘要：{summary}")
    return "\n".join(lines)


def remember_meal_ai_notes(person_name: str, selected_date: date, estimate: dict) -> None:
    notes = {
        key: estimate[key]
        for key in ("coach_note", "next_meal_suggestion", "warning_note")
        if estimate.get(key)
    }
    if notes:
        st.session_state[f"latest_meal_ai_notes_{person_name}"] = {
            "log_date": selected_date.isoformat(),
            "notes": notes,
        }


def show_latest_meal_ai_notes(person_name: str, selected_date: date) -> None:
    latest = st.session_state.get(f"latest_meal_ai_notes_{person_name}")
    if not latest or latest.get("log_date") != selected_date.isoformat():
        return
    notes = latest.get("notes") or {}
    if notes:
        st.markdown("#### 剛剛這餐的 AI 建議")
        for note in notes.values():
            st.info(note)


def analyze_meal_text_with_context(description: str, meal_type_override: str, coach_context: dict) -> dict:
    if "coach_context" in inspect.signature(analyze_meal_text).parameters:
        return analyze_meal_text(description, meal_type_override, coach_context)
    return analyze_meal_text(description, meal_type_override)


def analyze_meal_photo_with_context(
    image_bytes: bytes,
    mime_type: str,
    meal_type_override: str,
    coach_context: dict,
) -> dict:
    if "coach_context" in inspect.signature(analyze_meal_photo).parameters:
        return analyze_meal_photo(image_bytes, mime_type, meal_type_override, coach_context)
    return analyze_meal_photo(image_bytes, mime_type, meal_type_override)


# Reports

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


# UI helpers

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


def generate_weekly_summary(week_df: pd.DataFrame, window: WeekWindow, targets: dict[str, float]) -> str:
    def latest_note(column: str) -> str:
        if week_df.empty or column not in week_df.columns:
            return ""
        for _, row in week_df.sort_values("log_date", ascending=False).iterrows():
            note = str(row.get(column) or "").strip()
            if note:
                return note[:80] + ("..." if len(note) > 80 else "")
        return ""

    if week_df.empty:
        return "\n".join(
            [
                f"週期：{window.start.isoformat()} 至 {window.end.isoformat()}",
                "",
                "本週健康摘要：",
                "- 本週記錄 0 天。",
                "- 本週身體指標資料不足。",
                "- 本週睡眠資料不足。",
                "- 本週血壓 / 脈搏資料不足。",
                "- 本週運動資料不足。",
                "- 本週復健 / 活動度訓練資料不足。",
                "- 疼痛 / 疲勞紀錄：無。",
                "",
                "下週留意：",
                "- 繼續穩定記錄體重、睡眠、血壓與運動。",
                "- 若睡眠不足或疲勞增加，運動強度可先保守。",
                "- 若疼痛或不適持續，請以安全與專業建議為優先。",
                "",
                "本週總結僅作健康管理追蹤，不作醫療診斷。",
            ]
        )

    recorded_days = len(week_df)
    summary_lines = [f"- 本週記錄 {recorded_days} 天。"]

    weights = week_df[["log_date", "weight_kg"]].copy() if "weight_kg" in week_df.columns else pd.DataFrame()
    if not weights.empty:
        weights["weight_kg"] = pd.to_numeric(weights["weight_kg"], errors="coerce")
        weights = weights[weights["weight_kg"] > 0].dropna(subset=["weight_kg"]).sort_values("log_date")
    body_fat = positive_numeric_series(week_df, "body_fat_percent")
    if weights.empty and body_fat.empty:
        summary_lines.append("- 本週身體指標資料不足。")
    else:
        latest_weight = compact_number(float(weights.iloc[-1]["weight_kg"])) if not weights.empty else "-"
        avg_body_fat = compact_number(body_fat.mean()) if not body_fat.empty else "-"
        summary_lines.append(f"- 最新體重 {latest_weight} kg，平均體脂 {avg_body_fat}%。")

    sleep_hours = positive_numeric_series(week_df, "sleep_hours")
    sleep_quality = positive_numeric_series(week_df, "sleep_quality")
    if sleep_hours.empty and sleep_quality.empty:
        summary_lines.append("- 本週睡眠資料不足。")
    else:
        summary_lines.append(
            f"- 平均睡眠 {compact_number(sleep_hours.mean())} 小時，"
            f"平均睡眠品質 {compact_number(sleep_quality.mean(), 0)}%。"
        )

    bp_columns = ["systolic_bp", "diastolic_bp", "pulse_bpm"]
    available_bp_columns = [column for column in bp_columns if column in week_df.columns]
    if not available_bp_columns:
        summary_lines.append("- 本週血壓 / 脈搏資料不足。")
    else:
        bp_df = week_df[["log_date", *available_bp_columns]].copy()
        for column in available_bp_columns:
            bp_df[column] = pd.to_numeric(bp_df[column], errors="coerce")
            bp_df.loc[bp_df[column] <= 0, column] = pd.NA
        bp_rows = bp_df[bp_df[available_bp_columns].notna().any(axis=1)]
        if bp_rows.empty:
            summary_lines.append("- 本週血壓 / 脈搏資料不足。")
        else:
            avg_systolic = compact_number(bp_df.get("systolic_bp", pd.Series(dtype="float64")).mean(), 0)
            avg_diastolic = compact_number(bp_df.get("diastolic_bp", pd.Series(dtype="float64")).mean(), 0)
            avg_pulse = compact_number(bp_df.get("pulse_bpm", pd.Series(dtype="float64")).mean(), 0)
            summary_lines.append(
                f"- 本週有 {len(bp_rows)} 天血壓 / 脈搏紀錄，"
                f"平均約 {avg_systolic} / {avg_diastolic} mmHg，平均脈搏 {avg_pulse} bpm。"
            )

    workout_minutes = positive_numeric_series(week_df, "workout_minutes")
    if workout_minutes.empty:
        summary_lines.append("- 本週運動資料不足。")
    else:
        workout_df = week_df.copy()
        workout_df["workout_minutes"] = pd.to_numeric(workout_df["workout_minutes"], errors="coerce")
        valid_workouts = workout_df[workout_df["workout_minutes"] > 0]
        rpe = positive_numeric_series(valid_workouts, "rpe")
        summary_lines.append(
            f"- 本週運動 {len(valid_workouts)} 天，共 {int(workout_minutes.sum())} 分鐘，"
            f"平均 RPE {compact_number(rpe.mean())}。"
        )

    rehab_count = int(
        pd.to_numeric(
            week_df.get("rehab_done", pd.Series(dtype="float64")),
            errors="coerce",
        ).fillna(0).sum()
    )
    summary_lines.append(f"- 本週復健 / 活動度訓練 {rehab_count} 次。")

    discomfort_note = latest_note("discomfort_notes")
    if discomfort_note:
        summary_lines.append(f"- 疼痛 / 疲勞紀錄：有，最近一筆：{discomfort_note}")
    else:
        summary_lines.append("- 疼痛 / 疲勞紀錄：無。")

    return "\n".join(
        [
            f"週期：{window.start.isoformat()} 至 {window.end.isoformat()}",
            "",
            "本週健康摘要：",
            *summary_lines,
            "",
            "下週留意：",
            "- 繼續穩定記錄體重、睡眠、血壓與運動。",
            "- 若睡眠不足或疲勞增加，運動強度可先保守。",
            "- 若疼痛或不適持續，請以安全與專業建議為優先。",
            "",
            "本週總結僅作健康管理追蹤，不作醫療診斷。",
        ]
    )


def positive_numeric_series(df: pd.DataFrame, column: str) -> pd.Series:
    if df.empty or column not in df.columns:
        return pd.Series(dtype="float64")
    values = pd.to_numeric(df[column], errors="coerce")
    return values[values > 0].dropna()


def weekly_summary_table(rows: list[tuple[str, str]]) -> None:
    st.dataframe(
        pd.DataFrame(rows, columns=["項目", "本週摘要"]),
        use_container_width=True,
        hide_index=True,
    )


def render_weekly_body_summary(week_df: pd.DataFrame) -> None:
    st.markdown("### 本週身體指標摘要")
    weights = week_df[["log_date", "weight_kg"]].copy() if "weight_kg" in week_df else pd.DataFrame()
    if not weights.empty:
        weights["weight_kg"] = pd.to_numeric(weights["weight_kg"], errors="coerce")
        weights = weights[weights["weight_kg"] > 0].dropna(subset=["weight_kg"]).sort_values("log_date")

    body_fat = positive_numeric_series(week_df, "body_fat_percent")
    waist = positive_numeric_series(week_df, "waist_cm")
    if weights.empty and body_fat.empty and waist.empty:
        st.info("本週身體指標資料不足。")
        return

    first_weight = float(weights.iloc[0]["weight_kg"]) if not weights.empty else None
    latest_weight = float(weights.iloc[-1]["weight_kg"]) if not weights.empty else None
    weekly_summary_table(
        [
            ("週初體重", f"{compact_number(first_weight)} kg"),
            ("最新體重", f"{compact_number(latest_weight)} kg"),
            ("體重變化", format_delta(latest_weight, first_weight, "kg") or "-"),
            ("平均體脂", f"{compact_number(body_fat.mean())} %"),
            ("平均腰圍", f"{compact_number(waist.mean())} cm"),
        ]
    )


def render_weekly_sleep_summary(week_df: pd.DataFrame) -> None:
    st.markdown("### 本週睡眠摘要")
    sleep_hours = positive_numeric_series(week_df, "sleep_hours")
    sleep_quality = positive_numeric_series(week_df, "sleep_quality")
    if sleep_hours.empty and sleep_quality.empty:
        st.info("本週睡眠資料不足。")
        return

    low_sleep_days = int((sleep_hours < 6).sum()) if not sleep_hours.empty else 0
    weekly_summary_table(
        [
            ("有記錄睡眠天數", f"{int(sleep_hours.count())} 天"),
            ("平均睡眠時間", f"{compact_number(sleep_hours.mean())} 小時"),
            ("平均睡眠品質", f"{compact_number(sleep_quality.mean(), 0)} %"),
            ("睡眠少於 6 小時", f"{low_sleep_days} 天"),
        ]
    )
    st.caption("睡眠資料可作為恢復與訓練安排參考。")


def render_weekly_bp_summary(week_df: pd.DataFrame) -> None:
    st.markdown("### 本週血壓 / 脈搏摘要")
    bp_columns = ["systolic_bp", "diastolic_bp", "pulse_bpm"]
    available_columns = [column for column in bp_columns if column in week_df.columns]
    if week_df.empty or not available_columns:
        st.info("本週血壓 / 脈搏資料不足。")
        return

    bp_df = week_df[["log_date", *available_columns]].copy()
    for column in available_columns:
        bp_df[column] = pd.to_numeric(bp_df[column], errors="coerce")
        bp_df.loc[bp_df[column] <= 0, column] = pd.NA
    valid_rows = bp_df[bp_df[available_columns].notna().any(axis=1)].sort_values("log_date")
    if valid_rows.empty:
        st.info("本週血壓 / 脈搏資料不足。")
        return

    latest = valid_rows.iloc[-1]
    latest_bp = (
        f"{compact_number(latest.get('systolic_bp'), 0)} / "
        f"{compact_number(latest.get('diastolic_bp'), 0)} mmHg，"
        f"脈搏 {compact_number(latest.get('pulse_bpm'), 0)} bpm"
    )
    weekly_summary_table(
        [
            ("血壓 / 脈搏紀錄天數", f"{len(valid_rows)} 天"),
            ("平均收縮壓", f"{compact_number(bp_df.get('systolic_bp', pd.Series(dtype='float64')).mean(), 0)} mmHg"),
            ("平均舒張壓", f"{compact_number(bp_df.get('diastolic_bp', pd.Series(dtype='float64')).mean(), 0)} mmHg"),
            ("平均脈搏", f"{compact_number(bp_df.get('pulse_bpm', pd.Series(dtype='float64')).mean(), 0)} bpm"),
            ("最新一筆", latest_bp),
        ]
    )
    st.caption("血壓與脈搏摘要僅作健康管理追蹤，不作醫療診斷。")


def render_weekly_workout_summary(week_df: pd.DataFrame) -> None:
    st.markdown("### 本週運動 / 訓練摘要")
    workout_minutes = positive_numeric_series(week_df, "workout_minutes")
    if workout_minutes.empty:
        st.info("本週運動資料不足。")
        return

    workout_df = week_df.copy()
    workout_df["workout_minutes"] = pd.to_numeric(workout_df["workout_minutes"], errors="coerce")
    valid_workouts = workout_df[workout_df["workout_minutes"] > 0]
    workout_counts = valid_workouts["workout_type"].dropna().replace("", pd.NA).dropna().value_counts()
    main_workout = workout_counts.index[0] if not workout_counts.empty else "-"
    rpe = positive_numeric_series(valid_workouts, "rpe")
    active_calories = positive_numeric_series(valid_workouts, "active_calories")
    distance = positive_numeric_series(valid_workouts, "distance_km")
    active_calories_text = f"{compact_number(active_calories.sum(), 0)} kcal" if not active_calories.empty else "-"
    distance_text = f"{compact_number(distance.sum())} km" if not distance.empty else "-"
    weekly_summary_table(
        [
            ("運動天數", f"{len(valid_workouts)} 天"),
            ("運動總分鐘", f"{int(workout_minutes.sum())} 分鐘"),
            ("平均 RPE", compact_number(rpe.mean())),
            ("最高 RPE", compact_number(rpe.max())),
            ("主要運動類型", str(main_workout)),
            ("活動熱量總和", active_calories_text),
            ("距離總和", distance_text),
        ]
    )


def render_weekly_rehab_fatigue_summary(week_df: pd.DataFrame) -> None:
    st.markdown("### 本週復健與疲勞摘要")
    if week_df.empty:
        st.info("本週沒有明顯復健或疲勞紀錄。")
        return

    rehab_count = int(
        pd.to_numeric(
            week_df.get("rehab_done", pd.Series(dtype="float64")),
            errors="coerce",
        ).fillna(0).sum()
    )
    note_rows = []
    for _, row in week_df.sort_values("log_date", ascending=False).iterrows():
        log_date = row["log_date"].date().isoformat() if hasattr(row["log_date"], "date") else str(row["log_date"])
        discomfort = str(row.get("discomfort_notes") or "").strip()
        rehab = str(row.get("rehab_notes") or "").strip()
        if discomfort:
            note_rows.append((log_date, "疼痛 / 疲勞", discomfort))
        if rehab:
            note_rows.append((log_date, "復健", rehab))

    if rehab_count <= 0 and not note_rows:
        st.info("本週沒有明顯復健或疲勞紀錄。")
        return

    weekly_summary_table(
        [
            ("復健 / 活動度訓練次數", f"{rehab_count} 次"),
            ("疼痛 / 疲勞文字紀錄", "有" if note_rows else "無"),
        ]
    )
    if note_rows:
        st.dataframe(
            pd.DataFrame(note_rows[:3], columns=["日期", "類型", "內容"]),
            use_container_width=True,
            hide_index=True,
        )
    st.caption("復健與疲勞摘要只整理紀錄，不作醫療診斷或專業處置建議。")


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


def metric_cards(df: pd.DataFrame, height_cm: float) -> None:
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
                ["BMI", compact_number(bmi), f"{compact_number(height_cm)} cm"],
            ],
            columns=["指標", "目前", "變化"],
        ),
        use_container_width=True,
        hide_index=True,
    )


# UI pages

def daily_input_page(person_name: str) -> None:
    st.subheader(f"{person_name}｜每日輸入")
    st.markdown("#### 日期")
    daily_date_key = f"daily_input_date_{person_name}"
    local_today = prepare_local_date_input_state(daily_date_key)
    selected_date = st.date_input("日期", key=daily_date_key)
    st.caption(f"本地日期：{local_today.strftime('%Y/%m/%d')}（Asia/Kuala_Lumpur）")
    existing = get_daily_log(person_name, selected_date)

    def existing_value(key: str, fallback):
        if existing is None or existing[key] is None:
            return fallback
        return existing[key]

    st.markdown("---")
    st.markdown("#### 身體指標")
    st.caption("有量才填，沒量可留空。")
    existing_weight = existing_value("weight_kg", None)
    weight_measured = st.checkbox(
        "今天有量體重",
        value=existing_weight is not None,
        key=f"weight_measured_{person_name}_{selected_date.isoformat()}",
    )
    weight = None
    if weight_measured:
        weight = st.number_input(
            "體重 kg",
            min_value=30.0,
            max_value=180.0,
            value=float(existing_weight if existing_weight is not None else 75.0),
            step=0.1,
            format="%.1f",
            width=120,
        )

    existing_body_fat = existing_value("body_fat_percent", None)
    body_fat_measured = st.checkbox(
        "今天有量體脂",
        value=existing_body_fat is not None,
        key=f"body_fat_measured_{person_name}_{selected_date.isoformat()}",
    )
    body_fat = None
    if body_fat_measured:
        body_fat = st.number_input(
            "體脂 %",
            min_value=3.0,
            max_value=45.0,
            value=float(existing_body_fat if existing_body_fat is not None else 15.0),
            step=0.1,
            format="%.1f",
            width=120,
        )

    existing_waist = existing_value("waist_cm", None)
    waist_measured = st.checkbox(
        "今天有量腰圍",
        value=existing_waist is not None,
        key=f"waist_measured_{person_name}_{selected_date.isoformat()}",
    )
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

    st.markdown("---")
    st.markdown("#### 血壓 / 脈搏")
    systolic_bp = st.number_input(
        "收縮壓 mmHg",
        min_value=0,
        max_value=250,
        value=int(existing_value("systolic_bp", 0)),
        step=1,
        width=120,
    )
    diastolic_bp = st.number_input(
        "舒張壓 mmHg",
        min_value=0,
        max_value=180,
        value=int(existing_value("diastolic_bp", 0)),
        step=1,
        width=120,
    )
    pulse_bpm = st.number_input(
        "脈搏 bpm",
        min_value=0,
        max_value=220,
        value=int(existing_value("pulse_bpm", 0)),
        step=1,
        width=120,
    )
    st.caption("血壓紀錄僅作健康管理追蹤，不作醫療診斷；若數值異常或有不適，請諮詢醫師。")

    st.markdown("---")
    st.markdown("#### 睡眠與恢復")
    st.caption("睡眠不足時，運動強度建議保守一點。")
    existing_sleep_hours = existing_value("sleep_hours", None)
    existing_sleep_quality = existing_value("sleep_quality", None)
    sleep_recorded = st.checkbox(
        "有記錄睡眠",
        value=existing_sleep_hours is not None or existing_sleep_quality is not None,
        key=f"sleep_recorded_{person_name}_{selected_date.isoformat()}",
    )
    sleep_hour_part = 0
    sleep_minute_part = 0
    sleep_quality = None
    if sleep_recorded:
        current_sleep_hours, current_sleep_minutes = split_sleep_time(
            existing_sleep_hours if existing_sleep_hours is not None else 7.0
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
            value=int(existing_sleep_quality if existing_sleep_quality is not None else 75),
            step=1,
        )

    st.markdown("---")
    st.markdown("#### 飲食紀錄狀態")
    st.caption("詳細餐食請在 AI 飲食教練中記錄。")
    existing_food_category = existing_value("food_category", "")
    food_recorded = st.checkbox(
        "有記錄飲食總評",
        value=bool(existing_food_category),
        key=f"food_recorded_{person_name}_{selected_date.isoformat()}",
    )
    food_category = None
    if food_recorded:
        food_category = st.selectbox(
            "當日總評",
            FOOD_CATEGORIES,
            index=FOOD_CATEGORIES.index(existing_food_category)
            if existing_food_category in FOOD_CATEGORIES
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

    with st.form("daily_log_form"):
        st.markdown("---")
        st.markdown("#### 運動 / 訓練")
        current_workout_type = existing_value("workout_type", "休息 Rest")
        workout_type_display = WORKOUT_TYPE_LABELS.get(current_workout_type, current_workout_type)
        workout_type_options = list(WORKOUT_TYPES)
        if workout_type_display not in workout_type_options:
            workout_type_options.append(workout_type_display)

        workout_type = st.selectbox(
            "運動分類 / 運動類型",
            workout_type_options,
            index=workout_type_options.index(workout_type_display),
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
        st.markdown("---")
        st.markdown("#### 疼痛、疲勞與復健")
        st.caption("若膝蓋、腰、肩或疲勞明顯，請記錄下來，之後可作為訓練調整依據。")
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
        st.markdown("---")
        st.markdown("#### 備註")
        notes = st.text_area(
            "備註",
            value=existing_value("notes", ""),
            height=80,
            placeholder="例如：今天比較累、外食較多、膝蓋微酸、精神狀態不錯。",
        )

        submitted = st.form_submit_button("儲存今日紀錄", use_container_width=True)

    if submitted:
        upsert_daily_log(
            {
                "person_name": person_name,
                "log_date": selected_date.isoformat(),
                "weight_kg": weight,
                "body_fat_percent": body_fat,
                "waist_cm": waist if waist_measured else None,
                "systolic_bp": systolic_bp or None,
                "diastolic_bp": diastolic_bp or None,
                "pulse_bpm": pulse_bpm or None,
                "sleep_hours": sleep_hour_part + (sleep_minute_part / 60)
                if sleep_recorded
                else None,
                "sleep_quality": sleep_quality if sleep_recorded else None,
                "food_category": food_category if food_recorded else None,
                "breakfast_category": breakfast_category if food_recorded else "",
                "breakfast_notes": str(breakfast_notes).strip() if food_recorded else "",
                "lunch_category": lunch_category if food_recorded else "",
                "lunch_notes": str(lunch_notes).strip() if food_recorded else "",
                "dinner_category": dinner_category if food_recorded else "",
                "dinner_notes": str(dinner_notes).strip() if food_recorded else "",
                "snack_notes": str(snack_notes).strip() if food_recorded else "",
                "food_notes": str(food_notes).strip() if food_recorded else "",
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


def trend_page(df: pd.DataFrame, height_cm: float) -> None:
    st.subheader("趨勢圖表")
    if df.empty:
        st.info("還沒有資料。先到每日輸入新增第一筆紀錄。")
        return

    metric_cards(df, height_cm)

    days = st.slider("顯示最近幾天", 7, 180, 60, step=7)
    cutoff = pd.Timestamp(get_local_today() - timedelta(days=days - 1))
    recent = df[df["log_date"] >= cutoff]

    st.line_chart(
        recent.set_index("log_date")[["weight_kg", "body_fat_percent", "waist_cm"]],
        height=320,
    )

    st.caption("睡眠")
    st.bar_chart(recent.set_index("log_date")[["sleep_hours"]], height=220)

    st.markdown("### 血壓 / 脈搏趨勢")
    bp_columns = ["systolic_bp", "diastolic_bp", "pulse_bpm"]
    available_bp_columns = [column for column in bp_columns if column in recent.columns]
    if available_bp_columns:
        bp_recent = recent[["log_date", *available_bp_columns]].copy()
        for column in available_bp_columns:
            bp_recent[column] = pd.to_numeric(bp_recent[column], errors="coerce")
            bp_recent.loc[bp_recent[column] <= 0, column] = pd.NA

        bp_has_data = {
            column: bp_recent[column].notna().any()
            for column in available_bp_columns
        }
        bp_valid_rows = bp_recent[
            bp_recent[available_bp_columns].notna().any(axis=1)
        ].sort_values("log_date", ascending=False)
        if bp_has_data.get("systolic_bp") or bp_has_data.get("diastolic_bp"):
            st.markdown("#### 血壓趨勢")
            pressure_columns = [
                column
                for column in ["systolic_bp", "diastolic_bp"]
                if bp_has_data.get(column)
            ]
            st.line_chart(bp_recent.set_index("log_date")[pressure_columns], height=240)
        if bp_has_data.get("pulse_bpm"):
            st.markdown("#### 脈搏趨勢")
            st.line_chart(bp_recent.set_index("log_date")[["pulse_bpm"]], height=220)
        if len(bp_valid_rows) == 1:
            st.info("目前已有 1 筆血壓 / 脈搏紀錄；累積更多日期後，趨勢線會更明顯。")
        if not bp_valid_rows.empty:
            st.dataframe(
                bp_valid_rows[["log_date", *available_bp_columns]].rename(
                    columns={
                        "log_date": "日期",
                        "systolic_bp": "收縮壓 mmHg",
                        "diastolic_bp": "舒張壓 mmHg",
                        "pulse_bpm": "脈搏 bpm",
                    }
                ),
                use_container_width=True,
                hide_index=True,
            )
        if not any(bp_has_data.values()):
            st.info("尚無血壓 / 脈搏紀錄。可先到「每日輸入」新增資料。")
    else:
        st.info("尚無血壓 / 脈搏紀錄。可先到「每日輸入」新增資料。")
    st.caption("血壓與脈搏趨勢僅作健康管理追蹤，不作醫療診斷。")

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
        "systolic_bp",
        "diastolic_bp",
        "pulse_bpm",
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
    weekly_date_key = f"weekly_date_{person_name}"
    prepare_local_date_input_state(weekly_date_key)
    selected = st.date_input("選擇週內任一天", key=weekly_date_key)
    window = week_window(selected)
    st.caption(f"週期：{window.start.isoformat()} 至 {window.end.isoformat()}")
    targets = get_person_targets(person_name)

    if df.empty:
        week_df = df
    else:
        week_df = df[
            (df["log_date"].dt.date >= window.start)
            & (df["log_date"].dt.date <= window.end)
        ]

    summary = generate_weekly_summary(week_df, window, targets)
    saved = get_saved_report(person_name, window)

    if st.button("產生 / 更新本週總結", use_container_width=True):
        save_weekly_report(person_name, window, summary)
        st.success("已更新本週總結。")
        st.rerun()
    if saved:
        st.info(f"已儲存：{saved['generated_at']}")
    else:
        st.warning("尚未儲存本週總結。")

    render_weekly_body_summary(week_df)
    render_weekly_sleep_summary(week_df)
    render_weekly_bp_summary(week_df)
    render_weekly_workout_summary(week_df)
    render_weekly_rehab_fatigue_summary(week_df)

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
    latest_log_weight = latest_weight_from_logs(df)
    average_week_weight = average_weight_last_days(df)
    current_weight = latest_log_weight or 75.0
    current_height = float(PROFILE["height_cm"])
    current_activity_level = "一般活動"
    targets = get_person_targets(person_name)
    default_calories, default_protein, default_fiber = default_targets(
        current_weight,
        "減脂",
        current_activity_level,
    )

    if profile is not None:
        current_goal = profile["goal"]
        current_height = float(profile["height_cm"] or current_height)
        current_weight = float(latest_log_weight or profile["current_weight_kg"] or current_weight)
        current_preferences = profile["preferences"] or ""
        current_health_limitations = profile["health_limitations"] or ""
        current_gender = profile["gender"] if profile["gender"] in GENDERS else "不指定"
        current_birth_year = str(profile["birth_year"] or "")
        current_activity_level = (
            profile["activity_level"] if profile["activity_level"] in ACTIVITY_LEVELS else "一般活動"
        )
        suggested_current_calories, suggested_current_protein, suggested_current_fiber = default_targets(
            current_weight,
            current_goal,
            current_activity_level,
        )
        default_calories = int(profile["daily_calorie_target"] or suggested_current_calories)
        default_protein = int(profile["protein_target_g"] or suggested_current_protein)
        default_fiber = int(profile["fiber_target_g"] or suggested_current_fiber)
    else:
        current_goal = "減脂"
        current_preferences = "高蛋白、少油炸、外食可執行、亞洲食物優先"
        current_health_limitations = ""
        current_gender = "不指定"
        current_birth_year = ""
        default_calories, default_protein, default_fiber = default_targets(
            current_weight,
            current_goal,
            current_activity_level,
        )

    coach_date_key = f"coach_date_{person_name}"
    prepare_local_date_input_state(coach_date_key)
    selected_date = st.date_input("記錄日期", key=coach_date_key)
    meals = load_meals(person_name)
    totals = daily_meal_totals(meals, selected_date)
    profile = get_coach_profile(person_name)

    target_calories = profile["daily_calorie_target"] if profile else default_calories
    target_protein = profile["protein_target_g"] if profile else default_protein
    target_fiber = profile["fiber_target_g"] if profile else default_fiber
    nutrition_targets = {
        "calories": target_calories,
        "protein_g": target_protein,
        "fiber_g": target_fiber,
    }
    meal_ai_context = build_meal_ai_context(
        person_name,
        profile,
        current_weight,
        targets,
        nutrition_targets,
        totals,
    )
    pre_meal_ai_context = {
        **meal_ai_context,
        **build_today_meal_status_context(meals, selected_date, totals, nutrition_targets),
    }

    st.markdown("#### 今日營養總覽")
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
    show_latest_meal_ai_notes(person_name, selected_date)

    st.markdown("#### 餐前分析")
    pre_meal_result_key = f"pre_meal_analysis_result_{person_name}"
    meal_text_input_key = f"meal_text_input_{person_name}"
    pre_text_tab, pre_photo_tab = st.tabs(["文字分析", "圖片分析"])

    with pre_text_tab:
        with st.form(f"pre_meal_text_form_{person_name}"):
            pre_meal_text = st.text_area(
                "還沒吃之前，先描述眼前選項",
                placeholder="例：我現在有雞飯、生肉麵、經濟飯可以選，今天蛋白質還不夠，怎麼吃？",
                height=100,
                key=f"pre_meal_text_input_{person_name}",
            )
            analyze_pre_text = st.form_submit_button("分析怎麼吃", use_container_width=True)

        if analyze_pre_text:
            cleaned_pre_meal_text = pre_meal_text.strip()
            if not cleaned_pre_meal_text:
                st.warning("先輸入你現在看到或想吃的選項。")
            elif not get_openai_api_key():
                st.warning("尚未設定 OPENAI_API_KEY，無法使用餐前 AI 分析。")
            else:
                try:
                    with st.spinner("正在分析這餐怎麼選..."):
                        st.session_state[pre_meal_result_key] = analyze_pre_meal_text(
                            cleaned_pre_meal_text,
                            pre_meal_ai_context,
                        )
                except RuntimeError as error:
                    st.error(str(error))

    with pre_photo_tab:
        pre_meal_photo = st.file_uploader(
            "上傳菜單、餐檯或食物選項照片",
            type=["jpg", "jpeg", "png", "webp"],
            key=f"pre_meal_photo_{person_name}",
        )
        pre_meal_photo_note = st.text_area(
            "補充說明",
            placeholder="例：我想從這幾樣裡選晚餐，今天熱量剩不多。",
            height=80,
            key=f"pre_meal_photo_note_{person_name}",
        )
        if st.button("分析照片怎麼吃", use_container_width=True, key=f"pre_meal_photo_button_{person_name}"):
            if pre_meal_photo is None:
                st.warning("先上傳一張菜單、餐檯或食物選項照片。")
            elif not get_openai_api_key():
                st.warning("尚未設定 OPENAI_API_KEY，無法使用餐前圖片分析。")
            elif pre_meal_photo.size > PRE_MEAL_IMAGE_MAX_MB * 1024 * 1024:
                st.warning(
                    f"這張圖片超過 {PRE_MEAL_IMAGE_MAX_MB} MB，請先裁切或壓縮後再上傳，"
                    "或改用文字描述餐點選項。"
                )
            else:
                try:
                    with st.spinner("正在分析照片裡的選項..."):
                        st.session_state[pre_meal_result_key] = analyze_pre_meal_photo(
                            pre_meal_photo.getvalue(),
                            pre_meal_photo.type or "image/jpeg",
                            pre_meal_ai_context,
                            pre_meal_photo_note.strip()
                            or "請根據照片中的菜單、餐檯或食物選項提供餐前建議。",
                        )
                except RuntimeError as error:
                    st.error(str(error))

    if st.session_state.get(pre_meal_result_key):
        st.markdown("#### 餐前分析結果")
        st.markdown(st.session_state[pre_meal_result_key])
        if st.button("轉入餐後紀錄草稿", use_container_width=True, key=f"pre_meal_to_post_draft_{person_name}"):
            st.session_state[meal_text_input_key] = extract_post_meal_draft_from_pre_meal_analysis(
                st.session_state[pre_meal_result_key]
            )
            st.success("已轉入餐後輸入框，請確認實際吃的內容後再估算加入紀錄。")

    text_tab, photo_tab = st.tabs(["文字輸入", "照片輸入"])

    with text_tab:
        with st.form("chat_food_form"):
            text = st.text_area(
                "用一句話記錄飲食",
                placeholder="例：午餐吃海南雞飯加一顆蛋，喝無糖拿鐵",
                height=110,
                key=meal_text_input_key,
            )
            meal_type_override = st.selectbox("餐別", ["自動判斷", "早餐", "午餐", "晚餐", "點心"])
            submitted = st.form_submit_button("估算並加入今日紀錄", use_container_width=True)

        if submitted:
            cleaned = text.strip()
            if not cleaned:
                st.warning("先輸入一段飲食內容。")
            else:
                used_ai_estimate = False
                try:
                    if get_openai_api_key():
                        with st.spinner("正在用 AI 估算文字餐食..."):
                            estimate = analyze_meal_text_with_context(cleaned, meal_type_override, meal_ai_context)
                        used_ai_estimate = True
                    else:
                        raise RuntimeError("尚未設定 OPENAI_API_KEY。")
                except (RuntimeError, json.JSONDecodeError) as error:
                    estimate = estimate_nutrition(cleaned)
                    estimate["description"] = cleaned
                    estimate["meal_type"] = (
                        detect_meal_type(cleaned)
                        if meal_type_override == "自動判斷"
                        else meal_type_override
                    )
                    st.warning(f"AI 估算未使用，已改用本機規則估算。原因：{error}")
                save_meal_log(
                    {
                        "person_name": person_name,
                        "log_date": selected_date.isoformat(),
                        "meal_type": estimate["meal_type"],
                        "description": estimate["description"],
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
                    f"纖維 {estimate['fiber_g']} g。"
                    f"{'AI ' if used_ai_estimate else ''}辨識：{estimate['matched']}。"
                )
                remember_meal_ai_notes(person_name, selected_date, estimate)
                st.rerun()

    with photo_tab:
        photo_source = st.radio("照片來源", ["上傳照片", "拍照"], horizontal=True)
        captured_photo = None
        uploaded_photo = None
        if photo_source == "上傳照片":
            uploaded_photo = st.file_uploader("上傳餐食照片", type=["jpg", "jpeg", "png", "webp"])
            st.session_state["meal_camera_enabled"] = False
        else:
            if not st.session_state.get("meal_camera_enabled"):
                if st.button("啟用相機", use_container_width=True):
                    st.session_state["meal_camera_enabled"] = True
                    st.rerun()
            if st.session_state.get("meal_camera_enabled"):
                captured_photo = st.camera_input("拍一張餐食照片")

        photo_meal_type = st.selectbox(
            "餐別",
            ["自動判斷", "早餐", "午餐", "晚餐", "點心"],
            key="photo_meal_type",
        )
        photo_file = captured_photo or uploaded_photo
        if st.button("辨識並加入今日紀錄", use_container_width=True):
            if photo_file is None:
                st.warning("先拍照或上傳一張餐食照片。")
            elif not get_openai_api_key():
                st.warning("尚未設定 OPENAI_API_KEY，請先在 Streamlit Secrets 加入 OpenAI API key。")
            else:
                try:
                    with st.spinner("正在辨識餐食照片..."):
                        estimate = analyze_meal_photo_with_context(
                            photo_file.getvalue(),
                            photo_file.type or "image/jpeg",
                            photo_meal_type,
                            meal_ai_context,
                        )
                    save_meal_log(
                        {
                            "person_name": person_name,
                            "log_date": selected_date.isoformat(),
                            "meal_type": estimate["meal_type"],
                            "description": estimate["description"],
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
                    remember_meal_ai_notes(person_name, selected_date, estimate)
                    st.rerun()
                except json.JSONDecodeError:
                    st.error("照片辨識回傳格式不完整，請換一張更清楚的照片或改用文字輸入。")
                except RuntimeError as error:
                    st.error(str(error))

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
                                try:
                                    if get_openai_api_key():
                                        with st.spinner("正在用 AI 重新估算餐食..."):
                                            estimate = analyze_meal_text_with_context(
                                                cleaned_description,
                                                edited_meal_type,
                                                meal_ai_context,
                                            )
                                    else:
                                        raise RuntimeError("尚未設定 OPENAI_API_KEY。")
                                except (RuntimeError, json.JSONDecodeError) as error:
                                    estimate = estimate_nutrition(cleaned_description)
                                    st.warning(f"AI 重新估算未使用，已改用本機規則估算。原因：{error}")
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
                            if reestimate_edit:
                                remember_meal_ai_notes(person_name, selected_date, estimate)
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
        recent = meals[meals["log_date"] >= pd.Timestamp(get_local_today() - timedelta(days=13))]
        if not recent.empty:
            daily = recent.groupby("log_date", as_index=False)[
                ["calories", "protein_g", "fiber_g"]
            ].sum()
            st.line_chart(daily.set_index("log_date"), height=260)

    with st.expander("個人目標與飲食偏好", expanded=profile is None):
        height_cm = st.number_input(
            "身高 cm",
            min_value=100.0,
            max_value=230.0,
            value=float(current_height),
            step=0.5,
            format="%.1f",
            width=120,
            key=f"profile_height_{person_name}",
        )
        body_shape_goal = st.selectbox("體態方向", BODY_SHAPE_GOALS, key=f"body_shape_goal_{person_name}")
        recommended_targets = recommended_body_targets(height_cm, body_shape_goal)
        st.caption(
            "建議："
            f"目標體重 {compact_number(recommended_targets['target_weight_kg'])} kg；"
            f"體脂 {compact_number(recommended_targets['target_body_fat_min'])}-"
            f"{compact_number(recommended_targets['target_body_fat_max'])}%；"
            f"健康體重範圍 {compact_number(recommended_targets['healthy_weight_min'])}-"
            f"{compact_number(recommended_targets['healthy_weight_max'])} kg"
        )
        if st.button("套用建議值", use_container_width=True):
            st.session_state[f"target_weight_{person_name}"] = recommended_targets["target_weight_kg"]
            st.session_state[f"target_body_fat_min_{person_name}"] = recommended_targets["target_body_fat_min"]
            st.session_state[f"target_body_fat_max_{person_name}"] = recommended_targets["target_body_fat_max"]
            st.rerun()

        with st.form("coach_profile_form"):
            gender = st.selectbox(
                "性別",
                GENDERS,
                index=GENDERS.index(current_gender),
            )
            birth_year_text = st.text_input(
                "出生年份",
                value=current_birth_year,
                max_chars=4,
                placeholder="例：1980，可留空",
            )
            activity_level = st.selectbox(
                "活動量",
                ACTIVITY_LEVELS,
                index=ACTIVITY_LEVELS.index(current_activity_level),
            )
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
            if average_week_weight is not None:
                st.caption(f"最近 7 天平均：{compact_number(average_week_weight)} kg")
            target_weight = st.number_input(
                "目標體重 kg",
                min_value=30.0,
                max_value=180.0,
                value=float(st.session_state.get(f"target_weight_{person_name}", targets["target_weight_kg"])),
                step=0.1,
                format="%.1f",
                width=120,
            )
            target_body_fat_min = st.number_input(
                "目標體脂下限 %",
                min_value=3.0,
                max_value=45.0,
                value=float(st.session_state.get(f"target_body_fat_min_{person_name}", targets["target_body_fat_min"])),
                step=0.5,
                format="%.1f",
                width=120,
            )
            target_body_fat_max = st.number_input(
                "目標體脂上限 %",
                min_value=3.0,
                max_value=45.0,
                value=max(
                    float(st.session_state.get(f"target_body_fat_max_{person_name}", targets["target_body_fat_max"])),
                    float(target_body_fat_min),
                ),
                step=0.5,
                format="%.1f",
                width=120,
            )
            suggested_calories, suggested_protein, suggested_fiber = default_targets(weight, goal, activity_level)
            suggested_maintenance = maintenance_calories(weight, activity_level)
            activity_multiplier = ACTIVITY_CALORIE_MULTIPLIERS.get(
                activity_level,
                ACTIVITY_CALORIE_MULTIPLIERS["一般活動"],
            )
            calorie_target = st.number_input(
                "每日熱量目標 kcal",
                min_value=1000,
                max_value=5000,
                value=int(default_calories if profile is not None else suggested_calories),
                step=50,
                width=140,
            )
            st.caption(
                f"建議估算：{suggested_calories} kcal / 日；"
                f"{activity_level} = 體重 × {activity_multiplier}，"
                f"維持熱量約 {suggested_maintenance} kcal"
            )
            protein_target = st.number_input(
                "每日蛋白質目標 g",
                min_value=40,
                max_value=300,
                value=int(default_protein if profile is not None else suggested_protein),
                step=5,
                width=120,
            )
            st.caption(f"建議估算：{suggested_protein} g / 日")
            fiber_target = st.number_input(
                "每日纖維目標 g",
                min_value=10,
                max_value=80,
                value=int(default_fiber if profile is not None else suggested_fiber),
                step=1,
                width=120,
            )
            st.caption(f"建議估算：{suggested_fiber} g / 日")
            preferences = st.text_area(
                "飲食偏好 / 禁忌",
                value=current_preferences,
                height=90,
            )
            health_limitations = st.text_area(
                "健康限制 / 身體狀況",
                value=current_health_limitations,
                height=100,
                placeholder=(
                    "例如：尿酸管理、血脂偏高、血壓需注意、曾有肝功能異常、"
                    "右膝 ACL 術後，避免高衝擊訓練。"
                ),
                help=(
                    "可填寫尿酸、血脂、血壓、肝功能、膝蓋、過敏、醫生交代事項等。"
                    "AI 只會作一般健康管理建議，不作醫療診斷。"
                ),
            )
            if st.form_submit_button("儲存偏好", use_container_width=True):
                if target_body_fat_min > target_body_fat_max:
                    st.warning("目標體脂下限不能高於上限。")
                    st.stop()
                cleaned_birth_year = birth_year_text.strip()
                birth_year = None
                if cleaned_birth_year:
                    if not cleaned_birth_year.isdigit():
                        st.warning("出生年份請輸入 4 位數字，或留空。")
                        st.stop()
                    birth_year = int(cleaned_birth_year)
                    if birth_year < 1900 or birth_year > get_local_today().year:
                        st.warning("出生年份看起來不合理，請確認後再儲存。")
                        st.stop()
                save_coach_profile(
                    person_name,
                    {
                        "goal": goal,
                        "height_cm": height_cm,
                        "target_weight_kg": target_weight,
                        "target_body_fat_min": target_body_fat_min,
                        "target_body_fat_max": target_body_fat_max,
                        "current_weight_kg": weight,
                        "daily_calorie_target": calorie_target,
                        "protein_target_g": protein_target,
                        "fiber_target_g": fiber_target,
                        "preferences": preferences.strip(),
                        "health_limitations": health_limitations.strip(),
                        "gender": gender,
                        "birth_year": birth_year,
                        "activity_level": activity_level,
                    }
                )
                st.session_state.pop(f"target_weight_{person_name}", None)
                st.session_state.pop(f"target_body_fat_min_{person_name}", None)
                st.session_state.pop(f"target_body_fat_max_{person_name}", None)
                st.success("已儲存你的飲食偏好。")
                st.rerun()


# Admin tools and person selection

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


# Main app flow

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

    st.title(f"{selected_person} 的健康管理")
    st.caption(f"目前查看：{selected_person}")
    st.markdown(
        f"<div style='text-align: right; color: #8a8f98; font-size: 0.85rem;'>{APP_VERSION}</div>",
        unsafe_allow_html=True,
    )

    height_cm = get_person_height_cm(selected_person)
    targets = get_person_targets(selected_person)
    df = load_logs(selected_person)
    metric_cards(df, height_cm)

    st.markdown(
        f"目標：{compact_number(targets['target_weight_kg'])} kg，體脂 "
        f"{compact_number(targets['target_body_fat_min'])}-"
        f"{compact_number(targets['target_body_fat_max'])}%。"
    )

    tab_coach, tab_daily, tab_trends, tab_weekly = st.tabs(
        ["AI飲食教練", "每日輸入", "趨勢圖表", "每週報告"]
    )
    with tab_coach:
        coach_page(load_logs(selected_person), selected_person)
    with tab_daily:
        daily_input_page(selected_person)
    with tab_trends:
        trend_page(load_logs(selected_person), height_cm)
    with tab_weekly:
        weekly_report_page(load_logs(selected_person), selected_person)


if __name__ == "__main__":
    app()
