"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiJson } from "@/lib/api";
import type { CategoryOut, VendorOut, ItemOut } from "@/lib/types";

export default function NewItemPage() {
    const router = useRouter();
    const qc = useQueryClient();
    const cats = useQuery({ queryKey: ["cats"], queryFn: () => api<CategoryOut[]>("/categories") });
    const vendors = useQuery({ queryKey: ["vendors"], queryFn: () => api<VendorOut[]>("/vendors") });

    const [form, setForm] = useState({
        item_name: "", item_code: "", category: "", vendor_name: "",
        unit_price: 0, reorder_point: 10, location_text: "", expiry_date: "",
    });

    const create = useMutation({
        mutationFn: () => apiJson<ItemOut>("/items", form),
        onSuccess: (created) => {
            toast.success("登録しました");
            qc.invalidateQueries({ queryKey: ["items"] });
            qc.invalidateQueries({ queryKey: ["inventory"] });
            router.push(`/items/${created.id}`);
        },
        onError: (e: Error) => toast.error(e.message),
    });

    return (
        <div className="space-y-4 max-w-3xl">
            <h1 className="text-2xl font-bold">物品を新規登録</h1>
            <div className="card p-4 grid grid-cols-2 gap-3">
                <div className="col-span-2"><label className="label">物品名 *</label>
                    <input className="input" value={form.item_name} onChange={(e) => setForm({ ...form, item_name: e.target.value })} /></div>
                <div><label className="label">物品コード</label>
                    <input className="input" value={form.item_code} onChange={(e) => setForm({ ...form, item_code: e.target.value })} /></div>
                <div><label className="label">カテゴリ *</label>
                    <select className="input" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
                        <option value="">選択...</option>
                        {cats.data?.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
                    </select></div>
                <div><label className="label">業者</label>
                    <select className="input" value={form.vendor_name} onChange={(e) => setForm({ ...form, vendor_name: e.target.value })}>
                        <option value="">未設定</option>
                        {vendors.data?.map((v) => <option key={v.id} value={v.vendor_name}>{v.vendor_name}</option>)}
                    </select></div>
                <div><label className="label">単価</label>
                    <input type="number" className="input" value={form.unit_price} onChange={(e) => setForm({ ...form, unit_price: parseFloat(e.target.value || "0") })} /></div>
                <div><label className="label">発注点</label>
                    <input type="number" className="input" value={form.reorder_point} onChange={(e) => setForm({ ...form, reorder_point: parseInt(e.target.value || "0") })} /></div>
                <div><label className="label">保管場所</label>
                    <input className="input" value={form.location_text} onChange={(e) => setForm({ ...form, location_text: e.target.value })} /></div>
                <div><label className="label">有効期限</label>
                    <input type="date" className="input" value={form.expiry_date} onChange={(e) => setForm({ ...form, expiry_date: e.target.value })} /></div>
                <div className="col-span-2 flex gap-2">
                    <button className="btn-primary" disabled={!form.item_name || !form.category || create.isPending} onClick={() => create.mutate()}>
                        {create.isPending ? "登録中..." : "登録"}
                    </button>
                    <button className="btn-secondary" onClick={() => router.push("/items")}>キャンセル</button>
                </div>
            </div>
        </div>
    );
}
