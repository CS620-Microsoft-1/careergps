"""Unit tests read the certification, course and club catalog from the data files: CI has no database.
Tests that use Postgres switch catalog_store to the database themselves."""
from app.services import catalog_store

catalog_store.use_source(catalog_store.FileCatalogSource())
