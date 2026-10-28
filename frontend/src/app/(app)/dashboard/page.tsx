"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { ArrowDownToLine, ArrowUpFromLine, ClipboardList, History, ShoppingCart, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import type { InventoryKPI, Todo } from "@/lib/types";
import { useMe } from "@/lib/use-me";
import { useScope } from "@/lib/use-scope";
import { PageHeader, ScopeToggle } from "@/components/ui";

function KpiCard({ label, value, color, href }: { label: string; value: number | string; color: string; href: string }) {
    return (
        <Link href={href} className="card block p-4 hover:bg-slate-50">
            <div className="text-xs text-slate-500">{label}</div>
            <div className={`mt-1 text-3xl font-bold tabular-nums ${color}`}>{value}</div>
        </Link>
    );
}

export default function DashboardPage() {
    const { me, can, isAdmin, isGuest } = useMe();
    const { scope } = useScope();
    const kpi = useQuery({ queryKey: ["kpi", scope], queryFn: () => api<InventoryKPI>("/inventory/kpi", { params: { scope } }) });
    const todo = useQuery({ queryKey: ["todo"], queryFn: () => api<Todo>("/stats/todo"), enabled: can("USER") });
    const k = kpi.data;
    const t = todo.data;

    const quick = [
        { href: "/outbound", label: isGuest ? "出庫を申請する" : "出庫する", icon: ArrowUpFromLine, show: true },
        { href: "/inbound", label: "入庫する", icon: ArrowDownToLine, show: can("USER") },
        { href: "/purchase-requests", label: "発注を申請する", icon: ShoppingCart, show: can("USER") },
        { href: "/disposal", label: isGuest ? "廃棄が要りそうな物を連絡する" : "廃棄を申請する", icon: Trash2, show: true },
        { href: "/stocktake", label: "棚卸し", icon: ClipboardList, show: can("USER") },
        { href: "/history", label: "履歴を見る", icon: History, show: true },
    ].filter((q) => q.show);

    return (
        <div className="space-y-6">
            <PageHeader title="ダッシュボード" description={me ? `${me.display_name} さん、おつかれさまです` : undefined} actions={<ScopeToggle />} />
            {kpi.error ? (
                <p className="text-rose-600">{(kpi.error as Error).message}</p>
            ) : !k ? (
                <div className="text-slate-500">読み込み中...</div>
            ) : (
                <section aria-label="在庫の状況" className="grid grid-cols-2 gap-3 lg:grid-cols-5">
                    <KpiCard label="登録物品数" value={k.total_items} color="text-slate-800" href="/inventory" />
                    <KpiCard label="合計在庫数" value={k.total_quantity.toLocaleString()} color="text-brand-600" href="/inventory" />
                    <KpiCard label="在庫不足" value={k.low_stock_count} color="text-amber-600" href="/alerts" />
                    <KpiCard label="期限切れ" value={k.expired_count} color="text-red-600" href="/alerts" />
                    <KpiCard label="期限間近（30日）" value={k.expiring_soon_count} color="text-orange-600" href="/alerts" />
                </section>
            )}

            {t && (
                <section aria-label="処理待ち" className="card p-4">
                    <h2 className="mb-2 font-semibold">{isAdmin ? "処理待ち（全員分）" : "処理待ち（あなたの申請と、あなたの部署の分）"}</h2>
                    <ul className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2 lg:grid-cols-3">
                        <li><Link className="btn-link" href="/approvals">ゲスト出庫の承認待ち{isAdmin ? "" : "（部署）"}：<b>{t.guest_outbound}</b> 件</Link></li>
                        <li><Link className="btn-link" href="/disposal">ゲストからの廃棄の連絡（部署）：<b>{t.disposal_notices}</b> 件</Link></li>
                        <li><Link className="btn-link" href="/disposal">廃棄申請の承認待ち：<b>{t.disposal}</b> 件</Link></li>
                        <li><Link className="btn-link" href="/purchase-requests">発注申請の承認待ち：<b>{t.purchase}</b> 件</Link></li>
                        <li><Link className="btn-link" href="/inbound?tab=receive">届くのを待っている発注：<b>{t.receivable}</b> 件</Link></li>
                    </ul>
                </section>
            )}

            <section aria-label="よく使う操作" className="grid grid-cols-2 gap-3 lg:grid-cols-3">
                {quick.map((q) => {
                    const Icon = q.icon;
                    return (
                        <Link key={q.href} href={q.href} className="card flex items-center gap-2 p-4 hover:bg-slate-50">
                            <Icon size={18} className="text-brand-600" /> {q.label}
                        </Link>
                    );
                })}
            </section>
        </div>
    );
}
