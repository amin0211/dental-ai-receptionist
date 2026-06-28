import Link from "next/link";

const platformFeatures = [
  "AI phone receptionist",
  "Appointment request capture",
  "Customer and patient data workflows",
  "Calendar and software integrations",
  "Industry-specific AI assistants",
];

const dentHighlights = [
  {
    title: "Answers calls when the front desk is busy",
    description:
      "P-Core Dent can answer incoming patient calls while staff are helping in-person patients, handling files, or coordinating appointments.",
  },
  {
    title: "Handles after-hours requests",
    description:
      "When the clinic is closed, the AI can collect new appointment requests, cancellation requests, messages, and common questions.",
  },
  {
    title: "Collects appointment details",
    description:
      "The system can ask for the patient name, reason for visit, preferred date, and preferred time, then prepare the information for the front desk.",
  },
  {
    title: "Identifies follow-up cases",
    description:
      "Incomplete calls, urgent concerns, cancellation requests, and cases that need staff review can be flagged for follow-up.",
  },
];

const dentCapabilities = [
  "Initial call greeting",
  "Existing patient identification",
  "New patient information capture",
  "Reason-for-visit collection",
  "Appointment request management",
  "Change or cancellation request logging",
  "FAQ answers for insurance, parking, CDCP, payments, and clinic policies",
  "Urgent call detection for pain, swelling, infection, or broken teeth",
  "Careful handling of medical questions",
  "Call summary storage",
  "Follow-up organization",
  "Clinic-specific customization",
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
                AI automation for service businesses
              </p>
            </div>
          </Link>

          <nav className="flex items-center gap-4 text-sm">
            <Link
              href="/dent"
              className="hidden text-slate-300 hover:text-white sm:inline"
            >
              P-Core Dent
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
        <div className="absolute left-1/2 top-0 h-[500px] w-[500px] -translate-x-1/2 rounded-full bg-cyan-400/10 blur-3xl" />
        <div className="absolute right-0 top-32 h-[400px] w-[400px] rounded-full bg-blue-500/10 blur-3xl" />

        <div className="relative mx-auto grid max-w-7xl gap-12 px-6 py-24 lg:grid-cols-2 lg:items-center">
          <div>
            <p className="mb-5 inline-flex rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm font-medium text-cyan-300">
              AI • Voice • Data • Workflow Automation
            </p>

            <h1 className="max-w-4xl text-5xl font-black tracking-tight md:text-6xl">
              The AI core for business communication.
            </h1>

            <p className="mt-6 max-w-xl text-lg leading-8 text-slate-300">
              P-Core AI builds intelligent software that connects calls,
              appointments, customer data, workflows, and business operations
              into one automated layer.
            </p>

            <div className="mt-8 flex flex-wrap gap-4">
              <Link
                href="/dent"
                className="rounded-2xl bg-cyan-400 px-6 py-3 font-bold text-slate-950 shadow-lg shadow-cyan-400/20 hover:bg-cyan-300"
              >
                Explore P-Core Dent
              </Link>

              <a
                href="mailto:PCoreAI.Dev@gmail.com"
                className="rounded-2xl border border-white/15 px-6 py-3 font-bold text-white hover:bg-white/10"
              >
                Contact Development Team
              </a>
            </div>

            <p className="mt-6 max-w-lg text-sm leading-6 text-slate-500">
              Built for clinics and service businesses that need faster call
              handling, cleaner follow-ups, and more organized customer
              communication.
            </p>
          </div>

          <div className="rounded-[2rem] border border-white/10 bg-white/5 p-6 shadow-2xl">
            <div className="rounded-3xl bg-slate-900 p-6">
              <div className="mb-6 flex items-center justify-between">
                <div>
                  <p className="text-sm font-semibold text-cyan-300">
                    P-Core Platform
                  </p>
                  <h2 className="mt-2 text-2xl font-bold">
                    One AI layer for calls, data, and operations.
                  </h2>
                </div>

                <div className="hidden rounded-2xl bg-cyan-400/10 px-4 py-2 text-sm font-semibold text-cyan-300 sm:block">
                  Live system
                </div>
              </div>

              <div className="space-y-4">
                {platformFeatures.map((item) => (
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

      {/* Main Product */}
      <section className="mx-auto max-w-7xl px-6 py-20">
        <div className="grid gap-10 lg:grid-cols-[0.9fr_1.1fr] lg:items-start">
          <div>
            <p className="mb-4 inline-flex rounded-full border border-emerald-400/30 bg-emerald-400/10 px-4 py-2 text-sm font-medium text-emerald-300">
              Featured product
            </p>

            <h2 className="text-4xl font-black tracking-tight md:text-5xl">
              P-Core Dent
            </h2>

            <p className="mt-5 text-lg leading-8 text-slate-300">
              An AI receptionist and front-desk assistant for dental clinics.
              It is designed to support the reception team, not replace it.
              It helps manage routine calls, appointment requests, common
              questions, and follow-up cases more consistently.
            </p>

            <div className="mt-8 flex flex-wrap gap-4">
              <Link
                href="/dent"
                className="rounded-2xl bg-white px-6 py-3 font-bold text-slate-950 hover:bg-slate-200"
              >
                View dental solution
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
            {dentHighlights.map((feature) => (
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

      {/* Dental Capabilities */}
      <section className="border-y border-white/10 bg-white/[0.03]">
        <div className="mx-auto max-w-7xl px-6 py-20">
          <div className="mb-10 max-w-3xl">
            <h2 className="text-3xl font-black tracking-tight md:text-4xl">
              What P-Core Dent can help with
            </h2>

            <p className="mt-4 text-slate-300">
              The system can be configured around each clinic’s services,
              hours, cancellation policies, insurance information, booking
              process, and follow-up workflow.
            </p>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {dentCapabilities.map((capability, index) => (
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

      {/* Safety / Positioning */}
      <section className="mx-auto max-w-7xl px-6 py-20">
        <div className="rounded-[2rem] border border-cyan-400/20 bg-cyan-400/10 p-8 md:p-10">
          <div className="grid gap-8 lg:grid-cols-3">
            <div className="lg:col-span-1">
              <p className="text-sm font-bold uppercase tracking-[0.25em] text-cyan-300">
                Designed for real clinics
              </p>

              <h2 className="mt-4 text-3xl font-black">
                Human-led, AI-assisted front desk.
              </h2>
            </div>

            <div className="lg:col-span-2">
              <p className="text-lg leading-8 text-slate-200">
                P-Core Dent is built to organize patient communication and
                reduce repetitive front-desk workload. Sensitive medical
                questions are handled carefully: the system does not provide a
                final diagnosis and can guide patients toward staff review,
                dentist review, or urgent care when needed.
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

      {/* Contact */}
      <section className="mx-auto max-w-7xl px-6 pb-20">
        <div className="overflow-hidden rounded-[2rem] border border-white/10 bg-white/5">
          <div className="grid gap-0 lg:grid-cols-[1fr_0.9fr]">
            <div className="p-8 md:p-10">
              <p className="mb-4 inline-flex rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm font-medium text-cyan-300">
                Development & Integrations
              </p>

              <h2 className="text-3xl font-black tracking-tight md:text-4xl">
                Contact the P-Core AI development team.
              </h2>

              <p className="mt-5 max-w-2xl text-slate-300">
                For technical questions, integration discussions, API access,
                dental software compatibility, or partnership inquiries, contact
                our development and integrations team.
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
                  View P-Core Dent
                </Link>
              </div>
            </div>

            <div className="border-t border-white/10 bg-slate-900/70 p-8 md:p-10 lg:border-l lg:border-t-0">
              <p className="text-sm font-semibold uppercase tracking-[0.2em] text-slate-500">
                Contact email
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
                    third-party software connection inquiries.
                  </p>
                </div>

                <div className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <p className="font-bold text-white">Dental partnerships</p>
                  <p className="mt-2">
                    Contact us about P-Core Dent demos, pilot clinics, and
                    technical collaboration.
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

      {/* Products */}
      <section className="mx-auto max-w-7xl px-6 pb-24">
        <div className="mb-8">
          <h2 className="text-3xl font-black">Products</h2>

          <p className="mt-3 max-w-2xl text-slate-300">
            P-Core AI creates specialized AI systems for different service
            industries.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-3">
          <Link
            href="/dent"
            className="rounded-3xl border border-cyan-400/30 bg-cyan-400/10 p-6 transition hover:border-cyan-400/70 hover:bg-cyan-400/15"
          >
            <p className="mb-4 text-sm font-semibold text-cyan-300">
              Available now
            </p>

            <h3 className="text-xl font-bold">P-Core Dent</h3>

            <p className="mt-3 text-slate-300">
              AI receptionist and front-desk automation for dental clinics.
            </p>
          </Link>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-6 opacity-80">
            <p className="mb-4 text-sm font-semibold text-slate-500">
              Coming soon
            </p>

            <h3 className="text-xl font-bold">P-Core Beauty</h3>

            <p className="mt-3 text-slate-300">
              AI booking and client communication for salons and spas.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-6 opacity-80">
            <p className="mb-4 text-sm font-semibold text-slate-500">
              Coming soon
            </p>

            <h3 className="text-xl font-bold">P-Core Clinic</h3>

            <p className="mt-3 text-slate-300">
              AI communication workflows for healthcare and service clinics.
            </p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/10">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-6 py-8 text-sm text-slate-500 md:flex-row md:items-center md:justify-between">
          <p>© {new Date().getFullYear()} P-Core AI. All rights reserved.</p>

          <div className="flex flex-wrap gap-5">
            <Link href="/dent" className="hover:text-slate-300">
              P-Core Dent
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