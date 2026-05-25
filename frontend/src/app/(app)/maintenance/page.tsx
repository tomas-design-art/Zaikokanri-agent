"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiJson } from "@/lib/api";

export default function MaintenancePage() {
    const qc = useQueryClient();
    const schema = useQuery({ queryKey: ["mnt-schema"], queryFn: () => api<Record<string, string[]>>("/maintenance/schema") });

    const repair = useMutation({
        mutationFn: () => apiJson<{ created: number }>("/maintenance/repair-inventory", {}),
        onSuccess: (r) => { toast.success(`修復: ${r.created} 行追加`); qc.invalidateQueries({ queryKey: ["mnt-schema"] }); },
        onError: (e: Error) => toast.error(e.message),
    });

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-bold">メンテナンス</h1>
            <div className="card p-4 space-y-2">
                <h2 className="font-semibold">在庫レコード修復</h2>
                <p className="text-sm text-slate-500">物品マスタにあるが在庫レコードが欠落している場合、ゼロで補完します。</p>
                <button className="btn-primary" onClick={() => repair.mutate()} disabled={repair.isPending}>修復実行</button>
            </div>
            <div className="card p-4">
                <h2 className="font-semibold mb-2">DBスキーマ</h2>
                <pre className="bg-slate-100 p-3 text-xs rounded overflow-x-auto">{JSON.stringify(schema.data, null, 2)}</pre>
            </div>
        </div>
    );
}
