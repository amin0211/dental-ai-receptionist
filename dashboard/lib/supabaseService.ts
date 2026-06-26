import { supabase } from "@/lib/supabaseClient";

export type ServiceCategory = {
  id: string;
  clinic_id: string | null;
  name: string;
  canonical_reason: string;
  default_urgency: string | null;
  creates_appointment_request: boolean | null;
  is_active: boolean | null;
  created_at: string | null;
  default_duration_minutes: number;
  description: string | null;
  updated_at: string;
};

export type ServiceKeyword = {
  id: string;
  clinic_id: string | null;
  category_id: string | null;
  keyword: string;
  language: string | null;
  match_type: string | null;
  is_active: boolean | null;
  created_at: string | null;
};

export type CreateServiceCategoryInput = {
  clinicId: string | null;
  name: string;
  canonicalReason: string;
  defaultUrgency: string;
  createsAppointmentRequest: boolean;
  isActive: boolean;
  defaultDurationMinutes: number;
  description: string | null;
};

export type CreateServiceKeywordInput = {
  clinicId: string | null;
  categoryId: string;
  keyword: string;
  language: string;
  matchType: string;
};

// export async function getCurrentSession() {
//   const { data, error } = await supabase.auth.getSession();

//   if (error) {
//     throw new Error(error.message);
//   }

//   return data.session;
// }

export async function getServiceCategories(clinicId?: string | null) {
  let query = supabase
    .from("service_categories")
    .select(
      "id, clinic_id, name, canonical_reason, default_urgency, creates_appointment_request, is_active, created_at, default_duration_minutes, description, updated_at"
    )
    .order("created_at", { ascending: false });

  if (clinicId) {
    query = query.eq("clinic_id", clinicId);
  }

  const { data, error } = await query;

  if (error) {
    throw new Error(error.message);
  }

  return data || [];
}

export async function getServiceKeywords(categoryId: string) {
  const { data, error } = await supabase
    .from("service_keywords")
    .select(
      "id, clinic_id, category_id, keyword, language, match_type, is_active, created_at"
    )
    .eq("category_id", categoryId)
    .order("created_at", { ascending: false });

  if (error) {
    throw new Error(error.message);
  }

  return data || [];
}

export async function getActiveKeywordCounts(clinicId?: string | null) {
  let query = supabase
    .from("service_keywords")
    .select("category_id")
    .eq("is_active", true);

  if (clinicId) {
    query = query.eq("clinic_id", clinicId);
  }

  const { data, error } = await query;

  if (error) {
    throw new Error(error.message);
  }

  const counts: Record<string, number> = {};

  (data || []).forEach((row) => {
    if (!row.category_id) return;
    counts[row.category_id] = (counts[row.category_id] || 0) + 1;
  });

  return counts;
}

export async function createServiceCategory(input: CreateServiceCategoryInput) {
  const { data, error } = await supabase
    .from("service_categories")
    .insert({
      clinic_id: input.clinicId,
      name: input.name,
      canonical_reason: input.canonicalReason,
      default_urgency: input.defaultUrgency,
      creates_appointment_request: input.createsAppointmentRequest,
      is_active: input.isActive,
      default_duration_minutes: input.defaultDurationMinutes,
      description: input.description,
      updated_at: new Date().toISOString(),
    })
    .select("id")
    .single();

  if (error) {
    throw new Error(error.message);
  }

  if (!data?.id) {
    throw new Error("Service category was created, but no id was returned.");
  }

  return data.id as string;
}

export async function createServiceKeywords(inputs: CreateServiceKeywordInput[]) {
  if (inputs.length === 0) return;

  const rows = inputs.map((input) => ({
    clinic_id: input.clinicId,
    category_id: input.categoryId,
    keyword: input.keyword,
    language: input.language,
    match_type: input.matchType,
    is_active: true,
  }));

  const { error } = await supabase.from("service_keywords").insert(rows);

  if (error) {
    throw new Error(error.message);
  }
}

export async function createServiceKeyword(input: CreateServiceKeywordInput) {
  const { error } = await supabase.from("service_keywords").insert({
    clinic_id: input.clinicId,
    category_id: input.categoryId,
    keyword: input.keyword,
    language: input.language,
    match_type: input.matchType,
    is_active: true,
  });

  if (error) {
    throw new Error(error.message);
  }
}

export async function disableServiceKeyword(keywordId: string) {
  const { error } = await supabase
    .from("service_keywords")
    .update({
      is_active: false,
    })
    .eq("id", keywordId);

  if (error) {
    throw new Error(error.message);
  }
}

export type UpdateServiceCategoryInput = {
  id: string;
  name: string;
  canonicalReason: string;
  defaultUrgency: string;
  createsAppointmentRequest: boolean;
  isActive: boolean;
  defaultDurationMinutes: number;
  description: string | null;
};

export type UpdateServiceKeywordInput = {
  id: string;
  keyword: string;
  language: string;
  matchType: string;
  isActive: boolean;
};

export async function updateServiceCategory(input: UpdateServiceCategoryInput) {
  const { error } = await supabase
    .from("service_categories")
    .update({
      name: input.name,
      canonical_reason: input.canonicalReason,
      default_urgency: input.defaultUrgency,
      creates_appointment_request: input.createsAppointmentRequest,
      is_active: input.isActive,
      default_duration_minutes: input.defaultDurationMinutes,
      description: input.description,
      updated_at: new Date().toISOString(),
    })
    .eq("id", input.id);

  if (error) {
    throw new Error(error.message);
  }
}

export async function updateServiceKeyword(input: UpdateServiceKeywordInput) {
  const { error } = await supabase
    .from("service_keywords")
    .update({
      keyword: input.keyword,
      language: input.language,
      match_type: input.matchType,
      is_active: input.isActive,
    })
    .eq("id", input.id);

  if (error) {
    throw new Error(error.message);
  }
}

