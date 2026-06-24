"use client";

import { useEffect, useMemo, useState } from "react";
import DashboardShell from "@/components/layout/DashboardShell";
import { useClinic } from "@/components/providers/ClinicProvider";
import {
  Patient,
  createPatient,
  deletePatient,
  getPatients,
  updatePatient,
} from "@/lib/supabaseService";

type PatientForm = {
  full_name: string;
  phone_primary: string;
  phone_secondary: string;
  email: string;
  date_of_birth: string;
  address_line1: string;
  address_line2: string;
  city: string;
  province: string;
  postal_code: string;
  country: string;
  notes: string;
};

const emptyForm: PatientForm = {
  full_name: "",
  phone_primary: "",
  phone_secondary: "",
  email: "",
  date_of_birth: "",
  address_line1: "",
  address_line2: "",
  city: "",
  province: "",
  postal_code: "",
  country: "Canada",
  notes: "",
};

function normalizePhone(phone: string) {
  return phone.trim().replace(/\s+/g, "");
}

function formatDate(date: string | null) {
  if (!date) return "—";

  const parsed = new Date(`${date}T00:00:00`);

  if (Number.isNaN(parsed.getTime())) return date;

  return parsed.toLocaleDateString("en-CA", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function getPatientAddress(patient: Patient) {
  return [
    patient.address_line1,
    patient.address_line2,
    patient.city,
    patient.province,
    patient.postal_code,
    patient.country,
  ]
    .filter(Boolean)
    .join(", ");
}

export default function PatientsPage() {
  const { clinic } = useClinic();

  const [patients, setPatients] = useState<Patient[]>([]);
  const [form, setForm] = useState<PatientForm>(emptyForm);
  const [search, setSearch] = useState("");
  const [selectedPatient, setSelectedPatient] = useState<Patient | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeletingId, setIsDeletingId] = useState<string | null>(null);

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const filteredPatients = useMemo(() => {
    const query = search.trim().toLowerCase();

    if (!query) return patients;

    return patients.filter((patient) => {
      const address = getPatientAddress(patient).toLowerCase();

      return (
        patient.full_name.toLowerCase().includes(query) ||
        patient.phone_primary.toLowerCase().includes(query) ||
        patient.phone_secondary?.toLowerCase().includes(query) ||
        patient.email?.toLowerCase().includes(query) ||
        patient.date_of_birth?.toLowerCase().includes(query) ||
        patient.postal_code?.toLowerCase().includes(query) ||
        patient.notes?.toLowerCase().includes(query) ||
        address.includes(query)
      );
    });
  }, [patients, search]);

  async function loadPatients() {
    if (!clinic?.id) {
      setPatients([]);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const data = await getPatients(clinic.id);
      setPatients(data);
    } catch (error) {
      setPatients([]);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to load patients."
      );
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    loadPatients();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clinic?.id]);

  function updateForm<K extends keyof PatientForm>(
    key: K,
    value: PatientForm[K]
  ) {
    setForm((current) => ({
      ...current,
      [key]: value,
    }));
  }

  function clearMessages() {
    setErrorMessage(null);
    setSuccessMessage(null);
  }

  function resetForm() {
    setForm(emptyForm);
    setSelectedPatient(null);
    clearMessages();
  }

  function editPatient(patient: Patient) {
    setSelectedPatient(patient);
    clearMessages();

    setForm({
      full_name: patient.full_name ?? "",
      phone_primary: patient.phone_primary ?? "",
      phone_secondary: patient.phone_secondary ?? "",
      email: patient.email ?? "",
      date_of_birth: patient.date_of_birth ?? "",
      address_line1: patient.address_line1 ?? "",
      address_line2: patient.address_line2 ?? "",
      city: patient.city ?? "",
      province: patient.province ?? "",
      postal_code: patient.postal_code ?? "",
      country: patient.country ?? "Canada",
      notes: patient.notes ?? "",
    });
  }

  async function savePatient(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!clinic?.id) {
      setErrorMessage("Clinic not found. Please login again.");
      return;
    }

    const fullName = form.full_name.trim();
    const primaryPhone = normalizePhone(form.phone_primary);
    const secondaryPhone = form.phone_secondary
      ? normalizePhone(form.phone_secondary)
      : "";

    if (!fullName) {
      setErrorMessage("Patient full name is required.");
      return;
    }

    if (!primaryPhone) {
      setErrorMessage("Primary phone is required.");
      return;
    }

    setIsSaving(true);
    clearMessages();

    try {
      if (selectedPatient) {
        await updatePatient({
          id: selectedPatient.id,
          clinicId: clinic.id,
          fullName,
          phonePrimary: primaryPhone,
          phoneSecondary: secondaryPhone || null,
          email: form.email || null,
          dateOfBirth: form.date_of_birth || null,
          addressLine1: form.address_line1 || null,
          addressLine2: form.address_line2 || null,
          city: form.city || null,
          province: form.province || null,
          postalCode: form.postal_code || null,
          country: form.country || "Canada",
          notes: form.notes || null,
        });

        setSuccessMessage("Patient updated successfully.");
      } else {
        await createPatient({
          clinicId: clinic.id,
          fullName,
          phonePrimary: primaryPhone,
          phoneSecondary: secondaryPhone || null,
          email: form.email || null,
          dateOfBirth: form.date_of_birth || null,
          addressLine1: form.address_line1 || null,
          addressLine2: form.address_line2 || null,
          city: form.city || null,
          province: form.province || null,
          postalCode: form.postal_code || null,
          country: form.country || "Canada",
          notes: form.notes || null,
        });

        setSuccessMessage("Patient added successfully.");
      }

      setForm(emptyForm);
      setSelectedPatient(null);
      await loadPatients();
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to save patient."
      );
    } finally {
      setIsSaving(false);
    }
  }

  async function handleDeletePatient(patient: Patient) {
    if (!clinic?.id) {
      setErrorMessage("Clinic not found. Please login again.");
      return;
    }

    const confirmed = window.confirm(
      `Delete ${patient.full_name}? This cannot be undone.`
    );

    if (!confirmed) return;

    setIsDeletingId(patient.id);
    clearMessages();

    try {
      await deletePatient({
        id: patient.id,
        clinicId: clinic.id,
      });

      if (selectedPatient?.id === patient.id) {
        setForm(emptyForm);
        setSelectedPatient(null);
      }

      setSuccessMessage("Patient deleted successfully.");
      await loadPatients();
    } catch (error) {
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to delete patient."
      );
    } finally {
      setIsDeletingId(null);
    }
  }

  return (
return (
      <DashboardShell
        title="Patients"
        description="Add, search, edit, and manage patient records for this clinic."
      >
        <div className="space-y-6">
        <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Patients</h1>
            <p className="text-sm text-slate-500">
              Add, search, edit, and manage patient records for this clinic.
            </p>
          </div>

          <button
            type="button"
            onClick={resetForm}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
          >
            + New Patient
          </button>
        </div>

        {!clinic?.id && (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            Clinic is not loaded yet. If this stays visible, login again.
          </div>
        )}

        {(errorMessage || successMessage) && (
          <div
            className={`rounded-xl border px-4 py-3 text-sm ${
              errorMessage
                ? "border-red-200 bg-red-50 text-red-700"
                : "border-green-200 bg-green-50 text-green-700"
            }`}
          >
            {errorMessage || successMessage}
          </div>
        )}

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[430px_1fr]">
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-5">
              <h2 className="text-lg font-semibold text-slate-900">
                {selectedPatient ? "Edit Patient" : "Add Patient"}
              </h2>

              <p className="mt-1 text-sm text-slate-500">
                Full name and primary phone are required.
              </p>
            </div>

            <form onSubmit={savePatient} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  Full name *
                </label>
                <input
                  value={form.full_name}
                  onChange={(event) =>
                    updateForm("full_name", event.target.value)
                  }
                  placeholder="e.g. Parisa Yavari"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                />
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-1">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    Primary phone *
                  </label>
                  <input
                    value={form.phone_primary}
                    onChange={(event) =>
                      updateForm("phone_primary", event.target.value)
                    }
                    placeholder="+16041234567"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    Secondary phone
                  </label>
                  <input
                    value={form.phone_secondary}
                    onChange={(event) =>
                      updateForm("phone_secondary", event.target.value)
                    }
                    placeholder="+16047654321"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-1">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    Email
                  </label>
                  <input
                    type="email"
                    value={form.email}
                    onChange={(event) => updateForm("email", event.target.value)}
                    placeholder="patient@email.com"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    Date of birth
                  </label>
                  <input
                    type="date"
                    value={form.date_of_birth}
                    onChange={(event) =>
                      updateForm("date_of_birth", event.target.value)
                    }
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  Address line 1
                </label>
                <input
                  value={form.address_line1}
                  onChange={(event) =>
                    updateForm("address_line1", event.target.value)
                  }
                  placeholder="Street address"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  Address line 2
                </label>
                <input
                  value={form.address_line2}
                  onChange={(event) =>
                    updateForm("address_line2", event.target.value)
                  }
                  placeholder="Unit, suite, etc."
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    City
                  </label>
                  <input
                    value={form.city}
                    onChange={(event) => updateForm("city", event.target.value)}
                    placeholder="Vancouver"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    Province
                  </label>
                  <input
                    value={form.province}
                    onChange={(event) =>
                      updateForm("province", event.target.value)
                    }
                    placeholder="BC"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    Postal code
                  </label>
                  <input
                    value={form.postal_code}
                    onChange={(event) =>
                      updateForm("postal_code", event.target.value)
                    }
                    placeholder="V6B 1A1"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                  />
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    Country
                  </label>
                  <input
                    value={form.country}
                    onChange={(event) =>
                      updateForm("country", event.target.value)
                    }
                    placeholder="Canada"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  Notes
                </label>
                <textarea
                  value={form.notes}
                  onChange={(event) => updateForm("notes", event.target.value)}
                  placeholder="New patient, prefers Farsi, call after 5pm..."
                  rows={4}
                  className="w-full resize-none rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                />
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="submit"
                  disabled={isSaving || !clinic?.id}
                  className="flex-1 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {isSaving
                    ? "Saving..."
                    : selectedPatient
                    ? "Update Patient"
                    : "Add Patient"}
                </button>

                {selectedPatient && (
                  <button
                    type="button"
                    onClick={resetForm}
                    disabled={isSaving}
                    className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </form>
          </section>

          <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 p-5">
              <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <h2 className="text-lg font-semibold text-slate-900">
                    Patient List
                  </h2>
                  <p className="mt-1 text-sm text-slate-500">
                    {filteredPatients.length} of {patients.length} patients
                  </p>
                </div>

                <div className="w-full md:w-96">
                  <input
                    value={search}
                    onChange={(event) => setSearch(event.target.value)}
                    placeholder="Search name, phone, email, postal code..."
                    className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                  />
                </div>
              </div>
            </div>

            <div className="overflow-x-auto">
              {isLoading ? (
                <div className="p-8 text-center text-sm text-slate-500">
                  Loading patients...
                </div>
              ) : filteredPatients.length === 0 ? (
                <div className="p-8 text-center">
                  <p className="text-sm font-medium text-slate-900">
                    No patients found
                  </p>
                  <p className="mt-1 text-sm text-slate-500">
                    Add a patient or change your search.
                  </p>
                </div>
              ) : (
                <table className="min-w-full divide-y divide-slate-200">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Patient
                      </th>
                      <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Phone
                      </th>
                      <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Email
                      </th>
                      <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                        DOB
                      </th>
                      <th className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Address
                      </th>
                      <th className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-wide text-slate-500">
                        Actions
                      </th>
                    </tr>
                  </thead>

                  <tbody className="divide-y divide-slate-200 bg-white">
                    {filteredPatients.map((patient) => {
                      const address = getPatientAddress(patient);

                      return (
                        <tr key={patient.id} className="hover:bg-slate-50">
                          <td className="px-5 py-4 align-top">
                            <div className="font-medium text-slate-900">
                              {patient.full_name}
                            </div>

                            <div className="mt-1 max-w-xs truncate text-sm text-slate-500">
                              {patient.notes || "—"}
                            </div>
                          </td>

                          <td className="px-5 py-4 align-top text-sm text-slate-700">
                            <div>{patient.phone_primary}</div>

                            {patient.phone_secondary && (
                              <div className="mt-1 text-slate-500">
                                {patient.phone_secondary}
                              </div>
                            )}
                          </td>

                          <td className="px-5 py-4 align-top text-sm text-slate-700">
                            {patient.email || "—"}
                          </td>

                          <td className="px-5 py-4 align-top text-sm text-slate-700">
                            {formatDate(patient.date_of_birth)}
                          </td>

                          <td className="px-5 py-4 align-top text-sm text-slate-700">
                            <div className="max-w-xs truncate">
                              {address || "—"}
                            </div>
                          </td>

                          <td className="px-5 py-4 align-top">
                            <div className="flex justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => editPatient(patient)}
                                className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-100"
                              >
                                Edit
                              </button>

                              <button
                                type="button"
                                onClick={() => handleDeletePatient(patient)}
                                disabled={isDeletingId === patient.id}
                                className="rounded-lg border border-red-200 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-60"
                              >
                                {isDeletingId === patient.id
                                  ? "Deleting..."
                                  : "Delete"}
                              </button>
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </section>
        </div>
      </div>
    </DashboardShell>
  );
}