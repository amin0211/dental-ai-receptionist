"use client";

import { useEffect, useMemo, useState } from "react";
import DashboardShell from "@/components/layout/DashboardShell";
import { useClinic } from "@/components/providers/ClinicProvider";
import { supabase } from "@/lib/supabaseClient";
import {
  ClinicDoctor,
  ServiceCategory,
  getClinicDoctors,
  getServiceCategories,
} from "@/lib/supabaseService";

type AppointmentPatient = {
  id: string;
  full_name: string;
  phone_primary: string | null;
  phone_secondary: string | null;
  email: string | null;
};

type AppointmentReportRow = {
  id: string;
  clinic_id: string;
  appointment_request_id: string | null;
  patient_id: string | null;
  doctor_id: string | null;
  service_category_id: string | null;
  service_name: string | null;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  status: string;
  source: string | null;
  notes: string | null;
  reason: string | null;
  urgency: string | null;
  created_at: string;
  updated_at: string;
  patient: AppointmentPatient | null;
};

function normalizeAppointmentRows(rows: any[]): AppointmentReportRow[] {
  return rows.map((row) => {
    const patientValue = row.patient;

    const patient = Array.isArray(patientValue)
      ? patientValue[0] || null
      : patientValue || null;

    return {
      ...row,
      patient,
    } as AppointmentReportRow;
  });
}

function getTodayDateString() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function getThirtyDaysAgoDateString() {
  const date = new Date();
  date.setDate(date.getDate() - 30);

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function isValidDateString(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    return false;
  }

  const date = new Date(`${value}T00:00:00`);
  return !Number.isNaN(date.getTime());
}

function getDateRange(fromDate: string, toDate: string) {
  const start = new Date(`${fromDate}T00:00:00`);
  const end = new Date(`${toDate}T00:00:00`);
  end.setDate(end.getDate() + 1);

  return {
    startIso: start.toISOString(),
    endIso: end.toISOString(),
  };
}

function formatDateOnly(value: string) {
  const date = new Date(value);

  return date.toLocaleDateString("en-CA", {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

function formatDateTime(value: string) {
  const date = new Date(value);

  return date.toLocaleString("en-CA", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });
}

function formatTimeRange(startTime: string, endTime: string) {
  const start = new Date(startTime);
  const end = new Date(endTime);

  const startLabel = start.toLocaleTimeString("en-CA", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });

  const endLabel = end.toLocaleTimeString("en-CA", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: true,
  });

  return `${startLabel} - ${endLabel}`;
}

