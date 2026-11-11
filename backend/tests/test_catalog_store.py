"""Catalog snapshot cache and fallbacks, write validation, and the recommender reading the current
catalog. No database: sources are fakes or the data files."""
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy.exc import OperationalError

from app.services import catalog_store, catalog_writes
from app.services.catalog_store import CatalogNotReady, CatalogSnapshot, FileCatalogSource
from app.services.certifications.catalog import CATALOG_PATH, get_catalog
from app.services.certifications.recommender import CertificationRecommender
from app.services.resources import load_catalog as load_resources


def setUpModule() -> None:
    catalog_store.use_source(FileCatalogSource())


def _snapshot(version: str) -> CatalogSnapshot:
    return CatalogSnapshot(source="database", certification_version=version, certifications=(),
                           school_courses=(), student_orgs=())


class _Source:
    def __init__(self, *results) -> None:
        self.results = list(results)
        self.calls = 0

    def load(self) -> CatalogSnapshot:
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _db_error() -> OperationalError:
    return OperationalError("SELECT 1", {}, Exception("connection refused"))


class CatalogSnapshotTests(unittest.TestCase):
    def tearDown(self) -> None:
        catalog_store.use_source(FileCatalogSource())

    def test_caches_for_a_few_minutes(self) -> None:
        source = _Source(_snapshot("v1"), _snapshot("v2"))
        catalog_store.use_source(source)
        with patch.object(catalog_store.time, "monotonic", return_value=1000.0):
            self.assertEqual("v1", catalog_store.get_snapshot().certification_version)
        with patch.object(catalog_store.time, "monotonic", return_value=1000.0 + catalog_store.CACHE_SECONDS - 1):
            self.assertEqual("v1", catalog_store.get_snapshot().certification_version)
        with patch.object(catalog_store.time, "monotonic", return_value=1000.0 + catalog_store.CACHE_SECONDS):
            self.assertEqual("v2", catalog_store.get_snapshot().certification_version)
        self.assertEqual(2, source.calls)

    def test_invalidate_reads_again(self) -> None:
        catalog_store.use_source(_Source(_snapshot("v1"), _snapshot("v2")))
        self.assertEqual("v1", catalog_store.get_snapshot().certification_version)
        catalog_store.invalidate()
        self.assertEqual("v2", catalog_store.get_snapshot().certification_version)

    def test_missing_or_empty_tables_fall_back_to_the_files(self) -> None:
        for reason in ("missing", "empty"):
            catalog_store.use_source(_Source(CatalogNotReady(reason)))
            with self.assertLogs(catalog_store.logger, "WARNING"):
                snapshot = catalog_store.get_snapshot()
            self.assertEqual("files", snapshot.source)
            self.assertEqual(48, len(snapshot.certifications))

    def test_database_error_keeps_the_last_snapshot(self) -> None:
        source = _Source(_snapshot("v1"), _db_error(), _snapshot("v2"))
        catalog_store.use_source(source)
        self.assertEqual("v1", catalog_store.get_snapshot().certification_version)
        catalog_store.invalidate()
        with patch.object(catalog_store.time, "monotonic", return_value=5000.0), \
             self.assertLogs(catalog_store.logger, "ERROR"):
            self.assertEqual("v1", catalog_store.get_snapshot().certification_version)
        # Retried soon, not after the full cache time.
        with patch.object(catalog_store.time, "monotonic", return_value=5000.0 + catalog_store.RETRY_SECONDS):
            self.assertEqual("v2", catalog_store.get_snapshot().certification_version)

    def test_database_error_with_nothing_cached_is_a_503(self) -> None:
        catalog_store.use_source(_Source(_db_error()))
        with self.assertLogs(catalog_store.logger, "ERROR"), self.assertRaises(HTTPException) as caught:
            catalog_store.get_snapshot()
        self.assertEqual(503, caught.exception.status_code)

    def test_file_source_matches_the_files(self) -> None:
        snapshot = FileCatalogSource().load()
        entries = load_resources()
        self.assertEqual([e for e in entries if e["type"] == "school_course"], list(snapshot.school_courses))
        self.assertEqual([e for e in entries if e["type"] == "student_org"], list(snapshot.student_orgs))
        self.assertEqual("2026-10-26", snapshot.certification_version)


class RecommenderCatalogTests(unittest.TestCase):
    def tearDown(self) -> None:
        catalog_store.use_source(FileCatalogSource())

    def test_reads_the_current_catalog_unless_one_is_given(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            recommender = CertificationRecommender(Path(directory))
            self.assertEqual(get_catalog()["version"], recommender.catalog["version"])
            catalog_store.use_source(_Source(_snapshot("v-new")))
            self.assertEqual("v-new", recommender.catalog["version"])
            fixed = {"version": "fixed", "certifications": []}
            self.assertIs(fixed, CertificationRecommender(Path(directory), catalog=fixed).catalog)


class WriteValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        raw = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        self.certification = raw["certifications"][0]
        self.course = next(e for e in load_resources() if e["type"] == "school_course")
        self.org = next(e for e in load_resources() if e["type"] == "student_org")

    def test_certification_values(self) -> None:
        values = catalog_writes.certification_values(self.certification, date(2026, 11, 1))
        self.assertEqual(date(2026, 11, 1), values["last_verified"])
        self.assertEqual(self.certification["skills"], values["skills"])
        with self.assertRaises(ValueError):
            catalog_writes.certification_values({**self.certification, "skills": {"data_analyst": ["no_such_skill"]}},
                                                date(2026, 11, 1))
        with self.assertRaises(ValueError):
            catalog_writes.certification_values({**self.certification, "level": "expert"}, date(2026, 11, 1))

    def test_school_resource_values(self) -> None:
        self.assertNotIn("alongside", catalog_writes.school_resource_values("school_course", self.course))
        self.assertTrue(catalog_writes.school_resource_values("student_org", self.org)["alongside"])
        for kind, data in [("school_course", {**self.course, "skills": ["no_such_skill"]}),
                           ("school_course", {**self.course, "skills": []}),
                           ("school_course", self.org),  # wrong type
                           ("school_course", {**self.course, "type": None, "alongside": True}),
                           ("student_org", {**self.org, "extra": 1})]:
            with self.subTest(kind=kind, data=data), self.assertRaises(ValueError):
                catalog_writes.school_resource_values(kind, data)


if __name__ == "__main__":
    unittest.main()
