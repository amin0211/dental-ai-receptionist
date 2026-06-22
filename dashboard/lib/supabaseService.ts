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