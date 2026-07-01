from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

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
    import_pms_service_groups_to_db,
    import_pms_services_to_db,
    replace_pms_availability_rules_for_date_range,
    replace_pms_appointments_for_date_range,
    assign_all_services_to_all_pms_doctors,
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
        doctor_service_result = assign_all_services_to_all_pms_doctors(
            clinic_id=clinic_id,
            pms_connection_id=connection_id,
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
            "doctor_service_assignment": doctor_service_result,
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
    
@router.post("/import-service-groups/{clinic_id}")
async def import_pms_service_groups(clinic_id: str):
    """
    Imports service groups/categories from the active PMS connection into service_groups.
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

        if not hasattr(client, "list_service_groups"):
            return {
                "ok": False,
                "type": "unsupported_service_groups_import",
                "message": "This PMS client does not support service group import yet.",
                "clinic_id": clinic_id,
                "connection_id": connection_id,
                "pms_type": connection.get("pms_type"),
            }

        groups = await client.list_service_groups()

        result = import_pms_service_groups_to_db(
            clinic_id=clinic_id,
            connection=connection,
            groups=groups,
        )

        mark_pms_connection_success(connection_id)

        return {
            "ok": True,
            "mode": "manual_service_group_import",
            "clinic_id": clinic_id,
            "connection_id": connection_id,
            "pms_type": connection.get("pms_type"),
            "pulled_count": len(groups),
            "imported_count": result["imported_count"],
            "failed_count": result["failed_count"],
            "failed": result["failed"][:20],
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

@router.post("/import-services/{clinic_id}")
async def import_pms_services(clinic_id: str):
    """
    Imports services/procedure codes from the active PMS connection into service_categories.
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

        if not hasattr(client, "list_services"):
            return {
                "ok": False,
                "type": "unsupported_services_import",
                "message": "This PMS client does not support services/procedure import yet.",
                "clinic_id": clinic_id,
                "connection_id": connection_id,
                "pms_type": connection.get("pms_type"),
            }

        # Important:
        # Import groups first so procedure codes can link to service_group_id.
        if hasattr(client, "list_service_groups"):
            groups = await client.list_service_groups()

            import_pms_service_groups_to_db(
                clinic_id=clinic_id,
                connection=connection,
                groups=groups,
            )

        services = await client.list_services()

        result = import_pms_services_to_db(
            clinic_id=clinic_id,
            connection=connection,
            services=services,
        )
        doctor_service_result = assign_all_services_to_all_pms_doctors(
            clinic_id=clinic_id,
            pms_connection_id=connection_id,
        )

        mark_pms_connection_success(connection_id)

        return {
            "ok": True,
            "mode": "manual_service_import",
            "clinic_id": clinic_id,
            "connection_id": connection_id,
            "pms_type": connection.get("pms_type"),
            "pulled_count": len(services),
            "imported_count": result["imported_count"],
            "failed_count": result["failed_count"],
            "doctor_service_assignment": doctor_service_result,
            "failed": result["failed"][:20],
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


@router.post("/import-availability/{clinic_id}")
async def import_pms_availability(
    clinic_id: str,
    date_start: str | None = None,
    date_end: str | None = None,
    days_ahead: int = 90,
):
    """
    Replaces provider availability cache from the active PMS connection.

    Behavior:
    - If date_start/date_end are provided, replaces that exact range.
    - If not provided, replaces today through today + days_ahead.
    - Old PMS-synced availability rows in the range are deleted first.
    - Manual dashboard rules are not touched.

    Example:
    POST /pms/import-availability/{clinic_id}

    Example with range:
    POST /pms/import-availability/{clinic_id}?date_start=2026-07-01&date_end=2026-09-30
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
        if not date_start or not date_end:
            timezone_name = connection.get("timezone") or "America/Vancouver"
            tz = ZoneInfo(timezone_name)

            today = datetime.now(tz).date()
            end_day = today + timedelta(days=days_ahead)

            date_start = today.isoformat()
            date_end = end_day.isoformat()

        client = get_pms_client_from_connection(connection)

        if not hasattr(client, "list_availability_rules"):
            return {
                "ok": False,
                "type": "unsupported_availability_import",
                "message": "This PMS client does not support availability import yet.",
                "clinic_id": clinic_id,
                "connection_id": connection_id,
                "pms_type": connection.get("pms_type"),
            }

        # Make sure providers exist locally before linking availability to doctor_id.
        if hasattr(client, "list_providers"):
            doctors = await client.list_providers()

            import_pms_doctors_to_db(
                clinic_id=clinic_id,
                connection=connection,
                doctors=doctors,
            )

        rules = await client.list_availability_rules(
            date_start=date_start,
            date_end=date_end,
        )

        result = replace_pms_availability_rules_for_date_range(
            clinic_id=clinic_id,
            connection=connection,
            rules=rules,
            date_start=date_start,
            date_end=date_end,
        )

        mark_pms_connection_success(connection_id)

        return {
            "ok": True,
            "mode": "replace_availability_window",
            "clinic_id": clinic_id,
            "connection_id": connection_id,
            "pms_type": connection.get("pms_type"),
            "date_start": date_start,
            "date_end": date_end,
            "days_ahead": days_ahead,
            "pulled_count": len(rules),
            "deleted_count": result["deleted_count"],
            "imported_count": result["imported_count"],
            "failed_count": result["failed_count"],
            "failed": result["failed"][:20],
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
    
@router.post("/import-appointments/{clinic_id}")
async def import_pms_appointments(
    clinic_id: str,
    date_start: str | None = None,
    date_end: str | None = None,
    days_ahead: int = 90,
):
    """
    Replaces appointment cache from the active PMS connection.

    Behavior:
    - If date_start/date_end are provided, replaces that exact range.
    - If not provided, replaces today through today + days_ahead.
    - Old PMS-synced appointments in the range are deleted first.
    - AI/manual appointments are not touched.

    Example:
    POST /pms/import-appointments/{clinic_id}

    Example with range:
    POST /pms/import-appointments/{clinic_id}?date_start=2026-07-01&date_end=2026-09-30
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
        timezone_name = connection.get("timezone") or "America/Vancouver"

        if not date_start or not date_end:
            tz = ZoneInfo(timezone_name)

            today = datetime.now(tz).date()
            end_day = today + timedelta(days=days_ahead)

            date_start = today.isoformat()
            date_end = end_day.isoformat()

        client = get_pms_client_from_connection(connection)

        if not hasattr(client, "list_appointments"):
            return {
                "ok": False,
                "type": "unsupported_appointment_import",
                "message": "This PMS client does not support appointment import yet.",
                "clinic_id": clinic_id,
                "connection_id": connection_id,
                "pms_type": connection.get("pms_type"),
            }

        # Make sure doctors and patients are likely present locally.
        # Doctors are cheap to sync here because appointments need provider mapping.
        if hasattr(client, "list_providers"):
            doctors = await client.list_providers()

            import_pms_doctors_to_db(
                clinic_id=clinic_id,
                connection=connection,
                doctors=doctors,
            )

        appointments = await client.list_appointments(
            date_start=date_start,
            date_end=date_end,
            limit=500,
            offset=0,
        )

        result = replace_pms_appointments_for_date_range(
            clinic_id=clinic_id,
            connection=connection,
            appointments=appointments,
            date_start=date_start,
            date_end=date_end,
            timezone_name=timezone_name,
        )

        mark_pms_connection_success(connection_id)

        return {
            "ok": True,
            "mode": "replace_appointments_window",
            "clinic_id": clinic_id,
            "connection_id": connection_id,
            "pms_type": connection.get("pms_type"),
            "date_start": date_start,
            "date_end": date_end,
            "days_ahead": days_ahead,
            "pulled_count": len(appointments),
            "deleted_count": result["deleted_count"],
            "imported_count": result["imported_count"],
            "failed_count": result["failed_count"],
            "failed": result["failed"][:20],
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