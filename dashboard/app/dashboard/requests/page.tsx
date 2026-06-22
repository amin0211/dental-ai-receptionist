"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";
import DashboardShell from "@/components/layout/DashboardShell";
import { useClinic } from "@/components/providers/ClinicProvider";

type AppointmentRequest = {
  id: string;
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
  const searchParams = useSearchParams();
  const statusFilter = searchParams.get("status");

  const { clinicId, isLoadingClinic } = useClinic();

  const [requests, setRequests] = useState<AppointmentRequest[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  const pageTitle = useMemo(() => getStatusTitle(statusFilter), [statusFilter]);

  useEffect(() => {
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
          patient_name,
          patient_phone,
          reason,
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

    loadRequests();
  }, [clinicId, isLoadingClinic, statusFilter]);

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
      description="Review appointment requests created by the AI receptionist."
    >
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
            <table className="w-full min-w-[1000px] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-5 py-3 font-semibold">Created</th>
                  <th className="px-5 py-3 font-semibold">Patient</th>
                  <th className="px-5 py-3 font-semibold">Phone</th>
                  <th className="px-5 py-3 font-semibold">Reason</th>
                  <th className="px-5 py-3 font-semibold">Service</th>
                  <th className="px-5 py-3 font-semibold">Doctor</th>
                  <th className="px-5 py-3 font-semibold">Preferred</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold">Urgency</th>
                </tr>
              </thead>

              <tbody className="divide-y divide-slate-100">
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
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </DashboardShell>
  );
}