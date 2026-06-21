"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import DashboardShell from "@/components/layout/DashboardShell";
import {
  ServiceCategory,
  ServiceKeyword,
  createServiceCategory,
  createServiceKeyword,
  createServiceKeywords,
  deleteServiceKeyword,
  getActiveKeywordCounts,
  getCurrentSession,
  getServiceCategories,
  getServiceKeywords,
  updateServiceCategory,
  updateServiceKeyword,
  deleteServiceCategoryWithKeywords,
} from "@/lib/supabaseService";

type KeywordDraft = {
  keyword: string;
  language: string;
  matchType: string;
};

export default function ServicesPage() {
  const router = useRouter();

  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [isLoadingServices, setIsLoadingServices] = useState(true);
  const [isLoadingKeywords, setIsLoadingKeywords] = useState(false);
  const [isSavingService, setIsSavingService] = useState(false);
  const [isSavingKeyword, setIsSavingKeyword] = useState(false);

  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const [services, setServices] = useState<ServiceCategory[]>([]);
  const [keywords, setKeywords] = useState<ServiceKeyword[]>([]);
  const [keywordCounts, setKeywordCounts] = useState<Record<string, number>>({});

  const [selectedServiceId, setSelectedServiceId] = useState<string | null>(
    null
  );
  const [searchText, setSearchText] = useState("");

  const [isAddServiceOpen, setIsAddServiceOpen] = useState(false);
  const [isAddKeywordOpen, setIsAddKeywordOpen] = useState(false);

  const [isEditServiceOpen, setIsEditServiceOpen] = useState(false);
const [isEditKeywordOpen, setIsEditKeywordOpen] = useState(false);

const [editingServiceId, setEditingServiceId] = useState<string | null>(null);
const [editingKeywordId, setEditingKeywordId] = useState<string | null>(null);

const [editServiceName, setEditServiceName] = useState("");
const [editCanonicalReason, setEditCanonicalReason] = useState("");
const [editDefaultUrgency, setEditDefaultUrgency] = useState("normal");
const [editDefaultDurationMinutes, setEditDefaultDurationMinutes] = useState("30");
const [editDescription, setEditDescription] = useState("");
const [editCreatesAppointmentRequest, setEditCreatesAppointmentRequest] =
useState(true);
const [editIsActive, setEditIsActive] = useState(true);

const [editKeyword, setEditKeyword] = useState("");
const [editKeywordLanguage, setEditKeywordLanguage] = useState("fa");
const [editKeywordMatchType, setEditKeywordMatchType] = useState("contains");
const [editKeywordIsActive, setEditKeywordIsActive] = useState(true);
  // فعلاً clinic_id در دیتابیس nullable است، پس در UI نشان داده نمی‌شود.
  // اگر بعداً جدول clinics/profile را وصل کردی، فقط مقدار این state را از service جداگانه پر کن.
  const [currentClinicId] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [canonicalReason, setCanonicalReason] = useState("");
  const [defaultUrgency, setDefaultUrgency] = useState("normal");
  const [defaultDurationMinutes, setDefaultDurationMinutes] = useState("30");
  const [description, setDescription] = useState("");
  const [createsAppointmentRequest, setCreatesAppointmentRequest] =
    useState(true);
  const [isActive, setIsActive] = useState(true);

  const [keywordDrafts, setKeywordDrafts] = useState<KeywordDraft[]>([
    {
      keyword: "",
      language: "fa",
      matchType: "contains",
    },
  ]);

  const [newKeyword, setNewKeyword] = useState("");
  const [newKeywordLanguage, setNewKeywordLanguage] = useState("fa");
  const [newKeywordMatchType, setNewKeywordMatchType] = useState("contains");

  const selectedService =
    services.find((service) => service.id === selectedServiceId) || null;

  const filteredServices = useMemo(() => {
    const normalizedSearch = searchText.trim().toLowerCase();

    if (!normalizedSearch) return services;

    return services.filter((service) => {
      return (
        service.name.toLowerCase().includes(normalizedSearch) ||
        service.canonical_reason.toLowerCase().includes(normalizedSearch) ||
        service.default_urgency?.toLowerCase().includes(normalizedSearch)
      );
    });
  }, [services, searchText]);

  useEffect(() => {
    async function loadPage() {
      try {
        setErrorMessage("");

        const session = await getCurrentSession();

        if (!session) {
          router.replace("/login");
          return;
        }

        setIsCheckingSession(false);
        await loadServices();
      } catch (error) {
        console.error("Load services page error:", error);
        setErrorMessage(
          error instanceof Error ? error.message : "Failed to load services page."
        );
        setIsCheckingSession(false);
      }
    }

    loadPage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  async function loadServices(nextSelectedServiceId?: string) {
    try {
      setIsLoadingServices(true);
      setErrorMessage("");

      const loadedServices = await getServiceCategories(currentClinicId);
      setServices(loadedServices);

      const counts = await getActiveKeywordCounts(currentClinicId);
      setKeywordCounts(counts);

      if (loadedServices.length === 0) {
        setSelectedServiceId(null);
        setKeywords([]);
        setIsLoadingServices(false);
        return;
      }

      const serviceIdToSelect =
        nextSelectedServiceId || selectedServiceId || loadedServices[0].id;

      setSelectedServiceId(serviceIdToSelect);
      await loadKeywords(serviceIdToSelect);

      setIsLoadingServices(false);
    } catch (error) {
      console.error("Load services error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to load services."
      );
      setIsLoadingServices(false);
    }
  }

  async function loadKeywordCounts() {
    try {
      const counts = await getActiveKeywordCounts(currentClinicId);
      setKeywordCounts(counts);
    } catch (error) {
      console.error("Load keyword counts error:", error);
    }
  }

  async function loadKeywords(categoryId: string) {
    try {
      setIsLoadingKeywords(true);
      setErrorMessage("");

      const loadedKeywords = await getServiceKeywords(categoryId);
      setKeywords(loadedKeywords);

      setIsLoadingKeywords(false);
    } catch (error) {
      console.error("Load keywords error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to load keywords."
      );
      setIsLoadingKeywords(false);
    }
  }

  async function handleSelectService(serviceId: string) {
    setSelectedServiceId(serviceId);
    await loadKeywords(serviceId);
  }

  function resetServiceForm() {
    setName("");
    setCanonicalReason("");
    setDefaultUrgency("normal");
    setDefaultDurationMinutes("30");
    setDescription("");
    setCreatesAppointmentRequest(true);
    setIsActive(true);
    setKeywordDrafts([
      {
        keyword: "",
        language: "fa",
        matchType: "contains",
      },
    ]);
  }

  function updateKeywordDraft(
    index: number,
    field: keyof KeywordDraft,
    value: string
  ) {
    setKeywordDrafts((currentDrafts) =>
      currentDrafts.map((draft, draftIndex) =>
        draftIndex === index ? { ...draft, [field]: value } : draft
      )
    );
  }

  function addKeywordDraftRow() {
    setKeywordDrafts((currentDrafts) => [
      ...currentDrafts,
      {
        keyword: "",
        language: "fa",
        matchType: "contains",
      },
    ]);
  }

  function removeKeywordDraftRow(index: number) {
    setKeywordDrafts((currentDrafts) =>
      currentDrafts.filter((_, draftIndex) => draftIndex !== index)
    );
  }

  async function handleCreateService(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      setErrorMessage("");
      setSuccessMessage("");

      if (!name.trim()) {
        setErrorMessage("Service name is required.");
        return;
      }

      if (!canonicalReason.trim()) {
        setErrorMessage("Canonical reason is required.");
        return;
      }

      const durationNumber = Number(defaultDurationMinutes);

      if (!Number.isFinite(durationNumber) || durationNumber <= 0) {
        setErrorMessage("Default duration must be a positive number.");
        return;
      }

      const cleanedKeywords = keywordDrafts
        .map((item) => ({
          keyword: item.keyword.trim(),
          language: item.language.trim() || "fa",
          matchType: item.matchType.trim() || "contains",
        }))
        .filter((item) => item.keyword.length > 0);

      setIsSavingService(true);

      const categoryId = await createServiceCategory({
        clinicId: currentClinicId,
        name: name.trim(),
        canonicalReason: canonicalReason.trim(),
        defaultUrgency,
        createsAppointmentRequest,
        isActive,
        defaultDurationMinutes: durationNumber,
        description: description.trim() ? description.trim() : null,
      });

      await createServiceKeywords(
        cleanedKeywords.map((item) => ({
          clinicId: currentClinicId,
          categoryId,
          keyword: item.keyword,
          language: item.language,
          matchType: item.matchType,
        }))
      );

      setSuccessMessage("Service saved successfully.");
      setSelectedServiceId(categoryId);
      resetServiceForm();
      setIsAddServiceOpen(false);

      await loadServices(categoryId);
      await loadKeywords(categoryId);

      setIsSavingService(false);
    } catch (error) {
      console.error("Create service error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to create service."
      );
      setIsSavingService(false);
    }
  }

  async function handleAddKeyword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      setErrorMessage("");
      setSuccessMessage("");

      if (!selectedService) {
        setErrorMessage("Select a service first.");
        return;
      }

      if (!newKeyword.trim()) {
        setErrorMessage("Keyword is required.");
        return;
      }

      setIsSavingKeyword(true);

      await createServiceKeyword({
        clinicId: selectedService.clinic_id || currentClinicId,
        categoryId: selectedService.id,
        keyword: newKeyword.trim(),
        language: newKeywordLanguage,
        matchType: newKeywordMatchType,
      });

      setSuccessMessage("Keyword added successfully.");
      setNewKeyword("");
      setNewKeywordLanguage("fa");
      setNewKeywordMatchType("contains");
      setIsAddKeywordOpen(false);

      await loadKeywords(selectedService.id);
      await loadKeywordCounts();

      setIsSavingKeyword(false);
    } catch (error) {
      console.error("Add keyword error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to add keyword."
      );
      setIsSavingKeyword(false);
    }
  }

  async function handleDisableKeyword(keywordId: string) {
    try {
      setErrorMessage("");
      setSuccessMessage("");

      await disableServiceKeyword(keywordId);

      setSuccessMessage("Keyword disabled.");

      if (selectedService) {
        await loadKeywords(selectedService.id);
        await loadKeywordCounts();
      }
    } catch (error) {
      console.error("Disable keyword error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to disable keyword."
      );
    }
  }
  function openEditServiceModal(service: ServiceCategory) {
  setEditingServiceId(service.id);
  setEditServiceName(service.name);
  setEditCanonicalReason(service.canonical_reason);
  setEditDefaultUrgency(service.default_urgency || "normal");
  setEditDefaultDurationMinutes(String(service.default_duration_minutes));
  setEditDescription(service.description || "");
  setEditCreatesAppointmentRequest(Boolean(service.creates_appointment_request));
  setEditIsActive(Boolean(service.is_active));
  setIsEditServiceOpen(true);
}