function csvEscape(value: string | number | null | undefined) {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

function getStatusBadgeClass(status: string | null | undefined) {
  if (status === "confirmed") {
    return "bg-emerald-50 text-emerald-700 ring-emerald-200";
  }

  if (status === "cancelled") {
    return "bg-red-50 text-red-700 ring-red-200";
  }

  if (status === "completed") {
    return "bg-blue-50 text-blue-700 ring-blue-200";
  }

  if (status === "no_show") {
    return "bg-amber-50 text-amber-700 ring-amber-200";
  }

  return "bg-slate-50 text-slate-700 ring-slate-200";
}

function getUrgencyBadgeClass(urgency: string | null | undefined) {
  if (urgency === "emergency") {
    return "bg-red-50 text-red-700 ring-red-200";
  }

  if (urgency === "urgent") {
    return "bg-amber-50 text-amber-700 ring-amber-200";
  }

  return "bg-slate-50 text-slate-700 ring-slate-200";
}

function SummaryCard({
  label,
  value,
  valueClassName = "text-slate-900",
}: {
  label: string;
  value: string | number;
  valueClassName?: string;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
      <p className="text-[11px] font-bold uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className={`mt-2 text-2xl font-bold ${valueClassName}`}>{value}</p>
    </div>
  );
}

export default function AppointmentReportPage() {
  const { clinicId, isLoadingClinic } = useClinic();

  const [appointments, setAppointments] = useState<AppointmentReportRow[]>([]);
  const [doctors, setDoctors] = useState<ClinicDoctor[]>([]);
  const [services, setServices] = useState<ServiceCategory[]>([]);

  const [fromDate, setFromDate] = useState(getThirtyDaysAgoDateString());
  const [toDate, setToDate] = useState(getTodayDateString());

  const [patientSearch, setPatientSearch] = useState("");
  const [selectedDoctorId, setSelectedDoctorId] = useState("");
  const [selectedServiceId, setSelectedServiceId] = useState("");
  const [selectedStatus, setSelectedStatus] = useState("");
  const [selectedSource, setSelectedSource] = useState("");
  const [selectedUrgency, setSelectedUrgency] = useState("");

  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  const doctorNameById = useMemo(() => {
    const map: Record<string, string> = {};

    doctors.forEach((doctor) => {
      map[doctor.id] = doctor.display_name || doctor.full_name;
    });

    return map;
  }, [doctors]);

  const filteredAppointments = useMemo(() => {
    const search = patientSearch.trim().toLowerCase();

    if (!search) return appointments;

    return appointments.filter((appointment) => {
      const patientName = appointment.patient?.full_name?.toLowerCase() || "";
      const primaryPhone = appointment.patient?.phone_primary || "";
      const secondaryPhone = appointment.patient?.phone_secondary || "";
      const email = appointment.patient?.email?.toLowerCase() || "";

      return (
        patientName.includes(search) ||
        primaryPhone.includes(search) ||
        secondaryPhone.includes(search) ||
        email.includes(search)
      );
    });
  }, [appointments, patientSearch]);

  const summary = useMemo(() => {
    const total = filteredAppointments.length;

    const confirmed = filteredAppointments.filter(
      (appointment) => appointment.status === "confirmed"
    ).length;

    const cancelled = filteredAppointments.filter(
      (appointment) => appointment.status === "cancelled"
    ).length;

    const completed = filteredAppointments.filter(
      (appointment) => appointment.status === "completed"
    ).length;

    const noShow = filteredAppointments.filter(
      (appointment) => appointment.status === "no_show"
    ).length;

    const totalMinutes = filteredAppointments.reduce(
      (sum, appointment) => sum + (appointment.duration_minutes || 0),
      0
    );

    return {
      total,
      confirmed,
      cancelled,
      completed,
      noShow,
      totalMinutes,
    };
  }, [filteredAppointments]);

  async function loadFilters() {
    if (!clinicId) return;

    const [loadedDoctors, loadedServices] = await Promise.all([
      getClinicDoctors(clinicId),
      getServiceCategories(clinicId),
    ]);

    setDoctors(loadedDoctors);
    setServices(loadedServices);
  }

  async function loadReport() {
    if (isLoadingClinic) return;

    setIsLoading(true);
    setErrorMessage("");

    if (!clinicId) {
      setErrorMessage("Clinic was not found for this account.");
      setIsLoading(false);
      return;
    }

    if (!isValidDateString(fromDate) || !isValidDateString(toDate)) {
      setAppointments([]);
      setErrorMessage("Dates must be in YYYY-MM-DD format.");
      setIsLoading(false);
      return;
    }

    const { startIso, endIso } = getDateRange(fromDate, toDate);

    let query = supabase
      .from("appointments")
      .select(
        `
        id,
        clinic_id,
        appointment_request_id,
        patient_id,
        doctor_id,
        service_category_id,
        service_name,
        start_time,
        end_time,
        duration_minutes,
        status,
        source,
        notes,
        reason,
        urgency,
        created_at,
        updated_at,
        patient:patients (
          id,
          full_name,
          phone_primary,
          phone_secondary,
          email
        )
      `
      )
      .eq("clinic_id", clinicId)
      .gte("start_time", startIso)
      .lt("start_time", endIso)
      .order("start_time", { ascending: false });

    if (selectedDoctorId) {
      query = query.eq("doctor_id", selectedDoctorId);
    }

    if (selectedServiceId) {
      query = query.eq("service_category_id", selectedServiceId);
    }

    if (selectedStatus) {
      query = query.eq("status", selectedStatus);
    }

    if (selectedSource) {
      query = query.eq("source", selectedSource);
    }

    if (selectedUrgency) {
      query = query.eq("urgency", selectedUrgency);
    }

    const { data, error } = await query;

    if (error) {
      console.error("Load appointment report error:", error);
      setErrorMessage(error.message);
      setIsLoading(false);
      return;
    }

    setAppointments(normalizeAppointmentRows(data || []));
    setIsLoading(false);
  }

  function resetFilters() {
    setFromDate(getThirtyDaysAgoDateString());
    setToDate(getTodayDateString());
    setPatientSearch("");
    setSelectedDoctorId("");
    setSelectedServiceId("");
    setSelectedStatus("");
    setSelectedSource("");
    setSelectedUrgency("");
    setErrorMessage("");
  }

  function exportCsv() {
    const headers = [
      "Appointment ID",
      "Date/Time",
      "Time Range",
      "Patient",
      "Phone",
      "Email",
      "Doctor",
      "Service",
      "Status",
      "Source",
      "Urgency",
      "Duration Minutes",
      "Reason",
      "Notes",
      "Created At",
    ];

    const rows = filteredAppointments.map((appointment) => [
      appointment.id,
      formatDateTime(appointment.start_time),
      formatTimeRange(appointment.start_time, appointment.end_time),
      appointment.patient?.full_name || "",
      appointment.patient?.phone_primary ||
        appointment.patient?.phone_secondary ||
        "",
      appointment.patient?.email || "",
      appointment.doctor_id
        ? doctorNameById[appointment.doctor_id] || "Doctor"
        : "",
      appointment.service_name || "",
      appointment.status || "",
      appointment.source || "",
      appointment.urgency || "",
      appointment.duration_minutes || 0,
      appointment.reason || "",
      appointment.notes || "",
      formatDateTime(appointment.created_at),
    ]);

    const csvContent = [headers, ...rows]
      .map((row) => row.map(csvEscape).join(","))
      .join("\n");

    const blob = new Blob([csvContent], {
      type: "text/csv;charset=utf-8;",
    });

    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = url;
    link.download = `appointment-report-${fromDate}-to-${toDate}.csv`;
    link.click();

    URL.revokeObjectURL(url);
  }

  useEffect(() => {
    async function loadPage() {
      if (isLoadingClinic) return;

      try {
        await loadFilters();
        await loadReport();
      } catch (error) {
        console.error("Load appointment report page error:", error);
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Failed to load appointment report."
        );
        setIsLoading(false);
      }
    }

    loadPage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clinicId, isLoadingClinic]);

  useEffect(() => {
    loadReport();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    fromDate,
    toDate,
    selectedDoctorId,
    selectedServiceId,
    selectedStatus,
    selectedSource,
    selectedUrgency,
  ]);

  if (isLoadingClinic) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50">
        <p className="text-sm font-medium text-slate-500">Loading clinic...</p>
      </main>
    );
  }

  return (
    <DashboardShell
      title="Appointment Report"
      description="Analyze appointments by patient, date range, doctor, service, status, and source."
    >
      {errorMessage && (
        <div className="mb-5 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage}
        </div>
      )}

      <section className="mb-5 grid grid-cols-6 gap-3">
        <SummaryCard label="Total" value={summary.total} />
        <SummaryCard
          label="Confirmed"
          value={summary.confirmed}
          valueClassName="text-emerald-700"
        />
        <SummaryCard
          label="Cancelled"
          value={summary.cancelled}
          valueClassName="text-red-700"
        />
        <SummaryCard
          label="Completed"
          value={summary.completed}
          valueClassName="text-blue-700"
        />
        <SummaryCard
          label="No-show"
          value={summary.noShow}
          valueClassName="text-amber-700"
        />
        <SummaryCard label="Minutes" value={summary.totalMinutes} />
      </section>

      <section className="mb-5 rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="text-base font-bold text-slate-900">
              Report Filters
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Filter appointment records by date, patient, doctor, service, status, source, and urgency.
            </p>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              onClick={loadReport}
              className="h-10 rounded-xl bg-blue-600 px-4 text-sm font-semibold text-white hover:bg-blue-700"
            >
              Refresh
            </button>

            <button
              type="button"
              onClick={resetFilters}
              className="h-10 rounded-xl border border-slate-300 px-4 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              Reset
            </button>

            <button
              type="button"
              onClick={exportCsv}
              disabled={filteredAppointments.length === 0}
              className="h-10 rounded-xl border border-emerald-300 bg-emerald-50 px-4 text-sm font-semibold text-emerald-700 hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Export CSV
            </button>
          </div>
        </div>

        <div className="p-5">
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="text-sm font-medium text-slate-700">
                From date
              </label>
              <input
                type="text"
                value={fromDate}
                onChange={(event) => setFromDate(event.target.value)}
                placeholder="YYYY-MM-DD"
                className="mt-2 h-11 w-full rounded-xl border border-slate-300 bg-white px-4 text-sm outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                To date
              </label>
              <input
                type="text"
                value={toDate}
                onChange={(event) => setToDate(event.target.value)}
                placeholder="YYYY-MM-DD"
                className="mt-2 h-11 w-full rounded-xl border border-slate-300 bg-white px-4 text-sm outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Patient
              </label>
              <input
                type="text"
                value={patientSearch}
                onChange={(event) => setPatientSearch(event.target.value)}
                placeholder="Search name, phone, or email"
                className="mt-2 h-11 w-full rounded-xl border border-slate-300 bg-white px-4 text-sm outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Doctor
              </label>
              <select
                value={selectedDoctorId}
                onChange={(event) => setSelectedDoctorId(event.target.value)}
                className="mt-2 h-11 w-full rounded-xl border border-slate-300 bg-white px-4 text-sm outline-none focus:border-blue-500"
              >
                <option value="">All doctors</option>
                {doctors.map((doctor) => (
                  <option key={doctor.id} value={doctor.id}>
                    {doctor.display_name || doctor.full_name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Service
              </label>
              <select
                value={selectedServiceId}
                onChange={(event) => setSelectedServiceId(event.target.value)}
                className="mt-2 h-11 w-full rounded-xl border border-slate-300 bg-white px-4 text-sm outline-none focus:border-blue-500"
              >
                <option value="">All services</option>
                {services.map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.name}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Status
              </label>
              <select
                value={selectedStatus}
                onChange={(event) => setSelectedStatus(event.target.value)}
                className="mt-2 h-11 w-full rounded-xl border border-slate-300 bg-white px-4 text-sm outline-none focus:border-blue-500"
              >
                <option value="">All statuses</option>
                <option value="confirmed">Confirmed</option>
                <option value="cancelled">Cancelled</option>
                <option value="completed">Completed</option>
                <option value="no_show">No-show</option>
              </select>
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Source
              </label>
              <select
                value={selectedSource}
                onChange={(event) => setSelectedSource(event.target.value)}
                className="mt-2 h-11 w-full rounded-xl border border-slate-300 bg-white px-4 text-sm outline-none focus:border-blue-500"
              >
                <option value="">All sources</option>
                <option value="dashboard">Dashboard</option>
                <option value="ai">AI</option>
                <option value="request">Request</option>
                <option value="manual">Manual</option>
              </select>
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Urgency
              </label>
              <select
                value={selectedUrgency}
                onChange={(event) => setSelectedUrgency(event.target.value)}
                className="mt-2 h-11 w-full rounded-xl border border-slate-300 bg-white px-4 text-sm outline-none focus:border-blue-500"
              >
                <option value="">All urgency</option>
                <option value="normal">Normal</option>
                <option value="urgent">Urgent</option>
                <option value="emergency">Emergency</option>
              </select>
            </div>

            <div className="flex items-end">
              <div className="h-11 w-full rounded-xl bg-slate-50 px-4 py-2 text-sm text-slate-600">
                <span className="font-semibold text-slate-900">
                  {filteredAppointments.length}
                </span>{" "}
                results from{" "}
                <span className="font-semibold text-slate-900">
                  {fromDate}
                </span>{" "}
                to{" "}
                <span className="font-semibold text-slate-900">{toDate}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <div>
            <h2 className="text-base font-bold text-slate-900">
              Appointment Results
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Detailed records matching the selected filters.
            </p>
          </div>

          <span className="rounded-full bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-600">
            {filteredAppointments.length} results
          </span>
        </div>

        <div className="p-5">
          {isLoading && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 text-center text-sm font-medium text-slate-500">
              Loading appointment report...
            </div>
          )}

          {!isLoading && filteredAppointments.length === 0 && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
              No appointments found for this report.
            </div>
          )}

          {!isLoading && filteredAppointments.length > 0 && (
            <div className="overflow-x-auto rounded-2xl border border-slate-200">
              <table className="w-full min-w-[1250px] text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-5 py-3 font-semibold">Date</th>
                    <th className="px-5 py-3 font-semibold">Time</th>
                    <th className="px-5 py-3 font-semibold">Patient</th>
                    <th className="px-5 py-3 font-semibold">Phone</th>
                    <th className="px-5 py-3 font-semibold">Doctor</th>
                    <th className="px-5 py-3 font-semibold">Service</th>
                    <th className="px-5 py-3 font-semibold">Status</th>
                    <th className="px-5 py-3 font-semibold">Source</th>
                    <th className="px-5 py-3 font-semibold">Urgency</th>
                    <th className="px-5 py-3 font-semibold">Duration</th>
                    <th className="px-5 py-3 font-semibold">Reason</th>
                    <th className="px-5 py-3 font-semibold">Notes</th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-slate-100">
                  {filteredAppointments.map((appointment) => (
                    <tr key={appointment.id} className="hover:bg-slate-50">
                      <td className="whitespace-nowrap px-5 py-4">
                        <div className="font-semibold text-slate-900">
                          {formatDateOnly(appointment.start_time)}
                        </div>
                        <div className="mt-1 text-xs text-slate-400">
                          Created {formatDateOnly(appointment.created_at)}
                        </div>
                      </td>

                      <td className="whitespace-nowrap px-5 py-4 text-slate-700">
                        {formatTimeRange(
                          appointment.start_time,
                          appointment.end_time
                        )}
                      </td>

                      <td className="px-5 py-4">
                        <div className="font-semibold text-slate-900">
                          {appointment.patient?.full_name || "Unknown"}
                        </div>
                        <div className="mt-1 text-xs text-slate-400">
                          {appointment.patient?.email || "No email"}
                        </div>
                      </td>

                      <td className="whitespace-nowrap px-5 py-4 text-slate-600">
                        {appointment.patient?.phone_primary ||
                          appointment.patient?.phone_secondary ||
                          "-"}
                      </td>

                      <td className="px-5 py-4 text-slate-700">
                        {appointment.doctor_id
                          ? doctorNameById[appointment.doctor_id] || "Doctor"
                          : "-"}
                      </td>

                      <td className="px-5 py-4 text-slate-700">
                        {appointment.service_name || "-"}
                      </td>

                      <td className="px-5 py-4">
                        <span
                          className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold capitalize ring-1 ring-inset ${getStatusBadgeClass(
                            appointment.status
                          )}`}
                        >
                          {appointment.status || "-"}
                        </span>
                      </td>

                      <td className="px-5 py-4 text-slate-600">
                        {appointment.source || "-"}
                      </td>

                      <td className="px-5 py-4">
                        <span
                          className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold capitalize ring-1 ring-inset ${getUrgencyBadgeClass(
                            appointment.urgency
                          )}`}
                        >
                          {appointment.urgency || "normal"}
                        </span>
                      </td>

                      <td className="whitespace-nowrap px-5 py-4 text-slate-600">
                        {appointment.duration_minutes || 0} min
                      </td>

                      <td className="max-w-[220px] px-5 py-4 text-slate-600">
                        <div className="truncate">
                          {appointment.reason || "-"}
                        </div>
                      </td>

                      <td className="max-w-[260px] px-5 py-4 text-slate-600">
                        <div className="truncate">
                          {appointment.notes || "-"}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>
    </DashboardShell>
  );
}