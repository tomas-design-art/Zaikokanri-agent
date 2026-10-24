"use client";

import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiPost, errorText } from "@/lib/api";
import { useScope } from "@/lib/use-scope";
import { Field, PageHeader, ScopeToggle, StateRow } from "@/components/ui";

interface QueryResp { answer: string; sql: string | null; rows: Record<string, unknown>[] | null }
interface Suggest { item_id: number; item_name: string; current_quantity: number; threshold: number; suggested_qty: number; reason: string }

export default function AiPage() {
    const [q, setQ] = useState("");
    const ask = useMutation({
        mutationFn: () => apiPost<QueryResp>("/ai/query", { question: q }),
        onError: (e) => toast.error(errorText(e)),
    });
    const { scope } = useScope();
    const sugg = useQuery({ queryKey: ["ai-sugg", scope], queryFn: () => api<Suggest[]>("/ai/order-suggest", { params: { scope } }) });

    return (
        <div className="space-y-6">
            <PageHeader title="AIアシスタント" description="質問から読み取り専用の検索を作って実行します（物品・在庫・履歴・部署・カテゴリ・業者だけが対象、最大200件。AI の質問は部署の絞り込みを通らず、全部署が対象）" actions={<ScopeToggle />} />
            <section className="card space-y-3 p-4" aria-label="自然言語で検索">
                <form className="flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); ask.mutate(); }}>
                    <Field label="質問" className="min-w-64 flex-1">{(id) => <input id={id} className="input" placeholder="例：期限切れの物品を全部教えて" value={q} onChange={(e) => setQ(e.target.value)} maxLength={500} />}</Field>
                    <button className="btn-primary" disabled={!q.trim() || ask.isPending}>{ask.isPending ? "考え中..." : "尋ねる"}</button>
                </form>
                {ask.data && (
                    <div className="space-y-2">
                        <p className="text-sm" role="status">{ask.data.answer}</p>
                        {ask.data.sql && <pre className="overflow-x-auto rounded bg-slate-100 p-2 text-xs">{ask.data.sql}</pre>}
                        {ask.data.rows && ask.data.rows.length > 0 && (
                            <div className="overflow-x-auto">
                                <table className="table-zk">
                                    <thead><tr>{Object.keys(ask.data.rows[0]).map((k) => <th key={k}>{k}</th>)}</tr></thead>
                                    <tbody>{ask.data.rows.map((r, i) => <tr key={i}>{Object.values(r).map((v, j) => <td key={j}>{String(v ?? "")}</td>)}</tr>)}</tbody>
                                </table>
                            </div>
                        )}
                    </div>
                )}
            </section>
            <section className="card p-4" aria-label="発注の提案">
                <h2 className="mb-2 font-semibold">発注の提案（{sugg.data?.length ?? 0}件）</h2>
                <table className="table-zk">
                    <thead><tr><th>物品</th><th className="text-right">現在庫</th><th className="text-right">発注点</th><th className="text-right">推奨数</th><th>理由</th></tr></thead>
                    <tbody>
                        <StateRow colSpan={5} loading={sugg.isLoading} error={sugg.error} empty={sugg.data?.length === 0} emptyText="今は発注が必要な物品はありません" />
                        {sugg.data?.map((s) => (
                            <tr key={s.item_id}>
                                <td>{s.item_name}</td>
                                <td className="text-right tabular-nums">{s.current_quantity}</td>
                                <td className="text-right tabular-nums">{s.threshold}</td>
                                <td className="text-right font-semibold text-brand-600 tabular-nums">{s.suggested_qty}</td>
                                <td className="text-xs text-slate-500">{s.reason}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </section>
        </div>
    );
}
