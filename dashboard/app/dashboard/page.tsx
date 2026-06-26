"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { supabase } from "@/lib/supabaseClient";
import DashboardShell from "@/components/layout/DashboardShell";
import { useClinic } from "@/components/providers/ClinicProvider";
import {
  ClinicDoctor,
  getClinicDoctors,
  getIncompleteCallExtractionCount,
} from "@/lib/supabaseService";

type DashboardStats = {
  newRequests: number;
  needsFollowup: number;
  slotOffered: number;
  todaysAppointments: number;
  incompleteCalls: number;
};

type TodayAppointmentPatient = {
  id: string;
  full_name: string;
  phone_primary: string | null;
};

type TodayAppointment = {
  id: string;
  clinic_id: string;
  patient_id: string | null;
  doctor_id: string | null;
  service_name: string | null;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  notes: string | null;
  patient: TodayAppointmentPatient | null;
};

type ScheduleCellInfo = {
  appointment: TodayAppointment | null;
  isStart: boolean;
};

const DAY_START_MINUTES = 8 * 60;
const DAY_END_MINUTES = 18 * 60;
const SLOT_MINUTES = 30;

function normalizeTodayAppointments(rows: any[]): TodayAppointment[] {
  return rows.map((row) => {
    const patientValue = row.patient;

    const patient = Array.isArray(patientValue)
      ? patientValue[0] || null
      : patientValue || null;

    return {
      ...row,
      patient,
    } as TodayAppointment;
  });
}

