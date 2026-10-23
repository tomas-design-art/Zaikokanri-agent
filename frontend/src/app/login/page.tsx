"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiPost, errorText } from "@/lib/api";
import type { MeResponse } from "@/lib/types";
import { ME_KEY } from "@/lib/use-me";
import { Field } from "@/components/ui";

// 初期管理者のヒントは開発環境でだけ出す（A-03）
const SHOW_DEMO_HINT = process.env.NODE_ENV !== "production" || process.env.NEXT_PUBLIC_SHOW_DEMO_HINT === "true";

function safeNext(next: string | null): string {
    return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/login") ? next : "/dashboard";
}

function LoginForm() {
    const router = useRouter();
    const search = useSearchParams();
    const qc = useQueryClient();
    const [username, setUsername] = useState("");
    const [password, setPassword] = useState("");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);

    async function onSubmit(e: React.FormEvent) {
        e.preventDefault();
        setBusy(true);
        setError(null);
        try {
            const res = await apiPost<{ user: MeResponse }>("/auth/login", { username: username.trim(), password });
            qc.setQueryData(ME_KEY, res.user);
            toast.success(`ようこそ ${res.user.display_name} さん`);
            router.replace(res.user.must_change_password ? "/account/password" : safeNext(search.get("next")));
        } catch (err) {
            setError(errorText(err));
        } finally {
            setBusy(false);
        }
    }

    return (
        <form onSubmit={onSubmit} className="card w-full max-w-sm space-y-4 p-6">
            <div>
                <h1 className="text-2xl font-bold">在庫管理システム</h1>
                <p className="text-sm text-slate-500">ログインしてください</p>
            </div>
            <Field label="ユーザー名">{(id) => <input id={id} className="input" value={username} onChange={(e) => setUsername(e.target.value)} required autoFocus autoComplete="username" />}</Field>
            <Field label="パスワード">{(id) => <input id={id} type="password" className="input" value={password} onChange={(e) => setPassword(e.target.value)} required autoComplete="current-password" />}</Field>
            {error && <p role="alert" className="rounded bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
            <button type="submit" disabled={busy} className="btn-primary w-full">{busy ? "ログイン中..." : "ログイン"}</button>
            {SHOW_DEMO_HINT && <p className="text-xs text-slate-400">開発用：初期管理者 admin / admin123（初回ログイン時に変更が必要です）</p>}
        </form>
    );
}

export default function LoginPage() {
    return (
        <main className="flex min-h-screen items-center justify-center p-4">
            <Suspense fallback={null}><LoginForm /></Suspense>
        </main>
    );
}
