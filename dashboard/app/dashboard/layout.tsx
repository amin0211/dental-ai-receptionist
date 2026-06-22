"use client";

import { ClinicProvider } from "@/components/providers/ClinicProvider";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <ClinicProvider>{children}</ClinicProvider>;
}