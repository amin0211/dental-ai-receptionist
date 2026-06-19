import { createClient } from "@supabase/supabase-js";


export const dynamic = "force-dynamic";
export const revalidate = 0;

type Call = {
  id: string;
  caller_phone: string | null;
  speech_result: string | null;
  confidence: string | null;
  intent: string | null;
  urgency: string | null;
  summary: string | null;
  created_at: string;
};

type AppointmentRequest = {
  id: string;
  patient_name: string | null;
  patient_phone: string | null;
  reason: string | null;
  preferred_time: string | null;
  urgency: string | null;
  status: string | null;
  created_at: string;
};

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL!;
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!;

const supabase = createClient(supabaseUrl, supabaseAnonKey);

export default async function Home() {
  const { data: calls, error: callsError } = await supabase
    .from("calls")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(20);

  const { data: appointmentRequests, error: appointmentError } = await supabase
    .from("appointment_requests")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(20);

  if (callsError || appointmentError) {
    return (
      <main className="min-h-screen bg-gray-50 p-8">
        <h1 className="text-2xl font-bold text-red-600">Database error</h1>

        {callsError && (
          <pre className="mt-4 rounded bg-white p-4 text-sm text-red-700">
            Calls error: {callsError.message}
          </pre>
        )}

        {appointmentError && (
          <pre className="mt-4 rounded bg-white p-4 text-sm text-red-700">
            Appointment requests error: {appointmentError.message}
          </pre>
        )}
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gray-50 p-8">
      <div className="mx-auto max-w-7xl">
        <div className="mb-8">
          <p className="text-sm font-medium text-gray-500">
            Dental AI Receptionist
          </p>
          <h1 className="mt-2 text-3xl font-bold text-gray-900">
            Clinic Dashboard
          </h1>
          <p className="mt-2 text-gray-600">
            Calls and appointment requests captured from Twilio and saved in
            Supabase.
          </p>
        </div>

        <section className="mb-10 rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-200 px-6 py-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Appointment Requests
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              Requests created when a caller asks to book or schedule an
              appointment.
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-100 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-6 py-3">Time</th>
                  <th className="px-6 py-3">Patient Phone</th>
                  <th className="px-6 py-3">Reason</th>
                  <th className="px-6 py-3">Preferred Time</th>
                  <th className="px-6 py-3">Urgency</th>
                  <th className="px-6 py-3">Status</th>
                </tr>
              </thead>

              <tbody className="divide-y divide-gray-100">
                {(appointmentRequests as AppointmentRequest[] | null)?.map(
                  (request) => (
                    <tr key={request.id} className="align-top">
                      <td className="whitespace-nowrap px-6 py-4 text-gray-600">
                        {new Date(request.created_at).toLocaleString()}
                      </td>

                      <td className="whitespace-nowrap px-6 py-4 font-medium text-gray-900">
                        {request.patient_phone || "-"}
                      </td>

                      <td className="max-w-md px-6 py-4 text-gray-700">
                        {request.reason || "-"}
                      </td>

                      <td className="whitespace-nowrap px-6 py-4 text-gray-700">
                        {request.preferred_time || "-"}
                      </td>

                      <td className="whitespace-nowrap px-6 py-4">
                        <span
                          className={
                            request.urgency === "urgent"
                              ? "rounded-full bg-red-50 px-3 py-1 text-xs font-medium text-red-700"
                              : "rounded-full bg-green-50 px-3 py-1 text-xs font-medium text-green-700"
                          }
                        >
                          {request.urgency || "normal"}
                        </span>
                      </td>

                      <td className="whitespace-nowrap px-6 py-4">
                        <span className="rounded-full bg-yellow-50 px-3 py-1 text-xs font-medium text-yellow-700">
                          {request.status || "new"}
                        </span>
                      </td>
                    </tr>
                  )
                )}

                {(!appointmentRequests ||
                  appointmentRequests.length === 0) && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-6 py-10 text-center text-gray-500"
                    >
                      No appointment requests saved yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>

        <section className="rounded-xl border border-gray-200 bg-white shadow-sm">
          <div className="border-b border-gray-200 px-6 py-4">
            <h2 className="text-lg font-semibold text-gray-900">
              Recent Calls
            </h2>
            <p className="mt-1 text-sm text-gray-500">
              Latest calls captured from Twilio speech input.
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-gray-100 text-xs uppercase text-gray-500">
                <tr>
                  <th className="px-6 py-3">Time</th>
                  <th className="px-6 py-3">Caller</th>
                  <th className="px-6 py-3">Intent</th>
                  <th className="px-6 py-3">Urgency</th>
                  <th className="px-6 py-3">Speech</th>
                  <th className="px-6 py-3">Summary</th>
                </tr>
              </thead>

              <tbody className="divide-y divide-gray-100">
                {(calls as Call[] | null)?.map((call) => (
                  <tr key={call.id} className="align-top">
                    <td className="whitespace-nowrap px-6 py-4 text-gray-600">
                      {new Date(call.created_at).toLocaleString()}
                    </td>

                    <td className="whitespace-nowrap px-6 py-4 font-medium text-gray-900">
                      {call.caller_phone || "-"}
                    </td>

                    <td className="whitespace-nowrap px-6 py-4">
                      <span className="rounded-full bg-blue-50 px-3 py-1 text-xs font-medium text-blue-700">
                        {call.intent || "unknown"}
                      </span>
                    </td>

                    <td className="whitespace-nowrap px-6 py-4">
                      <span
                        className={
                          call.urgency === "urgent"
                            ? "rounded-full bg-red-50 px-3 py-1 text-xs font-medium text-red-700"
                            : "rounded-full bg-green-50 px-3 py-1 text-xs font-medium text-green-700"
                        }
                      >
                        {call.urgency || "normal"}
                      </span>
                    </td>

                    <td className="max-w-xs px-6 py-4 text-gray-700">
                      {call.speech_result || "-"}
                    </td>

                    <td className="max-w-sm px-6 py-4 text-gray-700">
                      {call.summary || "-"}
                    </td>
                  </tr>
                ))}

                {(!calls || calls.length === 0) && (
                  <tr>
                    <td
                      colSpan={6}
                      className="px-6 py-10 text-center text-gray-500"
                    >
                      No calls saved yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </main>
  );
}