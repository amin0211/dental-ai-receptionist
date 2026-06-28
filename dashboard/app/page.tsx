import Link from "next/link";

const coreFeatures = [
  "AI phone receptionist for dental clinics",
  "Appointment request capture",
  "Change and cancellation request logging",
  "Dental FAQ and clinic policy answers",
  "Urgent call flagging",
];

const clinicPainPoints = [
  {
    title: "Busy front desk",
    description:
      "When reception is handling in-person patients, files, phone calls, and scheduling at the same time, P-Core AI can help answer incoming calls and organize requests.",
  },
  {
    title: "After-hours calls",
    description:
      "When patients call outside business hours, the system can collect appointment requests, messages, cancellation requests, and common questions.",
  },
  {
    title: "Repeated questions",
    description:
      "Insurance, direct billing, CDCP, parking, new patients, children, payment methods, cancellation policy, and clinic services can be answered based on clinic information.",
  },
  {
    title: "Unclear follow-ups",
    description:
      "Incomplete calls, urgent symptoms, appointment requests, and cases that need staff review can be marked clearly for the reception team.",
  },
];

const dentalCapabilities = [
  "Initial patient call greeting",
  "Existing patient identification",
  "New patient information capture",
  "Reason-for-visit collection",
  "Appointment request management",
  "Change or cancellation request logging",
  "Common dental FAQ answers",
  "Urgent call detection",
  "Careful medical question handling",
  "Call summary storage",
  "Follow-up organization",
  "Clinic-specific customization",
];

