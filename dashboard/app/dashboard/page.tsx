"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";
import DashboardShell from "@/components/layout/DashboardShell";

type DashboardStats = {
  newRequests: number;
  needsFollowup: number;
  slotOffered: number;
  todaysAppointments: number;
  incompleteCalls: number;
};

type AppointmentRequest = {
  id: string;
  patient_name: string | null;
  service_name: string | null;
  doctor_name: string | null;
  status: string | null;
  created_at: string | null;
};

function StatCard({
  title,
  value,
  href,
  isLoading,
}: {
  title: string;
  value: number;
  href: string;
  isLoading: boolean;
}) {
  return (
    <Link
      href={href}
      className="min-w-0 flex-1 rounded-2xl border border-slate-200 bg-white p-4 shadow-sm transition hover:-translate-y-0.5 hover:shadow-md"
    >
      <p className="truncate text-sm font-medium text-slate-500">{title}</p>
      <p className="mt-3 text-3xl font-bold text-slate-900">
        {isLoading ? "..." : value}
      </p>
    </Link>
  );
}

function formatDate(value: string | null) {
  if (!value) return "-";

  return new Intl.DateTimeFormat("en-CA", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export default function DashboardPage() {
  const router = useRouter();

  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [isLoadingStats, setIsLoadingStats] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  const [stats, setStats] = useState<DashboardStats>({
    newRequests: 0,
    needsFollowup: 0,
    slotOffered: 0,
    todaysAppointments: 0,
    incompleteCalls: 0,
  });

  const [latestRequests, setLatestRequests] = useState<AppointmentRequest[]>([]);

  useEffect(() => {
    async function loadDashboard() {
      setErrorMessage("");

      const { data: sessionData } = await supabase.auth.getSession();

      if (!sessionData.session) {
        router.replace("/login");
        return;
      }

      setIsCheckingSession(false);
      setIsLoadingStats(true);

      const [
        newRequestsResult,
        needsFollowupResult,
        slotOfferedResult,
        latestRequestsResult,
      ] = await Promise.all([
        supabase
          .from("appointment_requests")
          .select("id", { count: "exact", head: true })
          .eq("status", "new"),

        supabase
          .from("appointment_requests")
          .select("id", { count: "exact", head: true })
          .eq("status", "needs_followup"),

        supabase
          .from("appointment_requests")
          .select("id", { count: "exact", head: true })
          .eq("status", "slot_offered"),

        supabase
          .from("appointment_requests")
          .select("id, patient_name, doctor_id, service_category_id, status, created_at")
          .order("created_at", { ascending: false })
          .limit(5),
      ]);

      if (newRequestsResult.error) {
        console.error("New requests count error:", newRequestsResult.error);
        setErrorMessage(newRequestsResult.error.message);
        setIsLoadingStats(false);
        return;
      }

      if (needsFollowupResult.error) {
        console.error("Needs follow-up count error:", needsFollowupResult.error);
        setErrorMessage(needsFollowupResult.error.message);
        setIsLoadingStats(false);
        return;
      }

      if (slotOfferedResult.error) {
        console.error("Slot offered count error:", slotOfferedResult.error);
        setErrorMessage(slotOfferedResult.error.message);
        setIsLoadingStats(false);
        return;
      }

      if (latestRequestsResult.error) {
        console.error("Latest requests error:", latestRequestsResult.error);
        setErrorMessage(latestRequestsResult.error.message);
        setIsLoadingStats(false);
        return;
      }

      setStats({
        newRequests: newRequestsResult.count || 0,
        needsFollowup: needsFollowupResult.count || 0,
        slotOffered: slotOfferedResult.count || 0,
        todaysAppointments: 0,
        incompleteCalls: 0,
      });

      setLatestRequests(latestRequestsResult.data || []);
      setIsLoadingStats(false);
    }

    loadDashboard();
  }, [router]);

  if (isCheckingSession) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50">
        <p className="text-sm font-medium text-slate-500">
          Checking session...
        </p>
      </main>
    );
  }

  return (
    <DashboardShell
      title="Clinic Workbench"
      description="Monitor AI calls, appointment requests, doctors, and clinic activity."
    >
      {errorMessage && (
        <div className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage}
        </div>
      )}

      <div className="flex w-full flex-nowrap gap-4">
        <StatCard
          title="New Requests"
          value={stats.newRequests}
          href="/dashboard/requests?status=new"
          isLoading={isLoadingStats}
        />

        <StatCard
          title="Needs Follow-up"
          value={stats.needsFollowup}
          href="/dashboard/requests?status=needs_followup"
          isLoading={isLoadingStats}
        />

        <StatCard
          title="Slot Offered"
          value={stats.slotOffered}
          href="/dashboard/requests?status=slot_offered"
          isLoading={isLoadingStats}
        />

        <StatCard
          title="Today's Appointments"
          value={stats.todaysAppointments}
          href="/dashboard/appointments?date=today"
          isLoading={isLoadingStats}
        />

        <StatCard
          title="Incomplete Calls"
          value={stats.incompleteCalls}
          href="/dashboard/calls?status=incomplete"
          isLoading={isLoadingStats}
        />
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold text-slate-900">
                Action Required
              </h2>
              <p className="mt-2 text-sm text-slate-500">
                Items that need human review or receptionist follow-up.
              </p>
            </div>

            <Link
              href="/dashboard/requests?status=needs_followup"
              className="text-sm font-semibold text-blue-600 hover:text-blue-700"
            >
              View all
            </Link>
          </div>

          <div className="mt-5 space-y-3">
            <div className="rounded-xl bg-amber-50 p-4 text-sm text-amber-900">
              Patients who asked for a specific time but no matching slot was found.
            </div>

            <div className="rounded-xl bg-red-50 p-4 text-sm text-red-900">
              Calls with missing name, phone number, doctor, or service.
            </div>

            <div className="rounded-xl bg-blue-50 p-4 text-sm text-blue-900">
              Patients who received a slot but have not confirmed yet.
            </div>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold text-slate-900">
                Today&apos;s Calendar
              </h2>
              <p className="mt-2 text-sm text-slate-500">
                Confirmed appointments and available doctor slots for today.
              </p>
            </div>

            <Link
              href="/dashboard/calendar"
              className="text-sm font-semibold text-blue-600 hover:text-blue-700"
            >
              Open calendar
            </Link>
          </div>

          <div className="mt-5 rounded-xl border border-dashed border-slate-200 bg-slate-50 p-5 text-sm text-slate-500">
            Today&apos;s confirmed appointments will appear here after the
            appointments table or calendar integration is connected.
          </div>
        </section>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold text-slate-900">
                Latest Appointment Requests
              </h2>
              <p className="mt-2 text-sm text-slate-500">
                Recent appointment requests created by the AI receptionist.
              </p>
            </div>

            <Link
              href="/dashboard/requests"
              className="text-sm font-semibold text-blue-600 hover:text-blue-700"
            >
              View requests
            </Link>
          </div>

          <div className="mt-5 overflow-hidden rounded-xl border border-slate-100">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-slate-500">
                <tr>
                  <th className="px-4 py-3 font-semibold">Patient</th>
                  <th className="px-4 py-3 font-semibold">Service</th>
                  <th className="px-4 py-3 font-semibold">Doctor</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Created</th>
                  <th className="px-4 py-3 font-semibold"></th>
                </tr>
              </thead>

              <tbody className="divide-y divide-slate-100 bg-white">
                {latestRequests.length === 0 && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-4 py-6 text-center text-sm text-slate-500"
                    >
                      No appointment requests yet.
                    </td>
                  </tr>
                )}

                {latestRequests.map((request) => (
                  <tr key={request.id}>
                    <td className="px-4 py-4 font-medium text-slate-900">
                      {request.patient_name || "Unknown patient"}
                    </td>

                    <td className="px-4 py-4 text-slate-600">
                      {request.service_name || "-"}
                    </td>

                    <td className="px-4 py-4 text-slate-600">
                      {request.doctor_name || "Any doctor"}
                    </td>

                    <td className="px-4 py-4">
                      <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-700">
                        {request.status || "-"}
                      </span>
                    </td>

                    <td className="px-4 py-4 text-slate-500">
                      {formatDate(request.created_at)}
                    </td>

                    <td className="px-4 py-4 text-right">
                      <Link
                        href={`/dashboard/requests/${request.id}`}
                        className="font-semibold text-blue-600 hover:text-blue-700"
                      >
                        View
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-bold text-slate-900">
            AI Activity Today
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            Summary of what the AI receptionist handled today.
          </p>

          <div className="mt-6 space-y-4">
            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-500">Calls handled</span>
              <span className="font-bold text-slate-900">0</span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-500">Requests collected</span>
              <span className="font-bold text-slate-900">
                {isLoadingStats ? "..." : stats.newRequests}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-500">Appointments booked</span>
              <span className="font-bold text-slate-900">
                {isLoadingStats ? "..." : stats.todaysAppointments}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-500">Human help needed</span>
              <span className="font-bold text-slate-900">
                {isLoadingStats ? "..." : stats.needsFollowup}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm text-slate-500">Incomplete calls</span>
              <span className="font-bold text-slate-900">
                {isLoadingStats ? "..." : stats.incompleteCalls}
              </span>
            </div>
          </div>
        </section>
      </div>
    </DashboardShell>
  );
}