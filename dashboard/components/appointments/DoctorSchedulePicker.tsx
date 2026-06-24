"use client";

import { useEffect, useMemo, useState } from "react";
import { supabase } from "@/lib/supabaseClient";
import {
  Appointment,
  CalendarAvailabilityException,
  CalendarAvailabilityRule,
  ClinicDoctor,
  ServiceCategory,
  createAppointmentFromRequest,
  getCalendarAvailabilityExceptions,
  getCalendarAvailabilityRules,
  getClinicDoctorServices,
  getClinicDoctors,
  getDoctorAppointmentsForRange,
  getServiceCategories,
} from "@/lib/supabaseService";

type RequestForSchedule = {
  id: string;
  patient_name: string | null;
  patient_phone: string | null;
  reason: string | null;
  urgency: string | null;
  doctor_id?: string | null;
  preferred_doctor_name: string | null;
  service_category_id?: string | null;
  service_category_name?: string | null;
  duration_minutes?: number | null;
};

type DoctorServiceRow = {
  service_category_id: string | null;
  is_active: boolean | null;
};

type Slot = {
  id: string;
  date: string;
  startTime: string;
  endTime: string;
  startDateTime: Date;
  endDateTime: Date;
  isBooked: boolean;
  bookedAppointment: Appointment | null;
};

const WEEK_DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

function formatDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

function addDays(date: Date, days: number) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function getWeekStart(date: Date) {
  const start = new Date(date);
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - start.getDay());
  return start;
}

function getWeekDays(weekStart: Date) {
  return Array.from({ length: 7 }, (_, index) => addDays(weekStart, index));
}

function timeToMinutes(time: string) {
  const [hours, minutes] = time.slice(0, 5).split(":").map(Number);
  return hours * 60 + minutes;
}