const faqItems = [
  "Insurance and direct billing",
  "CDCP questions",
  "Parking information",
  "New patient intake",
  "Children and family appointments",
  "Cancellation policy",
  "Payment methods",
  "Checkups, cleanings, tooth pain, wisdom teeth, and file transfer questions",
];

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-950 text-white">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-white/10 bg-slate-950/85 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <Link href="/" className="flex items-center gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-cyan-400 text-lg font-black text-slate-950 shadow-lg shadow-cyan-400/20">
              P
            </div>

            <div>
              <p className="text-xl font-bold tracking-tight">P-Core AI</p>
              <p className="text-xs text-slate-400">
                AI receptionist for dental clinics
              </p>
            </div>
          </Link>

          <nav className="flex items-center gap-4 text-sm">
            <Link
              href="/dent"
              className="hidden text-slate-300 hover:text-white sm:inline"
            >
              Dental Solution
            </Link>

            <a
              href="mailto:PCoreAI.Dev@gmail.com"
              className="hidden text-slate-300 hover:text-white md:inline"
            >
              Contact
            </a>

            <Link
              href="/login"
              className="rounded-full border border-white/15 px-5 py-2 font-semibold text-white hover:bg-white/10"
            >
              Login
            </Link>
          </nav>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute left-1/2 top-0 h-[520px] w-[520px] -translate-x-1/2 rounded-full bg-cyan-400/10 blur-3xl" />
        <div className="absolute right-0 top-32 h-[420px] w-[420px] rounded-full bg-blue-500/10 blur-3xl" />

        <div className="relative mx-auto grid max-w-7xl gap-12 px-6 py-24 lg:grid-cols-2 lg:items-center">
          <div>
            <p className="mb-5 inline-flex rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm font-medium text-cyan-300">
              Dental AI Reception • Calls • Scheduling • Follow-up
            </p>

            <h1 className="max-w-4xl text-5xl font-black tracking-tight md:text-6xl">
              AI receptionist built specifically for dental clinics.
            </h1>

            <p className="mt-6 max-w-xl text-lg leading-8 text-slate-300">
              P-Core AI helps dental front desks answer patient calls, collect
              appointment requests, handle routine questions, and organize
              follow-ups without replacing the reception team.
            </p>

            <div className="mt-8 flex flex-wrap gap-4">
              <Link
                href="/dent"
                className="rounded-2xl bg-cyan-400 px-6 py-3 font-bold text-slate-950 shadow-lg shadow-cyan-400/20 hover:bg-cyan-300"
              >
                View Dental Solution
              </Link>

              <a
                href="mailto:PCoreAI.Dev@gmail.com"
                className="rounded-2xl border border-white/15 px-6 py-3 font-bold text-white hover:bg-white/10"
              >
                Contact Development Team
              </a>
            </div>

            <p className="mt-6 max-w-lg text-sm leading-6 text-slate-500">
              Designed for dental clinics that need faster call handling, more
              organized appointment requests, and cleaner front-desk follow-up.
            </p>
          </div>

          <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-2xl">
            <div className="rounded-3xl bg-slate-900 p-6">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-cyan-300">
                    P-Core Dental Reception System
                  </p>
                  <h2 className="mt-2 text-2xl font-bold">
                    One AI layer for dental calls and front-desk workflow.
                  </h2>
                </div>

                <div className="hidden rounded-2xl bg-cyan-400/10 px-4 py-2 text-sm font-semibold text-cyan-300 sm:block">
                  Dental-focused
                </div>
              </div>

              <div className="space-y-4">
                {coreFeatures.map((item) => (
                  <div
                    key={item}
                    className="flex items-center gap-3 rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-slate-200"
                  >
                    <span className="h-2 w-2 rounded-full bg-cyan-400" />
                    {item}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Positioning */}
      <section className="mx-auto max-w-7xl px-6 py-20">
        <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-start">
          <div>
            <p className="mb-4 inline-flex rounded-full border border-emerald-400/30 bg-emerald-400/10 px-4 py-2 text-sm font-medium text-emerald-300">
              Built for dental reception teams
            </p>

            <h2 className="text-4xl font-black tracking-tight md:text-5xl">
              Not a replacement for your receptionist. A support layer for your
              front desk.
            </h2>

            <p className="mt-5 text-lg leading-8 text-slate-300">
              P-Core AI is designed to work beside the dental reception team.
              It helps manage simple calls, repeated questions, appointment
              requests, cancellations, and cases that need follow-up, so staff
              can focus on patients who need human attention.
            </p>

            <div className="mt-8 flex flex-wrap gap-4">
              <Link
                href="/dent"
                className="rounded-2xl bg-white px-6 py-3 font-bold text-slate-950 hover:bg-slate-200"
              >
                Learn more
              </Link>

              <Link
                href="/login"
                className="rounded-2xl border border-white/15 px-6 py-3 font-bold text-white hover:bg-white/10"
              >
                Clinic dashboard
              </Link>
            </div>
          </div>

          <div className="grid gap-5 sm:grid-cols-2">
            {clinicPainPoints.map((feature) => (
              <div
                key={feature.title}
                className="rounded-3xl border border-white/10 bg-white/5 p-6"
              >
                <h3 className="text-lg font-bold">{feature.title}</h3>
                <p className="mt-3 text-sm leading-6 text-slate-300">
                  {feature.description}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Capabilities */}
      <section className="border-y border-white/10 bg-white/[0.03]">
        <div className="mx-auto max-w-7xl px-6 py-20">
          <div className="mb-10 max-w-3xl">
            <h2 className="text-3xl font-black tracking-tight md:text-4xl">
              Dental call capabilities
            </h2>

            <p className="mt-4 text-slate-300">
              P-Core AI can be configured around each dental clinic’s services,
              hours, cancellation policies, insurance information, appointment
              process, and follow-up workflow.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {dentalCapabilities.map((capability, index) => (
              <div
                key={capability}
                className="rounded-2xl border border-white/10 bg-slate-950/60 p-5"
              >
                <div className="mb-4 flex h-9 w-9 items-center justify-center rounded-xl bg-cyan-400/10 text-sm font-bold text-cyan-300">
                  {index + 1}
                </div>

                <p className="font-semibold text-slate-100">{capability}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* FAQ / Common Questions */}
      <section className="mx-auto max-w-7xl px-6 py-20">
        <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-start">
          <div>
            <p className="mb-4 inline-flex rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm font-medium text-cyan-300">
              Dental FAQ automation
            </p>

            <h2 className="text-3xl font-black tracking-tight md:text-4xl">
              Answers routine patient questions using clinic-specific
              information.
            </h2>

            <p className="mt-5 text-slate-300">
              Many dental calls are about the same topics. P-Core AI can answer
              common questions based on each clinic’s approved information and
              policies.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            {faqItems.map((item) => (
              <div
                key={item}
                className="rounded-2xl border border-white/10 bg-white/5 p-5"
              >
                <p className="font-semibold text-slate-100">{item}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Safety / Medical */}
      <section className="mx-auto max-w-7xl px-6 pb-20">
        <div className="rounded-[2rem] border border-cyan-400/20 bg-cyan-400/10 p-8 md:p-10">
          <div className="grid gap-8 lg:grid-cols-3">
            <div className="lg:col-span-1">
              <p className="text-sm font-bold uppercase tracking-[0.25em] text-cyan-300">
                Dental safety workflow
              </p>

              <h2 className="mt-4 text-3xl font-black">
                Careful handling for urgent and medical questions.
              </h2>
            </div>

            <div className="lg:col-span-2">
              <p className="text-lg leading-8 text-slate-200">
                P-Core AI can flag urgent calls involving severe pain, swelling,
                infection, broken teeth, or other emergency concerns. For
                sensitive medical questions, the system does not provide a final
                diagnosis and can guide the patient toward staff review, dentist
                review, or urgent care when appropriate.
              </p>

              <div className="mt-8 grid gap-4 sm:grid-cols-3">
                <div className="rounded-2xl bg-slate-950/50 p-5">
                  <p className="text-2xl font-black">24/7</p>
                  <p className="mt-2 text-sm text-slate-300">
                    After-hours request capture
                  </p>
                </div>

                <div className="rounded-2xl bg-slate-950/50 p-5">
                  <p className="text-2xl font-black">Multi</p>
                  <p className="mt-2 text-sm text-slate-300">
                    Language support
                  </p>
                </div>

                <div className="rounded-2xl bg-slate-950/50 p-5">
                  <p className="text-2xl font-black">Smart</p>
                  <p className="mt-2 text-sm text-slate-300">
                    Follow-up organization
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Dental Integrations / Contact */}
      <section className="mx-auto max-w-7xl px-6 pb-20">
        <div className="overflow-hidden rounded-[2rem] border border-white/10 bg-white/5">
          <div className="grid gap-0 lg:grid-cols-[1fr_0.9fr]">
            <div className="p-8 md:p-10">
              <p className="mb-4 inline-flex rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm font-medium text-cyan-300">
                Dental Software Integrations
              </p>

              <h2 className="text-3xl font-black tracking-tight md:text-4xl">
                Contact the P-Core AI development team.
              </h2>

              <p className="mt-5 max-w-2xl text-slate-300">
                For dental software compatibility, PMS integrations, API
                access, calendar workflows, clinic pilots, or technical
                partnership inquiries, contact our development and integrations
                team.
              </p>

              <div className="mt-8 flex flex-wrap gap-4">
                <a
                  href="mailto:PCoreAI.Dev@gmail.com"
                  className="rounded-2xl bg-cyan-400 px-6 py-3 font-bold text-slate-950 hover:bg-cyan-300"
                >
                  Email Development Team
                </a>

                <Link
                  href="/dent"
                  className="rounded-2xl border border-white/15 px-6 py-3 font-bold text-white hover:bg-white/10"
                >
                  View Dental Solution
                </Link>
              </div>
            </div>

            <div className="border-t border-white/10 bg-slate-900/70 p-8 md:p-10 lg:border-l lg:border-t-0">
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-500">
                Development contact
              </p>

              <a
                href="mailto:PCoreAI.Dev@gmail.com"
                className="mt-4 block break-all text-2xl font-black text-white hover:text-cyan-300"
              >
                PCoreAI.Dev@gmail.com
              </a>

              <div className="mt-8 space-y-4 text-sm text-slate-300">
                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <p className="font-bold text-white">Integration requests</p>
                  <p className="mt-2">
                    PMS, calendar, patient data, appointment workflow, and
                    third-party dental software connection inquiries.
                  </p>
                </div>

                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <p className="font-bold text-white">Dental clinic pilots</p>
                  <p className="mt-2">
                    Contact us about P-Core AI demos, pilot clinics, and dental
                    front-desk automation workflows.
                  </p>
                </div>

                <p className="text-xs text-slate-500">
                  A domain-based email such as dev@pcoreai.com may be added
                  later. For now, this is the official development contact for
                  P-Core AI.
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Final CTA */}
      <section className="mx-auto max-w-7xl px-6 pb-24">
        <div className="rounded-[2rem] border border-white/10 bg-slate-900 p-8 text-center md:p-12">
          <p className="text-sm font-bold uppercase tracking-[0.25em] text-cyan-300">
            P-Core AI for dental clinics
          </p>

          <h2 className="mt-4 text-3xl font-black tracking-tight md:text-5xl">
            Dental front-desk automation, built for real clinic workflows.
          </h2>

          <p className="mx-auto mt-5 max-w-2xl text-slate-300">
            Answer calls, capture appointment requests, organize follow-ups, and
            support your reception team with an AI system focused only on dental
            clinic operations.
          </p>

          <div className="mt-8 flex flex-wrap justify-center gap-4">
            <a
              href="mailto:PCoreAI.Dev@gmail.com"
              className="rounded-2xl bg-cyan-400 px-6 py-3 font-bold text-slate-950 hover:bg-cyan-300"
            >
              Contact P-Core AI
            </a>

            <Link
              href="/login"
              className="rounded-2xl border border-white/15 px-6 py-3 font-bold text-white hover:bg-white/10"
            >
              Clinic Login
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/10">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-6 py-8 text-sm text-slate-500 md:flex-row md:items-center md:justify-between">
          <p>© {new Date().getFullYear()} P-Core AI. All rights reserved.</p>

          <div className="flex flex-wrap gap-5">
            <Link href="/dent" className="hover:text-slate-300">
              Dental Solution
            </Link>

            <a
              href="mailto:PCoreAI.Dev@gmail.com"
              className="hover:text-slate-300"
            >
              Contact
            </a>

            <Link href="/login" className="hover:text-slate-300">
              Login
            </Link>
          </div>
        </div>
      </footer>
    </main>
  );
}