import logging
import os
from functools import wraps

import firebase_admin
from firebase_admin import auth as firebase_auth
from flask import Flask, current_app, g, jsonify, render_template, request
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


class BulbDatabase:
    def __init__(self, config):
        self.connector = None
        database_url = config.get("DATABASE_URL")
        connection_name = config.get("CLOUD_SQL_CONNECTION_NAME")

        if database_url:
            self.engine = create_engine(database_url, pool_pre_ping=True)
        elif connection_name:
            dialect = config.get("DB_DIALECT", "postgres").lower()
            if dialect not in {"postgres", "mysql"}:
                raise ValueError("DB_DIALECT must be 'postgres' or 'mysql'.")

            user = config.get("DB_USER")
            password = config.get("DB_PASSWORD")
            database = config.get("DB_NAME")
            if not all((user, password, database)):
                raise ValueError(
                    "DB_USER, DB_PASSWORD, and DB_NAME are required for Cloud SQL."
                )

            from google.cloud.sql.connector import Connector, IPTypes

            driver = "pg8000" if dialect == "postgres" else "pymysql"
            uri = "postgresql+pg8000://" if dialect == "postgres" else "mysql+pymysql://"
            self.connector = Connector()
            self.engine = create_engine(
                uri,
                creator=lambda: self.connector.connect(
                    connection_name,
                    driver,
                    ip_type=IPTypes.PRIVATE,
                    user=user,
                    password=password,
                    db=database,
                ),
                pool_pre_ping=True,
                pool_size=5,
                max_overflow=2,
            )
        else:
            if os.environ.get("K_SERVICE"):
                raise RuntimeError(
                    "Cloud SQL is not configured. Set CLOUD_SQL_CONNECTION_NAME "
                    "and the database credentials."
                )
            self.engine = create_engine("sqlite:///bulb.db", pool_pre_ping=True)

        self._initialize()

    def _initialize(self):
        with self.engine.begin() as connection:
            dialect = self.engine.dialect.name
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS bulb_state (
                        id INTEGER PRIMARY KEY,
                        is_on BOOLEAN NOT NULL,
                        press_count BIGINT NOT NULL
                    )
                    """
                )
            )
            if dialect == "mysql":
                insert_statement = """
                    INSERT IGNORE INTO bulb_state (id, is_on, press_count)
                    VALUES (:id, :is_on, :press_count)
                """
            elif dialect in {"postgresql", "sqlite"}:
                insert_statement = """
                    INSERT INTO bulb_state (id, is_on, press_count)
                    VALUES (:id, :is_on, :press_count)
                    ON CONFLICT (id) DO NOTHING
                """
            else:
                raise ValueError(f"Unsupported database dialect: {dialect}")
            connection.execute(
                text(insert_statement),
                {"id": 1, "is_on": False, "press_count": 0},
            )

    def get_state(self):
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT is_on, press_count
                    FROM bulb_state
                    WHERE id = :id
                    """
                ),
                {"id": 1},
            ).one()
        return {
            "is_on": bool(row._mapping["is_on"]),
            "press_count": row._mapping["press_count"],
        }

    def toggle(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE bulb_state
                    SET is_on = CASE WHEN is_on THEN FALSE ELSE TRUE END,
                        press_count = press_count + 1
                    WHERE id = :id
                    """
                ),
                {"id": 1},
            )
            row = connection.execute(
                text(
                    """
                    SELECT is_on, press_count
                    FROM bulb_state
                    WHERE id = :id
                    """
                ),
                {"id": 1},
            ).one()
        return {
            "is_on": bool(row._mapping["is_on"]),
            "press_count": row._mapping["press_count"],
        }


# ── 認証 ──────────────────────────────────


def parse_allowed_emails(value):
    """カンマ区切りのメールアドレスを、小文字の集合に変換する"""
    return {email.strip().lower() for email in (value or "").split(",") if email.strip()}


def init_firebase(project_id):
    """Firebase Admin SDK を一度だけ初期化する"""
    try:
        firebase_admin.get_app()
    except ValueError:
        options = {"projectId": project_id} if project_id else None
        firebase_admin.initialize_app(options=options)


def require_login(view):
    """ログイン済み、かつ許可リストにあるユーザーだけを通す"""

    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify(error="login_required"), 401

        try:
            decoded = firebase_auth.verify_id_token(header.removeprefix("Bearer "))
        except Exception:
            logger.warning("IDトークンの検証に失敗しました。", exc_info=True)
            return jsonify(error="invalid_token"), 401

        email = (decoded.get("email") or "").lower()
        allowed = current_app.config["ALLOWED_EMAILS"]
        if not decoded.get("email_verified") or email not in allowed:
            return jsonify(error="forbidden"), 403

        g.user = decoded  # 後続の処理で uid などを使えるようにする
        return view(*args, **kwargs)

    return wrapper


# ── アプリ本体 ─────────────────────────────


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE_URL=os.environ.get("DATABASE_URL"),
        CLOUD_SQL_CONNECTION_NAME=os.environ.get("CLOUD_SQL_CONNECTION_NAME"),
        DB_DIALECT=os.environ.get("DB_DIALECT", "postgres"),
        DB_USER=os.environ.get("DB_USER"),
        DB_PASSWORD=os.environ.get("DB_PASSWORD"),
        DB_NAME=os.environ.get("DB_NAME"),
        ALLOWED_EMAILS=parse_allowed_emails(os.environ.get("ALLOWED_EMAILS")),
        FIREBASE_API_KEY=os.environ.get("FIREBASE_API_KEY"),
        FIREBASE_AUTH_DOMAIN=os.environ.get("FIREBASE_AUTH_DOMAIN"),
        FIREBASE_PROJECT_ID=os.environ.get("FIREBASE_PROJECT_ID"),
        FIREBASE_APP_ID=os.environ.get("FIREBASE_APP_ID"),
    )
    if test_config:
        app.config.update(test_config)

    if not app.config["ALLOWED_EMAILS"]:
        logger.warning("ALLOWED_EMAILS が空です。誰も操作できません。")

    init_firebase(app.config["FIREBASE_PROJECT_ID"])

    # フロントに渡す設定。どれか欠けていれば None（ログインUIを出さない）
    firebase_config = {
        "apiKey": app.config["FIREBASE_API_KEY"],
        "authDomain": app.config["FIREBASE_AUTH_DOMAIN"],
        "projectId": app.config["FIREBASE_PROJECT_ID"],
        "appId": app.config["FIREBASE_APP_ID"],
    }
    if not all(firebase_config.values()):
        firebase_config = None

    database = BulbDatabase(app.config)
    app.extensions["bulb_database"] = database

    @app.get("/")
    def index():
        return render_template(
            "index.html",
            state=database.get_state(),
            firebase_config=firebase_config,
        )

    @app.post("/api/toggle")
    @require_login
    def toggle():
        return jsonify(database.toggle())

    @app.after_request
    def no_cache_for_api(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
