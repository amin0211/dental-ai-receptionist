// http://localhost:3000/ai-reception
export default function AiReceptionPage() {
  return (
    <main className="min-h-screen bg-slate-950 text-white">
      {/* Navbar */}
      <header className="sticky top-0 z-50 border-b border-white/10 bg-slate-950/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-cyan-400 text-lg font-black text-slate-950">
              C
            </div>
            <div>
              <p className="text-lg font-bold tracking-tight">Costio DentAI Reception</p>
              <p className="text-xs text-slate-400">AI Front Desk for Dental Clinics</p>
            </div>
          </div>

          <nav className="hidden items-center gap-8 text-sm text-slate-300 md:flex">
            <a href="#features" className="hover:text-white">
              Features
            </a>
            <a href="#how-it-works" className="hover:text-white">
              How it works
            </a>
            <a href="#pricing" className="hover:text-white">
              Pricing
            </a>
            <a href="#faq" className="hover:text-white">
              FAQ
            </a>
          </nav>

          <a
            href="#demo"
            className="rounded-full bg-white px-5 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200"
          >
            Book a Demo
          </a>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute left-1/2 top-0 h-[500px] w-[900px] -translate-x-1/2 rounded-full bg-cyan-500/20 blur-3xl" />
        <div className="relative mx-auto grid max-w-7xl items-center gap-12 px-6 py-24 lg:grid-cols-2 lg:py-32">
          <div>
            <div className="mb-6 inline-flex rounded-full border border-cyan-300/30 bg-cyan-300/10 px-4 py-2 text-sm text-cyan-200">
              No PMS migration required
            </div>

            <h1 className="max-w-3xl text-5xl font-black tracking-tight text-white md:text-7xl">
              AI Receptionist for Dental Clinics
            </h1>

            <p className="mt-7 max-w-2xl text-lg leading-8 text-slate-300 md:text-xl">
              Answer calls, handle patient questions, capture appointment requests,
              and reduce front desk workload — without replacing your current dental software.
            </p>

            <div className="mt-10 flex flex-col gap-4 sm:flex-row">
              <a
                href="#demo"
                className="rounded-full bg-cyan-400 px-8 py-4 text-center font-bold text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:bg-cyan-300"
              >
                Start 14-Day Pilot
              </a>
              <a
                href="#how-it-works"
                className="rounded-full border border-white/15 px-8 py-4 text-center font-bold text-white transition hover:bg-white/10"
              >
                See How It Works
              </a>
            </div>

            <div className="mt-10 grid max-w-xl grid-cols-3 gap-4 text-sm text-slate-400">
              <div>
                <p className="text-2xl font-black text-white">24/7</p>
                <p>Call capture</p>
              </div>
              <div>
                <p className="text-2xl font-black text-white">0</p>
                <p>Software migration</p>
              </div>
              <div>
                <p className="text-2xl font-black text-white">AI</p>
                <p>Front desk support</p>
              </div>
            </div>
          </div>

          {/* Hero Card */}
          <div className="rounded-[2rem] border border-white/10 bg-white/10 p-4 shadow-2xl backdrop-blur-xl">
            <div className="rounded-[1.5rem] bg-slate-900 p-6">
              <div className="mb-6 flex items-center justify-between border-b border-white/10 pb-5">
                <div>
                  <p className="text-sm text-slate-400">Live AI Call</p>
                  <p className="text-xl font-bold">New appointment request</p>
                </div>
                <span className="rounded-full bg-emerald-400/10 px-3 py-1 text-sm font-medium text-emerald-300">
                  Active
                </span>
              </div>

              <div className="space-y-4">
                <Message label="Patient" text="Hi, I have tooth pain and I need an appointment." />
                <Message label="AI Receptionist" text="I can help with that. What is the patient's full name?" />
                <Message label="Patient" text="Sarah Thompson. I prefer tomorrow afternoon." />
              </div>

              <div className="mt-6 rounded-2xl border border-cyan-300/20 bg-cyan-300/10 p-5">
                <p className="mb-3 text-sm font-semibold text-cyan-200">
                  Structured request created
                </p>
                <div className="grid gap-3 text-sm text-slate-300">
                  <InfoRow label="Patient" value="Sarah Thompson" />
                  <InfoRow label="Reason" value="Tooth pain" />
                  <InfoRow label="Preferred time" value="Tomorrow afternoon" />
                  <InfoRow label="Urgency" value="Needs follow-up" />
                </div>
              </div>

              <div className="mt-5 rounded-2xl bg-white/5 p-4 text-sm text-slate-400">
                The front desk reviews and confirms inside your current dental software.
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Problem */}
      <section className="border-y border-white/10 bg-slate-900/60">
        <div className="mx-auto max-w-7xl px-6 py-20">
          <div className="max-w-3xl">
            <p className="mb-3 text-sm font-bold uppercase tracking-widest text-cyan-300">
              The problem
            </p>
            <h2 className="text-4xl font-black tracking-tight md:text-5xl">
              Dental front desks are overloaded.
            </h2>
            <p className="mt-5 text-lg leading-8 text-slate-300">
              Calls come in while staff are helping patients, answering insurance questions,
              handling walk-ins, and managing the schedule. Missed calls become missed revenue.
            </p>
          </div>

          <div className="mt-12 grid gap-6 md:grid-cols-4">
            <ProblemCard title="Missed calls" text="Patients call when the team is busy or after hours." />
            <ProblemCard title="Repeated questions" text="Insurance, parking, hours, services, and policies." />
            <ProblemCard title="Scheduling interruptions" text="New bookings, cancellations, and reschedules interrupt the team." />
            <ProblemCard title="No clean follow-up" text="Important call details can get lost or forgotten." />
          </div>
        </div>
      </section>

      {/* Solution */}
      <section id="features" className="mx-auto max-w-7xl px-6 py-24">
        <div className="mx-auto max-w-3xl text-center">
          <p className="mb-3 text-sm font-bold uppercase tracking-widest text-cyan-300">
            The solution
          </p>
          <h2 className="text-4xl font-black tracking-tight md:text-5xl">
            An AI front desk assistant that works beside your team.
          </h2>
          <p className="mt-5 text-lg leading-8 text-slate-300">
            It answers calls, understands patient intent, handles common questions,
            and creates clean requests for your front desk to review.
          </p>
        </div>

        <div className="mt-16 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          <FeatureCard
            title="AI Call Answering"
            text="Automatically answers patient calls when your front desk is busy or after hours."
          />
          <FeatureCard
            title="Appointment Request Capture"
            text="Collects patient name, phone, reason, preferred doctor, and preferred time."
          />
          <FeatureCard
            title="FAQ Handling"
            text="Answers approved clinic questions about insurance, parking, services, and policies."
          />
          <FeatureCard
            title="Working Hours"
            text="Answers clinic and doctor working-hour questions from your configured availability rules."
          />
          <FeatureCard
            title="Cancel & Reschedule Support"
            text="Supports cancellation and reschedule workflows while keeping your team in control."
          />
          <FeatureCard
            title="Call Summaries"
            text="Every call includes transcript, intent, urgency, summary, and next action."
          />
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="bg-white text-slate-950">
        <div className="mx-auto max-w-7xl px-6 py-24">
          <div className="max-w-3xl">
            <p className="mb-3 text-sm font-bold uppercase tracking-widest text-cyan-600">
              How it works
            </p>
            <h2 className="text-4xl font-black tracking-tight md:text-5xl">
              Keep your current dental software.
            </h2>
            <p className="mt-5 text-lg leading-8 text-slate-600">
              Your clinic does not need to migrate patient records, charts, billing, or clinical notes.
              The AI works as a call-handling layer on top of your current workflow.
            </p>
          </div>

          <div className="mt-14 grid gap-6 lg:grid-cols-5">
            <Step number="01" title="Patient calls" text="The patient calls your clinic phone line." />
            <Step number="02" title="AI answers" text="AI handles the conversation naturally." />
            <Step number="03" title="Details captured" text="Reason, name, phone, urgency, and preferred time." />
            <Step number="04" title="Front desk reviews" text="Your team sees a clean request in the dashboard." />
            <Step number="05" title="Team confirms" text="Staff confirms inside the current PMS." />
          </div>

          <div className="mt-16 rounded-[2rem] bg-slate-950 p-8 text-white">
            <div className="grid gap-8 lg:grid-cols-2">
              <div>
                <p className="text-sm font-bold uppercase tracking-widest text-cyan-300">
                  Works alongside
                </p>
                <h3 className="mt-3 text-3xl font-black">
                  No replacement. No migration. No disruption.
                </h3>
              </div>
              <p className="text-lg leading-8 text-slate-300">
                Designed to work alongside systems like Open Dental, Dentrix, Curve,
                CareStack, ClearDent, ABELDent, and others. Integration options can be added
                later depending on the clinic’s software.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Dashboard Preview */}
      <section className="mx-auto max-w-7xl px-6 py-24">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <div>
            <p className="mb-3 text-sm font-bold uppercase tracking-widest text-cyan-300">
              Dashboard
            </p>
            <h2 className="text-4xl font-black tracking-tight md:text-5xl">
              Everything your front desk needs in one place.
            </h2>
            <p className="mt-5 text-lg leading-8 text-slate-300">
              Review new requests, urgent calls, incomplete calls, patient questions,
              and AI activity without digging through voicemail or notes.
            </p>

            <div className="mt-8 space-y-4">
              <Check text="New appointment requests" />
              <Check text="Needs follow-up queue" />
              <Check text="Call transcript and summary" />
              <Check text="Urgency and intent detection" />
              <Check text="FAQ and clinic knowledge management" />
            </div>
          </div>

          <div className="rounded-[2rem] border border-white/10 bg-white/10 p-4">
            <div className="rounded-[1.5rem] bg-slate-900 p-5">
              <div className="mb-5 grid grid-cols-2 gap-4">
                <Metric label="New Requests" value="12" />
                <Metric label="Needs Follow-up" value="5" />
                <Metric label="FAQ Calls" value="28" />
                <Metric label="After-hours" value="9" />
              </div>

              <div className="rounded-2xl bg-white/5 p-5">
                <div className="mb-4 flex items-center justify-between">
                  <p className="font-bold">Latest Requests</p>
                  <span className="text-sm text-cyan-300">View all</span>
                </div>

                <div className="space-y-3">
                  <RequestRow name="Sarah Thompson" reason="Tooth pain" status="Urgent" />
                  <RequestRow name="Michael Lee" reason="Cleaning" status="New" />
                  <RequestRow name="Anna Chen" reason="Reschedule" status="Follow-up" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Safety */}
      <section className="border-y border-white/10 bg-slate-900/70">
        <div className="mx-auto max-w-7xl px-6 py-20">
          <div className="grid gap-10 lg:grid-cols-2">
            <div>
              <p className="mb-3 text-sm font-bold uppercase tracking-widest text-cyan-300">
                Safety & control
              </p>
              <h2 className="text-4xl font-black tracking-tight">
                AI assists. Your team stays in control.
              </h2>
            </div>

            <div className="space-y-5 text-lg leading-8 text-slate-300">
              <p>
                The AI does not diagnose, does not promise treatment, and does not confirm final
                appointments by default. Your front desk can review every request before taking action.
              </p>
              <div className="grid gap-3 sm:grid-cols-2">
                <Check text="No diagnosis" />
                <Check text="No treatment promises" />
                <Check text="Human review available" />
                <Check text="Emergency guidance supported" />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="mx-auto max-w-7xl px-6 py-24">
        <div className="mx-auto max-w-3xl text-center">
          <p className="mb-3 text-sm font-bold uppercase tracking-widest text-cyan-300">
            Pricing
          </p>
          <h2 className="text-4xl font-black tracking-tight md:text-5xl">
            Start with a low-risk pilot.
          </h2>
          <p className="mt-5 text-lg leading-8 text-slate-300">
            Test the AI receptionist without migrating patient records or replacing your dental software.
          </p>
        </div>

        <div className="mt-14 grid gap-6 lg:grid-cols-3">
          <PricingCard
            name="Starter"
            price="$299"
            description="For small clinics testing AI call handling."
            features={[
              "AI call answering",
              "FAQ handling",
              "Appointment request dashboard",
              "Call transcript and summary",
              "No PMS migration",
            ]}
          />
          <PricingCard
            highlighted
            name="Growth"
            price="$499"
            description="For busier clinics that want more automation."
            features={[
              "Everything in Starter",
              "After-hours handling",
              "Cancel/reschedule workflows",
              "Working-hours answers",
              "Priority setup support",
            ]}
          />
          <PricingCard
            name="Custom"
            price="Custom"
            description="For multi-location clinics or advanced workflows."
            features={[
              "Multiple locations",
              "Custom workflows",
              "Integration planning",
              "Advanced reporting",
              "Dedicated support",
            ]}
          />
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="bg-white text-slate-950">
        <div className="mx-auto max-w-4xl px-6 py-24">
          <div className="text-center">
            <p className="mb-3 text-sm font-bold uppercase tracking-widest text-cyan-600">
              FAQ
            </p>
            <h2 className="text-4xl font-black tracking-tight">
              Common questions
            </h2>
          </div>

          <div className="mt-12 space-y-4">
            <FAQ
              question="Does this replace our dental software?"
              answer="No. It works alongside your current dental software. Your team can continue using the PMS they already know."
            />
            <FAQ
              question="Does the AI confirm appointments?"
              answer="By default, no. The AI captures appointment requests and your front desk confirms them."
            />
            <FAQ
              question="Do we need to migrate patient records?"
              answer="No. The pilot does not require patient record migration, chart migration, billing migration, or clinical record migration."
            />
            <FAQ
              question="Can it answer clinic-specific questions?"
              answer="Yes. You can add approved answers for insurance, parking, services, emergency policy, and other common questions."
            />
            <FAQ
              question="Can it handle after-hours calls?"
              answer="Yes. The AI can answer after-hours calls and create follow-up requests for your team."
            />
          </div>
        </div>
      </section>

      {/* CTA */}
      <section id="demo" className="relative overflow-hidden">
        <div className="absolute inset-0 bg-cyan-500/10" />
        <div className="relative mx-auto max-w-5xl px-6 py-24 text-center">
          <h2 className="text-4xl font-black tracking-tight md:text-6xl">
            Ready to reduce missed calls?
          </h2>
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-slate-300">
            Start a 14-day AI receptionist pilot for your dental clinic.
            No PMS migration required.
          </p>

          <div className="mt-10 flex flex-col justify-center gap-4 sm:flex-row">
            <a
            href="tel:+17788816242"
            className="rounded-full bg-cyan-400 px-8 py-4 font-bold text-slate-950 transition hover:bg-cyan-300"
            >
            Book a Demo
            </a>
            <a
            href="tel:+17788816242"
            className="rounded-full border border-white/15 px-8 py-4 font-bold text-white transition hover:bg-white/10"
            >
            Call +1 (778) 881-6242
            </a>
          </div>
        </div>
      </section>

      <footer className="border-t border-white/10 px-6 py-8 text-center text-sm text-slate-500">
        © 2026 Costio DentAI Reception. AI receptionist for dental clinics.
      </footer>
    </main>
  );
}

