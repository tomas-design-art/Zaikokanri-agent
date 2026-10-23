"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { MeResponse, Role } from "@/lib/types";

const LEVEL: Record<Role, number> = { GUEST: 1, USER: 2, ADMIN: 3 };

export const ME_KEY = ["me"] as const;

export function useMeQuery() {
    return useQuery({ queryKey: ME_KEY, queryFn: () => api<MeResponse>("/auth/me"), retry: false, staleTime: 60_000 });
}

export function hasRole(user: MeResponse | null | undefined, role: Role): boolean {
    return !!user && (LEVEL[user.role] ?? 0) >= LEVEL[role];
}

/** AppShell の内側（ログイン済み）で使う。 */
export function useMe() {
    const { data } = useMeQuery();
    return {
        me: data ?? null,
        isAdmin: data?.role === "ADMIN",
        isGuest: data?.role === "GUEST",
        can: (role: Role) => hasRole(data, role),
    };
}
