"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";
import DashboardShell from "@/components/layout/DashboardShell";

type DashboardStats = {
  newRequests: number;
  needsFollowup: number;
  todaysAppointments: number;
  incompleteCalls: number;
};

export default function DashboardPage() {
  const router = useRouter();

  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [isLoadingStats, setIsLoadingStats] = useState(true);
  const [errorMessage, setErrorMessage] = useState("");

  const [stats, setStats] = useState<DashboardStats>({
    newRequests: 0,
    needsFollowup: 0,
    todaysAppointments: 0,
    incompleteCalls: 0,
  });

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

      const { count: newRequestsCount, error: newRequestsError } = await supabase
        .from("appointment_requests")
        .select("id", { count: "exact", head: true })
        .eq("status", "new");

      if (newRequestsError) {
        console.error("New requests count error:", newRequestsError);
        setErrorMessage(newRequestsError.message);
        setIsLoadingStats(false);
        return;
      }

      const { count: needsFollowupCount, error: needsFollowupError } =
        await supabase
          .from("appointment_requests")
          .select("id", { count: "exact", head: true })
          .eq("status", "needs_followup");

      if (needsFollowupError) {
        console.error("Needs follow-up count error:", needsFollowupError);
        setErrorMessage(needsFollowupError.message);
        setIsLoadingStats(false);
        return;
      }

      setStats({
        newRequests: newRequestsCount || 0,
        needsFollowup: needsFollowupCount || 0,
        todaysAppointments: 0,
        incompleteCalls: 0,
      });

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

      <div className="grid gap-4 md:grid-cols-4">
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">New Requests</p>
          <p className="mt-2 text-3xl font-bold text-slate-900">
            {isLoadingStats ? "..." : stats.newRequests}
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Needs Follow-up</p>
          <p className="mt-2 text-3xl font-bold text-slate-900">
            {isLoadingStats ? "..." : stats.needsFollowup}
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Today&apos;s Appointments</p>
          <p className="mt-2 text-3xl font-bold text-slate-900">
            {isLoadingStats ? "..." : stats.todaysAppointments}
          </p>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <p className="text-sm text-slate-500">Incomplete Calls</p>
          <p className="mt-2 text-3xl font-bold text-slate-900">
            {isLoadingStats ? "..." : stats.incompleteCalls}
          </p>
        </div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-bold text-slate-900">
            Latest Appointment Requests
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            Appointment requests created by the AI receptionist will appear here.
          </p>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <h2 className="text-lg font-bold text-slate-900">
            Today&apos;s Calendar
          </h2>
          <p className="mt-2 text-sm text-slate-500">
            Doctor availability and confirmed appointments will appear here.
          </p>
        </section>
      </div>
    </DashboardShell>
  );
}