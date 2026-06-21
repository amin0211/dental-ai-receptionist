"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navigationItems = [
  { label: "Dashboard", href: "/dashboard" },
  { label: "Requests", href: "/requests" },
  { label: "Doctors", href: "/doctors" },
  { label: "Services", href: "/services" },
  { label: "Calendar", href: "/calendar" },
  { label: "Calls", href: "/calls" },
  { label: "Settings", href: "/settings" },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="hidden min-h-screen w-64 border-r border-slate-200 bg-white px-4 py-6 lg:block">
      <div className="mb-8 px-2">
        <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-2xl bg-blue-600 text-lg font-bold text-white">
          AI
        </div>

        <h1 className="text-lg font-bold text-slate-900">
          Clinic AI
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Receptionist Dashboard
        </p>
      </div>

      <nav className="space-y-1">
        {navigationItems.map((item) => {
          const isActive = pathname === item.href;

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex rounded-xl px-3 py-2.5 text-sm font-medium transition ${
                isActive
                  ? "bg-blue-50 text-blue-700"
                  : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}