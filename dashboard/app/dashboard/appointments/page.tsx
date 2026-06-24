"use client";

import { useEffect, useMemo, useState } from "react";
import DashboardShell from "@/components/layout/DashboardShell";
import { useClinic } from "@/components/providers/ClinicProvider";
import AppointmentScheduleEditor from "@/components/appointments/AppointmentScheduleEditor";
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

type AppointmentRow = {
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
  source: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
  reason: string | null;
  urgency: string | null;
  patient: AppointmentPatient | null;
};

function normalizeAppointmentRows(rows: any[]): AppointmentRow[] {
  return rows.map((row) => {
    const patientValue = row.patient;

    const patient = Array.isArray(patientValue)
      ? patientValue[0] || null
      : patientValue || null;

    return {
      ...row,
      patient,
    } as AppointmentRow;
  });
}

function getTodayDateString() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  const day = String(today.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function getDateRange(dateString: string) {
  const start = new Date(`${dateString}T00:00:00`);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);

  return {
    startIso: start.toISOString(),
    endIso: end.toISOString(),
  };
}

function formatTimeRange(startTime: string, endTime: string) {
  const start = new Date(startTime);
  const end = new Date(endTime);

  const startLabel = start.toLocaleTimeString("en-CA", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  const endLabel = end.toLocaleTimeString("en-CA", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  return `${startLabel} - ${endLabel}`;
}

export default function AppointmentsPage() {
  const { clinicId, isLoadingClinic } = useClinic();

  const [appointments, setAppointments] = useState<AppointmentRow[]>([]);
  const [doctors, setDoctors] = useState<ClinicDoctor[]>([]);
  const [services, setServices] = useState<ServiceCategory[]>([]);

  const [selectedDate, setSelectedDate] = useState(getTodayDateString());
  const [selectedDoctorId, setSelectedDoctorId] = useState("");
  const [selectedServiceId, setSelectedServiceId] = useState("");

  const [selectedAppointment, setSelectedAppointment] =
    useState<AppointmentRow | null>(null);

  const [editingAppointment, setEditingAppointment] =
    useState<AppointmentRow | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isCancelling, setIsCancelling] = useState(false);

  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const doctorNameById = useMemo(() => {
    const map: Record<string, string> = {};

    doctors.forEach((doctor) => {
      map[doctor.id] = doctor.display_name || doctor.full_name;
    });

    return map;
  }, [doctors]);

  async function loadFilters() {
    if (!clinicId) return;

    const [loadedDoctors, loadedServices] = await Promise.all([
      getClinicDoctors(clinicId),
      getServiceCategories(clinicId),
    ]);

    setDoctors(loadedDoctors);
    setServices(loadedServices);
  }

  async function loadAppointments() {
    if (isLoadingClinic) return;

    setIsLoading(true);
    setErrorMessage("");
    setSuccessMessage("");

    if (!clinicId) {
      setErrorMessage("Clinic was not found for this account.");
      setIsLoading(false);
      return;
    }

    const { startIso, endIso } = getDateRange(selectedDate);

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
        created_at,
        updated_at,
        reason,
        urgency,
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
      .eq("status", "confirmed")
      .gte("start_time", startIso)
      .lt("start_time", endIso)
      .order("start_time", { ascending: true });

    if (selectedDoctorId) {
      query = query.eq("doctor_id", selectedDoctorId);
    }

    if (selectedServiceId) {
      query = query.eq("service_category_id", selectedServiceId);
    }

    const { data, error } = await query;

    if (error) {
      console.error("Load appointments error:", error);
      setErrorMessage(error.message);
      setIsLoading(false);
      return;
    }

    setAppointments(normalizeAppointmentRows(data || []));
    setIsLoading(false);
  }

  useEffect(() => {
    async function loadPage() {
      if (isLoadingClinic) return;

      try {
        if (!clinicId) {
          setErrorMessage("Clinic was not found for this account.");
          setIsLoading(false);
          return;
        }

        await loadFilters();
        await loadAppointments();
      } catch (error) {
        console.error("Load appointments page error:", error);
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Failed to load appointments."
        );
        setIsLoading(false);
      }
    }

    loadPage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clinicId, isLoadingClinic]);

  useEffect(() => {
    loadAppointments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDate, selectedDoctorId, selectedServiceId]);

  async function handleCancelAppointment(appointment: AppointmentRow) {
    const confirmed = window.confirm(
      "Cancel this appointment? This will remove it from today's confirmed appointments."
    );

    if (!confirmed) return;

    if (!clinicId) {
      setErrorMessage("Clinic was not found for this account.");
      return;
    }

    try {
      setIsCancelling(true);
      setErrorMessage("");
      setSuccessMessage("");

      const { error } = await supabase
        .from("appointments")
        .update({
          status: "cancelled",
          updated_at: new Date().toISOString(),
        })
        .eq("id", appointment.id)
        .eq("clinic_id", clinicId);

      if (error) {
        throw new Error(error.message);
      }

      setSelectedAppointment(null);
      setSuccessMessage("Appointment cancelled.");
      await loadAppointments();

      setIsCancelling(false);
    } catch (error) {
      console.error("Cancel appointment error:", error);
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Failed to cancel appointment."
      );
      setIsCancelling(false);
    }
  }

  if (isLoadingClinic) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50">
        <p className="text-sm font-medium text-slate-500">Loading clinic...</p>
      </main>
    );
  }

  return (
    <DashboardShell
      title="Appointments"
      description="View confirmed appointments by date, doctor, and service."
    >
      {successMessage && (
        <div className="mb-6 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          {successMessage}
        </div>
      )}

      {errorMessage && (
        <div className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage}
        </div>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 p-5">
          <div className="flex flex-wrap items-end gap-4">
            <div>
              <label className="text-sm font-medium text-slate-700">Date</label>
              <input
                type="date"
                value={selectedDate}
                onChange={(event) => setSelectedDate(event.target.value)}
                className="mt-2 w-full min-w-[180px] rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Doctor
              </label>
              <select
                value={selectedDoctorId}
                onChange={(event) => setSelectedDoctorId(event.target.value)}
                className="mt-2 w-full min-w-[220px] rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-blue-500"
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
                className="mt-2 w-full min-w-[220px] rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-blue-500"
              >
                <option value="">All services</option>
                {services.map((service) => (
                  <option key={service.id} value={service.id}>
                    {service.name}
                  </option>
                ))}
              </select>
            </div>

            <button
              type="button"
              onClick={() => {
                setSelectedDate(getTodayDateString());
                setSelectedDoctorId("");
                setSelectedServiceId("");
              }}
              className="rounded-xl border border-slate-300 px-5 py-3 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              Reset
            </button>
          </div>
        </div>

        <div className="p-5">
          {isLoading && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 text-center text-sm font-medium text-slate-500">
              Loading appointments...
            </div>
          )}

          {!isLoading && appointments.length === 0 && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
              No confirmed appointments found for this filter.
            </div>
          )}

          {!isLoading && appointments.length > 0 && (
            <div className="overflow-x-auto rounded-2xl border border-slate-200">
              <table className="w-full min-w-[900px] text-left text-sm">
                <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-5 py-3 font-semibold">Time</th>
                    <th className="px-5 py-3 font-semibold">Patient</th>
                    <th className="px-5 py-3 font-semibold">Phone</th>
                    <th className="px-5 py-3 font-semibold">Service</th>
                    <th className="px-5 py-3 font-semibold">Doctor</th>
                    <th className="px-5 py-3 font-semibold">Notes</th>
                    <th className="px-5 py-3 text-right font-semibold">
                      Actions
                    </th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-slate-100">
                  {appointments.map((appointment) => (
                    <tr key={appointment.id} className="hover:bg-slate-50">
                      <td className="whitespace-nowrap px-5 py-4 font-bold text-slate-900">
                        {formatTimeRange(
                          appointment.start_time,
                          appointment.end_time
                        )}
                        <div className="mt-1 text-xs font-medium text-slate-400">
                          {appointment.duration_minutes} min
                        </div>
                      </td>

                      <td className="px-5 py-4 font-medium text-slate-900">
                        {appointment.patient?.full_name || "Unknown"}
                      </td>

                      <td className="whitespace-nowrap px-5 py-4 text-slate-600">
                        {appointment.patient?.phone_primary ||
                          appointment.patient?.phone_secondary ||
                          "-"}
                      </td>

                      <td className="px-5 py-4 text-slate-700">
                        {appointment.service_name || "-"}
                      </td>

                      <td className="px-5 py-4 text-slate-700">
                        {appointment.doctor_id
                          ? doctorNameById[appointment.doctor_id] || "Doctor"
                          : "-"}
                      </td>

                      <td className="max-w-[260px] px-5 py-4 text-slate-600">
                        <div className="truncate">
                          {appointment.notes || "-"}
                        </div>
                      </td>

                      <td className="whitespace-nowrap px-5 py-4 text-right">
                        <button
                          type="button"
                          onClick={() => setSelectedAppointment(appointment)}
                          className="mr-4 font-semibold text-blue-600 hover:text-blue-700"
                        >
                          View
                        </button>

                        <button
                          type="button"
                          onClick={() => setEditingAppointment(appointment)}
                          className="mr-4 font-semibold text-emerald-600 hover:text-emerald-700"
                        >
                          Edit
                        </button>

                        <button
                          type="button"
                          onClick={() => handleCancelAppointment(appointment)}
                          disabled={isCancelling}
                          className="font-semibold text-red-600 hover:text-red-700 disabled:opacity-50"
                        >
                          Cancel
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </section>

      {selectedAppointment && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-2xl rounded-2xl bg-white shadow-xl">
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  Appointment Details
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Confirmed appointment information.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setSelectedAppointment(null)}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
              >
                Close
              </button>
            </div>

            <div className="space-y-4 p-5 text-sm">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="rounded-xl bg-slate-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Time
                  </p>
                  <p className="mt-1 font-bold text-slate-900">
                    {formatTimeRange(
                      selectedAppointment.start_time,
                      selectedAppointment.end_time
                    )}
                  </p>
                </div>

                <div className="rounded-xl bg-slate-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Doctor
                  </p>
                  <p className="mt-1 font-bold text-slate-900">
                    {selectedAppointment.doctor_id
                      ? doctorNameById[selectedAppointment.doctor_id] ||
                        "Doctor"
                      : "-"}
                  </p>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div className="rounded-xl bg-slate-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Patient
                  </p>
                  <p className="mt-1 font-bold text-slate-900">
                    {selectedAppointment.patient?.full_name || "Unknown"}
                  </p>
                </div>

                <div className="rounded-xl bg-slate-50 p-4">
                  <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                    Phone
                  </p>
                  <p className="mt-1 font-bold text-slate-900">
                    {selectedAppointment.patient?.phone_primary ||
                      selectedAppointment.patient?.phone_secondary ||
                      "-"}
                  </p>
                </div>
              </div>

              <div className="rounded-xl bg-slate-50 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Service
                </p>
                <p className="mt-1 font-bold text-slate-900">
                  {selectedAppointment.service_name || "-"}
                </p>
              </div>

              <div className="rounded-xl bg-slate-50 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Notes
                </p>
                <p className="mt-1 text-slate-700">
                  {selectedAppointment.notes || "-"}
                </p>
              </div>

              <button
                type="button"
                onClick={() => handleCancelAppointment(selectedAppointment)}
                disabled={isCancelling}
                className="w-full rounded-xl border border-red-200 bg-red-50 px-5 py-3 text-sm font-semibold text-red-700 hover:bg-red-100 disabled:opacity-50"
              >
                {isCancelling ? "Cancelling..." : "Cancel Appointment"}
              </button>
            </div>
          </div>
        </div>
      )}

      {editingAppointment && clinicId && (
        <AppointmentScheduleEditor
          mode="edit"
          clinicId={clinicId}
          appointment={editingAppointment}
          onClose={() => setEditingAppointment(null)}
          onSaved={async () => {
            setEditingAppointment(null);
            await loadAppointments();
          }}
        />
      )}
    </DashboardShell>
  );
}