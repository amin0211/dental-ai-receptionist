from fastapi import APIRouter

from pms.base import PmsApiError
from pms.factory import UnsupportedPmsError, get_pms_client_from_connection
from supabase_service import (
    get_active_pms_connection_for_clinic,
    get_pms_sync_state,
    import_pms_patients_to_db,
    mark_pms_connection_error,
    mark_pms_connection_success,
    mark_pms_sync_error,
    mark_pms_sync_started,
    mark_pms_sync_success,
    import_pms_doctors_to_db,
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
    """
    Simple import endpoint.
    Useful for quick manual testing.
    """

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
            "mode": "manual_import",
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


@router.post("/sync-patients/{clinic_id}")
async def sync_pms_patients(
    clinic_id: str,
    max_pages: int = 25,
):
    """
    Real patient sync endpoint.

    For Open Dental:
    - initial sync: reads all pages from /patients/Simple using Offset
    - incremental sync: uses cursor.date_tstamp as DateTStamp filter
    - after successful sync: stores max_pms_updated_at as next cursor
    """

    resource = "patients"

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

        if not hasattr(client, "list_patients_page"):
            return {
                "ok": False,
                "type": "unsupported_patient_paging",
                "message": "This PMS client does not support paged patient sync yet.",
                "clinic_id": clinic_id,
                "connection_id": connection_id,
                "pms_type": connection.get("pms_type"),
            }

        mark_pms_sync_started(
            clinic_id=clinic_id,
            pms_connection_id=connection_id,
            resource=resource,
        )

        state = get_pms_sync_state(
            clinic_id=clinic_id,
            pms_connection_id=connection_id,
            resource=resource,
        )

        cursor = (state or {}).get("cursor") or {}
        date_tstamp = cursor.get("date_tstamp")

        offset = 0
        page_count = 0
        pulled_count = 0
        imported_count = 0
        failed_count = 0
        all_failed = []
        max_pms_updated_at = date_tstamp

        while page_count < max_pages:
            page = await client.list_patients_page(
                offset=offset,
                date_tstamp=date_tstamp,
            )

            patients = page.get("patients") or []
            raw_count = page.get("raw_count") or 0

            if raw_count <= 0 or not patients:
                break

            pulled_count += len(patients)

            import_result = import_pms_patients_to_db(
                clinic_id=clinic_id,
                connection=connection,
                patients=patients,
            )

            imported_count += import_result.get("imported_count", 0)
            failed_count += import_result.get("failed_count", 0)
            all_failed.extend(import_result.get("failed", []))

            page_max_updated = page.get("max_pms_updated_at")

            if page_max_updated:
                if not max_pms_updated_at or page_max_updated > max_pms_updated_at:
                    max_pms_updated_at = page_max_updated

            offset = page.get("next_offset") or (offset + raw_count)
            page_count += 1

        next_cursor = {
            "date_tstamp": max_pms_updated_at,
            "last_offset": offset,
            "last_page_count": page_count,
            "last_pulled_count": pulled_count,
        }

        mark_pms_sync_success(
            clinic_id=clinic_id,
            pms_connection_id=connection_id,
            resource=resource,
            cursor=next_cursor,
        )

        mark_pms_connection_success(connection_id)

        return {
            "ok": True,
            "mode": "real_sync",
            "clinic_id": clinic_id,
            "connection_id": connection_id,
            "pms_type": connection.get("pms_type"),
            "resource": resource,
            "used_date_tstamp": date_tstamp,
            "next_cursor": next_cursor,
            "page_count": page_count,
            "pulled_count": pulled_count,
            "imported_count": imported_count,
            "failed_count": failed_count,
            "failed": all_failed[:20],
        }

    except PmsApiError as e:
        error_message = f"{e.message}: {e.response_body}"

        mark_pms_connection_error(connection_id, error_message)
        mark_pms_sync_error(
            clinic_id=clinic_id,
            pms_connection_id=connection_id,
            resource=resource,
            error_message=error_message,
        )

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
        error_message = str(e)

        mark_pms_connection_error(connection_id, error_message)
        mark_pms_sync_error(
            clinic_id=clinic_id,
            pms_connection_id=connection_id,
            resource=resource,
            error_message=error_message,
        )

        return {
            "ok": False,
            "type": "unsupported_pms",
            "connection_id": connection_id,
            "clinic_id": clinic_id,
            "message": error_message,
        }

    except Exception as e:
        error_message = str(e)

        mark_pms_connection_error(connection_id, error_message)
        mark_pms_sync_error(
            clinic_id=clinic_id,
            pms_connection_id=connection_id,
            resource=resource,
            error_message=error_message,
        )

        return {
            "ok": False,
            "type": "server_error",
            "connection_id": connection_id,
            "clinic_id": clinic_id,
            "message": error_message,
        }
    
@router.post("/import-doctors/{clinic_id}")
async def import_pms_doctors(clinic_id: str):
    """
    Imports providers/doctors from the active PMS connection into clinic_doctors.
    """

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

        doctors = await client.list_providers()

        result = import_pms_doctors_to_db(
            clinic_id=clinic_id,
            connection=connection,
            doctors=doctors,
        )

        mark_pms_connection_success(connection_id)

        return {
            "ok": True,
            "mode": "manual_doctor_import",
            "clinic_id": clinic_id,
            "connection_id": connection_id,
            "pms_type": connection.get("pms_type"),
            "pulled_count": len(doctors),
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