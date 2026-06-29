from fastapi import APIRouter

from pms.base import PmsApiError
from pms.factory import UnsupportedPmsError, get_pms_client_from_connection
from supabase_service import (
    get_active_pms_connection_for_clinic,
    import_pms_patients_to_db,
    mark_pms_connection_error,
    mark_pms_connection_success,
)


router = APIRouter(prefix="/pms", tags=["PMS"])


@router.get("/test/{clinic_id}")
async def test_pms_connection(clinic_id: str):
    connection = get_active_pms_connection_for_clinic(clinic_id)

    if not connection:
        return {
            "ok": False,
            "type": "missing_connection",
            "message": "No active PMS connection found for this clinic.",
        }

    connection_id = connection["id"]

    try:
        client = get_pms_client_from_connection(connection)
        result = await client.test_connection()

        mark_pms_connection_success(connection_id)

        return {
            "ok": True,
            "connection_id": connection_id,
            "clinic_id": clinic_id,
            "pms_type": connection.get("pms_type"),
            "result": result,
        }

    except PmsApiError as e:
        error_message = f"{e.message}: {e.response_body}"
        mark_pms_connection_error(connection_id, error_message)

        return {
            "ok": False,
            "type": "pms_api_error",
            "connection_id": connection_id,
            "clinic_id": clinic_id,
            "pms_type": connection.get("pms_type"),
            "status_code": e.status_code,
            "message": e.message,
            "response_body": e.response_body,
        }

    except UnsupportedPmsError as e:
        mark_pms_connection_error(connection_id, str(e))

        return {
            "ok": False,
            "type": "unsupported_pms",
            "connection_id": connection_id,
            "clinic_id": clinic_id,
            "message": str(e),
        }

    except Exception as e:
        mark_pms_connection_error(connection_id, str(e))

        return {
            "ok": False,
            "type": "server_error",
            "connection_id": connection_id,
            "clinic_id": clinic_id,
            "message": str(e),
        }
    

    @router.post("/import-patients/{clinic_id}")
async def import_pms_patients(clinic_id: str, limit: int = 50):
    connection = get_active_pms_connection_for_clinic(clinic_id)

    if not connection:
        return {
            "ok": False,
            "type": "missing_connection",
            "message": "No active PMS connection found for this clinic.",
        }

    connection_id = connection["id"]

    try:
        client = get_pms_client_from_connection(connection)

        patients = await client.list_patients(limit=limit)

        result = import_pms_patients_to_db(
            clinic_id=clinic_id,
            connection=connection,
            patients=patients,
        )

        mark_pms_connection_success(connection_id)

        return {
            "ok": True,
            "clinic_id": clinic_id,
            "connection_id": connection_id,
            "pms_type": connection.get("pms_type"),
            "pulled_count": len(patients),
            "imported_count": result["imported_count"],
            "failed_count": result["failed_count"],
            "failed": result["failed"],
        }

    except PmsApiError as e:
        error_message = f"{e.message}: {e.response_body}"
        mark_pms_connection_error(connection_id, error_message)

        return {
            "ok": False,
            "type": "pms_api_error",
            "connection_id": connection_id,
            "clinic_id": clinic_id,
            "pms_type": connection.get("pms_type"),
            "status_code": e.status_code,
            "message": e.message,
            "response_body": e.response_body,
        }

    except Exception as e:
        mark_pms_connection_error(connection_id, str(e))

        return {
            "ok": False,
            "type": "server_error",
            "connection_id": connection_id,
            "clinic_id": clinic_id,
            "message": str(e),
        }