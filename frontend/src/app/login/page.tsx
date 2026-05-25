"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiJson } from "@/lib/api";
import type { MeResponse } from "@/lib/types";
import { useAuth } from "@/lib/auth-store";

export default function LoginPage() {
    const router = useRouter();
    const qc = useQueryClient();
    const setUser = useAuth((s) => s.setUser);
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [busy, setBusy] = useState(false);

    async function onSubmit(e: React.FormEvent) {
        e.preventDefault();
        setBusy(true);
        try {
            const res = await apiJson<{ user: MeResponse }>("/auth/login", { username, password });
            setUser(res.user);
            qc.setQueryData(["me"], res.user);
            toast.success(`ようこそ ${res.user.display_name} さん`);
            router.push("/dashboard");
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : "ログインに失敗しました";
            toast.error(msg);
        } finally {
            setBusy(false);
        }
    }

    return (
        <main className="min-h-screen flex items-center justify-center p-4">
            <form onSubmit={onSubmit} className="card p-6 w-full max-w-sm space-y-4">
                <div>
                    <h1 className="text-2xl font-bold">在庫管理システム</h1>
                    <p className="text-sm text-slate-500">ログインしてください</p>
                </div>
                <div>
                    <label className="label">ユーザー名</label>
                    <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus />
                </div>
                <div>
                    <label className="label">パスワード</label>
                    <input type="password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} required />
                </div>
                <button type="submit" disabled={busy} className="btn-primary w-full">
                    {busy ? "ログイン中..." : "ログイン"}
                </button>
                <p className="text-xs text-slate-400">初期管理者: admin / admin123</p>
            </form>
        </main>
    );
}
