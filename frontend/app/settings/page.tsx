"use client";

import { ArrowRight } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";
import type { Project, Workflow } from "@/lib/types";

export default function SettingsPage() {
  const params = useSearchParams();
  const key = params.get("key") || "SCRUM";
  const [project, setProject] = useState<Project | null>(null);
  const [workflow, setWorkflow] = useState<Workflow | null>(null);

  useEffect(() => {
    api.project(key).then(setProject);
    api.projectWorkflow(key).then(setWorkflow);
  }, [key]);

  return (
    <AppShell>
      <div className="px-6 py-5 max-w-5xl">
        <header className="mb-4">
          <div className="text-[11px] uppercase tracking-wide text-ink-500">
            {key} · Settings
          </div>
          <h1 className="text-xl font-semibold">Project settings</h1>
        </header>

        {project && (
          <div className="rounded border border-ink-200 bg-white p-4 mb-6">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-700 mb-2">
              About
            </h2>
            <dl className="grid grid-cols-2 gap-y-1 text-sm">
              <dt className="text-ink-500">Key</dt>
              <dd className="font-mono">{project.key}</dd>
              <dt className="text-ink-500">Name</dt>
              <dd>{project.name}</dd>
              <dt className="text-ink-500">Type</dt>
              <dd className="capitalize">{project.project_type}</dd>
              <dt className="text-ink-500">Lead</dt>
              <dd>{project.lead_id || "—"}</dd>
              <dt className="text-ink-500">Workflow</dt>
              <dd className="font-mono text-xs">{project.workflow_id}</dd>
            </dl>
          </div>
        )}

        {workflow && (
          <div className="rounded border border-ink-200 bg-white p-4">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-700 mb-2">
              Workflow · {workflow.name}
            </h2>
            <p className="text-sm text-ink-600 mb-3">{workflow.description}</p>

            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-500 mt-3 mb-1">
              Statuses
            </h3>
            <div className="flex flex-wrap gap-2 mb-4">
              {workflow.statuses.map((s) => (
                <div
                  key={s.id}
                  className="rounded border border-ink-200 bg-ink-50 px-2 py-1 text-xs"
                  style={{ borderLeftColor: s.color, borderLeftWidth: 3 }}
                >
                  <span className="font-medium">{s.name}</span>
                  <span className="ml-1 text-ink-500">({s.category})</span>
                </div>
              ))}
            </div>

            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-500 mt-3 mb-1">
              Transitions
            </h3>
            <ul className="text-sm space-y-1">
              {workflow.transitions.map((t) => {
                const from = workflow.statuses.find((s) => s.id === t.from_status_id);
                const to = workflow.statuses.find((s) => s.id === t.to_status_id);
                return (
                  <li key={t.id} className="flex items-center gap-2 text-ink-700">
                    <span className="rounded bg-ink-100 px-1.5 py-0.5 text-xs">{from?.name}</span>
                    <ArrowRight size={12} className="text-ink-400" />
                    <span className="rounded bg-ink-100 px-1.5 py-0.5 text-xs">{to?.name}</span>
                    <span className="text-ink-500 text-xs">— {t.name}</span>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </AppShell>
  );
}
