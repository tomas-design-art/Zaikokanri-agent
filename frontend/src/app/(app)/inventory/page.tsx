"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import type { InventoryRow, Page } from "@/lib/types";
import { cn } from "@/lib/cn";
import { useDebouncedValue } from "@/lib/use-debounced-value";

export default function InventoryPage() {
    const [q, setQ] = useState("");
    const [category, setCategory] = useState("");
    const [onlyLow, setOnlyLow] = useState(false);
    const [page, setPage] = useState(1);
    const per_page = 100;

    const qDeb = useDebouncedValue(q, 300);
    const catDeb = useDebouncedValue(category, 300);
    const { data, isLoading } = useQuery({
        queryKey: ["inventory", qDeb, catDeb, onlyLow, page],
        queryFn: () => api<Page<InventoryRow>>("/inventory", {
            params: { q: qDeb, category: catDeb, only_low_stock: onlyLow, page, per_page },
        }),
    });

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h1 className="text-2xl font-bold">在庫一覧</h1>
                <Link href="/items/new" className="btn-primary">＋ 物品を登録</Link>
            </div>
            <div className="card p-3 flex flex-wrap gap-2 items-center">
                <input className="input max-w-xs" placeholder="物品名 / コード / 業者で検索" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
                <input className="input max-w-[180px]" placeholder="カテゴリ" value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }} />
                <label className="flex items-center gap-1 text-sm">
                    <input type="checkbox" checked={onlyLow} onChange={(e) => { setOnlyLow(e.target.checked); setPage(1); }} />
                    在庫不足のみ
                </label>
                <span className="ml-auto text-sm text-slate-500">{data ? `${data.total} 件` : "..."}</span>
            </div>
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead>
                        <tr>
                            <th>物品名</th><th>コード</th><th>カテゴリ</th><th>業者</th>
                            <th className="text-right">在庫</th><th className="text-right">閾値</th>
                            <th>有効期限</th><th>状態</th><th></th>
                        </tr>
                    </thead>
                    <tbody>
                        {isLoading ? (
                            <tr><td colSpan={9} className="text-center text-slate-500 py-6">読み込み中...</td></tr>
                        ) : (data?.items.length ?? 0) === 0 ? (
                            <tr><td colSpan={9} className="text-center text-slate-500 py-6">該当なし</td></tr>
                        ) : (
                            data!.items.map((r) => (
                                <tr key={r.item_id}>
                                    <td className="font-medium">{r.item_name}</td>
                                    <td className="text-slate-500">{r.item_code || "-"}</td>
                                    <td>{r.category}</td>
                                    <td className="text-slate-600">{r.vendor_name || "-"}</td>
                                    <td className={cn("text-right tabular-nums font-medium", r.is_low_stock && "text-amber-600")}>{r.quantity}</td>
                                    <td className="text-right tabular-nums text-slate-500">{r.threshold}</td>
                                    <td>{r.expiry_date || "-"}</td>
                                    <td>
                                        {r.is_expired && <span className="badge bg-red-100 text-red-700">期限切れ</span>}
                                        {r.is_expiring_soon && <span className="badge bg-orange-100 text-orange-700">期限間近</span>}
                                        {r.is_low_stock && <span className="badge bg-amber-100 text-amber-700 ml-1">在庫不足</span>}
                                    </td>
                                    <td><Link href={`/items/${r.item_id}`} className="text-brand-600 hover:underline text-xs">編集</Link></td>
                                </tr>
                            ))
                        )}
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