async function handleUpdateService(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();

  try {
    setErrorMessage("");
    setSuccessMessage("");

    if (!editingServiceId) {
      setErrorMessage("No service selected.");
      return;
    }

    if (!editServiceName.trim()) {
      setErrorMessage("Service name is required.");
      return;
    }

    if (!editCanonicalReason.trim()) {
      setErrorMessage("Canonical reason is required.");
      return;
    }

    const durationNumber = Number(editDefaultDurationMinutes);

    if (!Number.isFinite(durationNumber) || durationNumber <= 0) {
      setErrorMessage("Default duration must be a positive number.");
      return;
    }

    await updateServiceCategory({
      id: editingServiceId,
      name: editServiceName.trim(),
      canonicalReason: editCanonicalReason.trim(),
      defaultUrgency: editDefaultUrgency,
      createsAppointmentRequest: editCreatesAppointmentRequest,
      isActive: editIsActive,
      defaultDurationMinutes: durationNumber,
      description: editDescription.trim() ? editDescription.trim() : null,
    });

    setSuccessMessage("Service updated successfully.");
    setIsEditServiceOpen(false);

    await loadServices(editingServiceId);
  } catch (error) {
    console.error("Update service error:", error);
    setErrorMessage(
      error instanceof Error ? error.message : "Failed to update service."
    );
  }
}

