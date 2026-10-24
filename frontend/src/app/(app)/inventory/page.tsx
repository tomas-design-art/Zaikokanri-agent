"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, downloadFile, errorText } from "@/lib/api";
import { cn } from "@/lib/cn";
import { fmtQty } from "@/lib/format";
import type { CategoryOut, InventoryRow, Page } from "@/lib/types";
import { useDebouncedValue } from "@/lib/use-debounced-value";
import { useMe } from "@/lib/use-me";
import { useScope } from "@/lib/use-scope";
import { Field, ownerLabel, PageHeader, Pager, ScopeToggle, StateRow, useDepartmentNames } from "@/components/ui";

const PER_PAGE = 100;

export default function InventoryPage() {
    const { isAdmin, isGuest } = useMe();
    const { scope } = useScope();
    const deptNames = useDepartmentNames();
    const [q, setQ] = useState("");
    const [category, setCategory] = useState("");
    const [onlyLow, setOnlyLow] = useState(false);
    const [page, setPage] = useState(1);
    const qDeb = useDebouncedValue(q, 300);
    const params = { q: qDeb, category, only_low_stock: onlyLow, scope };

    const cats = useQuery({ queryKey: ["cats"], queryFn: () => api<CategoryOut[]>("/categories") });
    const { data, isLoading, error } = useQuery({
        queryKey: ["inventory", params, page],
        queryFn: () => api<Page<InventoryRow>>("/inventory", { params: { ...params, page, per_page: PER_PAGE } }),
    });

    async function exportCsv() {
        try { await downloadFile("/inventory/export.csv", "在庫一覧.csv", { params }); } catch (e) { toast.error(errorText(e)); }
    }

    return (
        <div className="space-y-4">
            <PageHeader title="在庫一覧" actions={<>
                <button className="btn-secondary" onClick={exportCsv}>CSV ダウンロード</button>
                {isAdmin && <Link href="/items/new" className="btn-primary">＋ 物品を登録</Link>}
            </>} />
            <div className="card flex flex-wrap items-end gap-3 p-3">
                <Field label="検索" className="w-full sm:w-72">
                    {(id) => <input id={id} className="input" placeholder="物品名 / コード / 業者" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />}
                </Field>
                <Field label="カテゴリ" className="w-full sm:w-48">
                    {(id) => (
                        <select id={id} className="input" value={category} onChange={(e) => { setCategory(e.target.value); setPage(1); }}>
                            <option value="">すべて</option>
                            {cats.data?.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
                        </select>
                    )}
                </Field>
                <label className="flex items-center gap-1 pb-2 text-sm">
                    <input type="checkbox" checked={onlyLow} onChange={(e) => { setOnlyLow(e.target.checked); setPage(1); }} />
                    在庫不足のみ
                </label>
                <ScopeToggle className="mb-1" />
                <span className="ml-auto pb-2 text-sm text-slate-500" aria-live="polite">{data ? `${data.total} 件` : ""}</span>
            </div>
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead>
                        <tr>
                            <th>物品名</th><th>コード</th><th>カテゴリ</th><th>所属</th><th>保管場所</th>{!isGuest && <th>業者</th>}
                            <th className="text-right">在庫</th><th className="text-right">発注点</th><th>有効期限</th><th>状態</th>{isAdmin && <th />}
                        </tr>
                    </thead>
                    <tbody>
                        <StateRow colSpan={9 + (isGuest ? 0 : 1) + (isAdmin ? 1 : 0)} loading={isLoading} error={error} empty={data?.items.length === 0} />
                        {data?.items.map((r) => (
                            <tr key={r.item_id}>
                                <td className="font-medium">{r.item_name}</td>
                                <td className="text-slate-500">{r.item_code || "-"}</td>
                                <td>{r.category}</td>
                                <td className="text-slate-600">{ownerLabel(deptNames, r.owner_department_id, r.is_common)}</td>
                                <td className="text-slate-600">{r.location || "-"}</td>
                                {!isGuest && <td className="text-slate-600">{r.vendor_name || "-"}</td>}
                                <td className={cn("text-right font-medium tabular-nums", r.is_low_stock && "text-amber-600")}>{fmtQty(r.quantity, r.unit)}</td>
                                <td className="text-right text-slate-500 tabular-nums">{r.threshold}</td>
                                <td>{r.expiry_date || "-"}</td>
                                <td className="space-x-1">
                                    {r.is_expired && <span className="badge bg-red-100 text-red-700">期限切れ</span>}
                                    {r.is_expiring_soon && <span className="badge bg-orange-100 text-orange-700">期限間近</span>}
                                    {r.is_low_stock && <span className="badge bg-amber-100 text-amber-800">在庫不足</span>}
                                </td>
                                {isAdmin && <td><Link href={`/items/${r.item_id}`} className="btn-link text-xs">編集・調整</Link></td>}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            {data && <Pager page={page} perPage={PER_PAGE} total={data.total} onChange={setPage} />}
        </div>
    );
}
