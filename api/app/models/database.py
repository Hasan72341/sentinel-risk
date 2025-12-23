from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import os


DB_PATH = os.path.join(os.path.expanduser("~"), ".sentinel-risk", "data.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

DATABASE_URL = os.getenv("SENTINEL_DATABASE_URL", f"sqlite:///{DB_PATH}")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "migrations"
)
BASELINE_REVISION = "0001"


def _alembic_config():
    from alembic.config import Config

    config = Config()
    config.set_main_option("script_location", MIGRATIONS_DIR)
    return config


def init_db():
    """Bring the database schema up to the latest migration."""
    from alembic import command
    from sqlalchemy import inspect

    config = _alembic_config()
    tables = set(inspect(engine).get_table_names())
    # Databases created before migrations existed already hold the baseline schema
    if "analyses" in tables and "alembic_version" not in tables:
        command.stamp(config, BASELINE_REVISION)
    command.upgrade(config, "head")