function StatCard({
  title,
  value,
  href,
  isLoading,
  tone,
}: {
  title: string;
  value: number;
  href: string;
  isLoading: boolean;
  tone: "blue" | "amber" | "violet" | "emerald" | "rose";
}) {
  const toneClass = {
    blue: "bg-blue-500",
    amber: "bg-amber-500",
    violet: "bg-violet-500",
    emerald: "bg-emerald-500",
    rose: "bg-rose-500",
  }[tone];

  return (
    <Link
      href={href}
      className="group min-w-[170px] flex-1 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-blue-200 hover:bg-blue-50/30 hover:shadow-md"
    >
      <div className="flex items-center justify-between gap-3">
        <p className="truncate text-sm font-semibold text-slate-500">
          {title}
        </p>

        <span className={`h-2.5 w-2.5 rounded-full ${toneClass}`} />
      </div>

      <div className="mt-3 flex items-end justify-between gap-3">
        <p className="text-3xl font-black tracking-tight text-slate-950">
          {isLoading ? "..." : value}
        </p>

        <p className="text-xs font-bold text-slate-400 transition group-hover:text-blue-600">
          Open →
        </p>
      </div>
    </Link>
  );
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

function minutesToTime(totalMinutes: number) {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(
    2,
    "0"
  )}`;
}

function getLocalMinutesFromIso(value: string) {
  const date = new Date(value);
  return date.getHours() * 60 + date.getMinutes();
}

function formatAppointmentTime(startTime: string, endTime: string) {
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

function formatTodayLabel() {
  return new Intl.DateTimeFormat("en-CA", {
    weekday: "long",
    month: "long",
    day: "numeric",
  }).format(new Date());
}

function buildTimeSlots() {
  const slots: number[] = [];

  for (
    let current = DAY_START_MINUTES;
    current < DAY_END_MINUTES;
    current += SLOT_MINUTES
  ) {
    slots.push(current);
  }

  return slots;
}

function getScheduleCellInfo({
  doctorId,
  slotStartMinutes,
  appointments,
}: {
  doctorId: string;
  slotStartMinutes: number;
  appointments: TodayAppointment[];
}): ScheduleCellInfo {
  const slotEndMinutes = slotStartMinutes + SLOT_MINUTES;

  const appointment =
    appointments.find((item) => {
      if (item.doctor_id !== doctorId) return false;

      const appointmentStart = getLocalMinutesFromIso(item.start_time);
      const appointmentEnd = getLocalMinutesFromIso(item.end_time);

      return (
        appointmentStart < slotEndMinutes && appointmentEnd > slotStartMinutes
      );
    }) || null;

  if (!appointment) {
    return {
      appointment: null,
      isStart: false,
    };
  }

  const appointmentStart = getLocalMinutesFromIso(appointment.start_time);

  return {
    appointment,
    isStart:
      appointmentStart >= slotStartMinutes && appointmentStart < slotEndMinutes,
  };
}

function getDoctorAppointmentCount({
  doctorId,
  appointments,
}: {
  doctorId: string;
  appointments: TodayAppointment[];
}) {
  return appointments.filter((appointment) => appointment.doctor_id === doctorId)
    .length;
}

export default function DashboardPage() {
  const { clinic, clinicId, isLoadingClinic } = useClinic();

  const [isLoadingStats, setIsLoadingStats] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  const [stats, setStats] = useState<DashboardStats>({
    newRequests: 0,
    needsFollowup: 0,
    slotOffered: 0,
    todaysAppointments: 0,
    incompleteCalls: 0,
  });

  const [doctors, setDoctors] = useState<ClinicDoctor[]>([]);
  const [todayAppointments, setTodayAppointments] = useState<
    TodayAppointment[]
  >([]);

  const timeSlots = useMemo(() => buildTimeSlots(), []);
  const todayDate = getTodayDateString();

  useEffect(() => {
    async function loadDashboard() {
      if (isLoadingClinic) return;
      if (!clinicId) return;

      setErrorMessage("");
      setIsLoadingStats(true);

      const { startIso, endIso } = getDateRange(todayDate);

      const [
        newRequestsResult,
        needsFollowupResult,
        slotOfferedResult,
        todaysAppointmentsResult,
        todayAppointmentsResult,
        incompleteCallsCount,
      ] = await Promise.all([
        supabase
          .from("appointment_requests")
          .select("id", { count: "exact", head: true })
          .eq("clinic_id", clinicId)
          .eq("status", "new"),

        supabase
          .from("appointment_requests")
          .select("id", { count: "exact", head: true })
          .eq("clinic_id", clinicId)
          .eq("status", "needs_followup"),

        supabase
          .from("appointment_requests")
          .select("id", { count: "exact", head: true })
          .eq("clinic_id", clinicId)
          .eq("status", "cancelled"),

        supabase
          .from("appointments")
          .select("id", { count: "exact", head: true })
          .eq("clinic_id", clinicId)
          .eq("status", "confirmed")
          .gte("start_time", startIso)
          .lt("start_time", endIso),

        supabase
          .from("appointments")
          .select(
            `
            id,
            clinic_id,
            patient_id,
            doctor_id,
            service_name,
            start_time,
            end_time,
            duration_minutes,
            notes,
            patient:patients (
              id,
              full_name,
              phone_primary
            )
          `
          )
          .eq("clinic_id", clinicId)
          .eq("status", "confirmed")
          .gte("start_time", startIso)
          .lt("start_time", endIso)
          .order("start_time", { ascending: true }),

        getIncompleteCallExtractionCount(clinicId),
      ]);

      if (newRequestsResult.error) {
        setErrorMessage(newRequestsResult.error.message);
        setIsLoadingStats(false);
        return;
      }

      if (needsFollowupResult.error) {
        setErrorMessage(needsFollowupResult.error.message);
        setIsLoadingStats(false);
        return;
      }

      if (slotOfferedResult.error) {
        setErrorMessage(slotOfferedResult.error.message);
        setIsLoadingStats(false);
        return;
      }

      if (todaysAppointmentsResult.error) {
        setErrorMessage(todaysAppointmentsResult.error.message);
        setIsLoadingStats(false);
        return;
      }

      if (todayAppointmentsResult.error) {
        setErrorMessage(todayAppointmentsResult.error.message);
        setIsLoadingStats(false);
        return;
      }

      try {
        const loadedDoctors = await getClinicDoctors(clinicId);
        setDoctors(loadedDoctors);
      } catch (error) {
        setErrorMessage(
          error instanceof Error ? error.message : "Failed to load doctors."
        );
        setIsLoadingStats(false);
        return;
      }

      setStats({
        newRequests: newRequestsResult.count || 0,
        needsFollowup: needsFollowupResult.count || 0,
        slotOffered: slotOfferedResult.count || 0,
        todaysAppointments: todaysAppointmentsResult.count || 0,
        incompleteCalls: incompleteCallsCount,
      });

      setTodayAppointments(
        normalizeTodayAppointments(todayAppointmentsResult.data || [])
      );

      setIsLoadingStats(false);
    }

    loadDashboard();
  }, [clinicId, isLoadingClinic, todayDate]);

  if (isLoadingClinic) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50">
        <p className="text-sm font-medium text-slate-500">Loading clinic...</p>
      </main>
    );
  }

  return (
    <DashboardShell
      title={clinic?.name || "Clinic Dashboard"}
      description="Monitor AI calls, appointment requests, doctors, and clinic activity."
    >
      {errorMessage && (
        <div className="mb-6 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm font-semibold text-red-700">
          {errorMessage}
        </div>
      )}

      <div className="flex w-full flex-nowrap gap-4 overflow-x-auto pb-2">
        <StatCard
          title="New Requests"
          value={stats.newRequests}
          href="/dashboard/requests?status=new"
          isLoading={isLoadingStats}
          tone="blue"
        />

        <StatCard
          title="Needs Follow-up"
          value={stats.needsFollowup}
          href="/dashboard/requests?status=needs_followup"
          isLoading={isLoadingStats}
          tone="amber"
        />


        <StatCard
          title="Today's Appointments"
          value={stats.todaysAppointments}
          href="/dashboard/appointments"
          isLoading={isLoadingStats}
          tone="emerald"
        />

        <StatCard
          title="Incomplete Calls"
          value={stats.incompleteCalls}
          href="/dashboard/calls?filter=incomplete"
          isLoading={isLoadingStats}
          tone="rose"
        />
        <StatCard
          title="Cancelled Appointments"
          value={stats.slotOffered}
          href="/dashboard/requests?status=cancelled"
          isLoading={isLoadingStats}
          tone="violet"
        />
      </div>

      <section className="mt-6 overflow-hidden rounded-[28px] border border-slate-200 bg-white shadow-sm ring-1 ring-slate-100">
        <div className="border-b border-slate-100 bg-gradient-to-r from-blue-50 via-white to-emerald-50 px-6 py-5">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="flex flex-wrap items-center gap-3">
                <h2 className="text-xl font-black tracking-tight text-slate-950">
                  Today&apos;s Doctor Schedule
                </h2>

                <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-black text-emerald-800 ring-1 ring-emerald-200">
                  {stats.todaysAppointments} confirmed
                </span>
              </div>

              <p className="mt-2 text-sm font-medium text-slate-500">
                {formatTodayLabel()} · 30-minute timeline · 8:00 to 18:00
              </p>
            </div>
          </div>
        </div>

        {isLoadingStats && (
          <div className="p-6">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-10 text-center text-sm font-semibold text-slate-500">
              Loading today&apos;s schedule...
            </div>
          </div>
        )}

        {!isLoadingStats && doctors.length === 0 && (
          <div className="p-6">
            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-10 text-center text-sm font-medium text-slate-500">
              No doctors found. Add doctors first to show today&apos;s schedule.
            </div>
          </div>
        )}

        {!isLoadingStats && doctors.length > 0 && (
          <div className="overflow-x-auto bg-white">
            <div
              className="w-max min-w-full"
              style={{
                display: "grid",
                gridTemplateColumns: `64px repeat(${doctors.length}, 150px)`,
              }}
            >
              <div className="sticky left-0 z-30 border-b border-r border-slate-200 bg-slate-50 px-3 py-2 text-[11px] font-black uppercase tracking-wide text-slate-500">
                Time
              </div>

              {doctors.map((doctor) => {
                const count = getDoctorAppointmentCount({
                  doctorId: doctor.id,
                  appointments: todayAppointments,
                });

                return (
                  <div
                    key={doctor.id}
                    className="border-b border-r border-slate-200 bg-slate-50/80 px-3 py-2 last:border-r-0"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-xs font-black text-slate-900">
                        {doctor.display_name || doctor.full_name}
                      </p>
                      <p className="mt-1 text-xs font-semibold text-slate-400">
                        {count} appointment{count === 1 ? "" : "s"}
                      </p>
                    </div>
                  </div>
                );
              })}

              {timeSlots.map((slotMinutes) => (
                <div key={`row-${slotMinutes}`} className="contents">
                  <div className="sticky left-0 z-20 border-b border-r border-slate-200 bg-slate-50 px-3 py-2">
                    <p className="text-xs font-black text-slate-500">
                      {minutesToTime(slotMinutes)}
                    </p>
                  </div>

                  {doctors.map((doctor) => {
                    const cellInfo = getScheduleCellInfo({
                      doctorId: doctor.id,
                      slotStartMinutes: slotMinutes,
                      appointments: todayAppointments,
                    });

                    const appointment = cellInfo.appointment;

                    if (!appointment) {
                      return (
                        <div
                          key={`${doctor.id}-${slotMinutes}`}
                          className="group min-h-[46px] border-b border-r border-slate-100 bg-white p-1.5 last:border-r-0"
                        >
                          <div className="h-full rounded-xl border border-dashed border-slate-200 bg-slate-50/60 transition group-hover:border-slate-300" />
                        </div>
                      );
                    }

                    if (!cellInfo.isStart) {
                      return (
                        <div
                          key={`${doctor.id}-${slotMinutes}`}
                          className="min-h-[46px] border-b border-r border-blue-100 bg-blue-50/30 p-1.5 last:border-r-0"
                        >
                          <div className="h-full rounded-xl border border-blue-100 bg-blue-100/50" />
                        </div>
                      );
                    }

                    return (
                      <Link
                        key={`${doctor.id}-${slotMinutes}`}
                        href="/dashboard/appointments"
                        className="min-h-[46px] border-b border-r border-blue-100 bg-blue-50/80 p-1.5 transition hover:bg-blue-100 last:border-r-0"
                      >
                        <div className="rounded-xl border border-blue-200 bg-gradient-to-br from-white to-blue-50 p-2 shadow-sm ring-1 ring-blue-100">
                          <div className="flex items-start justify-between gap-3">
                            <div className="min-w-0">
                              <p className="truncate text-xs font-black text-slate-950">
                                {appointment.patient?.full_name ||
                                  "Unknown patient"}
                              </p>

                              {appointment.patient?.phone_primary && (
                                <p className="mt-0.5 truncate text-[10px] font-semibold text-slate-400">
                                  {appointment.patient.phone_primary}
                                </p>
                              )}

                              <p className="mt-0.5 truncate text-[11px] font-bold text-blue-700">
                                {appointment.service_name || "Appointment"}
                              </p>
                            </div>

                            <span className="rounded-full bg-blue-600 px-1.5 py-0.5 text-[9px] font-black text-white shadow-sm">
                              {appointment.duration_minutes}m
                            </span>
                          </div>

                          <p className="mt-1 text-[11px] font-semibold text-slate-500">
                            {formatAppointmentTime(
                              appointment.start_time,
                              appointment.end_time
                            )}
                          </p>
                        </div>
                      </Link>
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        )}
      </section>
    </DashboardShell>
  );
}