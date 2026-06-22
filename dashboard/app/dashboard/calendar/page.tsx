"use client";

import {
  FormEvent,
  ReactNode,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useRouter } from "next/navigation";
import DashboardShell from "@/components/layout/DashboardShell";
import {
  CalendarAvailabilityException,
  CalendarAvailabilityRule,
  ClinicDoctor,
  cancelCalendarAvailabilityOnlyThisDay,
  cancelCalendarAvailabilityThisAndFuture,
  createCalendarAvailabilityRule,
  getCalendarAvailabilityExceptions,
  getCalendarAvailabilityRules,
  getClinicDoctors,
  getCurrentSession,
  updateCalendarAvailabilityOnlyThisDay,
  updateCalendarAvailabilityThisAndFuture,
} from "@/lib/supabaseService";

type CalendarEvent = {
  id: string;
  ruleId: string;
  date: string;
  doctorId: string | null;
  startTime: string;
  endTime: string;
  repeatType: string;
  notes: string | null;
  originalRule: CalendarAvailabilityRule;
};

type EditMode = "only_this_day" | "this_and_future";

const WEEK_DAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

function formatDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

function getDateLabel(dateString: string) {
  const date = new Date(`${dateString}T00:00:00`);

  const weekDay = date.toLocaleDateString("en-US", {
    weekday: "long",
  });

  const formattedDate = date.toLocaleDateString("en-US", {
    month: "long",
    day: "numeric",
    year: "numeric",
  });

  return `${weekDay}, ${formattedDate}`;
}

function getMonthStart(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function getMonthEnd(date: Date) {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0);
}

