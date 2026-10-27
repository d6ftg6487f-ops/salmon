import os

from flask import Flask, jsonify, render_template, request, session
from sqlalchemy import create_engine, text


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


def create_app(test_config=None):
    app = Flask(__name__)
    secret_key = os.environ.get("FLASK_SECRET_KEY")
    if not secret_key and os.environ.get("K_SERVICE"):
        raise RuntimeError("FLASK_SECRET_KEY must be configured on Cloud Run.")

    app.config.from_mapping(
        SECRET_KEY=secret_key or os.urandom(32),
        DATABASE_URL=os.environ.get("DATABASE_URL"),
        CLOUD_SQL_CONNECTION_NAME=os.environ.get("CLOUD_SQL_CONNECTION_NAME"),
        DB_DIALECT=os.environ.get("DB_DIALECT", "postgres"),
        DB_USER=os.environ.get("DB_USER"),
        DB_PASSWORD=os.environ.get("DB_PASSWORD"),
        DB_NAME=os.environ.get("DB_NAME"),
        GOOGLE_CLOUD_PROJECT=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        RECAPTCHA_PROJECT_ID=os.environ.get(
            "RECAPTCHA_PROJECT_ID", os.environ.get("GOOGLE_CLOUD_PROJECT")
        ),
        RECAPTCHA_SITE_KEY=os.environ.get(
            "RECAPTCHA_SITE_KEY", "6LcVAwMuAAAAAJuLWP3c9Hv62R__7hxkJAy7lYWf"
        ),
        VERTEX_AI_LOCATION=os.environ.get("VERTEX_AI_LOCATION", "global"),
        GEMINI_MODEL=os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite"),
    )
    if test_config:
        app.config.update(test_config)

    app.config.setdefault("SESSION_COOKIE_HTTPONLY", True)
    app.config.setdefault("SESSION_COOKIE_SAMESITE", "Lax")
    app.config.setdefault("SESSION_COOKIE_SECURE", bool(os.environ.get("K_SERVICE")))

    database = BulbDatabase(app.config)
    app.extensions["bulb_database"] = database

    def recaptcha_error(token, expected_action):
        if not isinstance(token, str) or not token:
            return "reCAPTCHA の確認を完了してください。", 400

        project_id = app.config.get("RECAPTCHA_PROJECT_ID")
        if not project_id:
            app.logger.error("RECAPTCHA_PROJECT_ID is not configured.")
            return "reCAPTCHA の設定が完了していません。", 503

        from google.api_core.exceptions import GoogleAPICallError
        from google.auth.exceptions import GoogleAuthError
        from google.cloud import recaptchaenterprise_v1

        client = app.config.get("RECAPTCHA_CLIENT")
        if client is None:
            client = app.extensions.get("recaptcha_client")

        try:
            if client is None:
                client = recaptchaenterprise_v1.RecaptchaEnterpriseServiceClient()
                app.extensions["recaptcha_client"] = client

            assessment = client.create_assessment(
                request=recaptchaenterprise_v1.CreateAssessmentRequest(
                    parent=f"projects/{project_id}",
                    assessment=recaptchaenterprise_v1.Assessment(
                        event=recaptchaenterprise_v1.Event(
                            token=token,
                            site_key=app.config["RECAPTCHA_SITE_KEY"],
                            expected_action=expected_action,
                        )
                    ),
                )
            )
        except (GoogleAPICallError, GoogleAuthError):
            app.logger.exception("reCAPTCHA Enterprise assessment failed.")
            return "reCAPTCHA の確認に失敗しました。少し待ってからお試しください。", 503

        token_properties = assessment.token_properties
        if not token_properties.valid:
            app.logger.warning(
                "reCAPTCHA token rejected: %s",
                token_properties.invalid_reason,
            )
            return "reCAPTCHA の確認に失敗しました。もう一度お試しください。", 403
        if token_properties.action != expected_action:
            app.logger.warning("reCAPTCHA action did not match %s.", expected_action)
            return "reCAPTCHA の確認に失敗しました。もう一度お試しください。", 403
        return None

    @app.get("/")
    def index():
        if not session.get("site_verified"):
            return render_template(
                "entry.html",
                recaptcha_site_key=app.config["RECAPTCHA_SITE_KEY"],
            )
        return render_template("index.html", state=database.get_state())

    @app.post("/api/site-entry")
    def site_entry():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="JSON形式で送信してください。"), 400
        error = recaptcha_error(data.get("recaptcha_token"), "SITE_ENTRY")
        if error:
            return jsonify(error=error[0]), error[1]
        session["site_verified"] = True
        return jsonify(success=True)

    @app.post("/api/toggle")
    def toggle():
        if not session.get("site_verified"):
            return jsonify(error="サイトに入る前に reCAPTCHA を完了してください。"), 403
        return jsonify(database.toggle())

    @app.post("/api/chat")
    def chat():
        if not session.get("site_verified"):
            return jsonify(error="サイトに入る前に reCAPTCHA を完了してください。"), 403
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify(error="JSON形式で送信してください。"), 400

        message = data.get("message")
        history = data.get("history", [])
        if not isinstance(message, str) or not message.strip() or len(message) > 1000:
            return jsonify(error="質問は1〜1000文字で入力してください。"), 400
        if not isinstance(history, list) or len(history) > 6:
            return jsonify(error="会話履歴の形式が正しくありません。"), 400

        contents = []
        for entry in history:
            if (
                not isinstance(entry, dict)
                or entry.get("role") not in {"user", "model"}
                or not isinstance(entry.get("text"), str)
                or not entry["text"].strip()
                or len(entry["text"]) > 1000
            ):
                return jsonify(error="会話履歴の形式が正しくありません。"), 400
            contents.append(
                {"role": entry["role"], "parts": [{"text": entry["text"]}]}
            )
        contents.append({"role": "user", "parts": [{"text": message.strip()}]})

        from google import genai
        from google.auth.exceptions import GoogleAuthError
        from google.genai import types
        from google.genai.errors import APIError

        try:
            client = app.config.get("VERTEX_CLIENT")
            if client is None:
                project = app.config.get("GOOGLE_CLOUD_PROJECT")
                if not project:
                    app.logger.error("GOOGLE_CLOUD_PROJECT is not configured.")
                    return jsonify(error="チャット機能の設定が完了していません。"), 503

                client = app.extensions.get("vertex_client")
                if client is None:
                    client = genai.Client(
                        vertexai=True,
                        project=project,
                        location=app.config["VERTEX_AI_LOCATION"],
                    )
                    app.extensions["vertex_client"] = client

            response = client.models.generate_content(
                model=app.config["GEMINI_MODEL"],
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "あなたは豆電球アプリの案内チャットです。豆電球の使い方、"
                        "点灯状態、アプリの機能について日本語で簡潔に回答してください。"
                        "それ以外の質問には、このアプリに関する質問のみ回答できると伝えてください。"
                    ),
                    max_output_tokens=256,
                    thinking_config=types.ThinkingConfig(
                        thinking_level=types.ThinkingLevel.MINIMAL
                    ),
                ),
            )
        except (APIError, GoogleAuthError):
            app.logger.exception("Vertex AI request failed.")
            return (
                jsonify(error="回答を取得できませんでした。少し待ってからお試しください。"),
                502,
            )

        answer = response.text
        if not answer:
            app.logger.error("Vertex AI returned an empty response.")
            return jsonify(error="回答を取得できませんでした。別の質問をお試しください。"), 502
        return jsonify(answer=answer)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
