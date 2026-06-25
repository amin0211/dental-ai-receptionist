"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useClinic } from "@/components/providers/ClinicProvider";
import DashboardShell from "@/components/layout/DashboardShell";
import {
  ClinicDoctor,
  ClinicDoctorService,
  ServiceCategory,
  createClinicDoctor,
  deleteClinicDoctorWithServices,
  getClinicDoctorServices,
  getClinicDoctors,
  getServiceCategories,
  updateClinicDoctor,
  setClinicDoctorServiceActive,
} from "@/lib/supabaseService";

export default function DoctorsPage() {
  const { clinicId, isLoadingClinic } = useClinic();

  const currentClinicId = clinicId || "";

  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [isLoadingDoctors, setIsLoadingDoctors] = useState(true);
  const [isLoadingServices, setIsLoadingServices] = useState(false);
  const [isSavingDoctor, setIsSavingDoctor] = useState(false);
  const [isSavingDoctorService, setIsSavingDoctorService] = useState(false);

  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const [doctors, setDoctors] = useState<ClinicDoctor[]>([]);
  const [doctorServices, setDoctorServices] = useState<ClinicDoctorService[]>(
    []
  );
  const [serviceCategories, setServiceCategories] = useState<ServiceCategory[]>(
    []
  );
  const [isUpdatingDoctorService, setIsUpdatingDoctorService] = useState(false);

  const [selectedDoctorId, setSelectedDoctorId] = useState<string | null>(null);
  const [searchText, setSearchText] = useState("");

  const [isAddDoctorOpen, setIsAddDoctorOpen] = useState(false);
  const [isEditDoctorOpen, setIsEditDoctorOpen] = useState(false);
  const [isAddServiceOpen, setIsAddServiceOpen] = useState(false);
  const [isEditDoctorServiceOpen, setIsEditDoctorServiceOpen] = useState(false);

  const [editingDoctorId, setEditingDoctorId] = useState<string | null>(null);
  const [editingDoctorServiceId, setEditingDoctorServiceId] = useState<
    string | null
  >(null);

  const [fullName, setFullName] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [title, setTitle] = useState("Dr.");
  const [specialty, setSpecialty] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [email, setEmail] = useState("");
  const [doctorNotes, setDoctorNotes] = useState("");
  const [doctorIsActive, setDoctorIsActive] = useState(true);

  const [editFullName, setEditFullName] = useState("");
  const [editDisplayName, setEditDisplayName] = useState("");
  const [editTitle, setEditTitle] = useState("Dr.");
  const [editSpecialty, setEditSpecialty] = useState("");
  const [editPhoneNumber, setEditPhoneNumber] = useState("");
  const [editEmail, setEditEmail] = useState("");
  const [editDoctorNotes, setEditDoctorNotes] = useState("");
  const [editDoctorIsActive, setEditDoctorIsActive] = useState(true);

  const [selectedServiceCategoryId, setSelectedServiceCategoryId] =
    useState("");
  const [doctorServiceNotes, setDoctorServiceNotes] = useState("");

  const [editDoctorServiceIsActive, setEditDoctorServiceIsActive] =
    useState(true);
  const [editDoctorServiceNotes, setEditDoctorServiceNotes] = useState("");

  const selectedDoctor =
    doctors.find((doctor) => doctor.id === selectedDoctorId) || null;

  const serviceNameById = useMemo(() => {
    const map: Record<string, string> = {};

    serviceCategories.forEach((service) => {
      map[service.id] = service.name;
    });

    return map;
  }, [serviceCategories]);

  const filteredDoctors = useMemo(() => {
    const normalizedSearch = searchText.trim().toLowerCase();

    if (!normalizedSearch) return doctors;

    return doctors.filter((doctor) => {
      return (
        doctor.full_name.toLowerCase().includes(normalizedSearch) ||
        doctor.display_name?.toLowerCase().includes(normalizedSearch) ||
        doctor.specialty?.toLowerCase().includes(normalizedSearch) ||
        doctor.title?.toLowerCase().includes(normalizedSearch)
      );
    });
  }, [doctors, searchText]);

  const availableServices = useMemo(() => {
    const assignedServiceIds = new Set(
      doctorServices.map((item) => item.service_category_id)
    );

    return serviceCategories.filter(
      (service) => !assignedServiceIds.has(service.id) && service.is_active
    );
  }, [doctorServices, serviceCategories]);

useEffect(() => {
  async function loadPage() {
    if (isLoadingClinic) return;

    try {
      setErrorMessage("");

      if (!currentClinicId) {
        setErrorMessage("Clinic was not found for this account.");
        setIsCheckingSession(false);
        setIsLoadingDoctors(false);
        return;
      }

      setIsCheckingSession(false);

      await Promise.all([loadDoctors(), loadServiceCategories()]);
    } catch (error) {
      console.error("Load doctors page error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to load doctors page."
      );
      setIsCheckingSession(false);
      setIsLoadingDoctors(false);
    }
  }

  loadPage();
  // eslint-disable-next-line react-hooks/exhaustive-deps
}, [currentClinicId, isLoadingClinic]);

  async function loadDoctors(nextSelectedDoctorId?: string) {
    try {
      setIsLoadingDoctors(true);
      setErrorMessage("");

      const loadedDoctors = await getClinicDoctors(currentClinicId);
      setDoctors(loadedDoctors);

      if (loadedDoctors.length === 0) {
        setSelectedDoctorId(null);
        setDoctorServices([]);
        setIsLoadingDoctors(false);
        return;
      }

      const doctorIdToSelect =
        nextSelectedDoctorId || selectedDoctorId || loadedDoctors[0].id;

      setSelectedDoctorId(doctorIdToSelect);
      await loadDoctorServices(doctorIdToSelect);

      setIsLoadingDoctors(false);
    } catch (error) {
      console.error("Load doctors error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to load doctors."
      );
      setIsLoadingDoctors(false);
    }
  }

  async function loadServiceCategories() {
    try {
      const loadedServices = await getServiceCategories(currentClinicId);
      setServiceCategories(loadedServices);
    } catch (error) {
      console.error("Load service categories error:", error);
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Failed to load service categories."
      );
    }
  }

  async function loadDoctorServices(doctorId: string) {
    try {
      setIsLoadingServices(true);
      setErrorMessage("");

      const loadedDoctorServices = await getClinicDoctorServices(doctorId);
      setDoctorServices(loadedDoctorServices);

      setIsLoadingServices(false);
    } catch (error) {
      console.error("Load doctor services error:", error);
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Failed to load doctor services."
      );
      setIsLoadingServices(false);
    }
  }

  const assignedServiceIds = useMemo(() => {
  return new Set(
    doctorServices
      .filter((item) => item.is_active)
      .map((item) => item.service_category_id)
  );
}, [doctorServices]);

