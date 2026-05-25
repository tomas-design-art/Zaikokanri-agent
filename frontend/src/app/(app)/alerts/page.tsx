"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { InventoryRow } from "@/lib/types";

export default function AlertsPage() {
    const low = useQuery({ queryKey: ["alert-low"], queryFn: () => api<InventoryRow[]>("/alerts/low-stock") });
    const exp = useQuery({ queryKey: ["alert-exp"], queryFn: () => api<InventoryRow[]>("/alerts/expiring", { params: { days: 30 } }) });

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">アラート</h1>
            <section>
                <h2 className="font-semibold mb-2">在庫不足 ({low.data?.length ?? 0})</h2>
                <div className="card overflow-x-auto">
                    <table className="table-zk">
                        <thead><tr><th>物品</th><th>カテゴリ</th><th className="text-right">在庫</th><th className="text-right">閾値</th></tr></thead>
                        <tbody>
                            {low.data?.map((r) => (
                                <tr key={r.item_id}>
                                    <td>{r.item_name}</td><td>{r.category}</td>
                                    <td className="text-right text-amber-600 font-semibold tabular-nums">{r.quantity}</td>
                                    <td className="text-right tabular-nums">{r.threshold}</td>
                                </tr>
                            )) || <tr><td colSpan={4} className="text-center py-4 text-slate-500">読み込み中...</td></tr>}
                        </tbody>
                    </table>
                </div>
            </section>
            <section>
                <h2 className="font-semibold mb-2">期限間近 / 期限切れ ({exp.data?.length ?? 0})</h2>
                <div className="card overflow-x-auto">
                    <table className="table-zk">
                        <thead><tr><th>物品</th><th>カテゴリ</th><th>有効期限</th><th>状態</th></tr></thead>
                        <tbody>
                            {exp.data?.map((r) => (
                                <tr key={r.item_id}>
                                    <td>{r.item_name}</td><td>{r.category}</td><td>{r.expiry_date}</td>
                                    <td>
                                        {r.is_expired && <span className="badge bg-red-100 text-red-700">期限切れ</span>}
                                        {r.is_expiring_soon && <span className="badge bg-orange-100 text-orange-700">期限間近</span>}
                                    </td>
                                </tr>
                            )) || <tr><td colSpan={4} className="text-center py-4 text-slate-500">読み込み中...</td></tr>}
                        </tbody>
                    </table>
                </div>
            </section>
        </div>
    );
}
