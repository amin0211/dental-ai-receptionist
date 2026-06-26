"use client";

import { FormEvent, Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import DashboardShell from "@/components/layout/DashboardShell";
import { useClinic } from "@/components/providers/ClinicProvider";
import {
  CallExtraction,
  ClinicDoctor,
  ServiceCategory,
  getCallExtractions,
  getClinicDoctors,
  getServiceCategories,
  updateCallExtractionReview,
} from "@/lib/supabaseService";

const missingFieldOptions = [
  { value: "patient_name", label: "Patient name missing" },
  { value: "patient_phone", label: "Patient phone missing" },
  { value: "service", label: "Service missing" },
  { value: "doctor_unclear", label: "Doctor unclear" },
  { value: "preferred_date", label: "Date missing" },
  { value: "preferred_time", label: "Time missing" },
  { value: "low_confidence", label: "Low confidence" },
];

function formatDateTime(value: string | null) {
  if (!value) return "-";

  return new Date(value).toLocaleString("en-CA", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatConfidence(value: number | null) {
  if (value === null || value === undefined) return "-";
  return `${Math.round(Number(value) * 100)}%`;
}

function getConfidenceClass(value: number | null) {
  if (value === null || value === undefined) {
    return "bg-slate-100 text-slate-600";
  }

  if (value < 0.6) {
    return "bg-red-50 text-red-700";
  }

  if (value < 0.8) {
    return "bg-amber-50 text-amber-700";
  }

  return "bg-green-50 text-green-700";
}

function getStatusClass(status: string | null) {
  switch (status) {
    case "complete":
      return "bg-green-50 text-green-700 border-green-200";
    case "converted":
      return "bg-blue-50 text-blue-700 border-blue-200";
    case "incomplete":
      return "bg-red-50 text-red-700 border-red-200";
    case "ignored":
      return "bg-slate-100 text-slate-600 border-slate-200";
    case "needs_review":
    default:
      return "bg-amber-50 text-amber-700 border-amber-200";
  }
}

function toDatetimeLocalValue(value: string | null) {
  if (!value) return "";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) return "";

  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  const localDate = new Date(date.getTime() - offsetMs);

  return localDate.toISOString().slice(0, 16);
}

function fromDatetimeLocalValue(value: string) {
  if (!value) return null;
  return new Date(value).toISOString();
}

function getFilterTitle(filter: string | null) {
  switch (filter) {
    case "incomplete":
      return "Incomplete Calls";
    case "needs_review":
      return "Needs Review";
    case "low_confidence":
      return "Low Confidence Calls";
    case "converted":
      return "Converted Calls";
    default:
      return "All Calls";
  }
}

export default function CallsPage() {
  return (
    <Suspense fallback={<CallsPageLoading />}>
      <CallsPageContent />
    </Suspense>
  );
}

function CallsPageLoading() {
  return (
    <DashboardShell
      title="Calls"
      description="Review AI call extractions, incomplete calls, and extracted appointment details."
    >
      <div className="rounded-2xl border border-slate-200 bg-white p-8 text-center text-sm font-medium text-slate-500">
        Loading calls...
      </div>
    </DashboardShell>
  );
}

function CallsPageContent() {
  const searchParams = useSearchParams();
  const filter = searchParams.get("filter");

  const { clinicId, isLoadingClinic } = useClinic();

  const [calls, setCalls] = useState<CallExtraction[]>([]);
  const [doctors, setDoctors] = useState<ClinicDoctor[]>([]);
  const [services, setServices] = useState<ServiceCategory[]>([]);

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const [selectedCall, setSelectedCall] = useState<CallExtraction | null>(null);
  const [isReviewOpen, setIsReviewOpen] = useState(false);

  const [patientName, setPatientName] = useState("");
  const [patientPhone, setPatientPhone] = useState("");
  const [serviceCategory, setServiceCategory] = useState("");
  const [canonicalReason, setCanonicalReason] = useState("");
  const [preferredDateRaw, setPreferredDateRaw] = useState("");
  const [preferredTimeRaw, setPreferredTimeRaw] = useState("");
  const [preferredDatetime, setPreferredDatetime] = useState("");
  const [urgency, setUrgency] = useState("normal");
  const [doctorId, setDoctorId] = useState("");
  const [preferredDoctorName, setPreferredDoctorName] = useState("");
  const [preferredDateConfirmed, setPreferredDateConfirmed] = useState(false);
  const [preferredTimeConfirmed, setPreferredTimeConfirmed] = useState(false);
  const [extractionStatus, setExtractionStatus] = useState("needs_review");
  const [missingFields, setMissingFields] = useState<string[]>([]);
  const [extractionNotes, setExtractionNotes] = useState("");

  const pageTitle = useMemo(() => getFilterTitle(filter), [filter]);

  async function loadCalls() {
    if (!clinicId) return;

    try {
      setIsLoading(true);
      setErrorMessage("");

      const [loadedCalls, loadedDoctors, loadedServices] = await Promise.all([
        getCallExtractions({
          clinicId,
          filter,
        }),
        getClinicDoctors(clinicId),
        getServiceCategories(clinicId),
      ]);

      setCalls(loadedCalls);
      setDoctors(loadedDoctors);
      setServices(loadedServices);
      setIsLoading(false);
    } catch (error) {
      console.error("Load calls error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to load calls."
      );
      setIsLoading(false);
    }
  }

  useEffect(() => {
    if (isLoadingClinic) return;

    if (!clinicId) {
      setErrorMessage("Clinic was not found for this account.");
      setIsLoading(false);
      return;
    }

    loadCalls();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clinicId, isLoadingClinic, filter]);

  function openReviewModal(call: CallExtraction) {
    setSelectedCall(call);

    setPatientName(call.patient_name || "");
    setPatientPhone(call.patient_phone || "");
    setServiceCategory(call.service_category || "");
    setCanonicalReason(call.canonical_reason || "");
    setPreferredDateRaw(call.preferred_date_raw || "");
    setPreferredTimeRaw(call.preferred_time_raw || "");
    setPreferredDatetime(toDatetimeLocalValue(call.preferred_datetime));
    setUrgency(call.urgency || "normal");
    setDoctorId(call.doctor_id || "");
    setPreferredDoctorName(call.preferred_doctor_name || "");
    setPreferredDateConfirmed(Boolean(call.preferred_date_confirmed));
    setPreferredTimeConfirmed(Boolean(call.preferred_time_confirmed));
    setExtractionStatus(call.extraction_status || "needs_review");
    setMissingFields(call.missing_fields || []);
    setExtractionNotes(call.extraction_notes || "");

    setIsReviewOpen(true);
  }

  function handleServiceSelect(value: string) {
    const selectedService = services.find((service) => service.id === value);

    if (!selectedService) {
      setServiceCategory("");
      setCanonicalReason("");
      return;
    }

    setServiceCategory(selectedService.name);
    setCanonicalReason(selectedService.canonical_reason);
  }

  function handleDoctorSelect(value: string) {
    setDoctorId(value);

    const selectedDoctor = doctors.find((doctor) => doctor.id === value);

    if (selectedDoctor) {
      setPreferredDoctorName(
        selectedDoctor.display_name || selectedDoctor.full_name
      );
    }
  }

  function toggleMissingField(value: string, checked: boolean) {
    setMissingFields((current) => {
      if (checked) {
        return Array.from(new Set([...current, value]));
      }

      return current.filter((item) => item !== value);
    });
  }

  async function handleSaveReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!clinicId) {
      setErrorMessage("Clinic was not found for this account.");
      return;
    }

    if (!selectedCall) {
      setErrorMessage("No call selected.");
      return;
    }

    try {
      setIsSaving(true);
      setErrorMessage("");
      setSuccessMessage("");

      await updateCallExtractionReview({
        id: selectedCall.id,
        clinicId,
        patientId: selectedCall.patient_id,
        patientName: patientName.trim() ? patientName.trim() : null,
        patientPhone: patientPhone.trim() ? patientPhone.trim() : null,
        serviceCategory: serviceCategory.trim() ? serviceCategory.trim() : null,
        canonicalReason: canonicalReason.trim() ? canonicalReason.trim() : null,
        preferredDateRaw: preferredDateRaw.trim() ? preferredDateRaw.trim() : null,
        preferredTimeRaw: preferredTimeRaw.trim() ? preferredTimeRaw.trim() : null,
        preferredDatetime: fromDatetimeLocalValue(preferredDatetime),
        urgency,
        doctorId: doctorId || null,
        preferredDoctorName: preferredDoctorName.trim()
          ? preferredDoctorName.trim()
          : null,
        preferredDateConfirmed,
        preferredTimeConfirmed,
        extractionStatus,
        missingFields,
        extractionNotes: extractionNotes.trim() ? extractionNotes.trim() : null,
        reviewedBy: null,
      });

      setSuccessMessage("Call review saved successfully.");
      setIsReviewOpen(false);
      setSelectedCall(null);

      await loadCalls();

      setIsSaving(false);
    } catch (error) {
      console.error("Save call review error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to save call review."
      );
      setIsSaving(false);
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
      title="Calls"
      description="Review AI call extractions, incomplete calls, and extracted appointment details."
    >
      {errorMessage && (
        <div className="mb-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage}
        </div>
      )}

      {successMessage && (
        <div className="mb-6 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
          {successMessage}
        </div>
      )}

      <div className="mb-6 flex flex-wrap gap-2">
        <FilterLink href="/dashboard/calls" active={!filter}>
          All
        </FilterLink>

        <FilterLink
          href="/dashboard/calls?filter=incomplete"
          active={filter === "incomplete"}
        >
          Incomplete
        </FilterLink>

        <FilterLink
          href="/dashboard/calls?filter=needs_review"
          active={filter === "needs_review"}
        >
          Needs Review
        </FilterLink>

        <FilterLink
          href="/dashboard/calls?filter=low_confidence"
          active={filter === "low_confidence"}
        >
          Low Confidence
        </FilterLink>

        <FilterLink
          href="/dashboard/calls?filter=converted"
          active={filter === "converted"}
        >
          Converted
        </FilterLink>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-lg font-bold text-slate-900">{pageTitle}</h2>
          <p className="mt-1 text-sm text-slate-500">
            Showing AI-extracted call details for this clinic.
          </p>
        </div>

        {isLoading && (
          <div className="p-6 text-sm font-medium text-slate-500">
            Loading calls...
          </div>
        )}

        {!isLoading && calls.length === 0 && (
          <div className="p-6 text-sm text-slate-500">No calls found.</div>
        )}

        {!isLoading && calls.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1150px] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-5 py-3 font-semibold text-right">
                    Actions
                  </th>                
                  <th className="px-5 py-3 font-semibold">Created</th>
                  <th className="px-5 py-3 font-semibold">Patient</th>
                  <th className="px-5 py-3 font-semibold">Phone</th>
                  <th className="px-5 py-3 font-semibold">Service</th>
                  <th className="px-5 py-3 font-semibold">Doctor</th>
                  <th className="px-5 py-3 font-semibold">Preferred</th>
                  <th className="px-5 py-3 font-semibold">Urgency</th>
                  <th className="px-5 py-3 font-semibold">Confidence</th>
                  <th className="px-5 py-3 font-semibold">Status</th>
                  <th className="px-5 py-3 font-semibold">Missing</th>
                    
                </tr>
              </thead>

              <tbody className="divide-y divide-slate-100">
                {calls.map((call) => (
                  <tr key={call.id} className="hover:bg-slate-50">
                    <td className="px-5 py-4 text-right">
                      <button
                        type="button"
                        onClick={() => openReviewModal(call)}
                        className="font-semibold text-blue-600 hover:text-blue-700"
                      >
                        Review
                      </button>
                    </td>
                    <td className="whitespace-nowrap px-5 py-4 text-slate-600">
                      {formatDateTime(call.created_at)}
                    </td>

                    <td className="px-5 py-4 font-medium text-slate-900">
                      {call.patient_name || "Unknown"}
                    </td>

                    <td className="whitespace-nowrap px-5 py-4 text-slate-600">
                      {call.patient_phone || "-"}
                    </td>

                    <td className="px-5 py-4 text-slate-700">
                      <div>{call.service_category || "-"}</div>
                      {call.canonical_reason && (
                        <div className="mt-1 text-xs text-slate-400">
                          {call.canonical_reason}
                        </div>
                      )}
                    </td>

                    <td className="px-5 py-4 text-slate-700">
                      {call.preferred_doctor_name || "-"}
                    </td>

                    <td className="px-5 py-4 text-slate-700">
                      <div>{call.preferred_date_raw || "-"}</div>
                      <div className="mt-1 text-xs text-slate-400">
                        {call.preferred_time_raw || ""}
                      </div>
                    </td>

                    <td className="px-5 py-4 text-slate-700">
                      {call.urgency || "-"}
                    </td>

                    <td className="px-5 py-4">
                      <span
                        className={`inline-flex rounded-full px-2.5 py-1 text-xs font-semibold ${getConfidenceClass(
                          call.confidence
                        )}`}
                      >
                        {formatConfidence(call.confidence)}
                      </span>
                    </td>

                    <td className="px-5 py-4">
                      <span
                        className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${getStatusClass(
                          call.extraction_status
                        )}`}
                      >
                        {call.extraction_status || "needs_review"}
                      </span>
                    </td>

                    <td className="px-5 py-4 text-slate-600">
                      {call.missing_fields && call.missing_fields.length > 0
                        ? call.missing_fields.join(", ")
                        : "-"}
                    </td>


                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {isReviewOpen && selectedCall && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-2xl bg-white shadow-xl">
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  Review Call Extraction
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Review what the AI understood from this call and fix missing
                  information.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setIsReviewOpen(false)}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
              >
                Close
              </button>
            </div>

            <form onSubmit={handleSaveReview} className="space-y-6 p-5">
              <section className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <h3 className="font-bold text-slate-900">Transcript</h3>

                <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-2">
                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Raw Transcript
                    </label>
                    <textarea
                      value={selectedCall.raw_transcript || ""}
                      readOnly
                      rows={6}
                      className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 outline-none"
                    />
                  </div>

                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Cleaned Transcript
                    </label>
                    <textarea
                      value={selectedCall.cleaned_transcript || ""}
                      readOnly
                      rows={6}
                      className="mt-2 w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600 outline-none"
                    />
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
                  <InfoBox
                    label="Detected Language"
                    value={selectedCall.detected_language || "-"}
                  />
                  <InfoBox
                    label="Confidence"
                    value={formatConfidence(selectedCall.confidence)}
                  />
                  <InfoBox
                    label="Created"
                    value={formatDateTime(selectedCall.created_at)}
                  />
                </div>
              </section>

              <section className="rounded-2xl border border-slate-200 p-4">
                <h3 className="font-bold text-slate-900">Patient Info</h3>

                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Patient Name
                    </label>
                    <input
                      value={patientName}
                      onChange={(event) => setPatientName(event.target.value)}
                      className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    />
                  </div>

                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Patient Phone
                    </label>
                    <input
                      value={patientPhone}
                      onChange={(event) => setPatientPhone(event.target.value)}
                      className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    />
                  </div>
                </div>
              </section>

              <section className="rounded-2xl border border-slate-200 p-4">
                <h3 className="font-bold text-slate-900">
                  Appointment Request Info
                </h3>

                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Service
                    </label>
                    <select
                      value={
                        services.find(
                          (service) =>
                            service.name === serviceCategory ||
                            service.canonical_reason === canonicalReason
                        )?.id || ""
                      }
                      onChange={(event) => handleServiceSelect(event.target.value)}
                      className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    >
                      <option value="">Select service</option>
                      {services.map((service) => (
                        <option key={service.id} value={service.id}>
                          {service.name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Canonical Reason
                    </label>
                    <input
                      value={canonicalReason}
                      onChange={(event) =>
                        setCanonicalReason(event.target.value)
                      }
                      className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    />
                  </div>

                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Preferred Doctor
                    </label>
                    <select
                      value={doctorId}
                      onChange={(event) => handleDoctorSelect(event.target.value)}
                      className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    >
                      <option value="">Any doctor / Not matched</option>
                      {doctors.map((doctor) => (
                        <option key={doctor.id} value={doctor.id}>
                          {doctor.display_name || doctor.full_name}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Preferred Doctor Name
                    </label>
                    <input
                      value={preferredDoctorName}
                      onChange={(event) =>
                        setPreferredDoctorName(event.target.value)
                      }
                      className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    />
                  </div>

                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Preferred Date Raw
                    </label>
                    <input
                      value={preferredDateRaw}
                      onChange={(event) =>
                        setPreferredDateRaw(event.target.value)
                      }
                      placeholder="Example: next Monday"
                      className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    />
                  </div>

                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Preferred Time Raw
                    </label>
                    <input
                      value={preferredTimeRaw}
                      onChange={(event) =>
                        setPreferredTimeRaw(event.target.value)
                      }
                      placeholder="Example: afternoon"
                      className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    />
                  </div>

                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Preferred Datetime
                    </label>
                    <input
                      type="datetime-local"
                      value={preferredDatetime}
                      onChange={(event) =>
                        setPreferredDatetime(event.target.value)
                      }
                      className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    />
                  </div>

                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Urgency
                    </label>
                    <select
                      value={urgency}
                      onChange={(event) => setUrgency(event.target.value)}
                      className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    >
                      <option value="low">Low</option>
                      <option value="normal">Normal</option>
                      <option value="urgent">Urgent</option>
                      <option value="emergency">Emergency</option>
                    </select>
                  </div>
                </div>

                <div className="mt-4 flex flex-wrap gap-4">
                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={preferredDateConfirmed}
                      onChange={(event) =>
                        setPreferredDateConfirmed(event.target.checked)
                      }
                      className="h-4 w-4 rounded border-slate-300"
                    />
                    Preferred date confirmed
                  </label>

                  <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={preferredTimeConfirmed}
                      onChange={(event) =>
                        setPreferredTimeConfirmed(event.target.checked)
                      }
                      className="h-4 w-4 rounded border-slate-300"
                    />
                    Preferred time confirmed
                  </label>
                </div>
              </section>

              <section className="rounded-2xl border border-slate-200 p-4">
                <h3 className="font-bold text-slate-900">Review Status</h3>

                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Extraction Status
                    </label>
                    <select
                      value={extractionStatus}
                      onChange={(event) =>
                        setExtractionStatus(event.target.value)
                      }
                      className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    >
                      <option value="needs_review">Needs Review</option>
                      <option value="incomplete">Incomplete</option>
                      <option value="complete">Complete</option>
                      <option value="converted">Converted</option>
                      <option value="ignored">Ignored</option>
                    </select>
                  </div>

                  <div>
                    <label className="text-sm font-medium text-slate-700">
                      Extraction Notes
                    </label>
                    <textarea
                      value={extractionNotes}
                      onChange={(event) =>
                        setExtractionNotes(event.target.value)
                      }
                      rows={3}
                      className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    />
                  </div>
                </div>

                <div className="mt-4 rounded-2xl border border-slate-200 bg-slate-50 p-4">
                  <p className="text-sm font-semibold text-slate-700">
                    Missing Fields
                  </p>

                  <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-2">
                    {missingFieldOptions.map((item) => (
                      <label
                        key={item.value}
                        className="flex items-center gap-2 text-sm text-slate-700"
                      >
                        <input
                          type="checkbox"
                          checked={missingFields.includes(item.value)}
                          onChange={(event) =>
                            toggleMissingField(item.value, event.target.checked)
                          }
                          className="h-4 w-4 rounded border-slate-300"
                        />
                        {item.label}
                      </label>
                    ))}
                  </div>
                </div>
              </section>

              <button
                type="submit"
                disabled={isSaving}
                className="w-full rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSaving ? "Saving..." : "Save Review"}
              </button>
            </form>
          </div>
        </div>
      )}
    </DashboardShell>
  );
}

function FilterLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`rounded-xl border px-4 py-2 text-sm font-semibold transition ${
        active
          ? "border-blue-200 bg-blue-50 text-blue-700"
          : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
      }`}
    >
      {children}
    </Link>
  );
}

function InfoBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3">
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">
        {label}
      </p>
      <p className="mt-1 text-sm font-semibold text-slate-800">{value}</p>
    </div>
  );
}