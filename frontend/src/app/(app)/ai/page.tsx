"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiJson } from "@/lib/api";

interface QueryResp { answer: string; sql: string | null; rows: Record<string, unknown>[] | null; }
interface Suggest { item_id: number; item_name: string; current_quantity: number; threshold: number; suggested_qty: number; reason: string; }

export default function AiPage() {
    const [q, setQ] = useState("");
    const ask = useMutation({
        mutationFn: () => apiJson<QueryResp>("/ai/query", { question: q }),
        onError: (e: Error) => toast.error(e.message),
    });
    const sugg = useQuery({ queryKey: ["ai-sugg"], queryFn: () => api<Suggest[]>("/ai/order-suggest") });

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">AIアシスタント</h1>
            <section className="card p-4 space-y-3">
                <h2 className="font-semibold">自然言語クエリ</h2>
                <div className="flex gap-2">
                    <input className="input flex-1" placeholder="例: 期限切れの物品を全部教えて" value={q} onChange={(e) => setQ(e.target.value)} />
                    <button className="btn-primary" disabled={!q || ask.isPending} onClick={() => ask.mutate()}>{ask.isPending ? "..." : "尋ねる"}</button>
                </div>
                {ask.data && (
                    <div className="space-y-2">
                        <div className="text-sm">{ask.data.answer}</div>
                        {ask.data.sql && <pre className="bg-slate-100 p-2 text-xs rounded overflow-x-auto">{ask.data.sql}</pre>}
                        {ask.data.rows && ask.data.rows.length > 0 && (
                            <div className="overflow-x-auto">
                                <table className="table-zk">
                                    <thead><tr>{Object.keys(ask.data.rows[0]).map((k) => <th key={k}>{k}</th>)}</tr></thead>
                                    <tbody>
                                        {ask.data.rows.map((r, i) => <tr key={i}>{Object.values(r).map((v, j) => <td key={j}>{String(v)}</td>)}</tr>)}
                                    </tbody>
                                </table>
                            </div>
                        )}
                    </div>
                )}
            </section>
            <section className="card p-4">
                <h2 className="font-semibold mb-2">発注提案 ({sugg.data?.length ?? 0})</h2>
                <table className="table-zk">
                    <thead><tr><th>物品</th><th className="text-right">現在庫</th><th className="text-right">閾値</th><th className="text-right">推奨</th><th>理由</th></tr></thead>
                    <tbody>
                        {sugg.data?.map((s) => (
                            <tr key={s.item_id}>
                                <td>{s.item_name}</td>
                                <td className="text-right tabular-nums">{s.current_quantity}</td>
                                <td className="text-right tabular-nums">{s.threshold}</td>
                                <td className="text-right tabular-nums font-semibold text-brand-600">{s.suggested_qty}</td>
                                <td className="text-xs text-slate-500">{s.reason}</td>
                            </tr>
                        )) || <tr><td colSpan={5} className="text-center py-6">読み込み中...</td></tr>}
                    </tbody>
                </table>
            </section>
        </div>
    );
}
