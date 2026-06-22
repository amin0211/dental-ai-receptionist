"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabaseClient";
import { createClinic } from "@/lib/supabaseService";

type AuthMode = "signin" | "signup";

export default function LoginPage() {
  const router = useRouter();

  const [mode, setMode] = useState<AuthMode>("signin");

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [clinicName, setClinicName] = useState("");
  const [adminFullName, setAdminFullName] = useState("");
  const [clinicPhoneNumber, setClinicPhoneNumber] = useState("");
  const [timezone, setTimezone] = useState("America/Vancouver");
  const [address, setAddress] = useState("");

  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  function clearMessages() {
    setErrorMessage("");
    setSuccessMessage("");
  }

  function switchMode(nextMode: AuthMode) {
    setMode(nextMode);
    clearMessages();
  }

  function validateSignInForm() {
    if (!email.trim()) return "Email address is required.";
    if (!password.trim()) return "Password is required.";

    return "";
  }

  function validateSignUpForm() {
    if (!clinicName.trim()) return "Clinic name is required.";
    if (!adminFullName.trim()) return "Admin full name is required.";
    if (!email.trim()) return "Email address is required.";
    if (!password.trim()) return "Password is required.";
    if (password.length < 6) return "Password must be at least 6 characters.";
    if (!clinicPhoneNumber.trim()) return "Clinic phone number is required.";
    if (!timezone.trim()) return "Timezone is required.";

    return "";
  }

  async function handleSignIn() {
    const validationError = validateSignInForm();

    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    const { error } = await supabase.auth.signInWithPassword({
      email: email.trim(),
      password,
    });

    if (error) {
      setErrorMessage(error.message);
      return;
    }

    router.replace("/dashboard");
  }

  async function handleSignUp() {
    const validationError = validateSignUpForm();

    if (validationError) {
      setErrorMessage(validationError);
      return;
    }

    const { data: signUpData, error: signUpError } = await supabase.auth.signUp({
      email: email.trim(),
      password,
      options: {
        data: {
          clinic_name: clinicName.trim(),
          admin_full_name: adminFullName.trim(),
        },
      },
    });

    if (signUpError) {
      setErrorMessage(signUpError.message);
      return;
    }

    const user = signUpData.user;
    const session = signUpData.session;

    if (!session) {
      setSuccessMessage(
        "Account created, but no active session was returned. Please turn off email confirmation in Supabase Auth settings, then try again."
      );
      return;
    }
    if (!user) {
      setSuccessMessage(
        "Account created. Please check your email to confirm your account."
      );
      return;
    }

    try {
      await createClinic({
        ownerUserId: user.id,
        clinicName: clinicName.trim(),
        adminFullName: adminFullName.trim(),
        adminEmail: email.trim(),
        phoneNumber: clinicPhoneNumber.trim(),
        timezone,
        address: address.trim() || null,
      });
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Account was created, but clinic setup failed.";

      setErrorMessage(message);
      return;
    }

    router.replace("/dashboard");
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setIsLoading(true);
    clearMessages();

    try {
      if (mode === "signin") {
        await handleSignIn();
      } else {
        await handleSignUp();
      }
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen bg-slate-50">
      <section className="hidden w-1/2 items-center bg-blue-600 px-16 text-white lg:flex">
        <div>
          <div className="mb-10 flex h-20 w-20 items-center justify-center rounded-3xl bg-white/15 text-2xl font-bold">
            AI
          </div>

          <h1 className="text-5xl font-bold tracking-tight">
            Clinic AI Dashboard
          </h1>

          <p className="mt-8 max-w-xl text-2xl leading-relaxed text-blue-100">
            Manage appointment requests, doctors, services, AI calls, and clinic
            activity from one clean workspace.
          </p>
        </div>
      </section>

      <section className="flex flex-1 items-center justify-center px-6 py-10">
        <div className="w-full max-w-xl rounded-3xl border border-slate-200 bg-white p-8 shadow-sm sm:p-10">
          <h1 className="text-3xl font-bold text-slate-900">
            {mode === "signin" ? "Sign in" : "Create account"}
          </h1>

          <p className="mt-3 text-slate-500">
            {mode === "signin"
              ? "Access your clinic dashboard."
              : "Create your clinic workspace and start managing appointment requests."}
          </p>

          {errorMessage && (
            <div className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {errorMessage}
            </div>
          )}

          {successMessage && (
            <div className="mt-6 rounded-xl border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
              {successMessage}
            </div>
          )}

          <form onSubmit={handleSubmit} className="mt-8 space-y-5">
            {mode === "signup" && (
              <>
                <div>
                  <label className="text-sm font-medium text-slate-700">
                    Clinic name
                  </label>
                  <input
                    value={clinicName}
                    onChange={(event) => setClinicName(event.target.value)}
                    className="mt-2 w-full rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                    placeholder="Example Dental Clinic"
                  />
                </div>

                <div>
                  <label className="text-sm font-medium text-slate-700">
                    Admin full name
                  </label>
                  <input
                    value={adminFullName}
                    onChange={(event) => setAdminFullName(event.target.value)}
                    className="mt-2 w-full rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                    placeholder="Sarah Johnson"
                  />
                </div>
              </>
            )}

            <div>
              <label className="text-sm font-medium text-slate-700">
                Email address
              </label>
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="mt-2 w-full rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                placeholder="admin@clinic.com"
              />
            </div>

            <div>
              <label className="text-sm font-medium text-slate-700">
                Password
              </label>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="mt-2 w-full rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                placeholder="Minimum 6 characters"
              />
            </div>

            {mode === "signup" && (
              <>
                <div>
                  <label className="text-sm font-medium text-slate-700">
                    Clinic phone number
                  </label>
                  <input
                    value={clinicPhoneNumber}
                    onChange={(event) =>
                      setClinicPhoneNumber(event.target.value)
                    }
                    className="mt-2 w-full rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                    placeholder="+1 604 123 4567"
                  />
                </div>

                <div>
                  <label className="text-sm font-medium text-slate-700">
                    Timezone
                  </label>
                  <select
                    value={timezone}
                    onChange={(event) => setTimezone(event.target.value)}
                    className="mt-2 w-full rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                  >
                    <option value="America/Vancouver">America/Vancouver</option>
                    <option value="America/Toronto">America/Toronto</option>
                    <option value="America/New_York">America/New_York</option>
                    <option value="America/Los_Angeles">
                      America/Los_Angeles
                    </option>
                  </select>
                </div>

                <div>
                  <label className="text-sm font-medium text-slate-700">
                    Clinic address{" "}
                    <span className="font-normal text-slate-400">
                      optional
                    </span>
                  </label>
                  <input
                    value={address}
                    onChange={(event) => setAddress(event.target.value)}
                    className="mt-2 w-full rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 outline-none transition focus:border-blue-500 focus:ring-4 focus:ring-blue-100"
                    placeholder="123 Main Street, Vancouver, BC"
                  />
                </div>
              </>
            )}

            <button
              type="submit"
              disabled={isLoading}
              className="w-full rounded-xl bg-blue-600 px-4 py-3 font-semibold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading
                ? "Please wait..."
                : mode === "signin"
                  ? "Sign In"
                  : "Create Account"}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-slate-500">
            {mode === "signin" ? (
              <>
                New clinic?{" "}
                <button
                  type="button"
                  onClick={() => switchMode("signup")}
                  className="font-semibold text-blue-600 hover:text-blue-700"
                >
                  Create an account
                </button>
              </>
            ) : (
              <>
                Already have an account?{" "}
                <button
                  type="button"
                  onClick={() => switchMode("signin")}
                  className="font-semibold text-blue-600 hover:text-blue-700"
                >
                  Sign in
                </button>
              </>
            )}
          </div>
        </div>
      </section>
    </main>
  );
}