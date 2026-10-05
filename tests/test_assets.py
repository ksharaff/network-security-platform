"""Integration tests for the /api/assets endpoints."""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

URL = "/api/assets"

# A valid request body. Tests copy it and change only what they are testing.
VALID = {
    "hostname": "web-01",
    "ip_address": "10.0.10.5",
    "asset_type": "server",
    "criticality": "high",
}


def create(client: TestClient, **overrides):
    """POST a valid asset, with any fields overridden."""
    return client.post(URL, json={**VALID, **overrides})


# ---------------------------------------------------------------- create


def test_create_returns_201_and_server_generated_fields(client: TestClient):
    response = create(client)

    assert response.status_code == 201
    body = response.json()
    assert body["hostname"] == "web-01"
    assert body["ip_address"] == "10.0.10.5"
    assert body["asset_type"] == "server"
    assert body["criticality"] == "high"
    # The client never sent these; the server must have generated them.
    assert isinstance(body["id"], int)
    assert body["created_at"]
    assert body["updated_at"]


def test_create_applies_defaults(client: TestClient):
    response = client.post(URL, json={"hostname": "pc-01", "ip_address": "10.0.20.5"})

    assert response.status_code == 201
    body = response.json()
    assert body["asset_type"] == "other"
    assert body["criticality"] == "medium"
    assert body["mac_address"] is None
    assert body["description"] is None


def test_create_duplicate_ip_returns_409_and_stores_nothing_extra(client: TestClient):
    assert create(client).status_code == 201

    response = create(client, hostname="web-02")

    assert response.status_code == 409
    # The failed insert was rolled back: still exactly one asset.
    assert len(client.get(URL).json()) == 1


def test_ipv6_is_stored_in_canonical_lowercase_form(client: TestClient):
    response = create(client, ip_address="2001:DB8::1")

    assert response.status_code == 201
    assert response.json()["ip_address"] == "2001:db8::1"


# `parametrize` runs the same test once per value in the list, and reports
# each as its own result.
@pytest.mark.parametrize(
    "bad_ip",
    [
        "10.0.10.999",  # octet out of range
        "banana",  # not an address at all
        "10.0.10.5/24",  # network notation, not a single host
        "",  # empty
    ],
)
def test_create_rejects_invalid_ip(client: TestClient, bad_ip: str):
    response = create(client, ip_address=bad_ip)

    assert response.status_code == 422
    # FastAPI reports where the problem is, e.g. ["body", "ip_address"].
    assert "ip_address" in response.json()["detail"][0]["loc"]


def test_create_rejects_unknown_field(client: TestClient):
    # A typo in a field name must fail loudly, not be silently dropped.
    response = create(client, critcality="high")

    assert response.status_code == 422


def test_create_rejects_invalid_mac_address(client: TestClient):
    assert create(client, mac_address="not-a-mac").status_code == 422


def test_create_rejects_invalid_enum_value(client: TestClient):
    assert create(client, asset_type="toaster").status_code == 422


# ------------------------------------------------------------- read/list


def test_get_returns_the_asset(client: TestClient):
    asset_id = create(client).json()["id"]

    response = client.get(f"{URL}/{asset_id}")

    assert response.status_code == 200
    assert response.json()["hostname"] == "web-01"


def test_get_missing_returns_404(client: TestClient):
    assert client.get(f"{URL}/999").status_code == 404


def test_list_paginates_in_id_order(client: TestClient):
    for number in range(1, 4):
        create(client, hostname=f"host-{number}", ip_address=f"10.0.10.{number}")

    first_page = client.get(URL, params={"limit": 2}).json()
    second_page = client.get(URL, params={"limit": 2, "offset": 2}).json()

    assert [a["hostname"] for a in first_page] == ["host-1", "host-2"]
    assert [a["hostname"] for a in second_page] == ["host-3"]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501}, {"offset": -1}])
def test_list_rejects_out_of_range_pagination(client: TestClient, params: dict):
    assert client.get(URL, params=params).status_code == 422


# ---------------------------------------------------------------- update


def test_patch_changes_only_the_supplied_fields(client: TestClient):
    created = create(client).json()

    response = client.patch(f"{URL}/{created['id']}", json={"criticality": "critical"})

    assert response.status_code == 200
    body = response.json()
    assert body["criticality"] == "critical"
    # Untouched fields keep their values.
    assert body["hostname"] == "web-01"
    assert body["ip_address"] == "10.0.10.5"
    # updated_at moved forward, created_at did not.
    assert body["created_at"] == created["created_at"]
    assert datetime.fromisoformat(body["updated_at"]) > datetime.fromisoformat(
        created["updated_at"]
    )


def test_patch_null_on_required_field_returns_422(client: TestClient):
    asset_id = create(client).json()["id"]

    response = client.patch(f"{URL}/{asset_id}", json={"hostname": None})

    assert response.status_code == 422


def test_patch_null_on_optional_field_clears_it(client: TestClient):
    asset_id = create(client, description="primary web server").json()["id"]

    response = client.patch(f"{URL}/{asset_id}", json={"description": None})

    assert response.status_code == 200
    assert response.json()["description"] is None


def test_patch_to_an_existing_ip_returns_409(client: TestClient):
    create(client, hostname="a", ip_address="10.0.10.1")
    second_id = create(client, hostname="b", ip_address="10.0.10.2").json()["id"]

    response = client.patch(f"{URL}/{second_id}", json={"ip_address": "10.0.10.1"})

    assert response.status_code == 409


def test_patch_missing_returns_404(client: TestClient):
    assert client.patch(f"{URL}/999", json={"hostname": "x"}).status_code == 404


# ---------------------------------------------------------------- delete


def test_delete_returns_204_then_404(client: TestClient):
    asset_id = create(client).json()["id"]

    assert client.delete(f"{URL}/{asset_id}").status_code == 204
    assert client.get(f"{URL}/{asset_id}").status_code == 404


def test_delete_missing_returns_404(client: TestClient):
    assert client.delete(f"{URL}/999").status_code == 404


# ------------------------------------------------------- database layer


def test_database_itself_rejects_invalid_asset_type(engine: Engine):
    """
    Bypass the API entirely and insert bad data with raw SQL. The CHECK
    constraint from the migration must still refuse it: this protects the
    data from any code path that skips Pydantic validation.
    """
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO assets (hostname, ip_address, asset_type, criticality) "
                    "VALUES ('x', '10.9.9.9', 'bogus', 'low')"
                )
            )