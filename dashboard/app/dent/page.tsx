import Link from "next/link";

export default function DentPage() {
  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <header className="border-b border-white/10 bg-slate-950/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <Link href="/" className="text-xl font-bold tracking-tight">
            P-Core AI
          </Link>

          <Link
            href="/login"
            className="rounded-full bg-white px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-slate-200"
          >
            Login
          </Link>
        </div>
      </header>

      <section className="mx-auto max-w-7xl px-6 py-24">
        <p className="mb-5 inline-flex rounded-full border border-cyan-400/30 bg-cyan-400/10 px-4 py-2 text-sm font-medium text-cyan-300">
          P-Core Dent
        </p>

        <h1 className="max-w-4xl text-5xl font-black tracking-tight md:text-6xl">
          AI receptionist for dental clinics.
        </h1>

        <p className="mt-6 max-w-2xl text-lg leading-8 text-slate-300">
          P-Core Dent answers patient calls, collects appointment requests,
          captures visit reasons, and keeps the front desk organized.
        </p>

        <div className="mt-8 flex flex-wrap gap-4">
          <Link
            href="/login"
            className="rounded-2xl bg-cyan-400 px-6 py-3 font-bold text-slate-950 hover:bg-cyan-300"
          >
            Clinic Login
          </Link>

          <Link
            href="/"
            className="rounded-2xl border border-white/15 px-6 py-3 font-bold text-white hover:bg-white/10"
          >
            Back to P-Core AI
          </Link>
        </div>

        <div className="mt-16 grid gap-6 md:grid-cols-3">
          <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
            <h2 className="text-xl font-bold">Answer calls</h2>
            <p className="mt-3 text-slate-300">
              Let AI handle routine patient calls and appointment requests.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
            <h2 className="text-xl font-bold">Capture requests</h2>
            <p className="mt-3 text-slate-300">
              Collect patient name, reason for visit, preferred date, and time.
            </p>
          </div>

          <div className="rounded-3xl border border-white/10 bg-white/5 p-6">
            <h2 className="text-xl font-bold">Support front desk</h2>
            <p className="mt-3 text-slate-300">
              Organize appointment requests so staff can follow up faster.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}