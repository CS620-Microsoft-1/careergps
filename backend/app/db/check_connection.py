"""Run with: python -m app.db.check_connection"""
from sqlalchemy import text

from app.db.session import engine


def main() -> None:
    with engine.connect() as conn:
        version = conn.execute(text("SELECT version()")).scalar_one()
        database = conn.execute(text("SELECT current_database()")).scalar_one()
        role = conn.execute(text("SELECT current_user")).scalar_one()
    print("Connected ✅")
    print(f"  database: {database}")
    print(f"  role:     {role}")
    print(f"  server:   {version}")


if __name__ == "__main__":
    main()