function openEditKeywordModal(keyword: ServiceKeyword) {
  setEditingKeywordId(keyword.id);
  setEditKeyword(keyword.keyword);
  setEditKeywordLanguage(keyword.language || "fa");
  setEditKeywordMatchType(keyword.match_type || "contains");
  setEditKeywordIsActive(Boolean(keyword.is_active));
  setIsEditKeywordOpen(true);
}

async function handleUpdateKeyword(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();

  try {
    setErrorMessage("");
    setSuccessMessage("");

    if (!editingKeywordId) {
      setErrorMessage("No keyword selected.");
      return;
    }

    if (!editKeyword.trim()) {
      setErrorMessage("Keyword is required.");
      return;
    }

    await updateServiceKeyword({
      id: editingKeywordId,
      keyword: editKeyword.trim(),
      language: editKeywordLanguage,
      matchType: editKeywordMatchType,
      isActive: editKeywordIsActive,
    });

    setSuccessMessage("Keyword updated successfully.");
    setIsEditKeywordOpen(false);

    if (selectedService) {
      await loadKeywords(selectedService.id);
      await loadKeywordCounts();
    }
  } catch (error) {
    console.error("Update keyword error:", error);
    setErrorMessage(
      error instanceof Error ? error.message : "Failed to update keyword."
    );
  }
}
async function handleDeleteKeyword(keywordId: string) {
  const confirmed = window.confirm("Are you sure you want to delete this keyword?");

  if (!confirmed) return;

  try {
    setErrorMessage("");
    setSuccessMessage("");

    await deleteServiceKeyword(keywordId);

    setSuccessMessage("Keyword deleted successfully.");

    if (selectedService) {
      await loadKeywords(selectedService.id);
      await loadKeywordCounts();
    }
  } catch (error) {
    console.error("Delete keyword error:", error);
    setErrorMessage(
      error instanceof Error ? error.message : "Failed to delete keyword."
    );
  }
}
async function handleDeleteService(service: ServiceCategory) {
  const confirmed = window.confirm(
    `Are you sure you want to delete "${service.name}"? All keywords for this service will also be deleted.`
  );

  if (!confirmed) return;

  try {
    setErrorMessage("");
    setSuccessMessage("");

    await deleteServiceCategoryWithKeywords(service.id);

    setSuccessMessage("Service and related keywords deleted successfully.");

    setSelectedServiceId(null);
    setKeywords([]);

    await loadServices();
  } catch (error) {
    console.error("Delete service error:", error);
    setErrorMessage(
      error instanceof Error ? error.message : "Failed to delete service."
    );
  }
}
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
      title="Services"
      description="Manage service categories and AI recognition keywords."
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

      <div
        dir="ltr"
        className="grid grid-cols-1 gap-6 lg:grid-cols-[400px_minmax(0,1fr)]"
      >
        <section
          dir="ltr"
          className="rounded-2xl border border-slate-200 bg-white shadow-sm"
        >
          <div className="border-b border-slate-100 p-5">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <h2 className="truncate text-lg font-bold text-slate-900">
                  Service List
                </h2>
                <p className="mt-1 truncate text-sm text-slate-500">
                  Select a service to manage its keywords.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setIsAddServiceOpen(true)}
                className="shrink-0 whitespace-nowrap rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
              >
                + Add Service
              </button>
            </div>

            <input
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="Search services..."
              className="mt-4 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-blue-500"
            />
          </div>

          <div className="max-h-[650px] overflow-y-auto p-3">
            {isLoadingServices && (
              <div className="rounded-xl bg-slate-50 p-5 text-center text-sm text-slate-500">
                Loading services...
              </div>
            )}

            {!isLoadingServices && filteredServices.length === 0 && (
              <div className="rounded-xl bg-slate-50 p-5 text-center text-sm text-slate-500">
                No services found.
              </div>
            )}

            {!isLoadingServices &&
              filteredServices.map((service) => {
                const isSelected = service.id === selectedServiceId;

                return (
                    <div
                    key={service.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => handleSelectService(service.id)}
                    onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        handleSelectService(service.id);
                        }
                    }}
                    className={`mb-2 w-full cursor-pointer rounded-2xl border px-4 py-3 text-left transition ${
                        isSelected
                        ? "border-blue-300 bg-blue-50 shadow-sm"
                        : "border-slate-200 bg-white hover:bg-slate-50"
                    }`}
                    >
                    

                    <div className="flex items-center justify-between gap-3">
                        <p className="min-w-0 truncate font-semibold text-slate-900">
                        {service.name}
                        </p>

                        <div className="flex shrink-0 items-center justify-end gap-2">
                        <span
                            className={`rounded-full px-3 py-1 text-xs font-semibold ${
                            service.is_active
                                ? "bg-green-50 text-green-700"
                                : "bg-slate-100 text-slate-500"
                            }`}
                        >
                            {service.is_active ? "Active" : "Inactive"}
                        </span>

                        <button
                            type="button"
                            onClick={(event) => {
                            event.stopPropagation();
                            openEditServiceModal(service);
                            }}
                            className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                        >
                            Edit
                        </button>

                        <button
                            type="button"
                            onClick={(event) => {
                            event.stopPropagation();
                            handleDeleteService(service);
                            }}
                            className="rounded-full border border-red-200 bg-red-50 px-3 py-1 text-xs font-semibold text-red-700 hover:bg-red-100"
                        >
                            Delete
                        </button>
                        </div>
                    </div>

                    <div className="mt-2 grid min-w-0 grid-cols-[1fr_auto] items-center gap-4 text-xs text-slate-500">
                        <span className="min-w-0 truncate font-medium text-slate-600">
                        {service.canonical_reason}
                        </span>

                        <div className="flex shrink-0 items-center gap-1.5 whitespace-nowrap text-slate-500">
                        <span>{service.default_duration_minutes}m</span>
                        <span className="text-slate-300">•</span>
                        <span>{service.default_urgency || "normal"}</span>
                        <span className="text-slate-300">•</span>
                        <span>{keywordCounts[service.id] || 0} kw</span>
                        </div>
                    </div>
                    </div>
                );
              })}
          </div>
        </section>

        <section
          dir="ltr"
          className="rounded-2xl border border-slate-200 bg-white shadow-sm"
        >
          {!selectedService && (
            <div className="flex min-h-[400px] items-center justify-center p-8 text-center">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  Select a service
                </h2>
                <p className="mt-2 text-sm text-slate-500">
                  Choose a service from the left list to view and manage its AI
                  recognition keywords.
                </p>
              </div>
            </div>
          )}

          {selectedService && (
            <>
              <div className="border-b border-slate-100 p-5">
                <div className="flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <h2 className="truncate text-xl font-bold text-slate-900">
                      {selectedService.name}
                    </h2>
                  </div>

                  <button
                    type="button"
                    onClick={() => setIsAddKeywordOpen(true)}
                    className="shrink-0 whitespace-nowrap rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
                  >
                    + Add Keyword
                  </button>
                </div>
              </div>

              <div className="p-5">
                <div className="overflow-hidden rounded-xl border border-slate-100">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-slate-50 text-slate-500">
                      <tr>
                        <th className="px-4 py-3 font-semibold">Keyword</th>
                        <th className="px-4 py-3 font-semibold">Match Type</th>
                        <th className="w-20 px-3 py-3 text-center font-semibold">Status</th>
                        <th className="px-4 py-3 font-semibold text-right">Actions</th>
                      </tr>
                    </thead>

                    <tbody className="divide-y divide-slate-100 bg-white">
                      {isLoadingKeywords && (
                        <tr>
                          <td
                            colSpan={4}
                            className="px-4 py-6 text-center text-sm text-slate-500"
                          >
                            Loading keywords...
                          </td>
                        </tr>
                      )}

                      {!isLoadingKeywords && keywords.length === 0 && (
                        <tr>
                          <td
                            colSpan={5}
                            className="px-4 py-6 text-center text-sm text-slate-500"
                          >
                            No keywords for this service yet.
                          </td>
                        </tr>
                      )}

                      {!isLoadingKeywords &&
                        keywords.map((keyword) => (
                          <tr key={keyword.id}>
                            <td className="px-4 py-4 font-medium text-slate-900">
                              {keyword.keyword}
                            </td>


                            <td className="px-4 py-4 text-slate-600">
                              {keyword.match_type || "contains"}
                            </td>

                            <td className="w-20 px-3 py-4 text-center">
                            <span
                                className={`inline-flex rounded-full px-2 py-1 text-[11px] font-semibold ${
                                keyword.is_active
                                    ? "bg-green-50 text-green-700"
                                    : "bg-slate-100 text-slate-500"
                                }`}
                            >
                                {keyword.is_active ? "Active" : "Off"}
                            </span>
                            </td>

                            <td className="px-4 py-4 text-right">
                            <div className="flex justify-end gap-3">
                                <button
                                type="button"
                                onClick={() => openEditKeywordModal(keyword)}
                                className="font-semibold text-blue-600 hover:text-blue-700"
                                >
                                Edit
                                </button>

                                <button
                                type="button"
                                onClick={() => handleDeleteKeyword(keyword.id)}
                                className="font-semibold text-red-600 hover:text-red-700"
                                >
                                Delete
                                </button>
                            </div>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </section>
      </div>

      {isAddServiceOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white shadow-xl">
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  Add Service
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Create a service category and optional keywords.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setIsAddServiceOpen(false)}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
              >
                Close
              </button>
            </div>

            <form onSubmit={handleCreateService} className="space-y-5 p-5">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div>
                  <label className="text-sm font-medium text-slate-700">
                    Service Name
                  </label>
                  <input
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="Example: Tooth Cleaning"
                    className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                  />
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
                    placeholder="Example: cleaning"
                    className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div>
                  <label className="text-sm font-medium text-slate-700">
                    Default Urgency
                  </label>
                  <select
                    value={defaultUrgency}
                    onChange={(event) =>
                      setDefaultUrgency(event.target.value)
                    }
                    className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                  >
                    <option value="low">Low</option>
                    <option value="normal">Normal</option>
                    <option value="urgent">Urgent</option>
                    <option value="emergency">Emergency</option>
                  </select>
                </div>

                <div>
                  <label className="text-sm font-medium text-slate-700">
                    Default Duration Minutes
                  </label>
                  <input
                    type="number"
                    min="1"
                    value={defaultDurationMinutes}
                    onChange={(event) =>
                      setDefaultDurationMinutes(event.target.value)
                    }
                    className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                  />
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Description
                </label>
                <textarea
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder="Optional internal description"
                  rows={3}
                  className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={createsAppointmentRequest}
                    onChange={(event) =>
                      setCreatesAppointmentRequest(event.target.checked)
                    }
                    className="h-4 w-4 rounded border-slate-300"
                  />
                  Creates appointment request
                </label>

                <label className="flex items-center gap-2 text-sm text-slate-700">
                  <input
                    type="checkbox"
                    checked={isActive}
                    onChange={(event) => setIsActive(event.target.checked)}
                    className="h-4 w-4 rounded border-slate-300"
                  />
                  Active
                </label>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <div className="mb-4 flex items-center justify-between gap-4">
                  <div>
                    <h3 className="font-bold text-slate-900">
                      Initial Keywords
                    </h3>
                    <p className="mt-1 text-sm text-slate-500">
                      Optional keywords for AI recognition.
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={addKeywordDraftRow}
                    className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
                  >
                    Add row
                  </button>
                </div>

                <div className="space-y-3">
                  {keywordDrafts.map((item, index) => (
                    <div
                      key={index}
                      className="grid grid-cols-1 gap-3 rounded-xl border border-slate-200 bg-white p-3 md:grid-cols-[1fr_120px_150px_auto]"
                    >
                      <input
                        value={item.keyword}
                        onChange={(event) =>
                          updateKeywordDraft(
                            index,
                            "keyword",
                            event.target.value
                          )
                        }
                        placeholder="Example: جرم گیری"
                        className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
                      />

                      <select
                        value={item.language}
                        onChange={(event) =>
                          updateKeywordDraft(
                            index,
                            "language",
                            event.target.value
                          )
                        }
                        className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
                      >
                        <option value="fa">fa</option>
                        <option value="en">en</option>
                        <option value="ar">ar</option>
                        <option value="auto">auto</option>
                      </select>

                      <select
                        value={item.matchType}
                        onChange={(event) =>
                          updateKeywordDraft(
                            index,
                            "matchType",
                            event.target.value
                          )
                        }
                        className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-blue-500"
                      >
                        <option value="contains">contains</option>
                        <option value="exact">exact</option>
                        <option value="starts_with">starts_with</option>
                      </select>

                      <button
                        type="button"
                        onClick={() => removeKeywordDraftRow(index)}
                        disabled={keywordDrafts.length === 1}
                        className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm font-semibold text-red-700 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              </div>

              <button
                type="submit"
                disabled={isSavingService}
                className="w-full rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSavingService ? "Saving..." : "Save Service"}
              </button>
            </form>
          </div>
        </div>
      )}
        {isEditServiceOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
            <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white shadow-xl">
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
                <div>
                <h2 className="text-lg font-bold text-slate-900">Edit Service</h2>
                <p className="mt-1 text-sm text-slate-500">
                    Update service category information.
                </p>
                </div>

                <button
                type="button"
                onClick={() => setIsEditServiceOpen(false)}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
                >
                Close
                </button>
            </div>

            <form onSubmit={handleUpdateService} className="space-y-5 p-5">
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div>
                    <label className="text-sm font-medium text-slate-700">
                    Service Name
                    </label>
                    <input
                    value={editServiceName}
                    onChange={(event) => setEditServiceName(event.target.value)}
                    className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    />
                </div>

                <div>
                    <label className="text-sm font-medium text-slate-700">
                    Canonical Reason
                    </label>
                    <input
                    value={editCanonicalReason}
                    onChange={(event) => setEditCanonicalReason(event.target.value)}
                    className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    />
                </div>
                </div>

                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div>
                    <label className="text-sm font-medium text-slate-700">
                    Default Urgency
                    </label>
                    <select
                    value={editDefaultUrgency}
                    onChange={(event) => setEditDefaultUrgency(event.target.value)}
                    className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    >
                    <option value="low">Low</option>
                    <option value="normal">Normal</option>
                    <option value="urgent">Urgent</option>
                    <option value="emergency">Emergency</option>
                    </select>
                </div>

                <div>
                    <label className="text-sm font-medium text-slate-700">
                    Default Duration Minutes
                    </label>
                    <input
                    type="number"
                    min="1"
                    value={editDefaultDurationMinutes}
                    onChange={(event) =>
                        setEditDefaultDurationMinutes(event.target.value)
                    }
                    className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    />
                </div>
                </div>

                <div>
                <label className="text-sm font-medium text-slate-700">
                    Description
                </label>
                <textarea
                    value={editDescription}
                    onChange={(event) => setEditDescription(event.target.value)}
                    rows={3}
                    className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
                </div>

                <div className="flex flex-wrap gap-4">
                <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                    type="checkbox"
                    checked={editCreatesAppointmentRequest}
                    onChange={(event) =>
                        setEditCreatesAppointmentRequest(event.target.checked)
                    }
                    className="h-4 w-4 rounded border-slate-300"
                    />
                    Creates appointment request
                </label>

                <label className="flex items-center gap-2 text-sm text-slate-700">
                    <input
                    type="checkbox"
                    checked={editIsActive}
                    onChange={(event) => setEditIsActive(event.target.checked)}
                    className="h-4 w-4 rounded border-slate-300"
                    />
                    Active
                </label>
                </div>

                <button
                type="submit"
                className="w-full rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800"
                >
                Save Changes
                </button>
            </form>
            </div>
        </div>
        )}

        {isEditKeywordOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
            <div className="w-full max-w-lg rounded-2xl bg-white shadow-xl">
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
                <div>
                <h2 className="text-lg font-bold text-slate-900">Edit Keyword</h2>
                <p className="mt-1 text-sm text-slate-500">
                    Update AI keyword matching information.
                </p>
                </div>

                <button
                type="button"
                onClick={() => setIsEditKeywordOpen(false)}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
                >
                Close
                </button>
            </div>

            <form onSubmit={handleUpdateKeyword} className="space-y-5 p-5">
                <div>
                <label className="text-sm font-medium text-slate-700">
                    Keyword
                </label>
                <input
                    value={editKeyword}
                    onChange={(event) => setEditKeyword(event.target.value)}
                    className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
                </div>

                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div>
                    <label className="text-sm font-medium text-slate-700">
                    Language
                    </label>
                    <select
                    value={editKeywordLanguage}
                    onChange={(event) => setEditKeywordLanguage(event.target.value)}
                    className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    >
                    <option value="fa">fa</option>
                    <option value="en">en</option>
                    <option value="ar">ar</option>
                    <option value="auto">auto</option>
                    </select>
                </div>

                <div>
                    <label className="text-sm font-medium text-slate-700">
                    Match Type
                    </label>
                    <select
                    value={editKeywordMatchType}
                    onChange={(event) => setEditKeywordMatchType(event.target.value)}
                    className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                    >
                    <option value="contains">contains</option>
                    <option value="exact">exact</option>
                    <option value="starts_with">starts_with</option>
                    </select>
                </div>
                </div>

                <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                    type="checkbox"
                    checked={editKeywordIsActive}
                    onChange={(event) => setEditKeywordIsActive(event.target.checked)}
                    className="h-4 w-4 rounded border-slate-300"
                />
                Active
                </label>

                <button
                type="submit"
                className="w-full rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800"
                >
                Save Changes
                </button>
            </form>
            </div>
        </div>
        )}

      {isAddKeywordOpen && selectedService && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white shadow-xl">
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  Add Keyword
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Add a keyword for {selectedService.name}.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setIsAddKeywordOpen(false)}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
              >
                Close
              </button>
            </div>

            <form onSubmit={handleAddKeyword} className="space-y-5 p-5">
              <div>
                <label className="text-sm font-medium text-slate-700">
                  Keyword
                </label>
                <input
                  value={newKeyword}
                  onChange={(event) => setNewKeyword(event.target.value)}
                  placeholder="Example: tooth cleaning"
                  className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <div>
                  <label className="text-sm font-medium text-slate-700">
                    Language
                  </label>
                  <select
                    value={newKeywordLanguage}
                    onChange={(event) =>
                      setNewKeywordLanguage(event.target.value)
                    }
                    className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                  >
                    <option value="fa">fa</option>
                    <option value="en">en</option>
                    <option value="ar">ar</option>
                    <option value="auto">auto</option>
                  </select>
                </div>

                <div>
                  <label className="text-sm font-medium text-slate-700">
                    Match Type
                  </label>
                  <select
                    value={newKeywordMatchType}
                    onChange={(event) =>
                      setNewKeywordMatchType(event.target.value)
                    }
                    className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                  >
                    <option value="contains">contains</option>
                    <option value="exact">exact</option>
                    <option value="starts_with">starts_with</option>
                  </select>
                </div>
              </div>

              <button
                type="submit"
                disabled={isSavingKeyword}
                className="w-full rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSavingKeyword ? "Saving..." : "Save Keyword"}
              </button>
            </form>
          </div>
        </div>
      )}
    </DashboardShell>
  );
}