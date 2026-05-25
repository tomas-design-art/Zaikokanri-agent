"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { HistoryRow, Page } from "@/lib/types";

export default function HistoryPage() {
    const [q, setQ] = useState("");
    const [change_type, setChangeType] = useState("");
    const [date_from, setDateFrom] = useState("");
    const [date_to, setDateTo] = useState("");
    const [page, setPage] = useState(1);
    const per_page = 50;

    const { data, isLoading } = useQuery({
        queryKey: ["history", q, change_type, date_from, date_to, page],
        queryFn: () => api<Page<HistoryRow>>("/history", { params: { q, change_type, date_from, date_to, page, per_page } }),
    });

    function exportCsv() {
        const params = new URLSearchParams();
        if (q) params.set("q", q);
        if (change_type) params.set("change_type", change_type);
        if (date_from) params.set("date_from", date_from);
        if (date_to) params.set("date_to", date_to);
        window.open(`/api/history/export.csv?${params.toString()}`, "_blank");
    }

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h1 className="text-2xl font-bold">履歴</h1>
                <button className="btn-secondary" onClick={exportCsv}>CSV ダウンロード</button>
            </div>
            <div className="card p-3 flex flex-wrap gap-2">
                <input className="input max-w-xs" placeholder="物品名・担当者" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
                <select className="input max-w-[160px]" value={change_type} onChange={(e) => { setChangeType(e.target.value); setPage(1); }}>
                    <option value="">全区分</option>
                    <option value="IN">入庫</option>
                    <option value="OUT">出庫</option>
                    <option value="DISPOSE">廃棄</option>
                </select>
                <input type="date" className="input max-w-[160px]" value={date_from} onChange={(e) => setDateFrom(e.target.value)} />
                <input type="date" className="input max-w-[160px]" value={date_to} onChange={(e) => setDateTo(e.target.value)} />
            </div>
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead>
                        <tr><th>日時</th><th>物品</th><th>区分</th><th className="text-right">数量</th><th>担当</th><th>部署</th><th>状態</th><th>備考</th></tr>
                    </thead>
                    <tbody>
                        {isLoading ? <tr><td colSpan={8} className="text-center py-6 text-slate-500">読み込み中...</td></tr> :
                            data?.items.map((h) => (
                                <tr key={h.id}>
                                    <td className="text-xs text-slate-500">{h.created_at?.replace("T", " ").slice(0, 19)}</td>
                                    <td>{h.item_name}</td>
                                    <td><span className={`badge ${h.change_type === "IN" ? "bg-emerald-100 text-emerald-700" : h.change_type === "OUT" ? "bg-blue-100 text-blue-700" : "bg-rose-100 text-rose-700"}`}>{h.change_type}</span></td>
                                    <td className="text-right tabular-nums">{h.quantity}</td>
                                    <td>{h.user_name}</td>
                                    <td>{h.department || "-"}</td>
                                    <td>{h.status}</td>
                                    <td className="text-xs text-slate-500">{h.note || ""}</td>
                                </tr>
                            ))}
                    </tbody>
                </table>
            </div>
            {data && data.total > per_page && (
                <div className="flex items-center justify-end gap-2">
                    <button className="btn-secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>前へ</button>
                    <span className="text-sm text-slate-500">{page} / {Math.ceil(data.total / per_page)}</span>
                    <button className="btn-secondary" disabled={page * per_page >= data.total} onClick={() => setPage((p) => p + 1)}>次へ</button>
                </div>
            )}
        </div>
    );
}
