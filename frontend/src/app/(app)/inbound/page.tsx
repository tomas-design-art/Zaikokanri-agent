"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiJson } from "@/lib/api";
import type { InventoryRow, Page } from "@/lib/types";
import { useDebouncedValue } from "@/lib/use-debounced-value";

export default function InboundPage() {
    const [q, setQ] = useState("");
    const [itemId, setItemId] = useState<number | null>(null);
    const [itemName, setItemName] = useState("");
    const [quantity, setQuantity] = useState(1);
    const [vendor, setVendor] = useState("");
    const [unitPrice, setUnitPrice] = useState<number | "">("");
    const [note, setNote] = useState("");

    const qDeb = useDebouncedValue(q, 250);
    const { data } = useQuery({
        queryKey: ["inv-search-in", qDeb],
        queryFn: () => api<Page<InventoryRow>>("/inventory", { params: { q: qDeb, per_page: 20 } }),
        enabled: qDeb.length > 0,
    });

    const submit = useMutation({
        mutationFn: () => apiJson("/inbound", {
            item_id: itemId, quantity, vendor_name: vendor || null,
            unit_price: unitPrice === "" ? null : Number(unitPrice), note: note || null,
        }),
        onSuccess: () => {
            toast.success("入庫を登録しました");
            setItemId(null); setItemName(""); setQuantity(1); setVendor(""); setUnitPrice(""); setNote("");
        },
        onError: (e: Error) => toast.error(e.message),
    });

    return (
        <div className="space-y-4 max-w-2xl">
            <h1 className="text-2xl font-bold">入庫</h1>
            <div className="card p-4 space-y-3">
                <div>
                    <label className="label">物品検索</label>
                    <input className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder="検索して下から選択" />
                    {data && data.items.length > 0 && itemId === null && (
                        <div className="mt-1 border rounded max-h-40 overflow-y-auto bg-white">
                            {data.items.map((r) => (
                                <button key={r.item_id} className="block w-full text-left px-3 py-1.5 text-sm hover:bg-slate-100"
                                    onClick={() => { setItemId(r.item_id); setItemName(r.item_name); setQ(""); }}>
                                    {r.item_name} <span className="text-xs text-slate-500">({r.category})</span>
                                </button>
                            ))}
                        </div>
                    )}
                </div>
                {itemId && (
                    <div className="rounded bg-brand-50 px-3 py-2 text-sm flex items-center justify-between">
                        <span>選択中: <b>{itemName}</b></span>
                        <button className="text-xs text-red-600" onClick={() => setItemId(null)}>解除</button>
                    </div>
                )}
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <label className="label">数量</label>
                        <input type="number" min={1} className="input" value={quantity} onChange={(e) => setQuantity(parseInt(e.target.value || "1"))} />
                    </div>
                    <div>
                        <label className="label">単価 (任意)</label>
                        <input type="number" className="input" value={unitPrice} onChange={(e) => setUnitPrice(e.target.value === "" ? "" : parseFloat(e.target.value))} />
                    </div>
                </div>
                <div>
                    <label className="label">業者名 (任意)</label>
                    <input className="input" value={vendor} onChange={(e) => setVendor(e.target.value)} />
                </div>
                <div>
                    <label className="label">備考 (任意)</label>
                    <input className="input" value={note} onChange={(e) => setNote(e.target.value)} />
                </div>
                <button className="btn-primary w-full" disabled={!itemId || submit.isPending} onClick={() => submit.mutate()}>
                    {submit.isPending ? "送信中..." : "入庫を登録"}
                </button>
            </div>
        </div>
    );
}
