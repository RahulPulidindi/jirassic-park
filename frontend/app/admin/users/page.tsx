"use client";

import { useEffect, useState } from "react";

import { AppShell } from "@/components/AppShell";
import { Avatar } from "@/components/Avatar";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";

export default function UsersPage() {
  const [users, setUsers] = useState<User[]>([]);
  useEffect(() => {
    api.users().then(setUsers);
  }, []);

  return (
    <AppShell>
      <div className="px-6 py-5 max-w-4xl">
        <header className="mb-4">
          <h1 className="text-xl font-semibold">Users</h1>
          <p className="text-sm text-ink-600 mt-0.5">
            {users.length} users across the workspace.
          </p>
        </header>

        <div className="rounded border border-ink-200 bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-ink-50 text-left text-[11px] uppercase tracking-wide text-ink-600">
                <th className="px-3 py-2">User</th>
                <th className="px-3 py-2">Email</th>
                <th className="px-3 py-2">Role</th>
                <th className="px-3 py-2">ID</th>
              </tr>
            </thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} className="border-t border-ink-100">
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <Avatar name={u.name} color={u.avatar_color} size={24} />
                      <span>{u.name}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2 text-ink-700">{u.email}</td>
                  <td className="px-3 py-2">
                    <span
                      className={
                        "rounded px-1.5 py-0.5 text-[11px] uppercase tracking-wide " +
                        (u.role === "admin"
                          ? "bg-red-100 text-red-700"
                          : u.role === "viewer"
                          ? "bg-ink-100 text-ink-700"
                          : "bg-brand-50 text-brand-700")
                      }
                    >
                      {u.role}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-[12px] text-ink-500">{u.id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </AppShell>
  );
}
