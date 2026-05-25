"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import type { InventoryKPI } from "@/lib/types";

function KpiCard({ label, value, color, href }: { label: string; value: number | string; color: string; href?: string }) {
    const inner = (
        <div className="card p-4">
            <div className="text-xs text-slate-500">{label}</div>
            <div className={`mt-1 text-3xl font-bold ${color}`}>{value}</div>
        </div>
    );
    return href ? <Link href={href}>{inner}</Link> : inner;
}

export default function DashboardPage() {
    const { data, isLoading } = useQuery({
        queryKey: ["kpi"],
        queryFn: () => api<InventoryKPI>("/inventory/kpi"),
    });

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">ダッシュボード</h1>
            {isLoading || !data ? (
                <div className="text-slate-500">読み込み中...</div>
            ) : (
                <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
                    <KpiCard label="登録物品数" value={data.total_items} color="text-slate-800" href="/items" />
                    <KpiCard label="合計在庫数" value={data.total_quantity} color="text-brand-600" href="/inventory" />
                    <KpiCard label="在庫不足" value={data.low_stock_count} color="text-amber-600" href="/alerts" />
                    <KpiCard label="期限切れ" value={data.expired_count} color="text-red-600" href="/alerts" />
                    <KpiCard label="期限間近" value={data.expiring_soon_count} color="text-orange-600" href="/alerts" />
                </div>
            )}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
                <Link href="/outbound" className="card p-4 hover:bg-slate-50">📤 出庫処理</Link>
                <Link href="/inbound" className="card p-4 hover:bg-slate-50">📥 入庫処理</Link>
                <Link href="/history" className="card p-4 hover:bg-slate-50">🕒 履歴を見る</Link>
            </div>
        </div>
    );
}
