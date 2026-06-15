"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { api } from "@/lib/api";
import type { Project } from "@/lib/types";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  useEffect(() => {
    api.projects().then(setProjects);
  }, []);

  return (
    <AppShell>
      <div className="px-8 py-6 max-w-6xl">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold">Projects</h1>
          <p className="text-ink-600 mt-1 text-sm">
            All projects across the workspace. Click into a project to see its board.
          </p>
        </header>

        <div className="grid grid-cols-2 gap-4">
          {projects.map((p) => (
            <Link
              key={p.key}
              href={`/board?key=${p.key}`}
              className="block rounded border border-ink-200 bg-white p-5 shadow-card hover:border-brand-500"
            >
              <div className="flex items-center gap-3 mb-2">
                <span
                  className="inline-block h-8 w-8 rounded"
                  style={{ backgroundColor: p.avatar_color }}
                />
                <div>
                  <div className="text-[11px] font-mono text-ink-500">{p.key}</div>
                  <div className="font-semibold text-lg">{p.name}</div>
                </div>
                <span className="ml-auto inline-flex items-center rounded-sm border border-ink-200 px-2 py-0.5 text-[10px] uppercase tracking-wide text-ink-600">
                  {p.project_type}
                </span>
              </div>
              <p className="text-sm text-ink-600">{p.description}</p>
              <div className="mt-3 flex gap-2 text-[11px] text-ink-500">
                <Link href={`/board?key=${p.key}`} className="hover:underline">Board</Link>
                <Link href={`/backlog?key=${p.key}`} className="hover:underline">Backlog</Link>
                <Link href={`/settings?key=${p.key}`} className="hover:underline">Settings</Link>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </AppShell>
  );
}