function minutesToTime(totalMinutes: number) {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(
    2,
    "0"
  )}`;
}

function buildLocalDateTime(date: string, time: string) {
  return new Date(`${date}T${time}:00`);
}

function appliesToDate(rule: CalendarAvailabilityRule, date: Date) {
  const dateString = formatDate(date);

  if (dateString < rule.start_date) return false;
  if (rule.end_date && dateString > rule.end_date) return false;

  const day = date.getDay();

  if (rule.repeat_type === "none") {
    return dateString === rule.start_date;
  }

  if (rule.repeat_type === "daily") {
    return true;
  }

  if (rule.repeat_type === "weekdays") {
    return day >= 1 && day <= 5;
  }

  if (rule.repeat_type === "weekly" || rule.repeat_type === "custom") {
    return rule.day_of_week === day;
  }

  return false;
}

function appointmentOverlapsSlot({
  appointment,
  slotStart,
  slotEnd,
}: {
  appointment: Appointment;
  slotStart: Date;
  slotEnd: Date;
}) {
  const appointmentStart = new Date(appointment.start_time);
  const appointmentEnd = new Date(appointment.end_time);

  return appointmentStart < slotEnd && appointmentEnd > slotStart;
}

function getDateLabel(date: Date) {
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

export default function DoctorSchedulePicker({
  clinicId,
  request,
  onClose,
  onConfirmed,
}: {
  clinicId: string;
  request: RequestForSchedule;
  onClose: () => void;
  onConfirmed: () => void;
}) {
  const [doctors, setDoctors] = useState<ClinicDoctor[]>([]);
  const [allServices, setAllServices] = useState<ServiceCategory[]>([]);
  const [doctorServiceRows, setDoctorServiceRows] = useState<DoctorServiceRow[]>(
    []
  );

  const [selectedDoctorId, setSelectedDoctorId] = useState(
    request.doctor_id || ""
  );

  const [selectedServiceId, setSelectedServiceId] = useState(
    request.service_category_id || ""
  );

  const [weekStart, setWeekStart] = useState(getWeekStart(new Date()));

  const [rules, setRules] = useState<CalendarAvailabilityRule[]>([]);
  const [exceptions, setExceptions] = useState<CalendarAvailabilityException[]>(
    []
  );
  const [appointments, setAppointments] = useState<Appointment[]>([]);

  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);
  const [notes, setNotes] = useState("");

  const [editablePatientName, setEditablePatientName] = useState(
    request.patient_name || ""
  );
  const [editablePatientPhone, setEditablePatientPhone] = useState(
    request.patient_phone || ""
  );
  const [editableReason, setEditableReason] = useState(request.reason || "");
  const [editableServiceName, setEditableServiceName] = useState(
    request.service_category_name || ""
  );
  const [editableUrgency, setEditableUrgency] = useState(
    request.urgency || "normal"
  );
  const [editableDurationMinutes, setEditableDurationMinutes] = useState(
    String(request.duration_minutes || 30)
  );

  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingDoctorServices, setIsLoadingDoctorServices] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const durationMinutes = Number(editableDurationMinutes) || 30;

  const weekDays = useMemo(() => getWeekDays(weekStart), [weekStart]);
  const weekStartString = formatDate(weekDays[0]);
  const weekEndString = formatDate(weekDays[6]);

  const doctorNameById = useMemo(() => {
    const map: Record<string, string> = {};

    doctors.forEach((doctor) => {
      map[doctor.id] = doctor.display_name || doctor.full_name;
    });

    return map;
  }, [doctors]);

  const availableServicesForDoctor = useMemo(() => {
    if (!selectedDoctorId) return [];

    const activeServiceIds = new Set(
      doctorServiceRows
        .filter((row) => row.is_active !== false && row.service_category_id)
        .map((row) => row.service_category_id as string)
    );

    return allServices.filter((service) => activeServiceIds.has(service.id));
  }, [allServices, doctorServiceRows, selectedDoctorId]);

  const exceptionsByRuleAndDate = useMemo(() => {
    const map = new Map<string, CalendarAvailabilityException>();

    exceptions.forEach((exception) => {
      map.set(`${exception.rule_id}:${exception.exception_date}`, exception);
    });

    return map;
  }, [exceptions]);

  const slotsByDate = useMemo(() => {
    const map: Record<string, Slot[]> = {};

    weekDays.forEach((day) => {
      const dateString = formatDate(day);
      map[dateString] = [];

      rules.forEach((rule) => {
        if (!appliesToDate(rule, day)) return;

        const exception = exceptionsByRuleAndDate.get(
          `${rule.id}:${dateString}`
        );

        if (exception?.exception_type === "cancelled") return;

        const startTime =
          exception?.exception_type === "modified" && exception.start_time
            ? exception.start_time
            : rule.start_time;

        const endTime =
          exception?.exception_type === "modified" && exception.end_time
            ? exception.end_time
            : rule.end_time;

        const startMinutes = timeToMinutes(startTime);
        const endMinutes = timeToMinutes(endTime);

        for (
          let current = startMinutes;
          current + durationMinutes <= endMinutes;
          current += durationMinutes
        ) {
          const slotStartTime = minutesToTime(current);
          const slotEndTime = minutesToTime(current + durationMinutes);

          const startDateTime = buildLocalDateTime(dateString, slotStartTime);
          const endDateTime = buildLocalDateTime(dateString, slotEndTime);

          const bookedAppointment =
            appointments.find((appointment) =>
              appointmentOverlapsSlot({
                appointment,
                slotStart: startDateTime,
                slotEnd: endDateTime,
              })
            ) || null;

          map[dateString].push({
            id: `${dateString}:${slotStartTime}`,
            date: dateString,
            startTime: slotStartTime,
            endTime: slotEndTime,
            startDateTime,
            endDateTime,
            isBooked: Boolean(bookedAppointment),
            bookedAppointment,
          });
        }
      });
    });

    return map;
  }, [
    weekDays,
    rules,
    exceptionsByRuleAndDate,
    appointments,
    durationMinutes,
  ]);

  useEffect(() => {
    async function loadInitialData() {
      try {
        setErrorMessage("");

        const [loadedDoctors, loadedServices] = await Promise.all([
          getClinicDoctors(clinicId),
          getServiceCategories(clinicId),
        ]);

        setDoctors(loadedDoctors);
        setAllServices(loadedServices);

        if (!selectedDoctorId && loadedDoctors.length > 0) {
          setSelectedDoctorId(loadedDoctors[0].id);
        }
      } catch (error) {
        console.error("Load initial schedule picker data error:", error);
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Failed to load doctors and services."
        );
      }
    }

    loadInitialData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clinicId]);

  useEffect(() => {
    async function loadDoctorServices() {
      if (!selectedDoctorId) {
        setDoctorServiceRows([]);
        setSelectedServiceId("");
        setEditableServiceName("");
        setEditableDurationMinutes("30");
        setSelectedSlot(null);
        return;
      }

      try {
        setIsLoadingDoctorServices(true);
        setErrorMessage("");

        const loadedDoctorServices = await getClinicDoctorServices(
          selectedDoctorId
        );

        const simplifiedRows = loadedDoctorServices.map((row) => ({
          service_category_id: row.service_category_id,
          is_active: row.is_active,
        }));

        setDoctorServiceRows(simplifiedRows);
        setIsLoadingDoctorServices(false);
      } catch (error) {
        console.error("Load doctor services error:", error);
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Failed to load doctor services."
        );
        setIsLoadingDoctorServices(false);
      }
    }

    loadDoctorServices();
  }, [selectedDoctorId]);

  useEffect(() => {
    if (!selectedDoctorId) return;
    if (isLoadingDoctorServices) return;

    if (availableServicesForDoctor.length === 0) {
      setSelectedServiceId("");
      setEditableServiceName("");
      setEditableDurationMinutes("30");
      setSelectedSlot(null);
      return;
    }

    const currentServiceStillAvailable = availableServicesForDoctor.some(
      (service) => service.id === selectedServiceId
    );

    if (selectedServiceId && currentServiceStillAvailable) {
      const selectedService = availableServicesForDoctor.find(
        (service) => service.id === selectedServiceId
      );

      if (selectedService) {
        setEditableServiceName(selectedService.name);
        setEditableDurationMinutes(
          String(selectedService.default_duration_minutes || 30)
        );

        if (selectedService.default_urgency) {
          setEditableUrgency(selectedService.default_urgency);
        }

        if (!editableReason && selectedService.canonical_reason) {
          setEditableReason(selectedService.canonical_reason);
        }
      }

      return;
    }

    const matchedService =
      availableServicesForDoctor.find(
        (service) => service.id === request.service_category_id
      ) ||
      availableServicesForDoctor.find(
        (service) => service.name === request.service_category_name
      ) ||
      null;

    if (matchedService) {
      setSelectedServiceId(matchedService.id);
      setEditableServiceName(matchedService.name);
      setEditableDurationMinutes(
        String(matchedService.default_duration_minutes || 30)
      );

      if (matchedService.default_urgency) {
        setEditableUrgency(matchedService.default_urgency);
      }

      if (!editableReason && matchedService.canonical_reason) {
        setEditableReason(matchedService.canonical_reason);
      }

      setSelectedSlot(null);
      return;
    }

    setSelectedServiceId("");
    setEditableServiceName("");
    setEditableDurationMinutes("30");
    setSelectedSlot(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    selectedDoctorId,
    availableServicesForDoctor,
    isLoadingDoctorServices,
    selectedServiceId,
  ]);

  useEffect(() => {
    async function loadSchedule() {
      if (!selectedDoctorId) {
        setIsLoading(false);
        return;
      }

      try {
        setIsLoading(true);
        setErrorMessage("");
        setSelectedSlot(null);

        const loadedRules = await getCalendarAvailabilityRules({
          clinicId,
          doctorId: selectedDoctorId,
          monthStart: weekStartString,
          monthEnd: weekEndString,
        });

        setRules(loadedRules);

        const loadedExceptions = await getCalendarAvailabilityExceptions({
          clinicId,
          ruleIds: loadedRules.map((rule) => rule.id),
          monthStart: weekStartString,
          monthEnd: weekEndString,
        });

        setExceptions(loadedExceptions);

        const rangeStart = new Date(`${weekStartString}T00:00:00`).toISOString();
        const rangeEnd = new Date(
          `${formatDate(addDays(weekDays[6], 1))}T00:00:00`
        ).toISOString();

        const loadedAppointments = await getDoctorAppointmentsForRange({
          clinicId,
          doctorId: selectedDoctorId,
          rangeStart,
          rangeEnd,
        });

        setAppointments(loadedAppointments);
        setIsLoading(false);
      } catch (error) {
        console.error("Load doctor schedule error:", error);
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Failed to load doctor schedule."
        );
        setIsLoading(false);
      }
    }

    loadSchedule();
  }, [
    clinicId,
    selectedDoctorId,
    weekStartString,
    weekEndString,
    weekDays,
  ]);

  function handleServiceChange(serviceId: string) {
    setSelectedServiceId(serviceId);
    setSelectedSlot(null);

    const selectedService = availableServicesForDoctor.find(
      (service) => service.id === serviceId
    );

    if (!selectedService) {
      setEditableServiceName("");
      setEditableDurationMinutes("30");
      return;
    }

    setEditableServiceName(selectedService.name);
    setEditableDurationMinutes(
      String(selectedService.default_duration_minutes || 30)
    );

    if (selectedService.canonical_reason) {
      setEditableReason(selectedService.canonical_reason);
    }

    if (selectedService.default_urgency) {
      setEditableUrgency(selectedService.default_urgency);
    }
  }

  async function handleConfirmAppointment() {
    if (!selectedDoctorId) {
      setErrorMessage("Select a doctor first.");
      return;
    }

    if (!selectedServiceId) {
      setErrorMessage("Select a service first.");
      return;
    }

    const selectedServiceAllowed = availableServicesForDoctor.some(
      (service) => service.id === selectedServiceId
    );

    if (!selectedServiceAllowed) {
      setErrorMessage("The selected doctor does not provide this service.");
      setSelectedServiceId("");
      setEditableServiceName("");
      setSelectedSlot(null);
      return;
    }

    if (!selectedSlot) {
      setErrorMessage("Select an available slot first.");
      return;
    }

    if (!Number.isFinite(durationMinutes) || durationMinutes <= 0) {
      setErrorMessage("Duration must be a positive number.");
      return;
    }

    try {
      setIsConfirming(true);
      setErrorMessage("");

      const { error: updateRequestError } = await supabase
        .from("appointment_requests")
        .update({
          patient_name: editablePatientName.trim()
            ? editablePatientName.trim()
            : null,
          patient_phone: editablePatientPhone.trim()
            ? editablePatientPhone.trim()
            : null,
          reason: editableReason.trim() ? editableReason.trim() : null,
          service_category_id: selectedServiceId,
          service_category_name: editableServiceName.trim()
            ? editableServiceName.trim()
            : null,
          urgency: editableUrgency,
          duration_minutes: durationMinutes,
        })
        .eq("id", request.id)
        .eq("clinic_id", clinicId);

      if (updateRequestError) {
        throw new Error(updateRequestError.message);
      }


      await createAppointmentFromRequest({
        clinicId,
        appointmentRequestId: request.id,
        patientId: request.patient_id || null,
        patientName: editablePatientName.trim()
          ? editablePatientName.trim()
          : null,
        patientPhone: editablePatientPhone.trim()
          ? editablePatientPhone.trim()
          : null,
        doctorId: selectedDoctorId,
        serviceCategoryId: selectedServiceId,
        serviceName: null,
        reason: request.reason || null,
        urgency: request.urgency || "normal",
        startTime: selectedSlot.startTime,
        endTime: selectedSlot.endTime,
        durationMinutes,
        notes: notes.trim() ? notes.trim() : null,
      });


      setIsConfirming(false);
      onConfirmed();
    } catch (error) {
      console.error("Confirm appointment error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to confirm appointment."
      );
      setIsConfirming(false);
    }
  }

  function goToPreviousWeek() {
    setWeekStart(addDays(weekStart, -7));
  }

  function goToNextWeek() {
    setWeekStart(addDays(weekStart, 7));
  }

  function goToThisWeek() {
    setWeekStart(getWeekStart(new Date()));
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/50 p-4">
      <div className="max-h-[94vh] w-full max-w-7xl overflow-y-auto rounded-2xl bg-white shadow-xl">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 p-5">
          <div>
            <h2 className="text-lg font-bold text-slate-900">
              Confirm Appointment
            </h2>
            <p className="mt-1 text-sm text-slate-500">
              Choose an available doctor slot and confirm this request.
            </p>

            <div className="mt-3 rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span className="font-semibold">Patient:</span>{" "}
              {editablePatientName || "Unknown"}{" "}
              <span className="mx-2 text-slate-300">|</span>
              <span className="font-semibold">Phone:</span>{" "}
              {editablePatientPhone || "-"}
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
          >
            Close
          </button>
        </div>

        <div className="space-y-5 p-5">
          {errorMessage && (
            <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {errorMessage}
            </div>
          )}

          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <h3 className="text-sm font-bold text-slate-900">
              Appointment Details
            </h3>

            <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
              <div>
                <label className="text-sm font-medium text-slate-700">
                  Patient Name
                </label>
                <input
                  value={editablePatientName}
                  onChange={(event) =>
                    setEditablePatientName(event.target.value)
                  }
                  className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Patient Phone
                </label>
                <input
                  value={editablePatientPhone}
                  onChange={(event) =>
                    setEditablePatientPhone(event.target.value)
                  }
                  className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Doctor
                </label>
                <select
                  value={selectedDoctorId}
                  onChange={(event) => {
                    setSelectedDoctorId(event.target.value);
                    setSelectedSlot(null);
                  }}
                  className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-blue-500"
                >
                  <option value="">Select doctor</option>
                  {doctors.map((doctor) => (
                    <option key={doctor.id} value={doctor.id}>
                      {doctor.display_name || doctor.full_name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Service
                </label>
                <select
                  value={selectedServiceId}
                  disabled={!selectedDoctorId || isLoadingDoctorServices}
                  onChange={(event) => handleServiceChange(event.target.value)}
                  className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-blue-500 disabled:bg-slate-100 disabled:text-slate-400"
                >
                  <option value="">
                    {isLoadingDoctorServices
                      ? "Loading services..."
                      : "Select service"}
                  </option>

                  {availableServicesForDoctor.map((service) => (
                    <option key={service.id} value={service.id}>
                      {service.name}
                    </option>
                  ))}
                </select>

                {selectedDoctorId &&
                  !isLoadingDoctorServices &&
                  availableServicesForDoctor.length === 0 && (
                    <p className="mt-2 text-xs font-medium text-red-600">
                      This doctor has no active services.
                    </p>
                  )}
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Reason
                </label>
                <input
                  value={editableReason}
                  onChange={(event) => setEditableReason(event.target.value)}
                  className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Urgency
                </label>
                <select
                  value={editableUrgency}
                  onChange={(event) => setEditableUrgency(event.target.value)}
                  className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-blue-500"
                >
                  <option value="low">Low</option>
                  <option value="normal">Normal</option>
                  <option value="urgent">Urgent</option>
                  <option value="emergency">Emergency</option>
                </select>
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Duration
                </label>
                <input
                  type="number"
                  min="1"
                  value={editableDurationMinutes}
                  onChange={(event) => {
                    setEditableDurationMinutes(event.target.value);
                    setSelectedSlot(null);
                  }}
                  className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={goToThisWeek}
                className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                This Week
              </button>

              <button
                type="button"
                onClick={goToPreviousWeek}
                className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                ‹
              </button>

              <button
                type="button"
                onClick={goToNextWeek}
                className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
              >
                ›
              </button>
            </div>

            <div className="text-sm font-semibold text-slate-700">
              Week: {weekStartString} to {weekEndString}
            </div>
          </div>

          {isLoading && (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 text-center text-sm font-medium text-slate-500">
              Loading doctor schedule...
            </div>
          )}

          {!isLoading && selectedDoctorId && (
            <div className="overflow-x-auto rounded-2xl border border-slate-200">
              <div className="grid min-w-[1050px] grid-cols-7 bg-slate-50">
                {weekDays.map((day, index) => {
                  const dateString = formatDate(day);
                  const daySlots = slotsByDate[dateString] || [];

                  return (
                    <div
                      key={dateString}
                      className="border-r border-slate-200 p-3 last:border-r-0"
                    >
                      <div className="text-sm font-bold text-slate-900">
                        {WEEK_DAYS[index]} {getDateLabel(day)}
                      </div>

                      <div className="mt-1 text-xs font-medium text-slate-500">
                        {daySlots.length > 0
                          ? `${daySlots[0].startTime} - ${
                              daySlots[daySlots.length - 1].endTime
                            } available`
                          : "Unavailable"}
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="grid min-w-[1050px] grid-cols-7">
                {weekDays.map((day) => {
                  const dateString = formatDate(day);
                  const daySlots = slotsByDate[dateString] || [];

                  return (
                    <div
                      key={dateString}
                      className="min-h-[520px] space-y-2 border-r border-slate-200 p-3 last:border-r-0"
                    >
                      {daySlots.length === 0 && (
                        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-center text-xs font-medium text-slate-400">
                          No availability
                        </div>
                      )}

                      {daySlots.map((slot) => {
                        const isSelected = selectedSlot?.id === slot.id;

                        if (slot.isBooked) {
                          return (
                            <div
                              key={slot.id}
                              className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
                            >
                              <div className="font-bold">
                                {slot.startTime} - {slot.endTime}
                              </div>
                              <div className="mt-1 truncate">
                                Booked:{" "}
                                {slot.bookedAppointment?.patient_name ||
                                  "Patient"}
                              </div>
                            </div>
                          );
                        }

                        return (
                          <button
                            key={slot.id}
                            type="button"
                            onClick={() => setSelectedSlot(slot)}
                            className={`w-full rounded-xl border px-3 py-2 text-left text-xs transition ${
                              isSelected
                                ? "border-emerald-300 bg-emerald-50 text-emerald-800"
                                : "border-slate-200 bg-white text-slate-700 hover:border-blue-300 hover:bg-blue-50"
                            }`}
                          >
                            <div className="font-bold">
                              {slot.startTime} - {slot.endTime}
                            </div>
                            <div className="mt-1">
                              {isSelected ? "Selected" : "Available"}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 rounded-2xl border border-slate-200 bg-slate-50 p-4 md:grid-cols-[1fr_2fr]">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Selected Slot
              </p>

              {selectedSlot ? (
                <div className="mt-2 text-sm font-bold text-slate-900">
                  {doctorNameById[selectedDoctorId] || "Doctor"}
                  <br />
                  {selectedSlot.date}
                  <br />
                  {selectedSlot.startTime} - {selectedSlot.endTime}
                </div>
              ) : (
                <p className="mt-2 text-sm text-slate-500">
                  No slot selected yet.
                </p>
              )}
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Appointment Notes
              </label>
              <textarea
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                rows={3}
                placeholder="Optional notes"
                className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-sm outline-none focus:border-blue-500"
              />
            </div>
          </div>

          <button
            type="button"
            disabled={!selectedSlot || isConfirming}
            onClick={handleConfirmAppointment}
            className="w-full rounded-xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isConfirming ? "Confirming..." : "Confirm Appointment"}
          </button>
        </div>
      </div>
    </div>
  );
}