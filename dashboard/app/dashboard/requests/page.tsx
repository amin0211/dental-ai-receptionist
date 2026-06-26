"use client";

import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";
import DashboardShell from "@/components/layout/DashboardShell";
import { useClinic } from "@/components/providers/ClinicProvider";
import AppointmentScheduleEditor from "@/components/appointments/AppointmentScheduleEditor";

type AppointmentRequest = {
  id: string;
  patient_id: string | null;
  patient_name: string | null;
  patient_phone: string | null;
  reason: string | null;
  preferred_doctor_name: string | null;
  preferred_date_raw: string | null;
  preferred_time_raw: string | null;
  status: string | null;
  urgency: string | null;
  created_at: string;
  service_category_name?: string | null;
  duration_minutes?: number | null;
  doctor_id?: string | null;
  service_category_id?: string | null;
};

function formatDateTime(value: string) {
  const date = new Date(value);

  return date.toLocaleString("en-CA", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function getStatusBadgeClass(status: string | null) {
  switch (status) {
    case "new":
      return "bg-blue-50 text-blue-700 border-blue-200";
    case "needs_followup":
      return "bg-amber-50 text-amber-700 border-amber-200";
    case "slot_offered":
      return "bg-indigo-50 text-indigo-700 border-indigo-200";
    case "confirmed":
      return "bg-emerald-50 text-emerald-700 border-emerald-200";
    case "cancelled":
      return "bg-slate-100 text-slate-600 border-slate-200";
    default:
      return "bg-slate-50 text-slate-700 border-slate-200";
  }
}

function getStatusTitle(status: string | null) {
  switch (status) {
    case "new":
      return "New Requests";
    case "needs_followup":
      return "Needs Follow-up";
    case "slot_offered":
      return "Slot Offered";
    case "confirmed":
      return "Confirmed Requests";
    case "cancelled":
      return "Cancelled Requests";
    default:
      return "Latest Requests";
  }
}

export default function RequestsPage() {
  return (
    <Suspense fallback={<RequestsPageLoading />}>
      <RequestsPageContent />
    </Suspense>
  );
}

function RequestsPageLoading() {
  return (
    <DashboardShell
      title="Appointment Requests"
      description="Review and manage appointment requests created by the AI receptionist."
    >
      <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-sm font-medium text-slate-500">
        Loading requests...
      </div>
    </DashboardShell>
  );
}

function RequestsPageContent() {
  const searchParams = useSearchParams();
  const statusFilter = searchParams.get("status");

  const { clinicId, isLoadingClinic } = useClinic();

  const [requests, setRequests] = useState<AppointmentRequest[]>([]);
  const [selectedRequest, setSelectedRequest] =
    useState<AppointmentRequest | null>(null);

  const [isSchedulePickerOpen, setIsSchedulePickerOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isDetailOpen, setIsDetailOpen] = useState(false);

  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const [patientName, setPatientName] = useState("");
  const [patientPhone, setPatientPhone] = useState("");
  const [reason, setReason] = useState("");
  const [serviceCategoryName, setServiceCategoryName] = useState("");
  const [preferredDoctorName, setPreferredDoctorName] = useState("");
  const [preferredDateRaw, setPreferredDateRaw] = useState("");
  const [preferredTimeRaw, setPreferredTimeRaw] = useState("");
  const [urgency, setUrgency] = useState("normal");
  const [durationMinutes, setDurationMinutes] = useState("");

  const pageTitle = useMemo(() => getStatusTitle(statusFilter), [statusFilter]);

  async function loadRequests() {
    if (isLoadingClinic) return;

    setIsLoading(true);
    setErrorMessage("");

    if (!clinicId) {
      setErrorMessage("Clinic was not found for this account.");
      setIsLoading(false);
      return;
    }

    let query = supabase
      .from("appointment_requests")
      .select(
        `
        id,
        patient_id,
        patient_name,
        patient_phone,
        reason,
        doctor_id,
        service_category_id,
        preferred_doctor_name,
        preferred_date_raw,
        preferred_time_raw,
        status,
        urgency,
        created_at,
        service_category_name,
        duration_minutes
      `
      )
      .eq("clinic_id", clinicId)
      .order("created_at", { ascending: false })
      .limit(50);

    if (statusFilter) {
      query = query.eq("status", statusFilter);
    }

    const { data, error } = await query;

    if (error) {
      console.error("Error loading appointment requests:", error);
      setErrorMessage(error.message);
      setIsLoading(false);
      return;
    }

    setRequests(data || []);
    setIsLoading(false);
  }

  useEffect(() => {
    loadRequests();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clinicId, isLoadingClinic, statusFilter]);

  function openRequestDetail(request: AppointmentRequest) {
    setSelectedRequest(request);

    setPatientName(request.patient_name || "");
    setPatientPhone(request.patient_phone || "");
    setReason(request.reason || "");
    setServiceCategoryName(request.service_category_name || "");
    setPreferredDoctorName(request.preferred_doctor_name || "");
    setPreferredDateRaw(request.preferred_date_raw || "");
    setPreferredTimeRaw(request.preferred_time_raw || "");
    setUrgency(request.urgency || "normal");
    setDurationMinutes(
      request.duration_minutes ? String(request.duration_minutes) : ""
    );

    setIsDetailOpen(true);
  }

  async function handleSaveChanges(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedRequest) {
      setErrorMessage("No request selected.");
      return;
    }

    if (!clinicId) {
      setErrorMessage("Clinic was not found for this account.");
      return;
    }


    try {
      setIsSaving(true);
      setErrorMessage("");
      setSuccessMessage("");

      const durationNumber = durationMinutes.trim()
        ? Number(durationMinutes)
        : null;

      if (
        durationNumber !== null &&
        (!Number.isFinite(durationNumber) || durationNumber <= 0)
      ) {
        setErrorMessage("Duration must be a positive number.");
        setIsSaving(false);
        return;
      }

      const { error } = await supabase
        .from("appointment_requests")
        .update({
          patient_name: patientName.trim() ? patientName.trim() : null,
          patient_phone: patientPhone.trim() ? patientPhone.trim() : null,
          reason: reason.trim() ? reason.trim() : null,
          service_category_name: serviceCategoryName.trim()
            ? serviceCategoryName.trim()
            : null,
          preferred_doctor_name: preferredDoctorName.trim()
            ? preferredDoctorName.trim()
            : null,
          preferred_date_raw: preferredDateRaw.trim()
            ? preferredDateRaw.trim()
            : null,
          preferred_time_raw: preferredTimeRaw.trim()
            ? preferredTimeRaw.trim()
            : null,
          urgency,
          duration_minutes: durationNumber,
        })
        .eq("id", selectedRequest.id)
        .eq("clinic_id", clinicId);

      if (error) {
        throw new Error(error.message);
      }


      const updatedRequest: AppointmentRequest = {
        ...selectedRequest,
        patient_name: patientName.trim() ? patientName.trim() : null,
        patient_phone: patientPhone.trim() ? patientPhone.trim() : null,
        reason: reason.trim() ? reason.trim() : null,
        service_category_name: serviceCategoryName.trim()
          ? serviceCategoryName.trim()
          : null,
        preferred_doctor_name: preferredDoctorName.trim()
          ? preferredDoctorName.trim()
          : null,
        preferred_date_raw: preferredDateRaw.trim()
          ? preferredDateRaw.trim()
          : null,
        preferred_time_raw: preferredTimeRaw.trim()
          ? preferredTimeRaw.trim()
          : null,
        urgency,
        duration_minutes: durationNumber,
      };

      setSelectedRequest(updatedRequest);


      setSuccessMessage("Request updated successfully.");
      await loadRequests();

      setIsSaving(false);
    } catch (error) {
      console.error("Save request error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to update request."
      );
      setIsSaving(false);
    }
  }

async function handleChangeStatus(nextStatus: string) {
  if (!selectedRequest) {
    setErrorMessage("No request selected.");
    return;
  }

  if (!clinicId) {
    setErrorMessage("Clinic was not found for this account.");
    return;
  }

  if (nextStatus === "confirmed") {
    setIsSchedulePickerOpen(true);
    return;
  }

  try {
    setIsSaving(true);
    setErrorMessage("");
    setSuccessMessage("");

    const { data, error } = await supabase
      .from("appointment_requests")
      .update({
        status: nextStatus,
      })
      .eq("id", selectedRequest.id)
      .eq("clinic_id", clinicId)
      .select("id, status")
      .single();

    if (error) {
      throw new Error(error.message);
    }

    if (!data?.id) {
      throw new Error("Request status was not updated.");
    }

    setSuccessMessage(`Request moved to ${nextStatus}.`);
    setIsDetailOpen(false);
    setSelectedRequest(null);

    await loadRequests();

    setIsSaving(false);
  } catch (error) {
    console.error("Update request status error:", error);
    setErrorMessage(
      error instanceof Error
        ? error.message
        : "Failed to update request status."
    );
    setIsSaving(false);
  }
}

  if (isLoadingClinic) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50">
        <p className="text-sm font-medium text-slate-500">
          Loading clinic...
        </p>
      </main>
    );
  }

  return (
    <DashboardShell
      title="Appointment Requests"
      description="Review and manage appointment requests created by the AI receptionist."
    >
      {successMessage && (
        <div className="mb-6 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          {successMessage}
        </div>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-lg font-bold text-slate-900">{pageTitle}</h2>

          <p className="mt-1 text-sm text-slate-500">
            {statusFilter
              ? `Showing latest 50 requests with status: ${statusFilter}.`
              : "Showing the latest 50 requests."}
          </p>
        </div>

        {isLoading && (
          <div className="p-6 text-sm font-medium text-slate-500">
            Loading requests...
          </div>
        )}

        {errorMessage && (
          <div className="m-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {errorMessage}
          </div>
        )}

        {!isLoading && !errorMessage && requests.length === 0 && (
          <div className="p-6 text-sm text-slate-500">
            No appointment requests found.
          </div>
        )}

        {!isLoading && !errorMessage && requests.length > 0 && (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
              <thead className="bg-slate-50">
                <tr>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Created
                  </th>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Patient
                  </th>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Phone
                  </th>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Reason
                  </th>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Service
                  </th>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Doctor
                  </th>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Preferred
                  </th>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Status
                  </th>
                  <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Urgency
                  </th>
                  <th className="sticky right-0 z-10 bg-slate-50 px-5 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Actions
                  </th>
                </tr>
              </thead>

              <tbody className="divide-y divide-slate-200 bg-white">
                {requests.map((request) => (
                  <tr key={request.id} className="hover:bg-slate-50">
                    <td className="whitespace-nowrap px-5 py-4 text-slate-600">
                      {formatDateTime(request.created_at)}
                    </td>

                    <td className="px-5 py-4 font-medium text-slate-900">
                      {request.patient_name || "Unknown"}
                    </td>

                    <td className="whitespace-nowrap px-5 py-4 text-slate-600">
                      {request.patient_phone || "-"}
                    </td>

                    <td className="px-5 py-4 text-slate-700">
                      {request.reason || "-"}
                    </td>

                    <td className="px-5 py-4 text-slate-700">
                      <div>{request.service_category_name || "-"}</div>

                      {request.duration_minutes && (
                        <div className="mt-1 text-xs text-slate-400">
                          {request.duration_minutes} min
                        </div>
                      )}
                    </td>

                    <td className="px-5 py-4 text-slate-700">
                      {request.preferred_doctor_name || "-"}
                    </td>

                    <td className="px-5 py-4 text-slate-700">
                      <div>{request.preferred_date_raw || "-"}</div>
                      <div className="mt-1 text-xs text-slate-400">
                        {request.preferred_time_raw || ""}
                      </div>
                    </td>

                    <td className="px-5 py-4">
                      <span
                        className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${getStatusBadgeClass(
                          request.status
                        )}`}
                      >
                        {request.status || "unknown"}
                      </span>
                    </td>

                    <td className="px-5 py-4 text-slate-700">
                      {request.urgency || "-"}
                    </td>

                    <td className="sticky right-0 bg-white px-5 py-4 text-right align-top shadow-[-8px_0_12px_-12px_rgba(15,23,42,0.35)]">
                      <button
                        type="button"
                        onClick={() => openRequestDetail(request)}
                        className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
                      >
                        Review
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {isDetailOpen && selectedRequest && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="max-h-[92vh] w-full max-w-4xl overflow-y-auto rounded-2xl bg-white shadow-xl">
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  Review Request
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Edit request details and choose the next status.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setIsDetailOpen(false)}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
              >
                Close
              </button>
            </div>

            <form onSubmit={handleSaveChanges} className="space-y-5 p-5">
            <div className="grid grid-cols-1 gap-x-4 gap-y-5 md:grid-cols-3">
              <div>
                <label className="text-sm font-medium text-slate-700">
                  Patient Name
                </label>
                <input
                  value={patientName}
                  onChange={(event) => setPatientName(event.target.value)}
                  className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Patient Phone
                </label>
                <input
                  value={patientPhone}
                  onChange={(event) => setPatientPhone(event.target.value)}
                  className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Reason
                </label>
                <input
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Service
                </label>
                <input
                  value={serviceCategoryName}
                  onChange={(event) => setServiceCategoryName(event.target.value)}
                  className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Preferred Doctor
                </label>
                <input
                  value={preferredDoctorName}
                  onChange={(event) => setPreferredDoctorName(event.target.value)}
                  className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Urgency
                </label>
                <select
                  value={urgency}
                  onChange={(event) => setUrgency(event.target.value)}
                  className="mt-2 h-[58px] w-full rounded-xl border border-slate-300 bg-white px-4 text-sm outline-none focus:border-blue-500"
                >
                  <option value="low">Low</option>
                  <option value="normal">Normal</option>
                  <option value="urgent">Urgent</option>
                  <option value="emergency">Emergency</option>
                </select>
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Preferred Date
                </label>
                <input
                  value={preferredDateRaw}
                  onChange={(event) => setPreferredDateRaw(event.target.value)}
                  placeholder="Example: next Monday"
                  className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Preferred Time
                </label>
                <input
                  value={preferredTimeRaw}
                  onChange={(event) => setPreferredTimeRaw(event.target.value)}
                  placeholder="Example: afternoon"
                  className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Duration Minutes
                </label>
                <input
                  type="number"
                  min="1"
                  value={durationMinutes}
                  onChange={(event) => setDurationMinutes(event.target.value)}
                  className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>
            </div>


              <button
                type="submit"
                disabled={isSaving}
                className="w-full rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSaving ? "Saving..." : "Save Changes"}
              </button>
            </form>

            <div className="border-t border-slate-100 p-5">
              <h3 className="text-sm font-bold text-slate-900">
                Change Status
              </h3>

              <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-4">
                <button
                  type="button"
                  disabled={isSaving}
                  onClick={() => handleChangeStatus("needs_followup")}
                  className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm font-semibold text-amber-800 hover:bg-amber-100 disabled:opacity-60"
                >
                  Needs Follow-up
                </button>

                <button
                  type="button"
                  disabled={isSaving}
                  onClick={() => handleChangeStatus("slot_offered")}
                  className="rounded-xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm font-semibold text-indigo-800 hover:bg-indigo-100 disabled:opacity-60"
                >
                  Slot Offered
                </button>

                <button
                  type="button"
                  disabled={isSaving}
                  onClick={() => handleChangeStatus("confirmed")}
                  className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-800 hover:bg-emerald-100 disabled:opacity-60"
                >
                  Confirm
                </button>

                <button
                  type="button"
                  disabled={isSaving}
                  onClick={() => handleChangeStatus("cancelled")}
                  className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-800 hover:bg-red-100 disabled:opacity-60"
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {isSchedulePickerOpen && selectedRequest && clinicId && (
        <AppointmentScheduleEditor
          mode="confirm"
          clinicId={clinicId}
          request={selectedRequest}
          onClose={() => setIsSchedulePickerOpen(false)}
          onSaved={async () => {
            setIsSchedulePickerOpen(false);
            setIsDetailOpen(false);
            setSelectedRequest(null);
            await loadRequests();
          }}
        />
      )}  
    </DashboardShell>
  );
}