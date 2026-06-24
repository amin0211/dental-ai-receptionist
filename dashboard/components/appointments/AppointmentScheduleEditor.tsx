"use client";

import { useEffect, useMemo, useState } from "react";
import { supabase } from "@/lib/supabaseClient";
import Link from "next/link";
import {
  Appointment,
  CalendarAvailabilityException,
  CalendarAvailabilityRule,
  ClinicDoctor,
  Patient,
  ServiceCategory,
  createAppointmentFromRequest,
  getCalendarAvailabilityExceptions,
  getCalendarAvailabilityRules,
  getClinicDoctorServices,
  getClinicDoctors,
  getDoctorAppointmentsForRange,
  getPatients,
  getServiceCategories,
  updateAppointment,
} from "@/lib/supabaseService";

type RequestForSchedule = {
  id: string;
  patient_id?: string | null;
  patient_name: string | null;
  patient_phone: string | null;
  reason: string | null;
  urgency: string | null;
  doctor_id?: string | null;
  preferred_doctor_name: string | null;
  preferred_date_raw: string | null;
  preferred_time_raw: string | null;
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
  ignoreAppointmentId,
}: {
  appointment: Appointment;
  slotStart: Date;
  slotEnd: Date;
  ignoreAppointmentId?: string | null;
}) {
  if (ignoreAppointmentId && appointment.id === ignoreAppointmentId) {
    return false;
  }

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

function normalizePreferredDate(value?: string | null) {
  if (!value) return "";

  let trimmed = value.trim();

  if (!trimmed) return "";

  if (/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) {
    return trimmed;
  }

  const fullNumericDateMatch = trimmed.match(
    /^(\d{4})[\/.](\d{1,2})[\/.](\d{1,2})$/
  );

  if (fullNumericDateMatch) {
    return `${fullNumericDateMatch[1]}-${fullNumericDateMatch[2].padStart(
      2,
      "0"
    )}-${fullNumericDateMatch[3].padStart(2, "0")}`;
  }

  trimmed = trimmed.replace(
    /^(sun|sunday|mon|monday|tue|tuesday|wed|wednesday|thu|thursday|fri|friday|sat|saturday),?\s+/i,
    ""
  );

  trimmed = trimmed.replace(/(\d{1,2})(st|nd|rd|th)/i, "$1");

  const currentYear = new Date().getFullYear();

  const monthMap: Record<string, number> = {
    jan: 1,
    january: 1,
    feb: 2,
    february: 2,
    mar: 3,
    march: 3,
    apr: 4,
    april: 4,
    may: 5,
    jun: 6,
    june: 6,
    jul: 7,
    july: 7,
    aug: 8,
    august: 8,
    sep: 9,
    sept: 9,
    september: 9,
    oct: 10,
    october: 10,
    nov: 11,
    november: 11,
    dec: 12,
    december: 12,
  };

  const monthDayYearMatch = trimmed.match(
    /^(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+(\d{1,2})(?:,\s*(\d{4}))?$/i
  );

  if (monthDayYearMatch) {
    const monthName = monthDayYearMatch[1].toLowerCase();
    const day = monthDayYearMatch[2].padStart(2, "0");
    const year = monthDayYearMatch[3] || String(currentYear);
    const month = String(monthMap[monthName]).padStart(2, "0");

    return `${year}-${month}-${day}`;
  }

  const dayMonthYearMatch = trimmed.match(
    /^(\d{1,2})\s+(jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)(?:\s+(\d{4}))?$/i
  );

  if (dayMonthYearMatch) {
    const day = dayMonthYearMatch[1].padStart(2, "0");
    const monthName = dayMonthYearMatch[2].toLowerCase();
    const year = dayMonthYearMatch[3] || String(currentYear);
    const month = String(monthMap[monthName]).padStart(2, "0");

    return `${year}-${month}-${day}`;
  }

  return "";
}

function normalizePreferredTime(value?: string | null) {
  if (!value) return "";

  const trimmed = value.trim().toLowerCase();

  const timeRangeStart = trimmed.split(/\s+to\s+|-/i)[0].trim();

  const twentyFourHourMatch = timeRangeStart.match(/^(\d{1,2}):(\d{2})$/);

  if (twentyFourHourMatch) {
    return `${twentyFourHourMatch[1].padStart(
      2,
      "0"
    )}:${twentyFourHourMatch[2]}`;
  }

  const twelveHourMatch = timeRangeStart.match(
    /^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$/
  );

  if (twelveHourMatch) {
    let hours = Number(twelveHourMatch[1]);
    const minutes = twelveHourMatch[2] || "00";
    const period = twelveHourMatch[3];

    if (period === "pm" && hours !== 12) hours += 12;
    if (period === "am" && hours === 12) hours = 0;

    return `${String(hours).padStart(2, "0")}:${minutes}`;
  }

  return "";
}

function getInitialWeekStart({
  appointment,
  request,
}: {
  appointment?: Appointment | null;
  request?: RequestForSchedule;
}) {
  if (appointment) {
    return getWeekStart(new Date(appointment.start_time));
  }

  const preferredDate = normalizePreferredDate(request?.preferred_date_raw);

  if (preferredDate) {
    return getWeekStart(new Date(`${preferredDate}T00:00:00`));
  }

  return getWeekStart(new Date());
}

function getLocalDateStringFromIso(value: string) {
  const date = new Date(value);
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");

  return `${year}-${month}-${day}`;
}

function getLocalTimeStringFromIso(value: string) {
  const date = new Date(value);
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");

  return `${hours}:${minutes}`;
}

function getPatientLabel(patient: Patient | null) {
  if (!patient) return "Select patient";
  return `${patient.full_name} — ${patient.phone_primary}`;
}

export default function AppointmentScheduleEditor({
  mode,
  clinicId,
  request,
  appointment,
  onClose,
  onSaved,
}: {
  mode: "confirm" | "edit";
  clinicId: string;
  request?: RequestForSchedule;
  appointment?: Appointment;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [doctors, setDoctors] = useState<ClinicDoctor[]>([]);
  const [allServices, setAllServices] = useState<ServiceCategory[]>([]);
  const [patients, setPatients] = useState<Patient[]>([]);
  const [doctorServiceRows, setDoctorServiceRows] = useState<DoctorServiceRow[]>(
    []
  );

  const [selectedPatientId, setSelectedPatientId] = useState(
    appointment?.patient_id || request?.patient_id || ""
  );
  useEffect(() => {
    if (mode !== "confirm") return;

    if (request?.patient_id) {
      setSelectedPatientId(request.patient_id);
    }
  }, [mode, request?.patient_id]);

  const [patientSearch, setPatientSearch] = useState("");
  const [isPatientDropdownOpen, setIsPatientDropdownOpen] = useState(false);

  const [selectedDoctorId, setSelectedDoctorId] = useState(
    appointment?.doctor_id || request?.doctor_id || ""
  );

  const [selectedServiceId, setSelectedServiceId] = useState(
    appointment?.service_category_id || request?.service_category_id || ""
  );

  const [weekStart, setWeekStart] = useState(
    getInitialWeekStart({ appointment, request })
  );

  const [rules, setRules] = useState<CalendarAvailabilityRule[]>([]);
  const [exceptions, setExceptions] = useState<CalendarAvailabilityException[]>(
    []
  );
  const [appointments, setAppointments] = useState<Appointment[]>([]);

  const [selectedSlot, setSelectedSlot] = useState<Slot | null>(null);
  const [notes, setNotes] = useState(appointment?.notes || "");

  const [editableReason, setEditableReason] = useState(
    appointment?.reason || request?.reason || ""
  );

  const [editableServiceName, setEditableServiceName] = useState(
    appointment?.service_name || request?.service_category_name || ""
  );

  const [editableUrgency, setEditableUrgency] = useState(
    appointment?.urgency || request?.urgency || "normal"
  );

  const [editableDurationMinutes, setEditableDurationMinutes] = useState(
    String(appointment?.duration_minutes || request?.duration_minutes || 30)
  );

  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingDoctorServices, setIsLoadingDoctorServices] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  const durationMinutes = Number(editableDurationMinutes) || 30;

  const weekDays = useMemo(() => getWeekDays(weekStart), [weekStart]);
  const weekStartString = formatDate(weekDays[0]);
  const weekEndString = formatDate(weekDays[6]);

  const editorTitle =
    mode === "confirm" ? "Confirm Appointment" : "Edit Appointment";

  const submitLabel =
    mode === "confirm" ? "Confirm Appointment" : "Save Appointment Changes";

  const doctorNameById = useMemo(() => {
    const map: Record<string, string> = {};

    doctors.forEach((doctor) => {
      map[doctor.id] = doctor.display_name || doctor.full_name;
    });

    return map;
  }, [doctors]);

  const selectedPatient = useMemo(() => {
    return patients.find((patient) => patient.id === selectedPatientId) || null;
  }, [patients, selectedPatientId]);

  const createPatientHref = useMemo(() => {
    const params = new URLSearchParams();

    if (request?.patient_name) {
      params.set("full_name", request.patient_name);
    }

    if (request?.patient_phone) {
      params.set("phone_primary", request.patient_phone);
    }

    const queryString = params.toString();

    return queryString
      ? `/dashboard/patients?${queryString}`
      : "/dashboard/patients";
  }, [request?.patient_name, request?.patient_phone]);


  const filteredPatients = useMemo(() => {
    const query = patientSearch.trim().toLowerCase();

    if (!query) return patients;

    return patients.filter((patient) => {
      return (
        patient.full_name.toLowerCase().includes(query) ||
        patient.phone_primary.toLowerCase().includes(query) ||
        patient.phone_secondary?.toLowerCase().includes(query) ||
        patient.email?.toLowerCase().includes(query)
      );
    });
  }, [patients, patientSearch]);

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

      const usedSlotKeys = new Set<string>();

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
            appointments.find((appointmentRow) =>
              appointmentOverlapsSlot({
                appointment: appointmentRow,
                slotStart: startDateTime,
                slotEnd: endDateTime,
                ignoreAppointmentId: mode === "edit" ? appointment?.id : null,
              })
            ) || null;

          const slotId = `${dateString}:${slotStartTime}:${slotEndTime}`;

          if (usedSlotKeys.has(slotId)) {
            continue;
          }

          usedSlotKeys.add(slotId);

          map[dateString].push({
            id: slotId,
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
    mode,
    appointment?.id,
  ]);

  const allSlotsForWeek = useMemo(() => {
    return Object.values(slotsByDate).flat();
  }, [slotsByDate]);

  const preferredDateFromRequest = useMemo(() => {
    if (mode !== "confirm" || !request) return "";
    return normalizePreferredDate(request.preferred_date_raw);
  }, [mode, request]);

  const preferredTimeFromRequest = useMemo(() => {
    if (mode !== "confirm" || !request) return "";
    return normalizePreferredTime(request.preferred_time_raw);
  }, [mode, request]);

  const selectedSlotIsBooked = Boolean(selectedSlot?.isBooked);

  useEffect(() => {
    async function loadInitialData() {
      try {
        setErrorMessage("");

        const [loadedDoctors, loadedServices, loadedPatients] =
          await Promise.all([
            getClinicDoctors(clinicId),
            getServiceCategories(clinicId),
            getPatients(clinicId),
          ]);

        setDoctors(loadedDoctors);
        setAllServices(loadedServices);
        setPatients(loadedPatients);

        if (!selectedDoctorId && loadedDoctors.length > 0) {
          setSelectedDoctorId(loadedDoctors[0].id);
        }
      } catch (error) {
        console.error("Load appointment editor initial data error:", error);
        setErrorMessage(
          error instanceof Error
            ? error.message
            : "Failed to load doctors, services, and patients."
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

      const correctDuration =
        appointment?.duration_minutes ||
        request?.duration_minutes ||
        30;

      setEditableDurationMinutes(String(correctDuration));

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

        if (!editableDurationMinutes) {
          setEditableDurationMinutes(
            String(selectedService.default_duration_minutes || 30)
          );
        }

        if (selectedService.default_urgency && !editableUrgency) {
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
        (service) => service.id === appointment?.service_category_id
      ) ||
      availableServicesForDoctor.find(
        (service) => service.id === request?.service_category_id
      ) ||
      availableServicesForDoctor.find(
        (service) =>
          service.name === appointment?.service_name ||
          service.name === request?.service_category_name
      ) ||
      null;

    if (matchedService) {
      setSelectedServiceId(matchedService.id);
      setEditableServiceName(matchedService.name);

      const correctDuration =
        appointment?.duration_minutes ||
        request?.duration_minutes ||
        matchedService.default_duration_minutes ||
        30;

      setEditableDurationMinutes(String(correctDuration));

      if (matchedService.default_urgency && !editableUrgency) {
        setEditableUrgency(matchedService.default_urgency);
      }

      if (!editableReason && matchedService.canonical_reason) {
        setEditableReason(matchedService.canonical_reason);
      }

      return;
    }

    setSelectedServiceId("");
    setEditableServiceName("");
    setEditableDurationMinutes("30");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    selectedDoctorId,
    availableServicesForDoctor,
    isLoadingDoctorServices,
    selectedServiceId,
  ]);

  useEffect(() => {
    if (mode !== "edit" || !appointment) return;

    const dateString = getLocalDateStringFromIso(appointment.start_time);
    const startTime = getLocalTimeStringFromIso(appointment.start_time);
    const endTime = getLocalTimeStringFromIso(appointment.end_time);

    setSelectedSlot({
      id: `${dateString}:${startTime}:${endTime}`,
      date: dateString,
      startTime,
      endTime,
      startDateTime: new Date(appointment.start_time),
      endDateTime: new Date(appointment.end_time),
      isBooked: false,
      bookedAppointment: null,
    });
  }, [mode, appointment]);

  useEffect(() => {
    async function loadSchedule() {
      if (!selectedDoctorId) {
        setIsLoading(false);
        return;
      }

      try {
        setIsLoading(true);
        setErrorMessage("");

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

  useEffect(() => {
    if (mode !== "confirm") return;
    if (!request) return;
    if (selectedSlot) return;
    if (!preferredDateFromRequest || !preferredTimeFromRequest) return;
    if (allSlotsForWeek.length === 0) return;

    const matchedSlot =
      allSlotsForWeek.find((slot) => {
        return (
          slot.date === preferredDateFromRequest &&
          slot.startTime === preferredTimeFromRequest
        );
      }) || null;

    if (!matchedSlot) return;

    setSelectedSlot(matchedSlot);
  }, [
    mode,
    request,
    selectedSlot,
    preferredDateFromRequest,
    preferredTimeFromRequest,
    allSlotsForWeek,
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

  async function handleSave() {
    if (!selectedDoctorId) {
      setErrorMessage("Select a doctor first.");
      return;
    }

    if (!selectedServiceId) {
      setErrorMessage("Select a service first.");
      return;
    }

    if (!selectedPatientId) {
      setErrorMessage("Select a patient first.");
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

    const slotToSave = selectedSlot;

    if (!slotToSave) {
      setErrorMessage("Select an available slot first.");
      return;
    }

    if (slotToSave.isBooked) {
      setErrorMessage("This slot is already booked. Choose another available slot.");
      return;
    }

    if (!Number.isFinite(durationMinutes) || durationMinutes <= 0) {
      setErrorMessage("Duration must be a positive number.");
      return;
    }

    try {
      setIsSaving(true);
      setErrorMessage("");

      if (mode === "confirm") {
        if (!request) {
          throw new Error("Appointment request was not provided.");
        }

        const { error: updateRequestError } = await supabase
          .from("appointment_requests")
          .update({
            patient_id: selectedPatientId || request.patient_id || null,
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
          patientId: selectedPatientId || request.patient_id || null,
          doctorId: selectedDoctorId,
          serviceCategoryId: selectedServiceId,
          serviceName: editableServiceName.trim()
            ? editableServiceName.trim()
            : null,
          reason: editableReason.trim() ? editableReason.trim() : null,
          urgency: editableUrgency,
          startTime: slotToSave.startDateTime.toISOString(),
          endTime: slotToSave.endDateTime.toISOString(),
          durationMinutes,
          notes: notes.trim() ? notes.trim() : null,
        });
      }

      if (mode === "edit") {
        if (!appointment) {
          throw new Error("Appointment was not provided.");
        }

        await updateAppointment({
          clinicId,
          appointmentId: appointment.id,
          patientId: selectedPatientId,
          doctorId: selectedDoctorId,
          serviceCategoryId: selectedServiceId,
          serviceName: editableServiceName.trim()
            ? editableServiceName.trim()
            : null,
          reason: editableReason.trim() ? editableReason.trim() : null,
          urgency: editableUrgency,
          startTime: slotToSave.startDateTime.toISOString(),
          endTime: slotToSave.endDateTime.toISOString(),
          durationMinutes,
          notes: notes.trim() ? notes.trim() : null,
        });
      }

      setIsSaving(false);
      onSaved();
    } catch (error) {
      console.error("Save appointment error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to save appointment."
      );
      setIsSaving(false);
    }
  }

  function goToPreviousWeek() {
    setWeekStart(addDays(weekStart, -7));
    setSelectedSlot(null);
  }

  function goToNextWeek() {
    setWeekStart(addDays(weekStart, 7));
    setSelectedSlot(null);
  }

  function goToThisWeek() {
    setWeekStart(getWeekStart(new Date()));
    setSelectedSlot(null);
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/50 p-4">
      <div className="max-h-[94vh] w-full max-w-7xl overflow-y-auto rounded-2xl bg-white shadow-xl">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-100 p-5">
          <div>
            <h2 className="text-lg font-bold text-slate-900">{editorTitle}</h2>

            <p className="mt-1 text-sm text-slate-500">
              {mode === "confirm"
                ? "Choose an available doctor slot and confirm this request."
                : "Edit patient, service, doctor, and appointment time."}
            </p>

            <div className="mt-3 rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-700">
              <span className="font-semibold">Patient:</span>{" "}
              {selectedPatient?.full_name || request?.patient_name || "Unknown"}
              <span className="mx-2 text-slate-300">|</span>
              <span className="font-semibold">Phone:</span>{" "}
              {selectedPatient?.phone_primary || request?.patient_phone || "-"}
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

            <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-[minmax(340px,1.4fr)_minmax(240px,1fr)_120px]">
              <div className="relative">
                <label className="text-sm font-medium text-slate-700">
                  Patient
                </label>

                <div className="mt-2 flex w-full overflow-hidden rounded-xl border border-slate-300 bg-white transition focus-within:border-blue-500 hover:border-blue-400">
                  <button
                    type="button"
                    onClick={() =>
                      setIsPatientDropdownOpen((current) => !current)
                    }
                    className="flex min-w-0 flex-1 items-center justify-between px-4 py-3 text-left text-sm outline-none"
                  >
                    <span
                      className={`truncate ${
                        selectedPatient
                          ? "font-medium text-slate-900"
                          : "text-slate-400"
                      }`}
                    >
                      {selectedPatient
                        ? getPatientLabel(selectedPatient)
                        : selectedPatientId
                        ? "Linked patient selected"
                        : "Select patient"}
                    </span>

                    <span className="ml-3 shrink-0 text-slate-400">
                      {isPatientDropdownOpen ? "▲" : "▼"}
                    </span>
                  </button>

                  {selectedPatientId && (
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedPatientId("");
                        setPatientSearch("");
                        setIsPatientDropdownOpen(false);
                      }}
                      className="border-l border-slate-200 px-3 text-sm font-bold text-slate-400 hover:bg-red-50 hover:text-red-600"
                      title="Clear selected patient"
                    >
                      ×
                    </button>
                  )}
                </div>

                {mode === "confirm" &&
                    !request?.patient_id &&
                    !selectedPatientId &&
                    request?.patient_name && (
                    <div className="mt-2 rounded-xl border border-red-200 bg-red-50 p-3">
                      <p className="text-xs font-bold text-red-700">
                        AI extracted: {request.patient_name}
                        {request.patient_phone ? ` — ${request.patient_phone}` : ""}
                      </p>

                      <p className="mt-1 text-xs text-red-600">
                        This request is not linked to an existing patient yet.
                      </p>

                      <Link
                        href={createPatientHref}
                        className="mt-3 inline-flex rounded-lg bg-red-600 px-3 py-2 text-xs font-bold text-white hover:bg-red-700"
                      >
                        Add this patient
                      </Link>
                    </div>
                  )}

                {isPatientDropdownOpen && (
                  <div className="absolute z-50 mt-2 w-full overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-xl">
                    <div className="border-b border-slate-100 p-3">
                      <input
                        autoFocus
                        value={patientSearch}
                        onChange={(event) =>
                          setPatientSearch(event.target.value)
                        }
                        placeholder="Search by name, phone, or email..."
                        className="w-full rounded-xl border border-slate-300 bg-slate-50 px-4 py-2.5 text-sm outline-none focus:border-blue-500 focus:bg-white"
                      />
                    </div>

                    <div className="max-h-72 overflow-y-auto p-2">
                      {filteredPatients.length === 0 && (
                        <div className="px-3 py-5 text-center text-sm text-slate-500">
                          No patients found.
                        </div>
                      )}

                      {filteredPatients.map((patient) => {
                        const isSelected = patient.id === selectedPatientId;

                        return (
                          <button
                            key={patient.id}
                            type="button"
                            onClick={() => {
                              setSelectedPatientId(patient.id);
                              setPatientSearch("");
                              setIsPatientDropdownOpen(false);
                            }}
                            className={`w-full rounded-xl px-3 py-3 text-left transition ${
                              isSelected
                                ? "bg-blue-50 ring-1 ring-blue-200"
                                : "hover:bg-slate-50"
                            }`}
                          >
                            <div className="flex items-start justify-between gap-3">
                              <div className="min-w-0">
                                <p className="truncate text-sm font-bold text-slate-900">
                                  {patient.full_name}
                                </p>

                                <p className="mt-1 text-xs font-medium text-slate-500">
                                  {patient.phone_primary}
                                  {patient.phone_secondary
                                    ? ` · ${patient.phone_secondary}`
                                    : ""}
                                </p>

                                {patient.email && (
                                  <p className="mt-1 truncate text-xs text-slate-400">
                                    {patient.email}
                                  </p>
                                )}
                              </div>

                              {isSelected && (
                                <span className="rounded-full bg-blue-600 px-2 py-1 text-[10px] font-bold text-white">
                                  Selected
                                </span>
                              )}
                            </div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                )}
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
                  className="mt-2 w-full rounded-xl border border-slate-300 bg-white px-3 py-3 text-sm outline-none focus:border-blue-500"
                />
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
            </div>

            {selectedPatient && (
              <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4 text-sm">
                <p className="font-bold text-slate-900">
                  {selectedPatient.full_name}
                </p>
                <p className="mt-1 text-slate-600">
                  Primary phone: {selectedPatient.phone_primary}
                </p>

                {selectedPatient.phone_secondary && (
                  <p className="mt-1 text-slate-600">
                    Secondary phone: {selectedPatient.phone_secondary}
                  </p>
                )}

                {selectedPatient.email && (
                  <p className="mt-1 text-slate-600">
                    Email: {selectedPatient.email}
                  </p>
                )}
              </div>
            )}
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
                              className={`rounded-xl border px-3 py-2 text-xs ${
                                isSelected
                                  ? "border-amber-300 bg-amber-50 text-amber-800 ring-2 ring-amber-300"
                                  : "border-red-200 bg-red-50 text-red-700"
                              }`}
                            >
                              <div className="font-bold">
                                {slot.startTime} - {slot.endTime}
                              </div>

                              <div className="mt-1 truncate">
                                {isSelected
                                  ? "Selected time is already booked"
                                  : "Booked appointment"}
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
                                ? "border-emerald-600 bg-emerald-100 text-emerald-950 ring-2 ring-emerald-500"
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
                <div
                  className={`mt-2 text-sm font-bold ${
                    selectedSlot.isBooked ? "text-amber-700" : "text-slate-900"
                  }`}
                >
                  {selectedSlot.isBooked
                    ? "Selected time is already booked."
                    : doctorNameById[selectedDoctorId] || "Doctor"}
                  <br />
                  {selectedSlot.date}
                  <br />
                  {selectedSlot.startTime} - {selectedSlot.endTime}

                  {selectedSlot.isBooked && (
                    <p className="mt-2 text-xs font-medium text-slate-500">
                      Choose another available slot.
                    </p>
                  )}
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
            disabled={!selectedSlot || selectedSlotIsBooked || !selectedPatientId || isSaving}
            onClick={handleSave}
            className="w-full rounded-xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSaving ? "Saving..." : submitLabel}
          </button>
        </div>
      </div>
    </div>
  );
}