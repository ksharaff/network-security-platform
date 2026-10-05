"""Request and response schemas for the /api/assets endpoints."""

import ipaddress
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

# Reuse the enums from the model so the allowed values are defined once.
from app.models.asset import AssetType, Criticality


def _normalise_ip(value: object) -> str:
    """
    Validate an IP address and return it in canonical text form.

    ipaddress.ip_address() accepts IPv4 and IPv6 and raises ValueError
    for anything else ("10.0.10.999", "banana"). Pydantic turns that
    ValueError into a 422 response that names the offending field.
    str(value) first, so this also works if the database driver hands
    back an ipaddress object instead of a string when reading a row.
    """
    try:
        return str(ipaddress.ip_address(str(value)))
    except ValueError as exc:
        raise ValueError("not a valid IPv4 or IPv6 address") from exc


# A str that is validated by _normalise_ip BEFORE Pydantic's own str check.
IPAddressStr = Annotated[str, BeforeValidator(_normalise_ip)]

# Six pairs of hex digits separated by colons, e.g. "aa:bb:cc:dd:ee:ff".
MacStr = Annotated[str, Field(pattern=r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")]


class AssetBase(BaseModel):
    """Fields a client may supply when describing an asset."""

    # extra="forbid": unknown fields are rejected with a 422 instead of
    # being silently ignored. Without it, a typo such as "critcality"
    # would be dropped and the client would never find out.
    model_config = ConfigDict(extra="forbid")

    hostname: str = Field(min_length=1, max_length=255)
    ip_address: IPAddressStr
    mac_address: MacStr | None = None
    asset_type: AssetType = AssetType.OTHER
    criticality: Criticality = Criticality.MEDIUM
    description: str | None = None


class AssetCreate(AssetBase):
    """Body of POST /api/assets. Identical to AssetBase for now."""


class AssetUpdate(BaseModel):
    """
    Body of PATCH /api/assets/{id}. Every field is optional: the client
    sends only what should change.
    """

    model_config = ConfigDict(extra="forbid")

    hostname: str | None = Field(default=None, min_length=1, max_length=255)
    ip_address: IPAddressStr | None = None
    mac_address: MacStr | None = None
    asset_type: AssetType | None = None
    criticality: Criticality | None = None
    description: str | None = None

    @field_validator("hostname", "ip_address", "asset_type", "criticality")
    @classmethod
    def _reject_null(cls, value: object) -> object:
        """
        These four database columns are NOT NULL. "Omitted" is fine
        (means: leave unchanged), but an explicit {"hostname": null}
        would otherwise reach the database and crash with a 500.
        mac_address and description are nullable, so null is allowed
        there (it means: clear the value).
        """
        if value is None:
            raise ValueError("cannot be null")
        return value


class AssetRead(AssetBase):
    """What the API returns: the client-supplied fields plus server-generated ones."""

    # from_attributes=True lets Pydantic read values off an ORM object
    # (asset.hostname) rather than only from a dict (data["hostname"]).
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime