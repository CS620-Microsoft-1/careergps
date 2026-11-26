"""Unit tests read the certification, course and club catalog from the data files: CI has no database.
Tests that use Postgres switch catalog_store to the database themselves."""
from app.services import catalog_store

catalog_store.use_source(catalog_store.FileCatalogSource())

# Unit tests never write Agent call records to a database; tests that check them install their own sink.
from app.services import agent_calls  # noqa: E402

agent_calls.use_sink(agent_calls.MemorySink())

# Plan writes record their audit row in a separate session; keep those in memory too.
from app.services import audit  # noqa: E402

audit.use_writer(audit.MemoryWriter())
