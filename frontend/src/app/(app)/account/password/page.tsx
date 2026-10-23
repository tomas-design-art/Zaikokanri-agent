"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiPost, errorText } from "@/lib/api";
import { ME_KEY, useMe } from "@/lib/use-me";
import { Field, PageHeader } from "@/components/ui";

export default function PasswordPage() {
    const router = useRouter();
    const qc = useQueryClient();
    const { me } = useMe();
    const [current, setCurrent] = useState("");
    const [next, setNext] = useState("");
    const [confirm, setConfirm] = useState("");
    const tooShort = next.length > 0 && next.length < 8;
    const mismatch = confirm.length > 0 && next !== confirm;

    const save = useMutation({
        mutationFn: () => apiPost("/auth/password", { current_password: current, new_password: next }),
        onSuccess: async () => {
            toast.success("パスワードを変更しました");
            await qc.invalidateQueries({ queryKey: ME_KEY });
            router.replace("/dashboard");
        },
        onError: (e) => toast.error(errorText(e)),
    });

    return (
        <div className="max-w-md space-y-4">
            <PageHeader title="パスワード変更" />
            {me?.must_change_password && (
                <p role="alert" className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900">
                    初期パスワード（または管理者が設定した仮のパスワード）のままです。使い始める前に新しいパスワードを設定してください。
                </p>
            )}
            <form className="card space-y-3 p-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
                <Field label="今のパスワード">{(id) => <input id={id} type="password" className="input" value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" required />}</Field>
                <Field label="新しいパスワード" hint="8文字以上" error={tooShort ? "8文字以上にしてください" : null}>
                    {(id) => <input id={id} type="password" className="input" value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" required aria-invalid={tooShort} />}
                </Field>
                <Field label="新しいパスワード（確認）" error={mismatch ? "上と同じパスワードを入力してください" : null}>
                    {(id) => <input id={id} type="password" className="input" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" required aria-invalid={mismatch} />}
                </Field>
                <button type="submit" className="btn-primary w-full" disabled={!current || next.length < 8 || next !== confirm || save.isPending}>
                    {save.isPending ? "変更中..." : "変更する"}
                </button>
            </form>
        </div>
    );
}