const activeServiceCategories = useMemo(() => {
  return serviceCategories.filter((service) => service.is_active);
}, [serviceCategories]);

const enabledActiveServiceCount = useMemo(() => {
  return activeServiceCategories.filter((service) =>
    assignedServiceIds.has(service.id)
  ).length;
}, [activeServiceCategories, assignedServiceIds]);

const areAllActiveServicesEnabled =
  activeServiceCategories.length > 0 &&
  enabledActiveServiceCount === activeServiceCategories.length;

async function handleToggleDoctorService(
serviceCategoryId: string,
enabled: boolean
) {
try {
    setErrorMessage("");
    setSuccessMessage("");

    if (!selectedDoctor) {
    setErrorMessage("Select a doctor first.");
    return;
    }

    setIsUpdatingDoctorService(true);

    await setClinicDoctorServiceActive({
    clinicId: currentClinicId,
    doctorId: selectedDoctor.id,
    serviceCategoryId,
    enabled,
    });

    await loadDoctorServices(selectedDoctor.id);

    setSuccessMessage(
    enabled
        ? "Service enabled for this doctor."
        : "Service removed from this doctor."
    );

    setIsUpdatingDoctorService(false);
} catch (error) {
    console.error("Toggle doctor service error:", error);
    setErrorMessage(
    error instanceof Error
        ? error.message
        : "Failed to update doctor service."
    );
    setIsUpdatingDoctorService(false);
}
}