function Message({ label, text }: { label: string; text: string }) {
  return (
    <div className="rounded-2xl bg-white/5 p-4">
      <p className="mb-1 text-xs font-bold uppercase tracking-widest text-cyan-300">
        {label}
      </p>
      <p className="text-sm text-slate-200">{text}</p>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-slate-400">{label}</span>
      <span className="font-medium text-white">{value}</span>
    </div>
  );
}

function ProblemCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
      <h3 className="text-xl font-bold">{title}</h3>
      <p className="mt-3 leading-7 text-slate-400">{text}</p>
    </div>
  );
}

function FeatureCard({ title, text }: { title: string; text: string }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/5 p-7 transition hover:border-cyan-300/40 hover:bg-white/10">
      <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-cyan-400/15 text-cyan-300">
        ✦
      </div>
      <h3 className="text-xl font-bold">{title}</h3>
      <p className="mt-3 leading-7 text-slate-400">{text}</p>
    </div>
  );
}

function Step({
  number,
  title,
  text,
}: {
  number: string;
  title: string;
  text: string;
}) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-slate-50 p-6">
      <p className="text-sm font-black text-cyan-600">{number}</p>
      <h3 className="mt-4 text-xl font-black">{title}</h3>
      <p className="mt-3 leading-7 text-slate-600">{text}</p>
    </div>
  );
}

