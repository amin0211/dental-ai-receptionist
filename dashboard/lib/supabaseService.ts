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

export async function getCurrentSession() {
  const { data, error } = await supabase.auth.getSession();

  if (error) {
    throw new Error(error.message);
  }

  return data.session;
}

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