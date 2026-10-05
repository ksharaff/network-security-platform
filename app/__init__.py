"""
ORM models package.

Every model module must be imported here. Importing a module runs its
class definitions, and each class registers its table on Base.metadata.
Alembic's env.py imports this package, so anything listed here is
visible to `alembic revision --autogenerate`.
"""

from app.models.asset import Asset, AssetType, Criticality

# __all__ declares this package's public names. It also tells linters
# the imports above are intentional, not unused.
__all__ = ["Asset", "AssetType", "Criticality"]