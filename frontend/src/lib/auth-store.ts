"use client";

import { create } from "zustand";
import type { MeResponse, Role } from "@/lib/types";

interface AuthState {
    user: MeResponse | null;
    loading: boolean;
    setUser: (u: MeResponse | null) => void;
    setLoading: (b: boolean) => void;
    hasRole: (r: Role) => boolean;
}

const LEVEL: Record<Role, number> = { GUEST: 1, USER: 2, ADMIN: 3 };

export const useAuth = create<AuthState>((set, get) => ({
    user: null,
    loading: true,
    setUser: (u) => set({ user: u }),
    setLoading: (b) => set({ loading: b }),
    hasRole: (r) => {
        const u = get().user;
        if (!u) return false;
        return (LEVEL[u.role] ?? 0) >= (LEVEL[r] ?? 99);
    },
}));
