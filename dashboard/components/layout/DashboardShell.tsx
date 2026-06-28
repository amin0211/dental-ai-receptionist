"use client";

import { useState } from "react";
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
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  return (
    <main className="min-h-screen bg-slate-50 lg:flex">
      {/* Desktop Sidebar */}
      <div className="hidden lg:block">
        <Sidebar />
      </div>

      {/* Mobile Sidebar Drawer */}
      {isMobileMenuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button
            type="button"
            aria-label="Close menu"
            onClick={() => setIsMobileMenuOpen(false)}
            className="absolute inset-0 bg-slate-950/40"
          />

          <div className="relative h-full w-[280px] max-w-[85vw] overflow-y-auto bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
              <p className="text-sm font-black text-slate-900">Menu</p>

              <button
                type="button"
                onClick={() => setIsMobileMenuOpen(false)}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm font-black text-slate-700"
              >
                ✕
              </button>
            </div>

            <Sidebar onNavigate={() => setIsMobileMenuOpen(false)} />
          </div>
        </div>
      )}

      <section className="flex min-h-screen flex-1 flex-col overflow-hidden">
        <header className="border-b border-slate-200 bg-white px-4 py-4 sm:px-6">
          <div className="flex items-center justify-between gap-4">
            <div className="flex min-w-0 items-center gap-3">
              <button
                type="button"
                onClick={() => setIsMobileMenuOpen(true)}
                className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-lg font-black text-slate-700 shadow-sm lg:hidden"
              >
                ☰
              </button>

              <div className="min-w-0">
                <h1 className="truncate text-xl font-bold text-slate-900 sm:text-2xl">
                  {title}
                </h1>

                {description && (
                  <p className="mt-1 line-clamp-2 text-sm text-slate-500">
                    {description}
                  </p>
                )}
              </div>
            </div>

            <button
              onClick={handleSignOut}
              className="shrink-0 rounded-xl border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 transition hover:bg-slate-100 sm:px-4 sm:text-sm"
            >
              Sign out
            </button>
          </div>
        </header>

        <div className="flex-1 overflow-x-hidden p-4 sm:p-6">
          {children}
        </div>
      </section>
    </main>
  );
}