async function handleToggleAllDoctorServices(enabled: boolean) {
  try {
    setErrorMessage("");
    setSuccessMessage("");

    if (!selectedDoctor) {
      setErrorMessage("Select a doctor first.");
      return;
    }

    if (activeServiceCategories.length === 0) {
      setErrorMessage("No active services found.");
      return;
    }

    setIsUpdatingDoctorService(true);

    await Promise.all(
      activeServiceCategories.map((service) =>
        setClinicDoctorServiceActive({
          clinicId: currentClinicId,
          doctorId: selectedDoctor.id,
          serviceCategoryId: service.id,
          enabled,
        })
      )
    );

    await loadDoctorServices(selectedDoctor.id);

    setSuccessMessage(
      enabled
        ? "All services enabled for this doctor."
        : "All services removed from this doctor."
    );

    setIsUpdatingDoctorService(false);
  } catch (error) {
    console.error("Toggle all doctor services error:", error);
    setErrorMessage(
      error instanceof Error
        ? error.message
        : "Failed to update doctor services."
    );
    setIsUpdatingDoctorService(false);
  }
}
  async function handleSelectDoctor(doctorId: string) {
    setSelectedDoctorId(doctorId);
    await loadDoctorServices(doctorId);
  }

  function resetDoctorForm() {
    setFullName("");
    setDisplayName("");
    setTitle("Dr.");
    setSpecialty("");
    setPhoneNumber("");
    setEmail("");
    setDoctorNotes("");
    setDoctorIsActive(true);
  }

  async function handleCreateDoctor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      setErrorMessage("");
      setSuccessMessage("");

      if (!fullName.trim()) {
        setErrorMessage("Full name is required.");
        return;
      }

      setIsSavingDoctor(true);

      const doctorId = await createClinicDoctor({
        clinicId: currentClinicId,
        fullName: fullName.trim(),
        displayName: displayName.trim() ? displayName.trim() : null,
        title: title.trim() ? title.trim() : null,
        specialty: specialty.trim() ? specialty.trim() : null,
        phoneNumber: phoneNumber.trim() ? phoneNumber.trim() : null,
        email: email.trim() ? email.trim() : null,
        isActive: doctorIsActive,
        notes: doctorNotes.trim() ? doctorNotes.trim() : null,
      });

      setSuccessMessage("Doctor saved successfully.");
      resetDoctorForm();
      setIsAddDoctorOpen(false);

      await loadDoctors(doctorId);

      setIsSavingDoctor(false);
    } catch (error) {
      console.error("Create doctor error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to create doctor."
      );
      setIsSavingDoctor(false);
    }
  }

  function openEditDoctorModal(doctor: ClinicDoctor) {
    setEditingDoctorId(doctor.id);
    setEditFullName(doctor.full_name);
    setEditDisplayName(doctor.display_name || "");
    setEditTitle(doctor.title || "Dr.");
    setEditSpecialty(doctor.specialty || "");
    setEditPhoneNumber(doctor.phone_number || "");
    setEditEmail(doctor.email || "");
    setEditDoctorNotes(doctor.notes || "");
    setEditDoctorIsActive(Boolean(doctor.is_active));
    setIsEditDoctorOpen(true);
  }

  async function handleUpdateDoctor(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      setErrorMessage("");
      setSuccessMessage("");

      if (!editingDoctorId) {
        setErrorMessage("No doctor selected.");
        return;
      }

      if (!editFullName.trim()) {
        setErrorMessage("Full name is required.");
        return;
      }

      await updateClinicDoctor({
        id: editingDoctorId,
        clinicId: currentClinicId,
        fullName: editFullName.trim(),
        displayName: editDisplayName.trim() ? editDisplayName.trim() : null,
        title: editTitle.trim() ? editTitle.trim() : null,
        specialty: editSpecialty.trim() ? editSpecialty.trim() : null,
        phoneNumber: editPhoneNumber.trim() ? editPhoneNumber.trim() : null,
        email: editEmail.trim() ? editEmail.trim() : null,
        isActive: editDoctorIsActive,
        notes: editDoctorNotes.trim() ? editDoctorNotes.trim() : null,
      });

      setSuccessMessage("Doctor updated successfully.");
      setIsEditDoctorOpen(false);

      await loadDoctors(editingDoctorId);
    } catch (error) {
      console.error("Update doctor error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to update doctor."
      );
    }
  }

  async function handleDeleteDoctor(doctor: ClinicDoctor) {
    const confirmed = window.confirm(
      `Are you sure you want to delete "${doctor.full_name}"? All assigned services for this doctor will also be deleted.`
    );

    if (!confirmed) return;

    try {
      setErrorMessage("");
      setSuccessMessage("");

      await deleteClinicDoctorWithServices(doctor.id);

      setSuccessMessage("Doctor and assigned services deleted successfully.");
      setSelectedDoctorId(null);
      setDoctorServices([]);

      await loadDoctors();
    } catch (error) {
      console.error("Delete doctor error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to delete doctor."
      );
    }
  }

  async function handleAssignService(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      setErrorMessage("");
      setSuccessMessage("");

      if (!selectedDoctor) {
        setErrorMessage("Select a doctor first.");
        return;
      }

      if (!selectedServiceCategoryId) {
        setErrorMessage("Select a service first.");
        return;
      }

      const alreadyAssigned = doctorServices.some(
        (item) => item.service_category_id === selectedServiceCategoryId
      );

      if (alreadyAssigned) {
        setErrorMessage("This service is already assigned to this doctor.");
        return;
      }

      setIsSavingDoctorService(true);



      setSuccessMessage("Service assigned successfully.");
      setSelectedServiceCategoryId("");
      setDoctorServiceNotes("");
      setIsAddServiceOpen(false);

      await loadDoctorServices(selectedDoctor.id);

      setIsSavingDoctorService(false);
    } catch (error) {
      console.error("Assign service error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to assign service."
      );
      setIsSavingDoctorService(false);
    }
  }

  function openEditDoctorServiceModal(doctorService: ClinicDoctorService) {
    setEditingDoctorServiceId(doctorService.id);
    setEditDoctorServiceIsActive(Boolean(doctorService.is_active));
    setEditDoctorServiceNotes(doctorService.notes || "");
    setIsEditDoctorServiceOpen(true);
  }

  async function handleUpdateDoctorService(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      setErrorMessage("");
      setSuccessMessage("");

      if (!editingDoctorServiceId) {
        setErrorMessage("No doctor service selected.");
        return;
      }

      setSuccessMessage("Doctor service updated successfully.");
      setIsEditDoctorServiceOpen(false);

      if (selectedDoctor) {
        await loadDoctorServices(selectedDoctor.id);
      }
    } catch (error) {
      console.error("Update doctor service error:", error);
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Failed to update doctor service."
      );
    }
  }

  async function handleDeleteDoctorService(doctorServiceId: string) {
    const confirmed = window.confirm(
      "Are you sure you want to remove this service from this doctor?"
    );

    if (!confirmed) return;

    try {
      setErrorMessage("");
      setSuccessMessage("");


      setSuccessMessage("Service removed from doctor successfully.");

      if (selectedDoctor) {
        await loadDoctorServices(selectedDoctor.id);
      }
    } catch (error) {
      console.error("Delete doctor service error:", error);
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Failed to remove service from doctor."
      );
    }
  }

  if (isCheckingSession || isLoadingClinic) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-slate-50">
        <p className="text-sm font-medium text-slate-500">
          Loading clinic...
        </p>
      </main>
    );
  }

  return (
    <DashboardShell
      title="Doctors"
      description="Manage clinic doctors and the services each doctor can provide."
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
        className="grid grid-cols-1 gap-6 lg:grid-cols-[420px_minmax(0,1fr)]"
      >
        <section
          dir="ltr"
          className="min-w-0 rounded-2xl border border-slate-200 bg-white shadow-sm"
        >
          <div className="border-b border-slate-100 p-5">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <h2 className="truncate text-lg font-bold text-slate-900">
                  Doctors
                </h2>
                <p className="mt-1 truncate text-sm text-slate-500">
                  Select a doctor to manage services.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setIsAddDoctorOpen(true)}
                className="shrink-0 whitespace-nowrap rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-slate-800"
              >
                + Add Doctor
              </button>
            </div>

            <input
              value={searchText}
              onChange={(event) => setSearchText(event.target.value)}
              placeholder="Search doctors..."
              className="mt-4 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-blue-500"
            />
          </div>

          <div className="max-h-[650px] overflow-y-auto p-3">
            {isLoadingDoctors && (
              <div className="rounded-xl bg-slate-50 p-5 text-center text-sm text-slate-500">
                Loading doctors...
              </div>
            )}

            {!isLoadingDoctors && filteredDoctors.length === 0 && (
              <div className="rounded-xl bg-slate-50 p-5 text-center text-sm text-slate-500">
                No doctors found.
              </div>
            )}

            {!isLoadingDoctors &&
              filteredDoctors.map((doctor) => {
                const isSelected = doctor.id === selectedDoctorId;

                return (
                  <div
                    key={doctor.id}
                    role="button"
                    tabIndex={0}
                    onClick={() => handleSelectDoctor(doctor.id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        handleSelectDoctor(doctor.id);
                      }
                    }}
                    className={`mb-2 w-full cursor-pointer rounded-2xl border px-4 py-3 text-left transition ${
                      isSelected
                        ? "border-blue-300 bg-blue-50 shadow-sm"
                        : "border-slate-200 bg-white hover:bg-slate-50"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate font-semibold text-slate-900">
                          {doctor.display_name || doctor.full_name}
                        </p>
                        <p className="mt-1 truncate text-xs font-medium text-slate-500">
                          {doctor.title || "Doctor"} •{" "}
                          {doctor.specialty || "General Dentistry"}
                        </p>
                      </div>

                      <div className="flex shrink-0 items-center justify-end gap-2">
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-semibold ${
                            doctor.is_active
                              ? "bg-green-50 text-green-700"
                              : "bg-slate-100 text-slate-500"
                          }`}
                        >
                          {doctor.is_active ? "Active" : "Inactive"}
                        </span>

                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            openEditDoctorModal(doctor);
                          }}
                          className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                        >
                          Edit
                        </button>

                        <button
                          type="button"
                          onClick={(event) => {
                            event.stopPropagation();
                            handleDeleteDoctor(doctor);
                          }}
                          className="rounded-full border border-red-200 bg-red-50 px-3 py-1 text-xs font-semibold text-red-700 hover:bg-red-100"
                        >
                          Delete
                        </button>
                      </div>
                    </div>

                    <div className="mt-2 grid min-w-0 grid-cols-[1fr_auto] items-center gap-4 text-xs text-slate-500">
                      <span className="min-w-0 truncate">
                        {doctor.email || doctor.phone_number || "No contact info"}
                      </span>
                    </div>
                  </div>
                );
              })}
          </div>
        </section>

        <section
          dir="ltr"
          className="min-w-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm"
        >
          {!selectedDoctor && (
            <div className="flex min-h-[400px] items-center justify-center p-8 text-center">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  Select a doctor
                </h2>
                <p className="mt-2 text-sm text-slate-500">
                  Choose a doctor from the left list to view and manage their
                  services.
                </p>
              </div>
            </div>
          )}

          {selectedDoctor && (
            <>
              <div className="border-b border-slate-100 p-5">
                <div className="flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <h2 className="truncate text-xl font-bold text-slate-900">
                      {selectedDoctor.display_name || selectedDoctor.full_name}
                    </h2>
                    <p className="mt-1 truncate text-sm text-slate-500">
                    {assignedServiceIds.size} of {serviceCategories.length} services enabled
                    </p>
                  </div>


                </div>
              </div>

              <div className="p-5">
                {serviceCategories.length > 0 && (
                  <div className="mb-4 flex items-center justify-between gap-4 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                    <label className="flex cursor-pointer items-center gap-3">
                      <input
                        type="checkbox"
                        checked={areAllActiveServicesEnabled}
                        disabled={isUpdatingDoctorService || activeServiceCategories.length === 0}
                        onChange={(event) =>
                          handleToggleAllDoctorServices(event.target.checked)
                        }
                        className="h-4 w-4 rounded border-slate-300"
                      />

                      <div>
                        <p className="text-sm font-semibold text-slate-900">
                          Select all services
                        </p>
                        <p className="text-xs text-slate-500">
                          {enabledActiveServiceCount} of {activeServiceCategories.length} active services selected
                        </p>
                      </div>
                    </label>

                    {isUpdatingDoctorService && (
                      <span className="text-xs font-semibold text-slate-500">
                        Updating...
                      </span>
                    )}
                  </div>
                )}

                <div className="space-y-2">
                    {serviceCategories.length === 0 && (
                    <div className="rounded-xl bg-slate-50 p-5 text-center text-sm text-slate-500 md:col-span-2 xl:col-span-3">
                        No services found. Create service categories first.
                    </div>
                    )}

                    {serviceCategories.map((service) => {
                    const isAssigned = assignedServiceIds.has(service.id);

                    return (
                        <label
                        key={service.id}
                        className={`flex cursor-pointer items-center justify-between gap-4 rounded-xl border px-4 py-3 transition ${
                            isAssigned
                            ? "border-blue-300 bg-blue-50 shadow-sm"
                            : "border-slate-200 bg-white hover:bg-slate-50"
                        }`}
                        >
                        <div className="flex min-w-0 items-center gap-3">
                            <input
                            type="checkbox"
                            checked={isAssigned}
                            disabled={isUpdatingDoctorService}
                            onChange={(event) =>
                                handleToggleDoctorService(service.id, event.target.checked)
                            }
                            className="h-4 w-4 shrink-0 rounded border-slate-300"
                            />

                            <div className="min-w-0">
                            <p className="truncate font-semibold text-slate-900">
                                {service.name}
                            </p>
                            </div>
                        </div>

                        <div className="flex shrink-0 items-center gap-2 text-xs text-slate-500">
                            <span>{service.default_duration_minutes}m</span>
                            <span className="text-slate-300">•</span>
                            <span>{service.default_urgency || "normal"}</span>

                            {!service.is_active && (
                            <>
                                <span className="text-slate-300">•</span>
                                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-500">
                                Inactive
                                </span>
                            </>
                            )}
                        </div>
                        </label>

                    );
                    })}
                </div>
                </div>

            </>
          )}
        </section>
      </div>

      {isAddDoctorOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white shadow-xl">
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  Add Doctor
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Create a doctor profile for this clinic.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setIsAddDoctorOpen(false)}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
              >
                Close
              </button>
            </div>

            <form onSubmit={handleCreateDoctor} className="space-y-5 p-5">
              <DoctorFormFields
                fullName={fullName}
                setFullName={setFullName}
                displayName={displayName}
                setDisplayName={setDisplayName}
                title={title}
                setTitle={setTitle}
                specialty={specialty}
                setSpecialty={setSpecialty}
                phoneNumber={phoneNumber}
                setPhoneNumber={setPhoneNumber}
                email={email}
                setEmail={setEmail}
                notes={doctorNotes}
                setNotes={setDoctorNotes}
                isActive={doctorIsActive}
                setIsActive={setDoctorIsActive}
              />

              <button
                type="submit"
                disabled={isSavingDoctor}
                className="w-full rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSavingDoctor ? "Saving..." : "Save Doctor"}
              </button>
            </form>
          </div>
        </div>
      )}

      {isEditDoctorOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white shadow-xl">
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  Edit Doctor
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Update doctor profile information.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setIsEditDoctorOpen(false)}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
              >
                Close
              </button>
            </div>

            <form onSubmit={handleUpdateDoctor} className="space-y-5 p-5">
              <DoctorFormFields
                fullName={editFullName}
                setFullName={setEditFullName}
                displayName={editDisplayName}
                setDisplayName={setEditDisplayName}
                title={editTitle}
                setTitle={setEditTitle}
                specialty={editSpecialty}
                setSpecialty={setEditSpecialty}
                phoneNumber={editPhoneNumber}
                setPhoneNumber={setEditPhoneNumber}
                email={editEmail}
                setEmail={setEditEmail}
                notes={editDoctorNotes}
                setNotes={setEditDoctorNotes}
                isActive={editDoctorIsActive}
                setIsActive={setEditDoctorIsActive}
              />

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

      {isAddServiceOpen && selectedDoctor && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white shadow-xl">
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  Assign Service
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Add a service for {selectedDoctor.display_name || selectedDoctor.full_name}.
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

            <form onSubmit={handleAssignService} className="space-y-5 p-5">
              <div>
                <label className="text-sm font-medium text-slate-700">
                  Service
                </label>
                <select
                  value={selectedServiceCategoryId}
                  onChange={(event) =>
                    setSelectedServiceCategoryId(event.target.value)
                  }
                  className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                >
                  <option value="">Select service</option>
                  {availableServices.map((service) => (
                    <option key={service.id} value={service.id}>
                      {service.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Notes
                </label>
                <textarea
                  value={doctorServiceNotes}
                  onChange={(event) => setDoctorServiceNotes(event.target.value)}
                  rows={3}
                  placeholder="Optional notes for this doctor-service assignment"
                  className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <button
                type="submit"
                disabled={isSavingDoctorService}
                className="w-full rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {isSavingDoctorService ? "Saving..." : "Assign Service"}
              </button>
            </form>
          </div>
        </div>
      )}

      {isEditDoctorServiceOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white shadow-xl">
            <div className="flex items-start justify-between border-b border-slate-100 p-5">
              <div>
                <h2 className="text-lg font-bold text-slate-900">
                  Edit Doctor Service
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  Update service assignment information.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setIsEditDoctorServiceOpen(false)}
                className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
              >
                Close
              </button>
            </div>

            <form onSubmit={handleUpdateDoctorService} className="space-y-5 p-5">
              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={editDoctorServiceIsActive}
                  onChange={(event) =>
                    setEditDoctorServiceIsActive(event.target.checked)
                  }
                  className="h-4 w-4 rounded border-slate-300"
                />
                Active
              </label>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Notes
                </label>
                <textarea
                  value={editDoctorServiceNotes}
                  onChange={(event) =>
                    setEditDoctorServiceNotes(event.target.value)
                  }
                  rows={3}
                  className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
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
    </DashboardShell>
  );
}

function DoctorFormFields({
  fullName,
  setFullName,
  displayName,
  setDisplayName,
  title,
  setTitle,
  specialty,
  setSpecialty,
  phoneNumber,
  setPhoneNumber,
  email,
  setEmail,
  notes,
  setNotes,
  isActive,
  setIsActive,
}: {
  fullName: string;
  setFullName: (value: string) => void;
  displayName: string;
  setDisplayName: (value: string) => void;
  title: string;
  setTitle: (value: string) => void;
  specialty: string;
  setSpecialty: (value: string) => void;
  phoneNumber: string;
  setPhoneNumber: (value: string) => void;
  email: string;
  setEmail: (value: string) => void;
  notes: string;
  setNotes: (value: string) => void;
  isActive: boolean;
  setIsActive: (value: boolean) => void;
}) {
  return (
    <>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <label className="text-sm font-medium text-slate-700">
            Full Name
          </label>
          <input
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
            placeholder="Example: Dr. Sarah Miller"
            className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
          />
        </div>

        <div>
          <label className="text-sm font-medium text-slate-700">
            Display Name
          </label>
          <input
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            placeholder="Example: Dr. Miller"
            className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <label className="text-sm font-medium text-slate-700">Title</label>
          <input
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="Example: Dr."
            className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
          />
        </div>

        <div>
          <label className="text-sm font-medium text-slate-700">
            Specialty
          </label>
          <input
            value={specialty}
            onChange={(event) => setSpecialty(event.target.value)}
            placeholder="Example: General Dentistry"
            className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div>
          <label className="text-sm font-medium text-slate-700">
            Phone Number
          </label>
          <input
            value={phoneNumber}
            onChange={(event) => setPhoneNumber(event.target.value)}
            placeholder="Example: +1 604 555 1234"
            className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
          />
        </div>

        <div>
          <label className="text-sm font-medium text-slate-700">Email</label>
          <input
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="Example: doctor@clinic.com"
            className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
          />
        </div>
      </div>

      <div>
        <label className="text-sm font-medium text-slate-700">Notes</label>
        <textarea
          value={notes}
          onChange={(event) => setNotes(event.target.value)}
          placeholder="Optional internal notes"
          rows={3}
          className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
        />
      </div>

      <label className="flex items-center gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={isActive}
          onChange={(event) => setIsActive(event.target.checked)}
          className="h-4 w-4 rounded border-slate-300"
        />
        Active
      </label>
    </>
  );
}