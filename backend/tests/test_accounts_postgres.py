"""AccountService against a real, throwaway Postgres, with the real migrations.

Skipped unless TEST_DATABASE_URL is set, so CI (no database) skips it. Never point it at the shared
Supabase database: it drops and recreates the public and auth schemas. For example:

    docker run --rm -d --name careergps-test-db -e POSTGRES_PASSWORD=test -p 55432:5432 postgres:17
    TEST_DATABASE_URL=postgresql+psycopg://postgres:test@localhost:55432/postgres python -m pytest tests/test_accounts_postgres.py
    docker stop careergps-test-db
"""
import os
import subprocess
import sys
import unittest
import uuid
from datetime import UTC, datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
os.environ.setdefault("DATABASE_URL", TEST_DATABASE_URL or "postgresql+psycopg://x:y@localhost:5432/test")

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.core.security import AuthenticatedUser
from app.models import Resume, User
from app.schemas.me import AccountCreate, ResumeSubmit
from app.services import accounts
from tests.test_me import classification, onboarding_body, resume_body


@unittest.skipUnless(TEST_DATABASE_URL, "set TEST_DATABASE_URL to a throwaway Postgres to run")
class AccountServicePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if "supabase" in TEST_DATABASE_URL:
            raise RuntimeError("TEST_DATABASE_URL points at Supabase; use a throwaway database")
        cls.engine = create_engine(TEST_DATABASE_URL)
        with cls.engine.begin() as connection:
            connection.execute(text("DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public"))
            # Stand-in for Supabase's auth schema: only what the migrations and the service touch.
            connection.execute(text("DROP SCHEMA IF EXISTS auth CASCADE; CREATE SCHEMA auth"))
            connection.execute(
                text(
                    "CREATE TABLE auth.users (id uuid PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now(),"
                    " email_confirmed_at timestamptz)"
                )
            )
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_ROOT,
            env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
            check=True,
            capture_output=True,
        )
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("TRUNCATE users, auth.users CASCADE"))
        self.db = self.Session()
        self.service = accounts.AccountService(self.db)

    def tearDown(self) -> None:
        self.db.close()

    SIGNED_UP_AT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

    def auth_user(self, email="ada@example.com", confirmed=True) -> AuthenticatedUser:
        user = AuthenticatedUser(id=uuid.uuid4(), email=email)
        with self.engine.begin() as connection:
            connection.execute(
                text("INSERT INTO auth.users (id, created_at, email_confirmed_at) VALUES (:id, :signed_up, :at)"),
                {"id": user.id, "signed_up": self.SIGNED_UP_AT, "at": datetime.now(UTC) if confirmed else None},
            )
        return user

    def onboard(self, auth_user, **changes) -> User:
        return self.service.create_account(auth_user, AccountCreate.model_validate(onboarding_body(**changes)))

    def test_creates_the_user_and_an_active_first_resume(self) -> None:
        user = self.onboard(self.auth_user("Ada@Example.com"))

        self.assertEqual("ada@example.com", user.primary_email)
        self.assertEqual(self.SIGNED_UP_AT, user.terms_accepted_at)  # from auth.users, not the request time
        resume = self.service.get_active_resume(user)
        self.assertEqual(user.id, resume.user_id)
        self.assertEqual("pdf", resume.file_type)

    def test_unconfirmed_email_is_refused(self) -> None:
        with self.assertRaises(accounts.EmailNotConfirmedError):
            self.onboard(self.auth_user(confirmed=False))

    def test_an_email_can_belong_to_one_account_only(self) -> None:
        self.onboard(self.auth_user("ada@example.com"))

        with self.assertRaises(accounts.AccountAlreadyExistsError):
            self.onboard(self.auth_user("ada@example.com"))

    def test_a_newer_resume_is_kept_alongside_and_becomes_active(self) -> None:
        user = self.onboard(self.auth_user(), resume=resume_body(classification=classification(linkedin=None)))

        newer = self.service.add_resume(
            user, ResumeSubmit.model_validate(resume_body(original_filename="v2.docx", classification=classification(linkedin="li")))
        )

        self.assertEqual(newer.id, self.service.get_user(user.id).active_resume_id)
        self.assertEqual(2, self.db.query(Resume).filter_by(user_id=user.id).count())
        self.assertEqual("li", self.service.get_user(user.id).linkedin_url)

    def test_long_resume_values_are_saved_without_errors(self) -> None:
        long = classification(location="x" * 300, website="https://example.com/" + "a" * 2100, name="n" * 300)

        user = self.onboard(self.auth_user(), resume=resume_body(classification=long))

        self.assertEqual(255, len(self.service.get_user(user.id).current_location))
        self.assertIsNone(self.service.get_user(user.id).website_url)

    def test_deleting_the_supabase_account_deletes_everything(self) -> None:
        auth_user = self.auth_user()
        self.onboard(auth_user)

        with self.engine.begin() as connection:
            connection.execute(text("DELETE FROM auth.users WHERE id = :id"), {"id": auth_user.id})

        self.db.expire_all()
        self.assertIsNone(self.service.get_user(auth_user.id))
        self.assertEqual(0, self.db.query(Resume).count())

    def test_email_sync_keeps_the_old_email_when_the_new_one_is_taken(self) -> None:
        ada = self.onboard(self.auth_user("ada@example.com"))
        self.onboard(self.auth_user("grace@example.com"), resume=resume_body(classification=classification(name="Grace Hopper")))

        self.service.sync_email(ada, "Grace@example.com")

        self.assertEqual("ada@example.com", self.service.get_user(ada.id).primary_email)

    def test_the_database_rejects_a_user_without_a_supabase_account(self) -> None:
        user = accounts.new_user(
            AuthenticatedUser(id=uuid.uuid4(), email="ghost@example.com"),
            AccountCreate.model_validate(onboarding_body()),
            signed_up_at=datetime.now(UTC),
        )
        self.db.add(user)

        with self.assertRaises(IntegrityError):
            self.db.commit()
        self.db.rollback()


if __name__ == "__main__":
    unittest.main()
