import os

from flask import Flask, jsonify, render_template
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
    app.config.from_mapping(
        DATABASE_URL=os.environ.get("DATABASE_URL"),
        CLOUD_SQL_CONNECTION_NAME=os.environ.get("CLOUD_SQL_CONNECTION_NAME"),
        DB_DIALECT=os.environ.get("DB_DIALECT", "postgres"),
        DB_USER=os.environ.get("DB_USER"),
        DB_PASSWORD=os.environ.get("DB_PASSWORD"),
        DB_NAME=os.environ.get("DB_NAME"),
    )
    if test_config:
        app.config.update(test_config)

    database = BulbDatabase(app.config)
    app.extensions["bulb_database"] = database

    @app.get("/")
    def index():
        return render_template("index.html", state=database.get_state())

    @app.post("/api/toggle")
    def toggle():
        return jsonify(database.toggle())

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
