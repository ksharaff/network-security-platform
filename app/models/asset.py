"""The Asset model: a known device on the monitored network."""

import enum
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, String, Text, func
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AssetType(enum.StrEnum):
    """
    What kind of device this is. StrEnum members behave like plain
    strings ("server"), so they serialise to JSON without extra work.
    """

    WORKSTATION = "workstation"
    SERVER = "server"
    NETWORK_DEVICE = "network_device"
    OTHER = "other"


class Criticality(enum.StrEnum):
    """
    How much the business cares about this device. Risk scoring
    (Phase 6) will weight alerts on a CRITICAL asset more heavily
    than alerts on a LOW one.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


def _enum_values(enum_class: type[enum.Enum]) -> list[str]:
    """
    By default SQLAlchemy stores an enum's NAME ("NETWORK_DEVICE").
    We want the VALUE ("network_device"), because that is what the API
    and any hand-written SQL will use. This helper tells it to do so.
    """
    return [member.value for member in enum_class]


def _in_list(column: str, enum_class: type[enum.Enum]) -> str:
    """
    Build the SQL text of a CHECK rule from an enum, so the allowed
    values are written once (in the enum) and never drift apart.
    Example result: "asset_type IN ('workstation', 'server', ...)"
    """
    quoted = ", ".join(f"'{value}'" for value in _enum_values(enum_class))
    return f"{column} IN ({quoted})"


class Asset(Base):
    """One row per known device (server, workstation, router...)."""

    # The actual table name in PostgreSQL.
    __tablename__ = "assets"

    # Table-level settings. Here: two named CHECK constraints, so the
    # database itself rejects any value outside the allowed lists, even
    # if someone inserts a row with hand-written SQL that bypasses this
    # application. Explicit names make the constraints easy to find in
    # error messages and to change in a later migration.
    __table_args__ = (
        CheckConstraint(_in_list("asset_type", AssetType), name="ck_assets_asset_type"),
        CheckConstraint(
            _in_list("criticality", Criticality), name="ck_assets_criticality"
        ),
    )

    # Mapped[int] is the Python type; mapped_column() configures the
    # database column. primary_key=True makes it the unique row ID,
    # and PostgreSQL fills it in automatically with an incrementing number.
    id: Mapped[int] = mapped_column(primary_key=True)

    # The device's name, e.g. "web-01". index=True builds a lookup
    # structure so searching by hostname stays fast as the table grows.
    hostname: Mapped[str] = mapped_column(String(255), index=True)

    # INET is PostgreSQL's native IP-address type. It stores addresses
    # compactly and supports subnet queries such as "is this IP inside
    # 10.0.10.0/24?", which enrichment needs later.
    # unique=True: no two assets may share an IP.
    ip_address: Mapped[str] = mapped_column(INET, unique=True)

    # "str | None" means the column is optional (NULL allowed).
    # 17 characters fits "aa:bb:cc:dd:ee:ff".
    mac_address: Mapped[str | None] = mapped_column(String(17))

    # native_enum=False stores the value as plain text (VARCHAR) instead
    # of a PostgreSQL ENUM type, which is painful to change later.
    # create_constraint=False: the CHECK rules live in __table_args__
    # above, so the Enum type must not also create its own copy (that
    # duplication is what caused the DuplicateObject error).
    # default= is applied by SQLAlchemy when you create an Asset
    # without specifying this field.
    asset_type: Mapped[AssetType] = mapped_column(
        Enum(
            AssetType,
            native_enum=False,
            length=20,
            create_constraint=False,
            values_callable=_enum_values,
        ),
        default=AssetType.OTHER,
    )

    criticality: Mapped[Criticality] = mapped_column(
        Enum(
            Criticality,
            native_enum=False,
            length=20,
            create_constraint=False,
            values_callable=_enum_values,
        ),
        default=Criticality.MEDIUM,
    )

    # Text has no length limit, unlike String(n).
    description: Mapped[str | None] = mapped_column(Text)

    # timezone=True stores an absolute moment in time (UTC internally).
    # A timestamp without a timezone is ambiguous, and security tooling
    # must always know exactly WHEN something happened.
    # server_default=func.now() makes the DATABASE fill this in on
    # insert, using its own clock.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # onupdate=func.now() refreshes this each time SQLAlchemy updates
    # the row.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )