"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiDelete, apiPatch, errorText } from "@/lib/api";
import { fmtYen } from "@/lib/format";
import type { ItemOut, Page } from "@/lib/types";
import { useDebouncedValue } from "@/lib/use-debounced-value";
import { ConfirmDialog, Field, PageHeader, Pager, StateRow } from "@/components/ui";

const PER_PAGE = 50;

export default function ItemsPage() {
    const qc = useQueryClient();
    const [q, setQ] = useState("");
    const [page, setPage] = useState(1);
    const [showInactive, setShowInactive] = useState(false);
    const [target, setTarget] = useState<ItemOut | null>(null);
    const qDeb = useDebouncedValue(q, 300);

    const list = useQuery({
        queryKey: ["items", qDeb, page, showInactive],
        queryFn: () => api<Page<ItemOut>>("/items", { params: { q: qDeb, page, per_page: PER_PAGE, include_inactive: showInactive } }),
    });
    const refresh = () => { for (const k of ["items", "inventory", "kpi"]) qc.invalidateQueries({ queryKey: [k] }); };
    const deact = useMutation({
        mutationFn: (id: number) => apiDelete(`/items/${id}`),
        onSuccess: () => { toast.success("無効にしました"); setTarget(null); refresh(); },
        onError: (e) => toast.error(errorText(e)),
    });
    const react = useMutation({
        mutationFn: (id: number) => apiPatch(`/items/${id}`, { is_active: 1 }),
        onSuccess: () => { toast.success("有効に戻しました"); refresh(); },
        onError: (e) => toast.error(errorText(e)),
    });

    return (
        <div className="space-y-4">
            <PageHeader title="物品マスター" actions={<Link className="btn-primary" href="/items/new">＋ 新規登録</Link>} />
            <div className="card flex flex-wrap items-end gap-3 p-3">
                <Field label="検索" className="w-full sm:w-80">{(id) => <input id={id} className="input" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="物品名 / コード / 業者" />}</Field>
                <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={showInactive} onChange={(e) => { setShowInactive(e.target.checked); setPage(1); }} />無効な物品も表示</label>
            </div>
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr><th>物品名</th><th>コード</th><th>カテゴリ</th><th>単位</th><th>業者</th><th className="text-right">単価</th><th>状態</th><th /></tr></thead>
                    <tbody>
                        <StateRow colSpan={8} loading={list.isLoading} error={list.error} empty={list.data?.items.length === 0} />
                        {list.data?.items.map((i) => (
                            <tr key={i.id} className={i.is_active ? "" : "text-slate-400"}>
                                <td className="font-medium">{i.item_name}</td>
                                <td>{i.item_code || "-"}</td>
                                <td>{i.category}</td>
                                <td>{i.unit}</td>
                                <td>{i.vendor_name || "-"}</td>
                                <td className="text-right tabular-nums">{fmtYen(i.unit_price)}</td>
                                <td>{i.is_active ? <span className="badge bg-emerald-100 text-emerald-700">有効</span> : <span className="badge bg-slate-100 text-slate-500">無効</span>}</td>
                                <td className="space-x-3 whitespace-nowrap">
                                    <Link href={`/items/${i.id}`} className="btn-link text-xs">編集</Link>
                                    {i.is_active
                                        ? <button className="btn-link text-xs text-rose-700" onClick={() => setTarget(i)}>無効にする</button>
                                        : <button className="btn-link text-xs" onClick={() => react.mutate(i.id)}>有効に戻す</button>}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            {list.data && <Pager page={page} perPage={PER_PAGE} total={list.data.total} onChange={setPage} />}
            <ConfirmDialog open={!!target} title="物品を無効にする" confirmText="無効にする" danger busy={deact.isPending}
                onClose={() => setTarget(null)} onConfirm={() => target && deact.mutate(target.id)}>
                「{target?.item_name}」を無効にします。在庫一覧・出庫の候補に出なくなります（履歴は残り、あとで有効に戻せます）。
            </ConfirmDialog>
        </div>
    );
}
