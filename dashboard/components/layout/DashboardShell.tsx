"use client";

import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";
import Sidebar from "@/components/layout/Sidebar";

type DashboardShellProps = {
  title: string;
  description?: string;
  children: React.ReactNode;
};

export default function DashboardShell({
  title,
  description,
  children,
}: DashboardShellProps) {
  const router = useRouter();

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  return (
    <main className="flex min-h-screen bg-slate-50">
      <Sidebar />

      <section className="flex min-h-screen flex-1 flex-col">
        <header className="border-b border-slate-200 bg-white px-6 py-4">
          <div className="flex items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold text-slate-900">
                {title}
              </h1>

              {description && (
                <p className="mt-1 text-sm text-slate-500">
                  {description}
                </p>
              )}
            </div>

            <button
              onClick={handleSignOut}
              className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:bg-slate-100"
            >
              Sign out
            </button>
          </div>
        </header>

        <div className="flex-1 p-6">{children}</div>
      </section>
    </main>
  );
}