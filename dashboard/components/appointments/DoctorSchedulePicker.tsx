"use client";

import AppointmentScheduleEditor from "./AppointmentScheduleEditor";

type RequestForSchedule = {
  id: string;
  patient_id?: string | null;
  patient_name: string | null;
  patient_phone: string | null;
  reason: string | null;
  urgency: string | null;
  doctor_id?: string | null;
  preferred_doctor_name: string | null;
  preferred_date_raw?: string | null;
  preferred_time_raw?: string | null;
  service_category_id?: string | null;
  service_category_name?: string | null;
  duration_minutes?: number | null;
};

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
  const requestForEditor = {
    id: request.id,
    patient_id: request.patient_id ?? null,
    patient_name: request.patient_name ?? null,
    patient_phone: request.patient_phone ?? null,
    reason: request.reason ?? null,
    urgency: request.urgency ?? null,
    doctor_id: request.doctor_id ?? null,
    preferred_doctor_name: request.preferred_doctor_name ?? null,
    preferred_date_raw: request.preferred_date_raw ?? null,
    preferred_time_raw: request.preferred_time_raw ?? null,
    service_category_id: request.service_category_id ?? null,
    service_category_name: request.service_category_name ?? null,
    duration_minutes: request.duration_minutes ?? null,
  };

  return (
    <AppointmentScheduleEditor
      mode="confirm"
      clinicId={clinicId}
      request={requestForEditor}
      onClose={onClose}
      onSaved={onConfirmed}
    />
  );
}