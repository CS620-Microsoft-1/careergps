from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import JSONB

# JSONB on Postgres; plain JSON elsewhere (the API tests run on SQLite).
JSONType = JSON().with_variant(JSONB(), "postgresql")
