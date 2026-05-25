"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiPatch } from "@/lib/api";
import type { CategoryOut, ItemOut, VendorOut } from "@/lib/types";

export default function ItemEditPage() {
    const router = useRouter();
    const qc = useQueryClient();
    const params = useParams<{ id: string }>();
    const id = Number(params.id);

    const { data: item } = useQuery({
        queryKey: ["item", id],
        queryFn: () => api<ItemOut>(`/items/${id}`),
        enabled: !!id,
    });
    const cats = useQuery({ queryKey: ["cats"], queryFn: () => api<CategoryOut[]>("/categories") });
    const vendors = useQuery({ queryKey: ["vendors"], queryFn: () => api<VendorOut[]>("/vendors") });

    const [form, setForm] = useState<Partial<ItemOut>>({});
    useEffect(() => { if (item) setForm(item); }, [item]);

    const save = useMutation({
        mutationFn: () => apiPatch(`/items/${id}`, {
            item_name: form.item_name,
            item_code: form.item_code,
            category: form.category,
            vendor_name: form.vendor_name,
            unit_price: form.unit_price,
            reorder_point: form.reorder_point,
            location_text: form.location_text,
            expiry_date: form.expiry_date,
            department_tags: form.department_tags,
        }),
        onSuccess: () => {
            toast.success("更新しました");
            qc.invalidateQueries({ queryKey: ["item", id] });
            qc.invalidateQueries({ queryKey: ["items"] });
            qc.invalidateQueries({ queryKey: ["inventory"] });
            router.push("/items");
        },
        onError: (e: Error) => toast.error(e.message),
    });

    if (!item) return <div className="text-slate-500">読み込み中...</div>;

    return (
        <div className="space-y-4 max-w-3xl">
            <h1 className="text-2xl font-bold">物品編集</h1>
            <div className="card p-4 grid grid-cols-2 gap-3">
                <div className="col-span-2"><label className="label">物品名 *</label>
                    <input className="input" value={form.item_name ?? ""} onChange={(e) => setForm({ ...form, item_name: e.target.value })} /></div>
                <div><label className="label">物品コード</label>
                    <input className="input" value={form.item_code ?? ""} onChange={(e) => setForm({ ...form, item_code: e.target.value })} /></div>
                <div><label className="label">カテゴリ *</label>
                    <select className="input" value={form.category ?? ""} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                        {cats.data?.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
                    </select></div>
                <div><label className="label">業者</label>
                    <select className="input" value={form.vendor_name ?? ""} onChange={(e) => setForm({ ...form, vendor_name: e.target.value })}>
                        <option value="">未設定</option>
                        {vendors.data?.map((v) => <option key={v.id} value={v.vendor_name}>{v.vendor_name}</option>)}
                    </select></div>
                <div><label className="label">単価</label>
                    <input type="number" className="input" value={form.unit_price ?? 0} onChange={(e) => setForm({ ...form, unit_price: parseFloat(e.target.value) })} /></div>
                <div><label className="label">発注点</label>
                    <input type="number" className="input" value={form.reorder_point ?? 0} onChange={(e) => setForm({ ...form, reorder_point: parseInt(e.target.value) })} /></div>
                <div><label className="label">保管場所</label>
                    <input className="input" value={form.location_text ?? ""} onChange={(e) => setForm({ ...form, location_text: e.target.value })} /></div>
                <div><label className="label">有効期限</label>
                    <input type="date" className="input" value={form.expiry_date ?? ""} onChange={(e) => setForm({ ...form, expiry_date: e.target.value })} /></div>
                <div className="col-span-2"><label className="label">部署タグ (カンマ区切り)</label>
                    <input className="input" value={form.department_tags ?? ""} onChange={(e) => setForm({ ...form, department_tags: e.target.value })} /></div>
                <div className="col-span-2 flex gap-2">
                    <button className="btn-primary" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? "保存中..." : "保存"}</button>
                    <button className="btn-secondary" onClick={() => router.push("/items")}>キャンセル</button>
                </div>
            </div>
        </div>
    );
}
