from typing import Any

from pms.open_dental_client import OpenDentalClient


class UnsupportedPmsError(Exception):
    pass


def get_pms_client_from_connection(connection: dict[str, Any]):
    """
    Build the correct PMS client from a pms_connections row.

    Expected connection example:
    {
        "id": "...",
        "clinic_id": "...",
        "pms_type": "open_dental",
        "base_url": "https://api.opendental.com/api/v1",
        "credentials": {
            "customer_key": "..."
        }
    }
    """

    pms_type = connection.get("pms_type")
    base_url = connection.get("base_url")

    credentials = connection.get("credentials") or {}

    if pms_type == "open_dental":
        customer_key = credentials.get("customer_key")

        return OpenDentalClient(
            customer_key=customer_key,
            base_url=base_url,
        )

    raise UnsupportedPmsError(f"Unsupported PMS type: {pms_type}")