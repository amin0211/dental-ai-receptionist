"use client";

import { useEffect, useMemo, useState } from "react";
import DashboardShell from "@/components/layout/DashboardShell";
import { useClinic } from "@/components/providers/ClinicProvider";
import {
  ClinicFaq,
  createClinicFaq,
  deleteClinicFaq,
  getClinicFaqs,
  regenerateClinicFaqAudio,
  setClinicFaqActive,
  updateClinicFaq,
} from "@/lib/supabaseService";

const FAQ_CATEGORIES = [
  "general",
  "insurance",
  "location",
  "children",
  "emergency",
  "services",
  "billing",
  "appointments",
  "policy",
];

const DEFAULT_FORM = {
  question: "",
  answer: "",
  category: "general",
  keywordsText: "",
  isActive: true,
  sortOrder: 0,
};

type FaqFormState = typeof DEFAULT_FORM;

function keywordsToText(keywords: string[] | null | undefined) {
  return (keywords || []).join(", ");
}

function textToKeywords(text: string) {
  return text
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function getAudioStatusLabel(faq: ClinicFaq) {
  if (faq.audio_status === "ready") return "Audio ready";
  if (faq.audio_status === "generating") return "Generating audio";
  if (faq.audio_status === "failed") return "Audio failed";
  return "Audio pending";
}

function getAudioStatusClass(faq: ClinicFaq) {
  if (faq.audio_status === "ready") return "bg-blue-50 text-blue-700";
  if (faq.audio_status === "generating") return "bg-amber-50 text-amber-700";
  if (faq.audio_status === "failed") return "bg-red-50 text-red-700";
  return "bg-slate-100 text-slate-500";
}

export default function ClinicFaqsPage() {
  const { clinic } = useClinic();

  const [faqs, setFaqs] = useState<ClinicFaq[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [audioGeneratingId, setAudioGeneratingId] = useState<string | null>(
    null
  );

  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("all");

  const [form, setForm] = useState<FaqFormState>(DEFAULT_FORM);
  const [editingFaqId, setEditingFaqId] = useState<string | null>(null);

  const clinicId = clinic?.id ?? null;

  async function loadFaqs() {
    if (!clinicId) return;

    setLoading(true);

    try {
      const rows = await getClinicFaqs(clinicId);
      setFaqs(rows);
    } catch (error) {
      console.error(error);
      alert("Could not load FAQs.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (clinicId) {
      loadFaqs();
    } else {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clinicId]);

  const filteredFaqs = useMemo(() => {
    const cleanSearch = search.trim().toLowerCase();

    return faqs.filter((faq) => {
      const matchesCategory =
        categoryFilter === "all" || faq.category === categoryFilter;

      const searchableText = [
        faq.question,
        faq.answer,
        faq.category,
        ...(faq.keywords || []),
      ]
        .join(" ")
        .toLowerCase();

      const matchesSearch =
        !cleanSearch || searchableText.includes(cleanSearch);

      return matchesCategory && matchesSearch;
    });
  }, [faqs, search, categoryFilter]);

  function resetForm() {
    setForm(DEFAULT_FORM);
    setEditingFaqId(null);
  }

  function startEdit(faq: ClinicFaq) {
    setEditingFaqId(faq.id);
    setForm({
      question: faq.question,
      answer: faq.answer,
      category: faq.category || "general",
      keywordsText: keywordsToText(faq.keywords),
      isActive: faq.is_active,
      sortOrder: faq.sort_order,
    });

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function generateAudioInBackground(faqId: string) {
    if (!clinicId) return;

    setAudioGeneratingId(faqId);

    try {
      await regenerateClinicFaqAudio({
        faqId,
        clinicId,
      });

      await loadFaqs();
    } catch (error) {
      console.error(error);
      await loadFaqs();
    } finally {
      setAudioGeneratingId(null);
    }
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!clinicId) {
      alert("Clinic not found.");
      return;
    }

    if (!form.question.trim()) {
      alert("Question is required.");
      return;
    }

    if (!form.answer.trim()) {
      alert("Answer is required.");
      return;
    }

    setSaving(true);

    try {
      let savedFaqId: string;

      if (editingFaqId) {
        await updateClinicFaq({
          id: editingFaqId,
          clinicId,
          question: form.question,
          answer: form.answer,
          category: form.category,
          keywords: textToKeywords(form.keywordsText),
          isActive: form.isActive,
          sortOrder: Number(form.sortOrder) || 0,
        });

        savedFaqId = editingFaqId;
      } else {
        savedFaqId = await createClinicFaq({
          clinicId,
          question: form.question,
          answer: form.answer,
          category: form.category,
          keywords: textToKeywords(form.keywordsText),
          isActive: form.isActive,
          sortOrder: Number(form.sortOrder) || 0,
        });
      }

      resetForm();
      await loadFaqs();

      void generateAudioInBackground(savedFaqId);
    } catch (error) {
      console.error(error);
      alert("Could not save FAQ.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(faq: ClinicFaq) {
    if (!clinicId) return;

    const confirmed = window.confirm(`Delete this FAQ?\n\n${faq.question}`);

    if (!confirmed) return;

    try {
      await deleteClinicFaq({
        id: faq.id,
        clinicId,
      });

      if (editingFaqId === faq.id) {
        resetForm();
      }

      await loadFaqs();
    } catch (error) {
      console.error(error);
      alert("Could not delete FAQ.");
    }
  }

  async function handleToggleActive(faq: ClinicFaq) {
    if (!clinicId) return;

    try {
      await setClinicFaqActive({
        id: faq.id,
        clinicId,
        isActive: !faq.is_active,
      });

      await loadFaqs();
    } catch (error) {
      console.error(error);
      alert("Could not update FAQ status.");
    }
  }

  async function handleRegenerateAudio(faq: ClinicFaq) {
    if (!clinicId) return;

    void generateAudioInBackground(faq.id);
  }

  if (loading) {
    return (
      <DashboardShell title="Clinic FAQs">
        <div className="p-6">
          <p className="text-sm text-slate-500">Loading FAQs...</p>
        </div>
      </DashboardShell>
    );
  }

  if (!clinicId) {
    return (
      <DashboardShell title="Clinic FAQs">
        <div className="p-6">
          <h1 className="text-xl font-semibold text-slate-900">
            Clinic FAQs
          </h1>
          <p className="mt-2 text-sm text-slate-500">
            No clinic found for this account.
          </p>
        </div>
      </DashboardShell>
    );
  }

  return (
    <DashboardShell title="Clinic FAQs">
      <div className="space-y-6 p-6">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">
              Clinic FAQs
            </h1>
            <p className="mt-1 text-sm text-slate-500">
              Manage answers that the AI receptionist can use for common clinic
              questions.
            </p>
          </div>

          <div className="rounded-full bg-slate-100 px-4 py-2 text-sm text-slate-600">
            {faqs.length} FAQs
          </div>
        </div>

        <div className="grid min-w-0 gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
          <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4">
              <h2 className="text-lg font-semibold text-slate-900">
                {editingFaqId ? "Edit FAQ" : "Add FAQ"}
              </h2>
              <p className="mt-1 text-sm text-slate-500">
                Add the exact answer you want the AI to say.
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  Question
                </label>
                <input
                  value={form.question}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      question: event.target.value,
                    }))
                  }
                  placeholder="Do you accept insurance?"
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                />
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  Answer
                </label>
                <textarea
                  value={form.answer}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      answer: event.target.value,
                    }))
                  }
                  placeholder="Yes, we accept many major dental insurance plans..."
                  rows={6}
                  className="w-full resize-none rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    Category
                  </label>
                  <select
                    value={form.category}
                    onChange={(event) =>
                      setForm((prev) => ({
                        ...prev,
                        category: event.target.value,
                      }))
                    }
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                  >
                    {FAQ_CATEGORIES.map((category) => (
                      <option key={category} value={category}>
                        {category}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700">
                    Sort order
                  </label>
                  <input
                    type="number"
                    value={form.sortOrder}
                    onChange={(event) =>
                      setForm((prev) => ({
                        ...prev,
                        sortOrder: Number(event.target.value),
                      }))
                    }
                    className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                  />
                </div>
              </div>

              <div>
                <label className="mb-1 block text-sm font-medium text-slate-700">
                  Keywords
                </label>
                <input
                  value={form.keywordsText}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      keywordsText: event.target.value,
                    }))
                  }
                  placeholder="insurance, coverage, بیمه, direct billing"
                  className="w-full rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                />
                <p className="mt-1 text-xs text-slate-500">
                  Separate keywords with commas. These help the AI match caller
                  questions.
                </p>
              </div>

              <label className="flex items-center gap-2 text-sm text-slate-700">
                <input
                  type="checkbox"
                  checked={form.isActive}
                  onChange={(event) =>
                    setForm((prev) => ({
                      ...prev,
                      isActive: event.target.checked,
                    }))
                  }
                  className="h-4 w-4 rounded border-slate-300"
                />
                Active
              </label>

              <div className="flex gap-3 pt-2">
                <button
                  type="submit"
                  disabled={saving}
                  className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {saving
                    ? "Saving..."
                    : editingFaqId
                      ? "Update FAQ"
                      : "Create FAQ"}
                </button>

                {editingFaqId && (
                  <button
                    type="button"
                    onClick={resetForm}
                    className="rounded-xl border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700"
                  >
                    Cancel
                  </button>
                )}
              </div>
            </form>
          </section>

          <section className="min-w-0 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="mb-4 flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">
                  FAQ List
                </h2>
                <p className="mt-1 text-sm text-slate-500">
                  These answers are available to the AI receptionist.
                </p>
              </div>

              <div className="flex flex-col gap-2 sm:flex-row">
                <input
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                  placeholder="Search..."
                  className="w-40 rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900 md:w-56"
                />

                <select
                  value={categoryFilter}
                  onChange={(event) => setCategoryFilter(event.target.value)}
                  className="rounded-xl border border-slate-300 px-3 py-2 text-sm outline-none focus:border-slate-900"
                >
                  <option value="all">All</option>
                  {FAQ_CATEGORIES.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {filteredFaqs.length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center">
                <p className="text-sm font-medium text-slate-700">
                  No FAQs found.
                </p>
                <p className="mt-1 text-sm text-slate-500">
                  Add your first FAQ from the form.
                </p>
              </div>
            ) : (
              <div className="space-y-3">
                {filteredFaqs.map((faq) => {
                  const isGeneratingThisAudio = audioGeneratingId === faq.id;

                  return (
                    <article
                      key={faq.id}
                      className="rounded-2xl border border-slate-200 p-4"
                    >
                      <div className="flex min-w-0 flex-col gap-4">
                        <div className="min-w-0">
                          <div className="mb-2 flex flex-wrap items-center gap-2">
                            <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
                              {faq.category}
                            </span>

                            <span
                              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                                faq.is_active
                                  ? "bg-emerald-50 text-emerald-700"
                                  : "bg-slate-100 text-slate-500"
                              }`}
                            >
                              {faq.is_active ? "Active" : "Inactive"}
                            </span>

                            <span
                              className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                                isGeneratingThisAudio
                                  ? "bg-amber-50 text-amber-700"
                                  : getAudioStatusClass(faq)
                              }`}
                            >
                              {isGeneratingThisAudio
                                ? "Generating audio"
                                : getAudioStatusLabel(faq)}
                            </span>

                            <span className="text-xs text-slate-400">
                              Order: {faq.sort_order}
                            </span>
                          </div>

                          <h3 className="max-w-full break-words text-sm font-semibold leading-6 text-slate-900">
                            {faq.question}
                          </h3>

                          <p className="mt-2 max-w-full whitespace-pre-wrap break-words text-sm leading-6 text-slate-600">
                            {faq.answer}
                          </p>

                          {faq.audio_url && faq.audio_status === "ready" && (
                            <div className="mt-3">
                              <audio
                                controls
                                src={faq.audio_url}
                                className="w-full"
                              />
                            </div>
                          )}

                          {faq.audio_status === "failed" && faq.audio_error && (
                            <p className="mt-2 text-xs text-red-600">
                              {faq.audio_error}
                            </p>
                          )}

                          {faq.keywords?.length > 0 && (
                            <div className="mt-3 flex flex-wrap gap-1.5">
                              {faq.keywords.map((keyword) => (
                                <span
                                  key={keyword}
                                  className="rounded-full bg-slate-50 px-2 py-1 text-xs text-slate-500"
                                >
                                  {keyword}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>

                        <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3">
                          <button
                            type="button"
                            onClick={() => handleToggleActive(faq)}
                            className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700"
                          >
                            {faq.is_active ? "Disable" : "Enable"}
                          </button>

                          <button
                            type="button"
                            onClick={() => handleRegenerateAudio(faq)}
                            disabled={audioGeneratingId === faq.id}
                            className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {audioGeneratingId === faq.id
                              ? "Generating..."
                              : "Regenerate audio"}
                          </button>

                          <button
                            type="button"
                            onClick={() => startEdit(faq)}
                            className="rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700"
                          >
                            Edit
                          </button>

                          <button
                            type="button"
                            onClick={() => handleDelete(faq)}
                            className="rounded-lg border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600"
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </section>
        </div>
      </div>
    </DashboardShell>
  );
}