"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiJson, apiPatch } from "@/lib/api";

interface STSession { id: number; name: string; start_date: string | null; end_date: string | null; status: string; note: string | null; }
interface STRecord { id: number; session_id: number; item_id: number; item_name: string; system_qty: number; actual_qty: number | null; diff_qty: number | null; status: string; note: string | null; }

export default function StocktakePage() {
    const qc = useQueryClient();
    const sessions = useQuery({ queryKey: ["st-sessions"], queryFn: () => api<STSession[]>("/stocktake/sessions") });
    const [sel, setSel] = useState<number | null>(null);
    const [name, setName] = useState("");

    const records = useQuery({
        queryKey: ["st-records", sel],
        queryFn: () => api<STRecord[]>(`/stocktake/sessions/${sel}/records`),
        enabled: sel !== null,
    });

    const create = useMutation({
        mutationFn: () => apiJson("/stocktake/sessions", { name }),
        onSuccess: () => { toast.success("セッション作成"); setName(""); qc.invalidateQueries({ queryKey: ["st-sessions"] }); },
        onError: (e: Error) => toast.error(e.message),
    });

    const upd = useMutation({
        mutationFn: ({ id, actual }: { id: number; actual: number }) =>
            apiPatch(`/stocktake/records/${id}`, { actual_qty: actual, status: "COUNTED" }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ["st-records", sel] }),
        onError: (e: Error) => toast.error(e.message),
    });

    const close = useMutation({
        mutationFn: (id: number) => apiJson(`/stocktake/sessions/${id}/close`, {}),
        onSuccess: () => { toast.success("締切しました"); qc.invalidateQueries({ queryKey: ["st-sessions"] }); },
        onError: (e: Error) => toast.error(e.message),
    });

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-bold">棚卸</h1>
            <div className="card p-3 flex gap-2 items-end">
                <div className="flex-1"><label className="label">新規セッション名</label><input className="input" value={name} onChange={(e) => setName(e.target.value)} /></div>
                <button className="btn-primary" disabled={!name || create.isPending} onClick={() => create.mutate()}>作成</button>
            </div>
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr><th>ID</th><th>名前</th><th>状態</th><th></th></tr></thead>
                    <tbody>
                        {sessions.data?.map((s) => (
                            <tr key={s.id} className={sel === s.id ? "bg-brand-50" : ""}>
                                <td>{s.id}</td><td>{s.name}</td><td>{s.status}</td>
                                <td className="flex gap-2">
                                    <button className="text-xs text-brand-700" onClick={() => setSel(s.id)}>レコード表示</button>
                                    {s.status === "OPEN" && <button className="text-xs text-slate-700" onClick={() => close.mutate(s.id)}>締切</button>}
                                    <a className="text-xs text-emerald-700" href={`/api/stocktake/sessions/${s.id}/export.xlsx`}>Excel出力</a>
                                </td>
                            </tr>
                        )) || <tr><td colSpan={4} className="text-center py-4 text-slate-500">読み込み中...</td></tr>}
                    </tbody>
                </table>
            </div>
            {sel !== null && (
                <div className="card overflow-x-auto">
                    <div className="p-3 font-semibold">セッション #{sel} のレコード</div>
                    <table className="table-zk">
                        <thead><tr><th>物品</th><th className="text-right">システム在庫</th><th className="text-right">実数</th><th className="text-right">差異</th><th>状態</th></tr></thead>
                        <tbody>
                            {records.data?.map((r) => (
                                <tr key={r.id}>
                                    <td>{r.item_name}</td>
                                    <td className="text-right tabular-nums">{r.system_qty}</td>
                                    <td className="text-right">
                                        <input type="number" min={0} className="input max-w-[100px] inline-block text-right" defaultValue={r.actual_qty ?? ""}
                                            onBlur={(e) => {
                                                const v = parseInt(e.target.value);
                                                if (!isNaN(v) && v !== r.actual_qty) upd.mutate({ id: r.id, actual: v });
                                            }} />
                                    </td>
                                    <td className={`text-right tabular-nums ${r.diff_qty && r.diff_qty !== 0 ? "text-rose-600" : ""}`}>{r.diff_qty ?? "-"}</td>
                                    <td>{r.status}</td>
                                </tr>
                            )) || <tr><td colSpan={5} className="text-center py-4">読み込み中...</td></tr>}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
