# Import every model here so Alembic's autogenerate can see it.
from app.models.profile import Profile
from app.models.user import User

__all__ = ["Profile", "User"]
