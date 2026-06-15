"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { api, setToken } from "@/lib/api";

const DEMO_TOKENS = [
  { token: "admin-token-jurassic", label: "Alex Park · admin" },
  { token: "token_sarah_kim", label: "Sarah Kim · SCRUM lead" },
  { token: "token_raj_patel", label: "Raj Patel · PLAT lead" },
  { token: "token_devon_lee", label: "Devon Lee · SUP lead" },
  { token: "token_priya_iyer", label: "Priya Iyer · developer" },
  { token: "token_observer", label: "Sam Observer · viewer (read-only)" },
];

export default function LoginPage() {
  const router = useRouter();
  const [token, setLocal] = useState("admin-token-jurassic");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function signIn(t: string) {
    setError(null);
    setBusy(true);
    setToken(t);
    try {
      await api.login(t);
      router.push("/");
    } catch (e: any) {
      setError(e.message || "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-ink-50">
      <div className="w-[400px] rounded-lg border border-ink-200 bg-white p-8 shadow-card">
        <div className="mb-6">
          <div className="mb-2 flex items-center gap-2">
            <span className="rounded bg-brand-500 px-2 py-1 font-bold text-white">JP</span>
            <h1 className="text-xl font-semibold">Jirassic Park</h1>
          </div>
          <p className="text-sm text-ink-600">
            Sign in with a demo api_token to explore the environment.
          </p>
        </div>

        <label className="block text-xs font-semibold uppercase tracking-wide text-ink-500">
          API token
        </label>
        <input
          type="text"
          className="mt-1 w-full rounded border border-ink-200 px-3 py-2 font-mono text-sm focus:border-brand-500 focus:outline-none"
          value={token}
          onChange={(e) => setLocal(e.target.value)}
        />

        <button
          type="button"
          disabled={busy}
          onClick={() => signIn(token)}
          className="mt-3 w-full rounded bg-brand-500 px-3 py-2 font-medium text-white hover:bg-brand-600 disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>

        {error && (
          <div className="mt-3 rounded bg-red-50 px-3 py-2 text-sm text-red-700 border border-red-200">
            {error}
          </div>
        )}

        <div className="mt-5">
          <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-ink-500">
            Quick demo accounts
          </div>
          <ul className="space-y-1">
            {DEMO_TOKENS.map((d) => (
              <li key={d.token}>
                <button
                  type="button"
                  onClick={() => signIn(d.token)}
                  className="w-full rounded border border-ink-200 px-3 py-1.5 text-left text-sm hover:bg-ink-50"
                >
                  <span className="text-ink-900">{d.label}</span>
                  <span className="ml-2 text-[11px] font-mono text-ink-500">{d.token}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
