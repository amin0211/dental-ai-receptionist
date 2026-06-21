import LoginForm from "@/components/auth/LoginForm";

export default function LoginPage() {
  return (
    <main className="flex min-h-screen bg-slate-50">
      <section className="hidden flex-1 items-center justify-center bg-blue-600 px-12 lg:flex">
        <div className="max-w-lg text-white">
          <div className="mb-8 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-white/15 text-2xl font-bold">
            AI
          </div>

          <h1 className="mb-4 text-4xl font-bold tracking-tight">
            Clinic AI Dashboard
          </h1>

          <p className="text-lg leading-8 text-blue-100">
            Manage appointment requests, doctors, services, calls, and clinic
            calendars from one clean workspace.
          </p>
        </div>
      </section>

      <section className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-600 text-xl font-bold text-white">
              AI
            </div>
            <h1 className="text-3xl font-bold text-slate-900">
              Clinic AI Dashboard
            </h1>
          </div>

          <div className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
            <div className="mb-8">
              <h2 className="text-2xl font-bold text-slate-900">Sign in</h2>
              <p className="mt-2 text-sm text-slate-500">
                Access your clinic workbench and appointment requests.
              </p>
            </div>

            <LoginForm />
          </div>
        </div>
      </section>
    </main>
  );
}