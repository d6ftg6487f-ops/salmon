import os

from flask import Flask, jsonify, render_template
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Integer,
    MetaData,
    Table,
    case,
    create_engine,
    select,
    update,
)
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

metadata = MetaData()
bulb_state = Table(
    "bulb_state",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("is_on", Boolean, nullable=False),
    Column("press_count", BigInteger, nullable=False),
)


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

            from google.cloud.sql.connector import Connector

            driver = "pg8000" if dialect == "postgres" else "pymysql"
            uri = "postgresql+pg8000://" if dialect == "postgres" else "mysql+pymysql://"
            self.connector = Connector()
            self.engine = create_engine(
                uri,
                creator=lambda: self.connector.connect(
                    connection_name,
                    driver,
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
        metadata.create_all(self.engine)
        values = {"id": 1, "is_on": False, "press_count": 0}
        with self.engine.begin() as connection:
            dialect = self.engine.dialect.name
            if dialect == "mysql":
                statement = mysql_insert(bulb_state).values(**values)
                statement = statement.on_duplicate_key_update(id=bulb_state.c.id)
            elif dialect == "postgresql":
                statement = postgresql_insert(bulb_state).values(**values)
                statement = statement.on_conflict_do_nothing(index_elements=["id"])
            elif dialect == "sqlite":
                statement = sqlite_insert(bulb_state).values(**values)
                statement = statement.on_conflict_do_nothing(index_elements=["id"])
            else:
                raise ValueError(f"Unsupported database dialect: {dialect}")
            connection.execute(statement)

    def get_state(self):
        with self.engine.connect() as connection:
            row = connection.execute(
                select(bulb_state.c.is_on, bulb_state.c.press_count).where(
                    bulb_state.c.id == 1
                )
            ).one()
        return {"is_on": row.is_on, "press_count": row.press_count}

    def toggle(self):
        with self.engine.begin() as connection:
            connection.execute(
                update(bulb_state)
                .where(bulb_state.c.id == 1)
                .values(
                    is_on=case((bulb_state.c.is_on.is_(True), False), else_=True),
                    press_count=bulb_state.c.press_count + 1,
                )
            )
            row = connection.execute(
                select(bulb_state.c.is_on, bulb_state.c.press_count).where(
                    bulb_state.c.id == 1
                )
            ).one()
        return {"is_on": row.is_on, "press_count": row.press_count}


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
