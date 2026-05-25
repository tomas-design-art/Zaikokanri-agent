"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import Link from "next/link";
import { api, apiJson } from "@/lib/api";
import type { ItemOut, Page, CategoryOut, VendorOut } from "@/lib/types";
import { useDebouncedValue } from "@/lib/use-debounced-value";

export default function ItemsPage() {
    const qc = useQueryClient();
    const [q, setQ] = useState("");
    const [page, setPage] = useState(1);
    const per_page = 50;

    const qDeb = useDebouncedValue(q, 300);
    const list = useQuery({
        queryKey: ["items", qDeb, page],
        queryFn: () => api<Page<ItemOut>>("/items", { params: { q: qDeb, page, per_page } }),
    });
    const cats = useQuery({ queryKey: ["cats"], queryFn: () => api<CategoryOut[]>("/categories") });
    const vendors = useQuery({ queryKey: ["vendors"], queryFn: () => api<VendorOut[]>("/vendors") });

    const [open, setOpen] = useState(false);
    const [form, setForm] = useState({
        item_name: "", item_code: "", category: "", vendor_name: "",
        unit_price: 0, reorder_point: 10,
    });

    const create = useMutation({
        mutationFn: () => apiJson("/items", form),
        onSuccess: () => { toast.success("登録しました"); setOpen(false); qc.invalidateQueries({ queryKey: ["items"] }); },
        onError: (e: Error) => toast.error(e.message),
    });

    const deact = useMutation({
        mutationFn: (id: number) => api(`/items/${id}`, { method: "DELETE" }),
        onSuccess: () => { toast.success("無効化しました"); qc.invalidateQueries({ queryKey: ["items"] }); },
        onError: (e: Error) => toast.error(e.message),
    });

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h1 className="text-2xl font-bold">物品マスター</h1>
                <button className="btn-primary" onClick={() => setOpen((v) => !v)}>{open ? "閉じる" : "＋ 新規登録"}</button>
            </div>

            {open && (
                <div className="card p-4 grid grid-cols-2 gap-3">
                    <div><label className="label">物品名 *</label><input className="input" value={form.item_name} onChange={(e) => setForm({ ...form, item_name: e.target.value })} /></div>
                    <div><label className="label">物品コード</label><input className="input" value={form.item_code} onChange={(e) => setForm({ ...form, item_code: e.target.value })} /></div>
                    <div><label className="label">カテゴリ *</label>
                        <select className="input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                            <option value="">選択...</option>
                            {cats.data?.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
                        </select>
                    </div>
                    <div><label className="label">業者</label>
                        <select className="input" value={form.vendor_name} onChange={(e) => setForm({ ...form, vendor_name: e.target.value })}>
                            <option value="">未設定</option>
                            {vendors.data?.map((v) => <option key={v.id} value={v.vendor_name}>{v.vendor_name}</option>)}
                        </select>
                    </div>
                    <div><label className="label">単価</label><input type="number" className="input" value={form.unit_price} onChange={(e) => setForm({ ...form, unit_price: parseFloat(e.target.value) })} /></div>
                    <div><label className="label">発注点</label><input type="number" className="input" value={form.reorder_point} onChange={(e) => setForm({ ...form, reorder_point: parseInt(e.target.value) })} /></div>
                    <div className="col-span-2"><button className="btn-primary" disabled={!form.item_name || !form.category || create.isPending} onClick={() => create.mutate()}>登録</button></div>
                </div>
            )}

            <div className="card p-3">
                <input className="input max-w-md" placeholder="検索" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
            </div>
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr><th>物品名</th><th>コード</th><th>カテゴリ</th><th>業者</th><th className="text-right">単価</th><th></th></tr></thead>
                    <tbody>
                        {list.data?.items.map((i) => (
                            <tr key={i.id}>
                                <td className="font-medium">{i.item_name}</td>
                                <td>{i.item_code || "-"}</td>
                                <td>{i.category}</td>
                                <td>{i.vendor_name || "-"}</td>
                                <td className="text-right tabular-nums">¥{i.unit_price.toLocaleString()}</td>
                                <td className="flex gap-2">
                                    <Link href={`/items/${i.id}`} className="text-xs text-brand-600 hover:underline">編集</Link>
                                    <button className="text-xs text-rose-600" onClick={() => { if (confirm(`「${i.item_name}」を無効化しますか?`)) deact.mutate(i.id); }}>削除</button>
                                </td>
                            </tr>
                        )) || <tr><td colSpan={6} className="text-center py-6 text-slate-500">読み込み中...</td></tr>}
                    </tbody>
                </table>
            </div>
            {list.data && list.data.total > per_page && (
                <div className="flex items-center justify-end gap-2">
                    <button className="btn-secondary" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>前へ</button>
                    <span className="text-sm text-slate-500">{page} / {Math.ceil(list.data.total / per_page)}</span>
                    <button className="btn-secondary" disabled={page * per_page >= list.data.total} onClick={() => setPage((p) => p + 1)}>次へ</button>
                </div>
            )}
        </div>
    );
}
