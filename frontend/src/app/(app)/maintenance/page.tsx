"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiPost, errorText } from "@/lib/api";
import { PageHeader } from "@/components/ui";

export default function MaintenancePage() {
    const qc = useQueryClient();
    const schema = useQuery({ queryKey: ["mnt-schema"], queryFn: () => api<Record<string, string[]>>("/maintenance/schema") });
    const ready = useQuery({ queryKey: ["readyz"], queryFn: () => api<{ ok: boolean; db: string }>("/readyz") });
    const repair = useMutation({
        mutationFn: () => apiPost<{ created: number }>("/maintenance/repair-inventory"),
        onSuccess: (r) => { toast.success(r.created ? `在庫レコードを ${r.created} 件補いました` : "欠けている在庫レコードはありません"); qc.invalidateQueries({ queryKey: ["inventory"] }); },
        onError: (e) => toast.error(errorText(e)),
    });

    return (
        <div className="space-y-4">
            <PageHeader title="メンテナンス" />
            <section className="card space-y-2 p-4" aria-label="接続状態">
                <h2 className="font-semibold">データベースの接続</h2>
                <p className="text-sm">{ready.isLoading ? "確認中..." : ready.data?.ok ? "✅ 正常に接続できています" : `⚠️ ${ready.error ? errorText(ready.error) : "接続できません"}`}</p>
            </section>
            <section className="card space-y-2 p-4" aria-label="在庫レコード修復">
                <h2 className="font-semibold">在庫レコードの修復</h2>
                <p className="text-sm text-slate-500">物品マスターにあるのに在庫の行が欠けている場合、在庫0で補います。</p>
                <button className="btn-primary" onClick={() => repair.mutate()} disabled={repair.isPending}>修復を実行</button>
            </section>
            <section className="card p-4" aria-label="DBスキーマ">
                <h2 className="mb-2 font-semibold">データベースの構成</h2>
                <pre className="overflow-x-auto rounded bg-slate-100 p-3 text-xs">{schema.data ? JSON.stringify(schema.data, null, 2) : "読み込み中..."}</pre>
            </section>
        </div>
    );
}
