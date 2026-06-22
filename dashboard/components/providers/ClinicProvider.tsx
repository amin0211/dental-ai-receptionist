"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";
import { getClinicByOwnerUserId, type Clinic } from "@/lib/supabaseService";

type ClinicContextValue = {
  clinic: Clinic | null;
  clinicId: string | null;
  isLoadingClinic: boolean;
  refreshClinic: () => Promise<void>;
};

const ClinicContext = createContext<ClinicContextValue | undefined>(undefined);

export function ClinicProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();

  const [clinic, setClinic] = useState<Clinic | null>(null);
  const [isLoadingClinic, setIsLoadingClinic] = useState(true);

  async function loadClinic() {
    setIsLoadingClinic(true);

    const {
      data: { user },
      error: userError,
    } = await supabase.auth.getUser();

    if (userError || !user) {
      setClinic(null);
      setIsLoadingClinic(false);
      router.replace("/login");
      return;
    }

    try {
      const currentClinic = await getClinicByOwnerUserId(user.id);
      setClinic(currentClinic);
    } catch (error) {
      console.error("Clinic load error:", error);
      setClinic(null);
      router.replace("/login");
    } finally {
      setIsLoadingClinic(false);
    }
  }

  useEffect(() => {
    loadClinic();
  }, []);

  const value = useMemo(
    () => ({
      clinic,
      clinicId: clinic?.id ?? null,
      isLoadingClinic,
      refreshClinic: loadClinic,
    }),
    [clinic, isLoadingClinic]
  );

  return (
    <ClinicContext.Provider value={value}>{children}</ClinicContext.Provider>
  );
}

export function useClinic() {
  const context = useContext(ClinicContext);

  if (!context) {
    throw new Error("useClinic must be used inside ClinicProvider");
  }

  return context;
}