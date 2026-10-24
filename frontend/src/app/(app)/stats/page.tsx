"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { todayJst } from "@/lib/format";
import { CHANGE_TYPE } from "@/lib/labels";
import { Field, PageHeader, StateRow } from "@/components/ui";

interface Monthly { ym: string; change_type: string; total_quantity: number }
interface Top { item_id: number; item_name: string; total_quantity: number }
interface Dept { department: string; total_outbound: number }

function Bar({ value, max }: { value: number; max: number }) {
    return <div className="h-2 rounded bg-brand-500" style={{ width: `${max ? Math.max((value / max) * 100, 2) : 0}%` }} aria-hidden />;
}

export default function StatsPage() {
    const [from, setFrom] = useState(() => `${todayJst().slice(0, 8)}01`);
    const [to, setTo] = useState(todayJst());
    const [months, setMonths] = useState(6);
    const period = { date_from: from, date_to: to };
    const m = useQuery({ queryKey: ["stats-m", months], queryFn: () => api<Monthly[]>("/stats/monthly", { params: { months } }) });
    const t = useQuery({ queryKey: ["stats-t", period], queryFn: () => api<Top[]>("/stats/top-outbound", { params: period }) });
    const d = useQuery({ queryKey: ["stats-d", period], queryFn: () => api<Dept[]>("/stats/by-department", { params: period }) });

    const yms = [...new Set(m.data?.map((r) => r.ym))];
    const cell = (ym: string, type: string) => m.data?.find((r) => r.ym === ym && r.change_type === type)?.total_quantity ?? 0;
    const topMax = Math.max(0, ...(t.data?.map((r) => r.total_quantity) ?? []));
    const deptMax = Math.max(0, ...(d.data?.map((r) => r.total_outbound) ?? []));

    return (
        <div className="space-y-6">
            <PageHeader title="統計" description="調整・棚卸し・取り消しは含みません" />
            <div className="card flex flex-wrap items-end gap-3 p-3">
                <Field label="開始日" className="w-40">{(id) => <input id={id} type="date" className="input" value={from} onChange={(e) => setFrom(e.target.value)} />}</Field>
                <Field label="終了日" className="w-40">{(id) => <input id={id} type="date" className="input" value={to} onChange={(e) => setTo(e.target.value)} />}</Field>
                <span className="pb-2 text-xs text-slate-500">出庫ランキング・部署別に使う期間です</span>
            </div>
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <section className="card p-3" aria-label="出庫の多い物品">
                    <h2 className="mb-2 font-semibold">出庫の多い物品（上位10）</h2>
                    <table className="table-zk">
                        <thead><tr><th>物品</th><th className="w-1/3" /><th className="text-right">数量</th></tr></thead>
                        <tbody>
                            <StateRow colSpan={3} loading={t.isLoading} error={t.error} empty={t.data?.length === 0} emptyText="この期間の出庫はありません" />
                            {t.data?.map((r) => <tr key={r.item_id}><td>{r.item_name}</td><td><Bar value={r.total_quantity} max={topMax} /></td><td className="text-right tabular-nums">{r.total_quantity}</td></tr>)}
                        </tbody>
                    </table>
                </section>
                <section className="card p-3" aria-label="部署別の出庫">
                    <h2 className="mb-2 font-semibold">部署別の出庫</h2>
                    <table className="table-zk">
                        <thead><tr><th>部署</th><th className="w-1/3" /><th className="text-right">数量</th></tr></thead>
                        <tbody>
                            <StateRow colSpan={3} loading={d.isLoading} error={d.error} empty={d.data?.length === 0} emptyText="この期間の出庫はありません" />
                            {d.data?.map((r) => <tr key={r.department}><td>{r.department}</td><td><Bar value={r.total_outbound} max={deptMax} /></td><td className="text-right tabular-nums">{r.total_outbound}</td></tr>)}
                        </tbody>
                    </table>
                </section>
                <section className="card p-3 lg:col-span-2" aria-label="月別">
                    <div className="mb-2 flex items-center justify-between">
                        <h2 className="font-semibold">月別の数量</h2>
                        <label className="text-sm">期間：
                            <select className="input ml-1 inline-block w-auto" value={months} onChange={(e) => setMonths(Number(e.target.value))} aria-label="月別の期間">
                                {[3, 6, 12, 24].map((n) => <option key={n} value={n}>直近{n}か月</option>)}
                            </select>
                        </label>
                    </div>
                    <table className="table-zk">
                        <thead><tr><th>年月</th>{["IN", "OUT", "DISPOSE"].map((k) => <th key={k} className="text-right">{CHANGE_TYPE[k].label}</th>)}</tr></thead>
                        <tbody>
                            <StateRow colSpan={4} loading={m.isLoading} error={m.error} empty={yms.length === 0} emptyText="データがありません" />
                            {yms.map((ym) => <tr key={ym}><td>{ym}</td>{["IN", "OUT", "DISPOSE"].map((k) => <td key={k} className="text-right tabular-nums">{cell(ym, k)}</td>)}</tr>)}
                        </tbody>
                    </table>
                </section>
            </div>
        </div>
    );
}