function addDays(date: Date, days: number) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function getCalendarGridDays(currentMonth: Date) {
  const monthStart = getMonthStart(currentMonth);
  const monthEnd = getMonthEnd(currentMonth);

  const gridStart = addDays(monthStart, -monthStart.getDay());
  const gridEnd = addDays(monthEnd, 6 - monthEnd.getDay());

  const days: Date[] = [];
  let current = gridStart;

  while (current <= gridEnd) {
    days.push(new Date(current));
    current = addDays(current, 1);
  }

  return days;
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

function generateMonthEvents({
  rules,
  exceptions,
  monthDays,
}: {
  rules: CalendarAvailabilityRule[];
  exceptions: CalendarAvailabilityException[];
  monthDays: Date[];
}) {
  const exceptionByRuleAndDate = new Map<
    string,
    CalendarAvailabilityException
  >();

  exceptions.forEach((exception) => {
    exceptionByRuleAndDate.set(
      `${exception.rule_id}:${exception.exception_date}`,
      exception
    );
  });

  const events: CalendarEvent[] = [];

  rules.forEach((rule) => {
    monthDays.forEach((date) => {
      if (!appliesToDate(rule, date)) return;

      const dateString = formatDate(date);
      const exception = exceptionByRuleAndDate.get(`${rule.id}:${dateString}`);

      if (exception?.exception_type === "cancelled") return;

      const startTime =
        exception?.exception_type === "modified" && exception.start_time
          ? exception.start_time
          : rule.start_time;

      const endTime =
        exception?.exception_type === "modified" && exception.end_time
          ? exception.end_time
          : rule.end_time;

      events.push({
        id: `${rule.id}:${dateString}`,
        ruleId: rule.id,
        date: dateString,
        doctorId: rule.doctor_id,
        startTime,
        endTime,
        repeatType: rule.repeat_type,
        notes: exception?.notes || rule.notes,
        originalRule: rule,
      });
    });
  });

  return events;
}

export default function CalendarPage() {
  const router = useRouter();
  const currentClinicId = process.env.NEXT_PUBLIC_CLINIC_ID || "";

  const [isCheckingSession, setIsCheckingSession] = useState(true);
  const [isLoadingCalendar, setIsLoadingCalendar] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  const [errorMessage, setErrorMessage] = useState("");

  const [currentMonth, setCurrentMonth] = useState(new Date());
  const [scope, setScope] = useState("all");

  const [doctors, setDoctors] = useState<ClinicDoctor[]>([]);
  const [rules, setRules] = useState<CalendarAvailabilityRule[]>([]);
  const [exceptions, setExceptions] = useState<CalendarAvailabilityException[]>(
    []
  );

  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isEventModalOpen, setIsEventModalOpen] = useState(false);

  const [selectedDate, setSelectedDate] = useState("");
  const [selectedEvent, setSelectedEvent] = useState<CalendarEvent | null>(
    null
  );

  const [editMode, setEditMode] = useState<EditMode>("only_this_day");

  const [formDoctorId, setFormDoctorId] = useState<string | null>(null);
  const [formStartDate, setFormStartDate] = useState("");
  const [formEndDate, setFormEndDate] = useState("");
  const [formStartTime, setFormStartTime] = useState("09:00");
  const [formEndTime, setFormEndTime] = useState("17:00");
  const [formRepeatType, setFormRepeatType] =
    useState<CalendarAvailabilityRule["repeat_type"]>("none");
  const [formTimezone, setFormTimezone] = useState("America/Vancouver");
  const [formNotes, setFormNotes] = useState("");

  const monthDays = useMemo(() => getCalendarGridDays(currentMonth), [
    currentMonth,
  ]);

  const monthStart = formatDate(getMonthStart(currentMonth));
  const monthEnd = formatDate(getMonthEnd(currentMonth));

  const doctorNameById = useMemo(() => {
    const map: Record<string, string> = {};

    doctors.forEach((doctor) => {
      map[doctor.id] = doctor.display_name || doctor.full_name;
    });

    return map;
  }, [doctors]);

  const visibleEvents = useMemo(() => {
    return generateMonthEvents({
      rules,
      exceptions,
      monthDays,
    });
  }, [rules, exceptions, monthDays]);

  const eventsByDate = useMemo(() => {
    const map: Record<string, CalendarEvent[]> = {};

    visibleEvents.forEach((event) => {
      if (!map[event.date]) map[event.date] = [];
      map[event.date].push(event);
    });

    return map;
  }, [visibleEvents]);

  useEffect(() => {
    async function loadPage() {
      try {
        setErrorMessage("");

        if (!currentClinicId) {
          setErrorMessage("Missing NEXT_PUBLIC_CLINIC_ID in .env.local.");
          setIsCheckingSession(false);
          setIsLoadingCalendar(false);
          return;
        }

        const session = await getCurrentSession();

        if (!session) {
          router.replace("/login");
          return;
        }

        setIsCheckingSession(false);

        const loadedDoctors = await getClinicDoctors(currentClinicId);
        setDoctors(loadedDoctors);

        await loadCalendar();
      } catch (error) {
        console.error("Load calendar page error:", error);
        setErrorMessage(
          error instanceof Error ? error.message : "Failed to load calendar."
        );
        setIsCheckingSession(false);
        setIsLoadingCalendar(false);
      }
    }

    loadPage();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [router]);

  useEffect(() => {
    if (!isCheckingSession && currentClinicId) {
      loadCalendar();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentMonth, scope]);

  useEffect(() => {
    if (!selectedEvent) return;

    if (editMode === "only_this_day") {
      setFormStartDate(selectedEvent.date);
      setFormEndDate(selectedEvent.date);
      return;
    }

    if (editMode === "this_and_future") {
      setFormStartDate(selectedEvent.date);
      setFormEndDate(selectedEvent.originalRule.end_date || "");
    }
  }, [editMode, selectedEvent]);

  async function loadCalendar() {
    try {
      setIsLoadingCalendar(true);
      setErrorMessage("");

      let doctorIdFilter: string | null | undefined = undefined;

      if (scope === "clinic") {
        doctorIdFilter = null;
      } else if (scope.startsWith("doctor:")) {
        doctorIdFilter = scope.replace("doctor:", "");
      }

      const loadedRules = await getCalendarAvailabilityRules({
        clinicId: currentClinicId,
        doctorId: doctorIdFilter,
        monthStart,
        monthEnd,
      });

      setRules(loadedRules);

      const loadedExceptions = await getCalendarAvailabilityExceptions({
        clinicId: currentClinicId,
        ruleIds: loadedRules.map((rule) => rule.id),
        monthStart,
        monthEnd,
      });

      setExceptions(loadedExceptions);
      setIsLoadingCalendar(false);
    } catch (error) {
      console.error("Load calendar error:", error);
      setErrorMessage(
        error instanceof Error ? error.message : "Failed to load calendar."
      );
      setIsLoadingCalendar(false);
    }
  }

function openAddModal(dateString: string) {
  setErrorMessage("");

  if (scope === "all") {
    setErrorMessage("Please select Clinic availability or a doctor before adding availability.");
    return;
  }

  setSelectedDate(dateString);
  setFormStartDate(dateString);
  setFormEndDate("");
  setFormStartTime("09:00");
  setFormEndTime("17:00");
  setFormRepeatType("none");
  setFormTimezone("America/Vancouver");
  setFormNotes("");

  if (scope === "clinic") {
    setFormDoctorId(null);
  } else if (scope.startsWith("doctor:")) {
    setFormDoctorId(scope.replace("doctor:", ""));
  }

  setIsAddModalOpen(true);
}

  function openEventModal(event: CalendarEvent) {
    setSelectedEvent(event);
    setEditMode("only_this_day");

    setFormDoctorId(event.originalRule.doctor_id);
    setFormStartDate(event.date);
    setFormEndDate(event.date);
    setFormStartTime(event.startTime.slice(0, 5));
    setFormEndTime(event.endTime.slice(0, 5));
    setFormRepeatType(event.originalRule.repeat_type);
    setFormTimezone(event.originalRule.timezone);
    setFormNotes(event.notes || "");

    setIsEventModalOpen(true);
  }

  async function handleCreateAvailability(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    try {
      setErrorMessage("");

      if (!formStartDate) {
        setErrorMessage("Start date is required.");
        return;
      }

      if (!formStartTime || !formEndTime) {
        setErrorMessage("Start time and end time are required.");
        return;
      }

      if (formStartTime >= formEndTime) {
        setErrorMessage("Start time must be before end time.");
        return;
      }

      setIsSaving(true);

      const startDateObject = new Date(`${formStartDate}T00:00:00`);
      const dayOfWeek =
        formRepeatType === "weekly" || formRepeatType === "custom"
          ? startDateObject.getDay()
          : null;

      await createCalendarAvailabilityRule({
        clinicId: currentClinicId,
        doctorId: formDoctorId,
        startDate: formStartDate,
        endDate: formEndDate || null,
        dayOfWeek,
        startTime: formStartTime,
        endTime: formEndTime,
        timezone: formTimezone,
        repeatType: formRepeatType,
        isActive: true,
        notes: formNotes.trim() ? formNotes.trim() : null,
      });

      setIsAddModalOpen(false);
      await loadCalendar();

      setIsSaving(false);
    } catch (error) {
      console.error("Create availability error:", error);
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Failed to create availability."
      );
      setIsSaving(false);
    }
  }

  async function handleUpdateAvailability(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!selectedEvent) return;

    try {
      setErrorMessage("");

      if (!formStartDate) {
        setErrorMessage("Start date is required.");
        return;
      }

      if (!formEndDate && editMode === "only_this_day") {
        setErrorMessage("Repeat until is required for only this day.");
        return;
      }

      if (formStartTime >= formEndTime) {
        setErrorMessage("Start time must be before end time.");
        return;
      }

      if (formEndDate && formEndDate < formStartDate) {
        setErrorMessage("Repeat until must be after start date.");
        return;
      }

      setIsSaving(true);

      if (editMode === "only_this_day") {
        await updateCalendarAvailabilityOnlyThisDay({
          clinicId: currentClinicId,
          ruleId: selectedEvent.ruleId,
          exceptionDate: selectedEvent.date,
          startTime: formStartTime,
          endTime: formEndTime,
          notes: formNotes.trim() ? formNotes.trim() : null,
        });
      }

      if (editMode === "this_and_future") {
        await updateCalendarAvailabilityThisAndFuture({
          clinicId: currentClinicId,
          originalRule: selectedEvent.originalRule,
          clickedDate: selectedEvent.date,
          newEndDate: formEndDate || null,
          startTime: formStartTime,
          endTime: formEndTime,
          timezone: formTimezone,
          notes: formNotes.trim() ? formNotes.trim() : null,
        });
      }

      setIsEventModalOpen(false);
      setSelectedEvent(null);

      await loadCalendar();

      setIsSaving(false);
    } catch (error) {
      console.error("Update availability error:", error);
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Failed to update availability."
      );
      setIsSaving(false);
    }
  }

  async function handleRemoveAvailability() {
    if (!selectedEvent) return;

    const confirmed = window.confirm(
      editMode === "only_this_day"
        ? "Remove availability only for this day?"
        : "Remove availability from this date and future?"
    );

    if (!confirmed) return;

    try {
      setErrorMessage("");
      setIsSaving(true);

      if (editMode === "only_this_day") {
        await cancelCalendarAvailabilityOnlyThisDay({
          clinicId: currentClinicId,
          ruleId: selectedEvent.ruleId,
          exceptionDate: selectedEvent.date,
          notes: "Cancelled from calendar",
        });
      }

      if (editMode === "this_and_future") {
        await cancelCalendarAvailabilityThisAndFuture({
          originalRuleId: selectedEvent.ruleId,
          clickedDate: selectedEvent.date,
        });
      }

      setIsEventModalOpen(false);
      setSelectedEvent(null);

      await loadCalendar();

      setIsSaving(false);
    } catch (error) {
      console.error("Remove availability error:", error);
      setErrorMessage(
        error instanceof Error
          ? error.message
          : "Failed to remove availability."
      );
      setIsSaving(false);
    }
  }

  function goToPreviousMonth() {
    setCurrentMonth(
      new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1, 1)
    );
  }

  function goToNextMonth() {
    setCurrentMonth(
      new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1)
    );
  }

  function goToToday() {
    setCurrentMonth(new Date());
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
      title="Calendar"
      description="Manage clinic and doctor availability."
    >
      {errorMessage && (
        <div className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {errorMessage}
        </div>
      )}

      <div className="rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-100 p-5">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={goToToday}
              className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              Today
            </button>

            <button
              type="button"
              onClick={goToPreviousMonth}
              className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              ‹
            </button>

            <button
              type="button"
              onClick={goToNextMonth}
              className="rounded-xl border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              ›
            </button>

            <h2 className="ml-2 text-xl font-bold text-slate-900">
              {currentMonth.toLocaleString("en-US", {
                month: "long",
                year: "numeric",
              })}
            </h2>
          </div>

          <select
            value={scope}
            onChange={(event) => setScope(event.target.value)}
            className="min-w-[240px] rounded-xl border border-slate-300 bg-white px-4 py-2 text-sm outline-none focus:border-blue-500"
          >
            <option value="all">All schedules</option>
            <option value="clinic">Clinic availability</option>
            {doctors.map((doctor) => (
              <option key={doctor.id} value={`doctor:${doctor.id}`}>
                {doctor.display_name || doctor.full_name}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-7 border-b border-slate-200 bg-slate-50 text-center text-xs font-bold text-slate-500">
          {WEEK_DAYS.map((day) => (
            <div key={day} className="border-r border-slate-200 px-2 py-3">
              {day}
            </div>
          ))}
        </div>

        <div className="grid grid-cols-7">
          {monthDays.map((day) => {
            const dateString = formatDate(day);
            const dayEvents = eventsByDate[dateString] || [];
            const isCurrentMonth = day.getMonth() === currentMonth.getMonth();
            const isToday = dateString === formatDate(new Date());

            return (
              <div
                key={dateString}
                onClick={() => openAddModal(dateString)}
                className={`min-h-[135px] cursor-pointer border-b border-r border-slate-200 p-2 transition hover:bg-slate-50 ${
                  isCurrentMonth ? "bg-white" : "bg-slate-50/60"
                }`}
              >
                <div className="mb-2 flex items-center justify-between">
                  <span
                    className={`flex h-7 w-7 items-center justify-center rounded-full text-sm font-semibold ${
                      isToday
                        ? "bg-blue-600 text-white"
                        : isCurrentMonth
                          ? "text-slate-900"
                          : "text-slate-400"
                    }`}
                  >
                    {day.getDate()}
                  </span>
                </div>

                <div className="space-y-1">
                  {dayEvents.slice(0, 3).map((calendarEvent) => (
                    <button
                      key={calendarEvent.id}
                      type="button"
                      onClick={(clickEvent) => {
                        clickEvent.stopPropagation();
                        openEventModal(calendarEvent);
                      }}
                      className={`w-full truncate rounded-lg px-2 py-1 text-left text-xs font-semibold ${
                        calendarEvent.doctorId
                          ? "bg-green-50 text-green-700"
                          : "bg-blue-50 text-blue-700"
                      }`}
                    >
                      {calendarEvent.startTime.slice(0, 5)}-
                      {calendarEvent.endTime.slice(0, 5)}{" "}
                      {calendarEvent.doctorId
                        ? doctorNameById[calendarEvent.doctorId] || "Doctor"
                        : "Clinic"}
                    </button>
                  ))}

                  {dayEvents.length > 3 && (
                    <div className="text-xs font-medium text-slate-500">
                      +{dayEvents.length - 3} more
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {isLoadingCalendar && (
          <div className="border-t border-slate-100 p-4 text-center text-sm text-slate-500">
            Loading calendar...
          </div>
        )}
      </div>

      {isAddModalOpen && (
        <AvailabilityModal
          mode="add"
          title="Add Availability"
          selectedDateLabel={selectedDate ? getDateLabel(selectedDate) : ""}
          availabilityForLabel={
            formDoctorId
              ? doctorNameById[formDoctorId] || "Doctor"
              : "Clinic availability"
          }
          showAvailabilityForField={false}
          editMode={editMode}
          setEditMode={setEditMode}
          submitLabel={isSaving ? "Saving..." : "Save Availability"}
          onClose={() => setIsAddModalOpen(false)}
          onSubmit={handleCreateAvailability}
          onRemove={handleRemoveAvailability}
          doctors={doctors}
          formDoctorId={formDoctorId}
          setFormDoctorId={setFormDoctorId}
          formStartDate={formStartDate}
          setFormStartDate={setFormStartDate}
          formEndDate={formEndDate}
          setFormEndDate={setFormEndDate}
          formStartTime={formStartTime}
          setFormStartTime={setFormStartTime}
          formEndTime={formEndTime}
          setFormEndTime={setFormEndTime}
          formRepeatType={formRepeatType}
          setFormRepeatType={setFormRepeatType}
          formTimezone={formTimezone}
          setFormTimezone={setFormTimezone}
          formNotes={formNotes}
          setFormNotes={setFormNotes}
          isSaving={isSaving}
        />
      )}

      {isEventModalOpen && selectedEvent && (
        <AvailabilityModal
          mode="edit"
          title="Edit Availability"
          selectedDateLabel={getDateLabel(selectedEvent.date)}
          availabilityForLabel={
            selectedEvent.doctorId
              ? doctorNameById[selectedEvent.doctorId] || "Doctor"
              : "Clinic availability"
          }
          showAvailabilityForField={false}
          editMode={editMode}
          setEditMode={setEditMode}
          submitLabel={isSaving ? "Saving..." : "Save Changes"}
          onClose={() => {
            setIsEventModalOpen(false);
            setSelectedEvent(null);
          }}
          onSubmit={handleUpdateAvailability}
          onRemove={handleRemoveAvailability}
          doctors={doctors}
          formDoctorId={formDoctorId}
          setFormDoctorId={setFormDoctorId}
          formStartDate={formStartDate}
          setFormStartDate={setFormStartDate}
          formEndDate={formEndDate}
          setFormEndDate={setFormEndDate}
          formStartTime={formStartTime}
          setFormStartTime={setFormStartTime}
          formEndTime={formEndTime}
          setFormEndTime={setFormEndTime}
          formRepeatType={formRepeatType}
          setFormRepeatType={setFormRepeatType}
          formTimezone={formTimezone}
          setFormTimezone={setFormTimezone}
          formNotes={formNotes}
          setFormNotes={setFormNotes}
          isSaving={isSaving}
        />
      )}
    </DashboardShell>
  );
}

function AvailabilityModal({
  mode,
  title,
  selectedDateLabel,
  availabilityForLabel,
  showAvailabilityForField,
  editMode,
  setEditMode,
  submitLabel,
  onClose,
  onSubmit,
  onRemove,
  doctors,
  formDoctorId,
  setFormDoctorId,
  formStartDate,
  setFormStartDate,
  formEndDate,
  setFormEndDate,
  formStartTime,
  setFormStartTime,
  formEndTime,
  setFormEndTime,
  formRepeatType,
  setFormRepeatType,
  formTimezone,
  setFormTimezone,
  formNotes,
  setFormNotes,
  isSaving,
}: {
  mode: "add" | "edit";
  title: string;
  selectedDateLabel: string;
  availabilityForLabel: string;
  showAvailabilityForField: boolean;
  editMode: EditMode;
  setEditMode: (value: EditMode) => void;
  submitLabel: string;
  onClose: () => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onRemove: () => void;
  doctors: ClinicDoctor[];
  formDoctorId: string | null;
  setFormDoctorId: (value: string | null) => void;
  formStartDate: string;
  setFormStartDate: (value: string) => void;
  formEndDate: string;
  setFormEndDate: (value: string) => void;
  formStartTime: string;
  setFormStartTime: (value: string) => void;
  formEndTime: string;
  setFormEndTime: (value: string) => void;
  formRepeatType: CalendarAvailabilityRule["repeat_type"];
  setFormRepeatType: (value: CalendarAvailabilityRule["repeat_type"]) => void;
  formTimezone: string;
  setFormTimezone: (value: string) => void;
  formNotes: string;
  setFormNotes: (value: string) => void;
  isSaving: boolean;
  footer?: ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white shadow-xl">
        <div className="flex items-start justify-between border-b border-slate-100 p-5">
          <div className="w-full pr-4">
            <h2 className="text-lg font-bold text-slate-900">{title}</h2>

            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="rounded-xl bg-slate-50 px-4 py-3">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                  Availability For
                </p>
                <p className="mt-1 text-sm font-bold text-slate-900">
                  {availabilityForLabel}
                </p>
              </div>

              {selectedDateLabel && (
                <div className="rounded-xl bg-blue-50 px-4 py-3">
                  <p className="text-xs font-semibold uppercase tracking-wide text-blue-500">
                    Selected Date
                  </p>
                  <p className="mt-1 text-sm font-bold text-blue-900">
                    {selectedDateLabel}
                  </p>
                </div>
              )}
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded-xl border border-slate-200 px-3 py-2 text-sm font-semibold text-slate-600 hover:bg-slate-50"
          >
            Close
          </button>
        </div>

        <form onSubmit={onSubmit} className="space-y-5 p-5">


          {mode === "edit" && (
            <div>
              <label className="text-sm font-medium text-slate-700">
                Apply Change To
              </label>

              <div className="mt-2 grid grid-cols-1 gap-3 md:grid-cols-2">
                <button
                  type="button"
                  onClick={() => setEditMode("only_this_day")}
                  className={`rounded-xl border px-4 py-3 text-left text-sm font-semibold ${
                    editMode === "only_this_day"
                      ? "border-blue-300 bg-blue-50 text-blue-700"
                      : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  Only this day
                  <span className="mt-1 block text-xs font-normal text-slate-500">
                    Change only the selected date.
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => setEditMode("this_and_future")}
                  className={`rounded-xl border px-4 py-3 text-left text-sm font-semibold ${
                    editMode === "this_and_future"
                      ? "border-blue-300 bg-blue-50 text-blue-700"
                      : "border-slate-200 bg-white text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  This and future days
                  <span className="mt-1 block text-xs font-normal text-slate-500">
                    Keep previous days unchanged.
                  </span>
                </button>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label className="text-sm font-medium text-slate-700">
                Start Date
              </label>
              <input
                type="date"
                value={formStartDate}
                readOnly={mode === "edit"}
                onChange={(event) => setFormStartDate(event.target.value)}
                className={`mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500 ${
                  mode === "edit" ? "bg-slate-50 text-slate-500" : ""
                }`}
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Repeat Until
              </label>
              <input
                type="date"
                value={formEndDate}
                readOnly={mode === "edit" && editMode === "only_this_day"}
                onChange={(event) => setFormEndDate(event.target.value)}
                className={`mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500 ${
                  mode === "edit" && editMode === "only_this_day"
                    ? "bg-slate-50 text-slate-500"
                    : ""
                }`}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <label className="text-sm font-medium text-slate-700">
                Start Time
              </label>
              <input
                type="time"
                value={formStartTime}
                onChange={(event) => setFormStartTime(event.target.value)}
                className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                End Time
              </label>
              <input
                type="time"
                value={formEndTime}
                onChange={(event) => setFormEndTime(event.target.value)}
                className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
              />
            </div>
          </div>

          {mode === "add" && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <label className="text-sm font-medium text-slate-700">
                  Repeat
                </label>
                <select
                  value={formRepeatType}
                  onChange={(event) =>
                    setFormRepeatType(
                      event.target
                        .value as CalendarAvailabilityRule["repeat_type"]
                    )
                  }
                  className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                >
                  <option value="none">Does not repeat</option>
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly on this day</option>
                  <option value="weekdays">Weekdays Monday-Friday</option>
                  <option value="custom">Custom weekly on this day</option>
                </select>
              </div>

              <div>
                <label className="text-sm font-medium text-slate-700">
                  Timezone
                </label>
                <input
                  value={formTimezone}
                  onChange={(event) => setFormTimezone(event.target.value)}
                  className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
                />
              </div>
            </div>
          )}

          {mode === "edit" && (
            <div className="rounded-xl bg-slate-50 px-4 py-3 text-sm text-slate-600">
              Repeat pattern and doctor/clinic cannot be changed from this edit.
              Previous days stay unchanged.
            </div>
          )}

          <div>
            <label className="text-sm font-medium text-slate-700">Notes</label>
            <textarea
              value={formNotes}
              onChange={(event) => setFormNotes(event.target.value)}
              rows={3}
              placeholder="Optional notes"
              className="mt-2 w-full rounded-xl border border-slate-300 px-4 py-3 text-sm outline-none focus:border-blue-500"
            />
          </div>

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <button
              type="submit"
              disabled={isSaving}
              className="rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {submitLabel}
            </button>

            {mode === "edit" && (
              <button
                type="button"
                onClick={onRemove}
                disabled={isSaving}
                className="rounded-xl border border-red-200 bg-red-50 px-5 py-3 text-sm font-semibold text-red-700 hover:bg-red-100 disabled:opacity-60"
              >
                Remove Availability
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}