function Check({ text }: { text: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="flex h-6 w-6 items-center justify-center rounded-full bg-cyan-400 text-sm font-black text-slate-950">
        ✓
      </span>
      <span className="text-slate-300">{text}</span>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-2xl bg-white/5 p-5">
      <p className="text-3xl font-black text-white">{value}</p>
      <p className="mt-1 text-sm text-slate-400">{label}</p>
    </div>
  );
}

function RequestRow({
  name,
  reason,
  status,
}: {
  name: string;
  reason: string;
  status: string;
}) {
  return (
    <div className="flex items-center justify-between rounded-2xl bg-slate-800 p-4">
      <div>
        <p className="font-bold">{name}</p>
        <p className="text-sm text-slate-400">{reason}</p>
      </div>
      <span className="rounded-full bg-cyan-400/10 px-3 py-1 text-xs font-bold text-cyan-300">
        {status}
      </span>
    </div>
  );
}

function PricingCard({
  name,
  price,
  description,
  features,
  highlighted = false,
}: {
  name: string;
  price: string;
  description: string;
  features: string[];
  highlighted?: boolean;
}) {
  return (
    <div
      className={`rounded-[2rem] border p-8 ${
        highlighted
          ? "border-cyan-300 bg-cyan-400 text-slate-950 shadow-2xl shadow-cyan-500/20"
          : "border-white/10 bg-white/5 text-white"
      }`}
    >
      <p className="text-xl font-black">{name}</p>
      <div className="mt-5 flex items-end gap-2">
        <p className="text-5xl font-black">{price}</p>
        {price !== "Custom" && <p className="mb-2 text-sm opacity-70">/month</p>}
      </div>
      <p className={`mt-4 leading-7 ${highlighted ? "text-slate-800" : "text-slate-400"}`}>
        {description}
      </p>

      <div className="mt-8 space-y-3">
        {features.map((feature) => (
          <div key={feature} className="flex gap-3">
            <span className="font-black">✓</span>
            <span>{feature}</span>
          </div>
        ))}
      </div>

      <a
        href="#demo"
        className={`mt-8 block rounded-full px-6 py-3 text-center font-bold ${
          highlighted
            ? "bg-slate-950 text-white hover:bg-slate-800"
            : "bg-white text-slate-950 hover:bg-cyan-200"
        }`}
      >
        Get Started
      </a>
    </div>
  );
}

function FAQ({ question, answer }: { question: string; answer: string }) {
  return (
    <div className="rounded-3xl border border-slate-200 bg-slate-50 p-6">
      <h3 className="text-lg font-black">{question}</h3>
      <p className="mt-3 leading-7 text-slate-600">{answer}</p>
    </div>
  );
}