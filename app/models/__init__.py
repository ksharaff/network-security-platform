"""
ORM models package.

Every model module must be imported here. Importing a module runs its
class definitions, and each class registers its table on Base.metadata.
Alembic's env.py imports this package, so anything listed here is
visible to `alembic revision --autogenerate`.

Currently empty; the Asset model is added next.
"""