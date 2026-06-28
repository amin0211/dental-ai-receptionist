import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <header className="border-b border-white/10 bg-slate-950/80 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <div>
            <p className="text-xl font-bold tracking-tight">P-Core AI</p>
            <p className="text-sm text-slate-400">
              AI software for modern business operations
            </p>
          </div>

          <nav className="flex items-center gap-4 text-sm">
            <Link href="/dent" className="text-slate-300 hover:text-white">
              P-Core Dent
            </Link>
            <Link
              href="/login"
              className="rounded-full bg-white px-5 py-2 font-semibold text-slate-950 hover:bg-slate-200"
            >
              Login
            </Link>
          </nav>
        </div>
      </header>

      <section className="mx-auto grid max-w-7xl gap-12 px-6 py-24 lg:grid-cols-2 lg:items-center">
        <div>
          <p className="mb-4 inline-flex rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm font-medium text-cyan-300">
            AI • Voice • Data • Automation
          </p>

          <h1 className="text-5xl font-black tracking-tight md:text-6xl">
            The AI core for business communication.
          </h1>

          <p className="mt-6 max-w-xl text-lg leading-8 text-slate-300">
            P-Core AI builds intelligent software systems that connect calls,
            appointments, customer data, workflows, and business operations in
            one automated layer.
          </p>

          <div className="mt-8 flex flex-wrap gap-4">
            <Link
              href="/dent"
              className="rounded-2xl bg-cyan-400 px-6 py-3 font-bold text-slate-950 hover:bg-cyan-300"
            >
              Explore P-Core Dent
            </Link>
            <Link
              href="/login"
              className="rounded-2xl border border-white/15 px-6 py-3 font-bold text-white hover:bg-white/10"
            >
              Client Login
            </Link>
          </div>
        </div>

        <div className="rounded-3xl border border-white/10 bg-white/5 p-6 shadow-2xl">
          <div className="rounded-2xl bg-slate-900 p-6">
            <p className="text-sm font-semibold text-cyan-300">
              P-Core Platform
            </p>

            <div className="mt-6 space-y-4">
              {[
                "AI phone receptionist",
                "Appointment request capture",
                "Customer and patient data workflows",
                "Calendar and software integrations",
                "Industry-specific AI assistants",
              ].map((item) => (
                <div
                  key={item}
                  className="rounded-xl border border-white/10 bg-white/5 px-4 py-3 text-slate-200"
                >
                  {item}
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-6 pb-24">
        <div className="grid gap-6 md:grid-cols-3">
          <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
            <h2 className="text-xl font-bold">P-Core Dent</h2>
            <p className="mt-3 text-slate-300">
              AI receptionist and front-desk automation for dental clinics.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
            <h2 className="text-xl font-bold">P-Core Beauty</h2>
            <p className="mt-3 text-slate-300">
              AI booking and client communication for salons and spas.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
            <h2 className="text-xl font-bold">P-Core Clinic</h2>
            <p className="mt-3 text-slate-300">
              AI communication workflows for healthcare and service clinics.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}