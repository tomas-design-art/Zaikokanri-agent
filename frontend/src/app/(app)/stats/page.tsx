"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

interface Monthly { ym: string; change_type: string; total_quantity: number; }
interface Top { item_id: number; item_name: string; total_quantity: number; }
interface Dept { department: string; total_outbound: number; }

export default function StatsPage() {
    const m = useQuery({ queryKey: ["stats-m"], queryFn: () => api<Monthly[]>("/stats/monthly") });
    const t = useQuery({ queryKey: ["stats-t"], queryFn: () => api<Top[]>("/stats/top-outbound") });
    const d = useQuery({ queryKey: ["stats-d"], queryFn: () => api<Dept[]>("/stats/by-department") });

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">統計</h1>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <section className="card p-3">
                    <h2 className="font-semibold mb-2">月別合計</h2>
                    <table className="table-zk">
                        <thead><tr><th>年月</th><th>区分</th><th className="text-right">数量</th></tr></thead>
                        <tbody>
                            {m.data?.map((r, i) => <tr key={i}><td>{r.ym}</td><td>{r.change_type}</td><td className="text-right tabular-nums">{r.total_quantity}</td></tr>) ||
                                <tr><td colSpan={3} className="text-center py-4 text-slate-500">読み込み中...</td></tr>}
                        </tbody>
                    </table>
                </section>
                <section className="card p-3">
                    <h2 className="font-semibold mb-2">出庫トップ10</h2>
                    <table className="table-zk">
                        <thead><tr><th>物品</th><th className="text-right">合計</th></tr></thead>
                        <tbody>
                            {t.data?.map((r) => <tr key={r.item_id}><td>{r.item_name}</td><td className="text-right tabular-nums">{r.total_quantity}</td></tr>) ||
                                <tr><td colSpan={2} className="text-center py-4 text-slate-500">読み込み中...</td></tr>}
                        </tbody>
                    </table>
                </section>
                <section className="card p-3 lg:col-span-2">
                    <h2 className="font-semibold mb-2">部署別出庫</h2>
                    <table className="table-zk">
                        <thead><tr><th>部署</th><th className="text-right">合計</th></tr></thead>
                        <tbody>
                            {d.data?.map((r, i) => <tr key={i}><td>{r.department}</td><td className="text-right tabular-nums">{r.total_outbound}</td></tr>) ||
                                <tr><td colSpan={2} className="text-center py-4 text-slate-500">読み込み中...</td></tr>}
                        </tbody>
                    </table>
                </section>
            </div>
        </div>
    );
}