export async function deleteServiceKeyword(keywordId: string) {
  const { error } = await supabase
    .from("service_keywords")
    .delete()
    .eq("id", keywordId);

  if (error) {
    throw new Error(error.message);
  }
}

export async function deleteServiceCategoryWithKeywords(categoryId: string) {
  const { error: keywordsError } = await supabase
    .from("service_keywords")
    .delete()
    .eq("category_id", categoryId);

  if (keywordsError) {
    throw new Error(keywordsError.message);
  }

  const { error: categoryError } = await supabase
    .from("service_categories")
    .delete()
    .eq("id", categoryId);

  if (categoryError) {
    throw new Error(categoryError.message);
  }
}

export type ClinicDoctor = {
  id: string;
  clinic_id: string;
  full_name: string;
  display_name: string | null;
  title: string | null;
  specialty: string | null;
  phone_number: string | null;
  email: string | null;
  is_active: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type ClinicDoctorService = {
  id: string;
  clinic_id: string;
  doctor_id: string;
  service_category_id: string;
  is_active: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type CreateClinicDoctorInput = {
  clinicId: string;
  fullName: string;
  displayName: string | null;
  title: string | null;
  specialty: string | null;
  phoneNumber: string | null;
  email: string | null;
  isActive: boolean;
  notes: string | null;
};

export type UpdateClinicDoctorInput = CreateClinicDoctorInput & {
  id: string;
};

export type CreateClinicDoctorServiceInput = {
  clinicId: string;
  doctorId: string;
  serviceCategoryId: string;
  notes: string | null;
};

export type UpdateClinicDoctorServiceInput = {
  id: string;
  isActive: boolean;
  notes: string | null;
};

export async function getClinicDoctors(clinicId: string) {
  const { data, error } = await supabase
    .from("clinic_doctors")
    .select(
      "id, clinic_id, full_name, display_name, title, specialty, phone_number, email, is_active, notes, created_at, updated_at"
    )
    .eq("clinic_id", clinicId)
    .order("created_at", { ascending: false });

  if (error) throw new Error(error.message);

  return data || [];
}

export async function createClinicDoctor(input: CreateClinicDoctorInput) {
  const now = new Date().toISOString();

  const { data, error } = await supabase
    .from("clinic_doctors")
    .insert({
      clinic_id: input.clinicId,
      full_name: input.fullName,
      display_name: input.displayName,
      title: input.title,
      specialty: input.specialty,
      phone_number: input.phoneNumber,
      email: input.email,
      is_active: input.isActive,
      notes: input.notes,
      created_at: now,
      updated_at: now,
    })
    .select("id")
    .single();

  if (error) throw new Error(error.message);

  return data.id as string;
}

export async function updateClinicDoctor(input: UpdateClinicDoctorInput) {
  const { error } = await supabase
    .from("clinic_doctors")
    .update({
      clinic_id: input.clinicId,
      full_name: input.fullName,
      display_name: input.displayName,
      title: input.title,
      specialty: input.specialty,
      phone_number: input.phoneNumber,
      email: input.email,
      is_active: input.isActive,
      notes: input.notes,
      updated_at: new Date().toISOString(),
    })
    .eq("id", input.id);

  if (error) throw new Error(error.message);
}

export async function deleteClinicDoctorWithServices(doctorId: string) {
  const { error: servicesError } = await supabase
    .from("clinic_doctor_services")
    .delete()
    .eq("doctor_id", doctorId);

  if (servicesError) throw new Error(servicesError.message);

  const { error: doctorError } = await supabase
    .from("clinic_doctors")
    .delete()
    .eq("id", doctorId);

  if (doctorError) throw new Error(doctorError.message);
}

export async function getClinicDoctorServices(doctorId: string) {
  const { data, error } = await supabase
    .from("clinic_doctor_services")
    .select(
      "id, clinic_id, doctor_id, service_category_id, is_active, notes, created_at, updated_at"
    )
    .eq("doctor_id", doctorId)
    .order("created_at", { ascending: false });

  if (error) throw new Error(error.message);

  return data || [];
}

export async function createClinicDoctorService(
  input: CreateClinicDoctorServiceInput
) {
  const now = new Date().toISOString();

  const { error } = await supabase.from("clinic_doctor_services").insert({
    clinic_id: input.clinicId,
    doctor_id: input.doctorId,
    service_category_id: input.serviceCategoryId,
    is_active: true,
    notes: input.notes,
    created_at: now,
    updated_at: now,
  });

  if (error) throw new Error(error.message);
}

export async function updateClinicDoctorService(
  input: UpdateClinicDoctorServiceInput
) {
  const { error } = await supabase
    .from("clinic_doctor_services")
    .update({
      is_active: input.isActive,
      notes: input.notes,
      updated_at: new Date().toISOString(),
    })
    .eq("id", input.id);

  if (error) throw new Error(error.message);
}

export async function deleteClinicDoctorService(doctorServiceId: string) {
  const { error } = await supabase
    .from("clinic_doctor_services")
    .delete()
    .eq("id", doctorServiceId);

  if (error) throw new Error(error.message);
}
export async function setClinicDoctorServiceActive({
  clinicId,
  doctorId,
  serviceCategoryId,
  enabled,
}: {
  clinicId: string;
  doctorId: string;
  serviceCategoryId: string;
  enabled: boolean;
}) {
  if (enabled) {
    const { data: existing, error: findError } = await supabase
      .from("clinic_doctor_services")
      .select("id")
      .eq("doctor_id", doctorId)
      .eq("service_category_id", serviceCategoryId)
      .maybeSingle();

    if (findError) throw new Error(findError.message);

    if (existing?.id) {
      const { error } = await supabase
        .from("clinic_doctor_services")
        .update({
          is_active: true,
          updated_at: new Date().toISOString(),
        })
        .eq("id", existing.id);

      if (error) throw new Error(error.message);
      return;
    }

    const now = new Date().toISOString();

    const { error } = await supabase.from("clinic_doctor_services").insert({
      clinic_id: clinicId,
      doctor_id: doctorId,
      service_category_id: serviceCategoryId,
      is_active: true,
      notes: null,
      created_at: now,
      updated_at: now,
    });

    if (error) throw new Error(error.message);
    return;
  }

  const { error } = await supabase
    .from("clinic_doctor_services")
    .delete()
    .eq("doctor_id", doctorId)
    .eq("service_category_id", serviceCategoryId);

  if (error) throw new Error(error.message);
}

export type CalendarAvailabilityRule = {
  id: string;
  clinic_id: string;
  doctor_id: string | null;
  start_date: string;
  end_date: string | null;
  day_of_week: number | null;
  start_time: string;
  end_time: string;
  timezone: string;
  repeat_type: "none" | "daily" | "weekly" | "weekdays" | "custom";
  is_active: boolean;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type CalendarAvailabilityException = {
  id: string;
  clinic_id: string;
  rule_id: string;
  exception_date: string;
  exception_type: "cancelled" | "modified";
  start_time: string | null;
  end_time: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type CreateCalendarAvailabilityRuleInput = {
  clinicId: string;
  doctorId: string | null;
  startDate: string;
  endDate: string | null;
  dayOfWeek: number | null;
  startTime: string;
  endTime: string;
  timezone: string;
  repeatType: "none" | "daily" | "weekly" | "weekdays" | "custom";
  isActive: boolean;
  notes: string | null;
};




export async function getCalendarAvailabilityRules({
  clinicId,
  doctorId,
  monthStart,
  monthEnd,
}: {
  clinicId: string;
  doctorId?: string | null;
  monthStart: string;
  monthEnd: string;
}) {
  let query = supabase
    .from("calendar_availability_rules")
    .select(
      "id, clinic_id, doctor_id, start_date, end_date, day_of_week, start_time, end_time, timezone, repeat_type, is_active, notes, created_at, updated_at"
    )
    .eq("clinic_id", clinicId)
    .eq("is_active", true)
    .lte("start_date", monthEnd)
    .or(`end_date.is.null,end_date.gte.${monthStart}`)
    .order("start_date", { ascending: true });

  if (doctorId !== undefined) {
    if (doctorId === null) {
      query = query.is("doctor_id", null);
    } else {
      query = query.eq("doctor_id", doctorId);
    }
  }

  const { data, error } = await query;

  if (error) throw new Error(error.message);

  return data || [];
}

export async function getCalendarAvailabilityExceptions({
  clinicId,
  ruleIds,
  monthStart,
  monthEnd,
}: {
  clinicId: string;
  ruleIds: string[];
  monthStart: string;
  monthEnd: string;
}) {
  if (ruleIds.length === 0) return [];

  const { data, error } = await supabase
    .from("calendar_availability_exceptions")
    .select(
      "id, clinic_id, rule_id, exception_date, exception_type, start_time, end_time, notes, created_at, updated_at"
    )
    .eq("clinic_id", clinicId)
    .in("rule_id", ruleIds)
    .gte("exception_date", monthStart)
    .lte("exception_date", monthEnd)
    .order("exception_date", { ascending: true });

  if (error) throw new Error(error.message);

  return data || [];
}

export async function createCalendarAvailabilityRule(
  input: CreateCalendarAvailabilityRuleInput
) {
  const { data, error } = await supabase
    .from("calendar_availability_rules")
    .insert({
      clinic_id: input.clinicId,
      doctor_id: input.doctorId,
      start_date: input.startDate,
      end_date: input.endDate,
      day_of_week: input.dayOfWeek,
      start_time: input.startTime,
      end_time: input.endTime,
      timezone: input.timezone,
      repeat_type: input.repeatType,
      is_active: input.isActive,
      notes: input.notes,
    })
    .select("id")
    .single();

  if (error) throw new Error(error.message);

  return data.id as string;
}





function addDaysToDateString(dateString: string, days: number) {
  const date = new Date(`${dateString}T00:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

export async function updateCalendarAvailabilityOnlyThisDay(input: {
  clinicId: string;
  ruleId: string;
  exceptionDate: string;
  startTime: string;
  endTime: string;
  notes: string | null;
}) {
  const { error } = await supabase
    .from("calendar_availability_exceptions")
    .upsert(
      {
        clinic_id: input.clinicId,
        rule_id: input.ruleId,
        exception_date: input.exceptionDate,
        exception_type: "modified",
        start_time: input.startTime,
        end_time: input.endTime,
        notes: input.notes,
        updated_at: new Date().toISOString(),
      },
      {
        onConflict: "rule_id,exception_date",
      }
    );

  if (error) throw new Error(error.message);
}

export async function cancelCalendarAvailabilityOnlyThisDay(input: {
  clinicId: string;
  ruleId: string;
  exceptionDate: string;
  notes: string | null;
}) {
  const { error } = await supabase
    .from("calendar_availability_exceptions")
    .upsert(
      {
        clinic_id: input.clinicId,
        rule_id: input.ruleId,
        exception_date: input.exceptionDate,
        exception_type: "cancelled",
        start_time: null,
        end_time: null,
        notes: input.notes,
        updated_at: new Date().toISOString(),
      },
      {
        onConflict: "rule_id,exception_date",
      }
    );

  if (error) throw new Error(error.message);
}

export async function updateCalendarAvailabilityThisAndFuture(input: {
  clinicId: string;
  originalRule: CalendarAvailabilityRule;
  clickedDate: string;
  newEndDate: string | null;
  startTime: string;
  endTime: string;
  timezone: string;
  notes: string | null;
}) {
  const safeNewEndDate =
    input.newEndDate && input.newEndDate >= input.clickedDate
      ? input.newEndDate
      : null;

  // اگر روی اولین روز rule کلیک شده باشد، چیزی قبل از آن وجود ندارد.
  // پس split نمی‌کنیم؛ همان rule اصلی را update می‌کنیم.
  if (input.originalRule.start_date >= input.clickedDate) {
    const { error: updateRuleError } = await supabase
      .from("calendar_availability_rules")
      .update({
        start_date: input.clickedDate,
        end_date: safeNewEndDate,
        start_time: input.startTime,
        end_time: input.endTime,
        timezone: input.timezone,
        notes: input.notes,
        updated_at: new Date().toISOString(),
      })
      .eq("id", input.originalRule.id);

    if (updateRuleError) throw new Error(updateRuleError.message);

    const { error: deleteFutureExceptionsError } = await supabase
      .from("calendar_availability_exceptions")
      .delete()
      .eq("rule_id", input.originalRule.id)
      .gte("exception_date", input.clickedDate);

    if (deleteFutureExceptionsError) {
      throw new Error(deleteFutureExceptionsError.message);
    }

    return;
  }

  // اگر وسط rule کلیک شده باشد، rule قبلی تا روز قبل کوتاه می‌شود.
  const previousDay = addDaysToDateString(input.clickedDate, -1);

  const { error: updateOldRuleError } = await supabase
    .from("calendar_availability_rules")
    .update({
      end_date: previousDay,
      updated_at: new Date().toISOString(),
    })
    .eq("id", input.originalRule.id);

  if (updateOldRuleError) throw new Error(updateOldRuleError.message);

  // rule جدید از تاریخ کلیک‌شده شروع می‌شود.
  const { error: insertNewRuleError } = await supabase
    .from("calendar_availability_rules")
    .insert({
      clinic_id: input.clinicId,
      doctor_id: input.originalRule.doctor_id,
      start_date: input.clickedDate,
      end_date: safeNewEndDate,
      day_of_week: input.originalRule.day_of_week,
      start_time: input.startTime,
      end_time: input.endTime,
      timezone: input.timezone,
      repeat_type: input.originalRule.repeat_type,
      is_active: true,
      notes: input.notes,
    });

  if (insertNewRuleError) throw new Error(insertNewRuleError.message);

  const { error: deleteFutureExceptionsError } = await supabase
    .from("calendar_availability_exceptions")
    .delete()
    .eq("rule_id", input.originalRule.id)
    .gte("exception_date", input.clickedDate);

  if (deleteFutureExceptionsError) {
    throw new Error(deleteFutureExceptionsError.message);
  }
}

export async function cancelCalendarAvailabilityThisAndFuture(input: {
  originalRuleId: string;
  clickedDate: string;
}) {
  const { data: originalRule, error: findRuleError } = await supabase
    .from("calendar_availability_rules")
    .select("id, start_date")
    .eq("id", input.originalRuleId)
    .single();

  if (findRuleError) throw new Error(findRuleError.message);

  // اگر روی اولین روز rule کلیک شده باشد،
  // دیگر قسمت قبلی وجود ندارد که نگه داریم، پس کل rule حذف می‌شود.
  if (originalRule.start_date >= input.clickedDate) {
    const { error: deleteRuleError } = await supabase
      .from("calendar_availability_rules")
      .delete()
      .eq("id", input.originalRuleId);

    if (deleteRuleError) throw new Error(deleteRuleError.message);

    return;
  }

  // اگر روی وسط rule کلیک شده باشد،
  // فقط rule قبلی را تا روز قبل کوتاه می‌کنیم.
  const previousDay = addDaysToDateString(input.clickedDate, -1);

  const { error: updateOldRuleError } = await supabase
    .from("calendar_availability_rules")
    .update({
      end_date: previousDay,
      updated_at: new Date().toISOString(),
    })
    .eq("id", input.originalRuleId);

  if (updateOldRuleError) throw new Error(updateOldRuleError.message);

  const { error: deleteFutureExceptionsError } = await supabase
    .from("calendar_availability_exceptions")
    .delete()
    .eq("rule_id", input.originalRuleId)
    .gte("exception_date", input.clickedDate);

  if (deleteFutureExceptionsError) {
    throw new Error(deleteFutureExceptionsError.message);
  }
}

export type Clinic = {
  id: string;
  name: string;
  phone_number: string | null;
  timezone: string | null;
  address: string | null;
  created_at: string | null;
  owner_user_id: string | null;
  admin_full_name: string | null;
  admin_email: string | null;
  twilio_phone_number: string | null;
};

export type CreateClinicInput = {
  ownerUserId: string;
  clinicName: string;
  adminFullName: string;
  adminEmail: string;
  phoneNumber: string;
  timezone: string;
  address: string | null;
};

export async function createClinic(input: CreateClinicInput) {
  const { data, error } = await supabase
    .from("clinics")
    .insert({
      owner_user_id: input.ownerUserId,
      name: input.clinicName,
      admin_full_name: input.adminFullName,
      admin_email: input.adminEmail,
      phone_number: input.phoneNumber,
      timezone: input.timezone,
      address: input.address,
      twilio_phone_number: null,
    })
    .select(
      "id, name, phone_number, timezone, address, created_at, owner_user_id, admin_full_name, admin_email, twilio_phone_number"
    )
    .single();

  if (error) {
    throw new Error(error.message);
  }

  if (!data?.id) {
    throw new Error("Clinic was created, but no clinic id was returned.");
  }

  return data as Clinic;
}

export async function getClinicByOwnerUserId(ownerUserId: string) {
  const { data, error } = await supabase
    .from("clinics")
    .select(
      "id, name, phone_number, timezone, address, created_at, owner_user_id, admin_full_name, admin_email, twilio_phone_number"
    )
    .eq("owner_user_id", ownerUserId)
    .single();

  if (error) {
    throw new Error(error.message);
  }

  return data as Clinic;
}

export type CallExtraction = {
  id: string;
  clinic_id: string | null;
  call_id: string | null;
  patient_id: string | null;
  raw_transcript: string | null;
  cleaned_transcript: string | null;
  detected_language: string | null;
  patient_name: string | null;
  patient_phone: string | null;
  service_category: string | null;
  canonical_reason: string | null;
  preferred_time_raw: string | null;
  preferred_datetime: string | null;
  urgency: string | null;
  confidence: number | null;
  extraction_notes: string | null;
  created_at: string | null;
  preferred_date_raw: string | null;
  preferred_date_confirmed: boolean | null;
  preferred_time_confirmed: boolean | null;
  doctor_id: string | null;
  preferred_doctor_name: string | null;
  extraction_status: string | null;
  missing_fields: string[] | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  converted_to_request: boolean | null;
  appointment_request_id: string | null;
};

export type UpdateCallExtractionReviewInput = {
  id: string;
  clinicId: string;
  patientId: string | null;
  patientName: string | null;
  patientPhone: string | null;
  serviceCategory: string | null;
  canonicalReason: string | null;
  preferredDateRaw: string | null;
  preferredTimeRaw: string | null;
  preferredDatetime: string | null;
  urgency: string | null;
  doctorId: string | null;
  preferredDoctorName: string | null;
  preferredDateConfirmed: boolean;
  preferredTimeConfirmed: boolean;
  extractionStatus: string;
  missingFields: string[];
  extractionNotes: string | null;
  reviewedBy: string | null;
};

export async function getCallExtractions({
  clinicId,
  filter,
}: {
  clinicId: string;
  filter?: string | null;
}) {
  let query = supabase
    .from("call_extractions")
    .select(
      `
      id,
      clinic_id,
      call_id,
      patient_id,
      raw_transcript,
      cleaned_transcript,
      detected_language,
      patient_name,
      patient_phone,
      service_category,
      canonical_reason,
      preferred_time_raw,
      preferred_datetime,
      urgency,
      confidence,
      extraction_notes,
      created_at,
      preferred_date_raw,
      preferred_date_confirmed,
      preferred_time_confirmed,
      doctor_id,
      preferred_doctor_name,
      extraction_status,
      missing_fields,
      reviewed_by,
      reviewed_at,
      converted_to_request,
      appointment_request_id
    `
    )
    .eq("clinic_id", clinicId)
    .order("created_at", { ascending: false });

  if (filter === "incomplete") {
    query = query.or(
      "extraction_status.eq.incomplete,patient_name.is.null,canonical_reason.is.null,preferred_date_raw.is.null,preferred_time_raw.is.null"
    );
  }

  if (filter === "needs_review") {
    query = query.eq("extraction_status", "needs_review");
  }

  if (filter === "low_confidence") {
    query = query.lt("confidence", 0.6);
  }

  if (filter === "converted") {
    query = query.eq("converted_to_request", true);
  }

  const { data, error } = await query;

  if (error) {
    throw new Error(error.message);
  }

  return (data || []) as CallExtraction[];
}


export async function getCallExtractionById({
  id,
  clinicId,
}: {
  id: string;
  clinicId: string;
}) {
  const { data, error } = await supabase
    .from("call_extractions")
    .select(
      `
      id,
      clinic_id,
      call_id,
      patient_id,
      raw_transcript,
      cleaned_transcript,
      detected_language,
      patient_name,
      patient_phone,
      service_category,
      canonical_reason,
      preferred_time_raw,
      preferred_datetime,
      urgency,
      confidence,
      extraction_notes,
      created_at,
      preferred_date_raw,
      preferred_date_confirmed,
      preferred_time_confirmed,
      doctor_id,
      preferred_doctor_name,
      extraction_status,
      missing_fields,
      reviewed_by,
      reviewed_at,
      converted_to_request,
      appointment_request_id
    `
    )
    .eq("id", id)
    .eq("clinic_id", clinicId)
    .single();

  if (error) {
    throw new Error(error.message);
  }

  return data as CallExtraction;
}

export async function updateCallExtractionReview(
  input: UpdateCallExtractionReviewInput
) {
  const { error } = await supabase
    .from("call_extractions")
    .update({
      patient_id: input.patientId,
      patient_name: input.patientName,
      patient_phone: input.patientPhone,
      service_category: input.serviceCategory,
      canonical_reason: input.canonicalReason,
      preferred_date_raw: input.preferredDateRaw,
      preferred_time_raw: input.preferredTimeRaw,
      preferred_datetime: input.preferredDatetime,
      urgency: input.urgency,
      doctor_id: input.doctorId,
      preferred_doctor_name: input.preferredDoctorName,
      preferred_date_confirmed: input.preferredDateConfirmed,
      preferred_time_confirmed: input.preferredTimeConfirmed,
      extraction_status: input.extractionStatus,
      missing_fields: input.missingFields,
      extraction_notes: input.extractionNotes,
      reviewed_by: input.reviewedBy,
      reviewed_at: new Date().toISOString(),
    })
    .eq("id", input.id)
    .eq("clinic_id", input.clinicId);

  if (error) {
    throw new Error(error.message);
  }
}

export async function getIncompleteCallExtractionCount(clinicId: string) {
  const { count, error } = await supabase
    .from("call_extractions")
    .select("id", { count: "exact", head: true })
    .eq("clinic_id", clinicId)
    .or(
      "extraction_status.eq.incomplete,patient_name.is.null,canonical_reason.is.null,preferred_date_raw.is.null,preferred_time_raw.is.null"
    );

  if (error) {
    throw new Error(error.message);
  }

  return count || 0;
}

export type Appointment = {
  id: string;
  clinic_id: string;
  appointment_request_id: string | null;
  patient_id: string | null;
  doctor_id: string | null;
  service_category_id: string | null;
  service_name: string | null;
  reason: string | null;
  urgency: string | null;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  status: string;
  source: string;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type CreateAppointmentFromRequestInput = {
  clinicId: string;
  appointmentRequestId: string;
  patientId: string | null;
  doctorId: string;
  serviceCategoryId: string | null;
  serviceName: string | null;
  startTime: string;
  endTime: string;
  durationMinutes: number;
  notes: string | null;
  reason: string | null;
  urgency: string | null;
  patientName?: string | null;
  patientPhone?: string | null;
};

export async function getDoctorAppointmentsForRange({
  clinicId,
  doctorId,
  rangeStart,
  rangeEnd,
}: {
  clinicId: string;
  doctorId: string;
  rangeStart: string;
  rangeEnd: string;
}) {
  const { data, error } = await supabase
    .from("appointments")
    .select(
      `
      id,
      clinic_id,
      appointment_request_id,
      patient_id,
      doctor_id,
      service_category_id,
      service_name,
      start_time,
      end_time,
      duration_minutes,
      status,
      source,
      urgency,
      reason,
      notes,
      created_at,
      updated_at
    `
    )
    .eq("clinic_id", clinicId)
    .eq("doctor_id", doctorId)
    .in("status", ["confirmed"])
    .lt("start_time", rangeEnd)
    .gt("end_time", rangeStart)
    .order("start_time", { ascending: true });

  if (error) {
    throw new Error(error.message);
  }

  return (data || []) as Appointment[];
}

export async function createAppointmentFromRequest(
  input: CreateAppointmentFromRequestInput
) {
  const { data: appointment, error: appointmentError } = await supabase
    .from("appointments")
    .insert({
      clinic_id: input.clinicId,
      appointment_request_id: input.appointmentRequestId,
      patient_id: input.patientId,
      patient_name: input.patientName,
      patient_phone: input.patientPhone,
      doctor_id: input.doctorId,
      service_category_id: input.serviceCategoryId,
      service_name: input.serviceName,
      start_time: input.startTime,
      end_time: input.endTime,
      duration_minutes: input.durationMinutes,
      status: "confirmed",
      source: "ai_request",
      notes: input.notes,
      reason: input.reason,
      urgency: input.urgency,
    })
    .select("id")
    .single();

  if (appointmentError) {
    throw new Error(appointmentError.message);
  }

  const { error: requestError } = await supabase
    .from("appointment_requests")
    .update({
      status: "confirmed",
      confirmed_appointment_id: appointment.id,
    })
    .eq("id", input.appointmentRequestId)
    .eq("clinic_id", input.clinicId);

  if (requestError) {
    await supabase.from("appointments").delete().eq("id", appointment.id);
    throw new Error(requestError.message);
  }

  return appointment;
}

export type UpdateAppointmentInput = {
  clinicId: string;
  appointmentId: string;
  patientId: string | null;
  doctorId: string;
  serviceCategoryId: string;
  serviceName: string | null;
  reason: string | null;
  urgency: string | null;
  startTime: string;
  endTime: string;
  durationMinutes: number;
  notes: string | null;
};

export async function updateAppointment(input: UpdateAppointmentInput) {
  const { data, error } = await supabase
    .from("appointments")
    .update({
      patient_id: input.patientId,
      doctor_id: input.doctorId,
      service_category_id: input.serviceCategoryId,
      service_name: input.serviceName,
      reason: input.reason,
      urgency: input.urgency,
      start_time: input.startTime,
      end_time: input.endTime,
      duration_minutes: input.durationMinutes,
      notes: input.notes,
      updated_at: new Date().toISOString(),
    })
    .eq("id", input.appointmentId)
    .eq("clinic_id", input.clinicId)
    .select("id")
    .single();

  if (error) {
    throw new Error(error.message);
  }

  return data;
}

export type Patient = {
  id: string;
  clinic_id: string;
  full_name: string;
  phone_primary: string;
  phone_secondary: string | null;
  email: string | null;
  date_of_birth: string | null;
  address_line1: string | null;
  address_line2: string | null;
  city: string | null;
  province: string | null;
  postal_code: string | null;
  country: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type CreatePatientInput = {
  clinicId: string;
  fullName: string;
  phonePrimary: string;
  phoneSecondary: string | null;
  email: string | null;
  dateOfBirth: string | null;
  addressLine1: string | null;
  addressLine2: string | null;
  city: string | null;
  province: string | null;
  postalCode: string | null;
  country: string | null;
  notes: string | null;
};

export type UpdatePatientInput = CreatePatientInput & {
  id: string;
};

function normalizePatientPhone(phone: string | null) {
  if (!phone) return null;
  return phone.trim().replace(/\s+/g, "");
}

export async function getPatients(clinicId: string) {
  const { data, error } = await supabase
    .from("patients")
    .select(
      `
      id,
      clinic_id,
      full_name,
      phone_primary,
      phone_secondary,
      email,
      date_of_birth,
      address_line1,
      address_line2,
      city,
      province,
      postal_code,
      country,
      notes,
      created_at,
      updated_at
    `
    )
    .eq("clinic_id", clinicId)
    .order("created_at", { ascending: false });

  if (error) {
    throw new Error(error.message);
  }

  return (data || []) as Patient[];
}

export async function searchPatients({
  clinicId,
  query,
}: {
  clinicId: string;
  query: string;
}) {
  const cleanQuery = query.trim();

  if (!cleanQuery) {
    return getPatients(clinicId);
  }

  const safeQuery = cleanQuery.replace(/[%_]/g, "");

  const { data, error } = await supabase
    .from("patients")
    .select(
      `
      id,
      clinic_id,
      full_name,
      phone_primary,
      phone_secondary,
      email,
      date_of_birth,
      address_line1,
      address_line2,
      city,
      province,
      postal_code,
      country,
      notes,
      created_at,
      updated_at
    `
    )
    .eq("clinic_id", clinicId)
    .or(
      [
        `full_name.ilike.%${safeQuery}%`,
        `phone_primary.ilike.%${safeQuery}%`,
        `phone_secondary.ilike.%${safeQuery}%`,
        `email.ilike.%${safeQuery}%`,
        `postal_code.ilike.%${safeQuery}%`,
        `notes.ilike.%${safeQuery}%`,
      ].join(",")
    )
    .order("created_at", { ascending: false });

  if (error) {
    throw new Error(error.message);
  }

  return (data || []) as Patient[];
}

export async function createPatient(input: CreatePatientInput) {
  const { data, error } = await supabase
    .from("patients")
    .insert({
      clinic_id: input.clinicId,
      full_name: input.fullName.trim(),
      phone_primary: normalizePatientPhone(input.phonePrimary),
      phone_secondary: normalizePatientPhone(input.phoneSecondary),
      email: input.email?.trim() || null,
      date_of_birth: input.dateOfBirth || null,
      address_line1: input.addressLine1?.trim() || null,
      address_line2: input.addressLine2?.trim() || null,
      city: input.city?.trim() || null,
      province: input.province?.trim() || null,
      postal_code: input.postalCode?.trim() || null,
      country: input.country?.trim() || "Canada",
      notes: input.notes?.trim() || null,
    })
    .select("id")
    .single();

  if (error) {
    throw new Error(error.message);
  }

  return data.id as string;
}

export async function updatePatient(input: UpdatePatientInput) {
  const { error } = await supabase
    .from("patients")
    .update({
      full_name: input.fullName.trim(),
      phone_primary: normalizePatientPhone(input.phonePrimary),
      phone_secondary: normalizePatientPhone(input.phoneSecondary),
      email: input.email?.trim() || null,
      date_of_birth: input.dateOfBirth || null,
      address_line1: input.addressLine1?.trim() || null,
      address_line2: input.addressLine2?.trim() || null,
      city: input.city?.trim() || null,
      province: input.province?.trim() || null,
      postal_code: input.postalCode?.trim() || null,
      country: input.country?.trim() || "Canada",
      notes: input.notes?.trim() || null,
      updated_at: new Date().toISOString(),
    })
    .eq("id", input.id)
    .eq("clinic_id", input.clinicId);

  if (error) {
    if (error.message.includes("patients_clinic_phone_unique")) {
      throw new Error("A patient with this primary phone already exists.");
    }

    throw new Error(error.message);
  }
}

export async function deletePatient({
  id,
  clinicId,
}: {
  id: string;
  clinicId: string;
}) {
  const { error } = await supabase
    .from("patients")
    .delete()
    .eq("id", id)
    .eq("clinic_id", clinicId);

  if (error) {
    throw new Error(error.message);
  }
}

export async function getPatientByPhone({
  clinicId,
  phonePrimary,
}: {
  clinicId: string;
  phonePrimary: string;
}) {
  const phone = normalizePatientPhone(phonePrimary);

  if (!phone) return null;

  const { data, error } = await supabase
    .from("patients")
    .select(
      `
      id,
      clinic_id,
      full_name,
      phone_primary,
      phone_secondary,
      email,
      date_of_birth,
      address_line1,
      address_line2,
      city,
      province,
      postal_code,
      country,
      notes,
      created_at,
      updated_at
    `
    )
    .eq("clinic_id", clinicId)
    .eq("phone_primary", phone)
    .maybeSingle();

  if (error) {
    throw new Error(error.message);
  }

  return data as Patient | null;
}

export type ClinicFaqAudioStatus = "pending" | "generating" | "ready" | "failed";

export type ClinicFaq = {
  id: string;
  clinic_id: string;
  question: string;
  answer: string;
  category: string;
  keywords: string[];
  is_active: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;

  audio_url: string | null;
  audio_storage_path: string | null;
  audio_hash: string | null;
  audio_status: ClinicFaqAudioStatus;
  audio_error: string | null;
  audio_generated_at: string | null;
};

export type CreateClinicFaqInput = {
  clinicId: string;
  question: string;
  answer: string;
  category: string;
  keywords: string[];
  isActive: boolean;
  sortOrder: number;
};

export type UpdateClinicFaqInput = {
  id: string;
  clinicId: string;
  question: string;
  answer: string;
  category: string;
  keywords: string[];
  isActive: boolean;
  sortOrder: number;
};

const CLINIC_FAQ_SELECT = `
  id,
  clinic_id,
  question,
  answer,
  category,
  keywords,
  is_active,
  sort_order,
  created_at,
  updated_at,
  audio_url,
  audio_storage_path,
  audio_hash,
  audio_status,
  audio_error,
  audio_generated_at
`;

export async function getClinicFaqs(clinicId: string) {
  const { data, error } = await supabase
    .from("clinic_faqs")
    .select(CLINIC_FAQ_SELECT)
    .eq("clinic_id", clinicId)
    .order("sort_order", { ascending: true })
    .order("created_at", { ascending: false });

  if (error) {
    throw new Error(error.message);
  }

  return (data || []) as ClinicFaq[];
}

export async function getActiveClinicFaqs(clinicId: string) {
  const { data, error } = await supabase
    .from("clinic_faqs")
    .select(CLINIC_FAQ_SELECT)
    .eq("clinic_id", clinicId)
    .eq("is_active", true)
    .order("sort_order", { ascending: true })
    .order("created_at", { ascending: false });

  if (error) {
    throw new Error(error.message);
  }

  return (data || []) as ClinicFaq[];
}

export async function getClinicFaqsByCategory({
  clinicId,
  category,
}: {
  clinicId: string;
  category: string;
}) {
  const { data, error } = await supabase
    .from("clinic_faqs")
    .select(CLINIC_FAQ_SELECT)
    .eq("clinic_id", clinicId)
    .eq("category", category)
    .eq("is_active", true)
    .order("sort_order", { ascending: true })
    .order("created_at", { ascending: false });

  if (error) {
    throw new Error(error.message);
  }

  return (data || []) as ClinicFaq[];
}

export async function createClinicFaq(input: CreateClinicFaqInput) {
  const { data, error } = await supabase
    .from("clinic_faqs")
    .insert({
      clinic_id: input.clinicId,
      question: input.question.trim(),
      answer: input.answer.trim(),
      category: input.category.trim() || "general",
      keywords: input.keywords || [],
      is_active: input.isActive,
      sort_order: input.sortOrder,
      audio_status: "pending",
      audio_error: null,
    })
    .select("id")
    .single();

  if (error) {
    throw new Error(error.message);
  }

  if (!data?.id) {
    throw new Error("FAQ was created, but no id was returned.");
  }

  return data.id as string;
}

export async function updateClinicFaq(input: UpdateClinicFaqInput) {
  const { error } = await supabase
    .from("clinic_faqs")
    .update({
      question: input.question.trim(),
      answer: input.answer.trim(),
      category: input.category.trim() || "general",
      keywords: input.keywords || [],
      is_active: input.isActive,
      sort_order: input.sortOrder,
      updated_at: new Date().toISOString(),
      audio_status: "pending",
      audio_error: null,
    })
    .eq("id", input.id)
    .eq("clinic_id", input.clinicId);

  if (error) {
    throw new Error(error.message);
  }
}

export async function deleteClinicFaq({
  id,
  clinicId,
}: {
  id: string;
  clinicId: string;
}) {
  const { error } = await supabase
    .from("clinic_faqs")
    .delete()
    .eq("id", id)
    .eq("clinic_id", clinicId);

  if (error) {
    throw new Error(error.message);
  }
}

export async function setClinicFaqActive({
  id,
  clinicId,
  isActive,
}: {
  id: string;
  clinicId: string;
  isActive: boolean;
}) {
  const { error } = await supabase
    .from("clinic_faqs")
    .update({
      is_active: isActive,
      updated_at: new Date().toISOString(),
    })
    .eq("id", id)
    .eq("clinic_id", clinicId);

  if (error) {
    throw new Error(error.message);
  }
}

function cleanFaqSearchQuery(query: string) {
  return query.trim().replace(/[%_]/g, "");
}

export async function searchClinicFaqs({
  clinicId,
  query,
}: {
  clinicId: string;
  query: string;
}) {
  const cleanQuery = cleanFaqSearchQuery(query);

  if (!cleanQuery) {
    return getActiveClinicFaqs(clinicId);
  }

  const { data, error } = await supabase
    .from("clinic_faqs")
    .select(CLINIC_FAQ_SELECT)
    .eq("clinic_id", clinicId)
    .eq("is_active", true)
    .or(
      [
        `question.ilike.%${cleanQuery}%`,
        `answer.ilike.%${cleanQuery}%`,
        `category.ilike.%${cleanQuery}%`,
      ].join(",")
    )
    .order("sort_order", { ascending: true })
    .limit(20);

  if (error) {
    throw new Error(error.message);
  }

  return (data || []) as ClinicFaq[];
}

export async function findBestClinicFaqAnswer({
  clinicId,
  question,
}: {
  clinicId: string;
  question: string;
}) {
  const cleanQuestion = cleanFaqSearchQuery(question).toLowerCase();

  if (!cleanQuestion) {
    return null;
  }

  const faqs = await getActiveClinicFaqs(clinicId);

  const exactQuestionMatch = faqs.find(
    (faq) => faq.question.toLowerCase() === cleanQuestion
  );

  if (exactQuestionMatch) {
    return exactQuestionMatch;
  }

  const keywordMatch = faqs.find((faq) => {
    if (!Array.isArray(faq.keywords)) return false;

    return faq.keywords.some((keyword) => {
      const cleanKeyword = keyword.trim().toLowerCase();
      if (!cleanKeyword) return false;

      return cleanQuestion.includes(cleanKeyword);
    });
  });

  if (keywordMatch) {
    return keywordMatch;
  }

  const textMatch = faqs.find((faq) => {
    const searchableText = [
      faq.question,
      faq.answer,
      faq.category,
      ...(faq.keywords || []),
    ]
      .join(" ")
      .toLowerCase();

    return cleanQuestion
      .split(/\s+/)
      .filter(Boolean)
      .some((word) => searchableText.includes(word));
  });

  return textMatch || null;
}
const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL;

export async function regenerateClinicFaqAudio({
  faqId,
  clinicId,
}: {
  faqId: string;
  clinicId: string;
}) {
  if (!API_BASE_URL) {
    throw new Error("NEXT_PUBLIC_API_BASE_URL is not set.");
  }

  const response = await fetch(
    `${API_BASE_URL}/admin/faqs/${faqId}/regenerate-audio`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        clinic_id: clinicId,
      }),
    }
  );

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Could not regenerate FAQ audio.");
  }

  return response.json();
}