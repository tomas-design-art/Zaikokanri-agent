"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiJson } from "@/lib/api";
import type { InventoryRow, Page } from "@/lib/types";
import { useDebouncedValue } from "@/lib/use-debounced-value";

interface CartLine { item_id: number; item_name: string; quantity: number; note: string; }

export default function OutboundPage() {
    const qc = useQueryClient();
    const [q, setQ] = useState("");
    const [cart, setCart] = useState<CartLine[]>([]);

    const qDeb = useDebouncedValue(q, 250);
    const { data, isLoading } = useQuery({
        queryKey: ["inv-search", qDeb],
        queryFn: () => api<Page<InventoryRow>>("/inventory", { params: { q: qDeb, per_page: 30 } }),
    });

    const submit = useMutation({
        mutationFn: async () => {
            if (cart.length === 1) {
                return apiJson("/outbound", { item_id: cart[0].item_id, quantity: cart[0].quantity, note: cart[0].note || null });
            }
            return apiJson("/outbound/bulk", { items: cart.map((c) => ({ item_id: c.item_id, quantity: c.quantity, note: c.note || null })) });
        },
        onSuccess: () => {
            toast.success("出庫を登録しました");
            setCart([]);
            qc.invalidateQueries({ queryKey: ["inv-search"] });
            qc.invalidateQueries({ queryKey: ["kpi"] });
        },
        onError: (e: Error) => toast.error(e.message),
    });

    function addToCart(r: InventoryRow) {
        if (cart.find((c) => c.item_id === r.item_id)) return toast.info("既にカートにあります");
        setCart((c) => [...c, { item_id: r.item_id, item_name: r.item_name, quantity: 1, note: "" }]);
    }

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-bold">出庫</h1>
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                <div className="card p-3 space-y-3">
                    <div>
                        <label className="label">物品を検索</label>
                        <input className="input" placeholder="物品名 / コード / 業者" value={q} onChange={(e) => setQ(e.target.value)} />
                    </div>
                    <div className="max-h-[500px] overflow-y-auto">
                        <table className="table-zk">
                            <thead><tr><th>物品名</th><th className="text-right">在庫</th><th></th></tr></thead>
                            <tbody>
                                {isLoading ? <tr><td colSpan={3} className="text-center py-4 text-slate-500">検索中...</td></tr> :
                                    data?.items.map((r) => (
                                        <tr key={r.item_id}>
                                            <td>{r.item_name}<div className="text-xs text-slate-500">{r.category} / {r.vendor_name || "-"}</div></td>
                                            <td className="text-right tabular-nums">{r.quantity}</td>
                                            <td><button className="btn-secondary text-xs" disabled={r.quantity <= 0} onClick={() => addToCart(r)}>追加</button></td>
                                        </tr>
                                    ))}
                            </tbody>
                        </table>
                    </div>
                </div>
                <div className="card p-3 space-y-3">
                    <h2 className="font-semibold">カート ({cart.length})</h2>
                    {cart.length === 0 ? (
                        <p className="text-sm text-slate-500">物品を追加してください</p>
                    ) : (
                        <div className="space-y-2">
                            {cart.map((c, i) => (
                                <div key={c.item_id} className="border rounded p-2">
                                    <div className="flex items-center justify-between">
                                        <span className="font-medium text-sm">{c.item_name}</span>
                                        <button className="text-xs text-red-600" onClick={() => setCart((arr) => arr.filter((_, j) => j !== i))}>削除</button>
                                    </div>
                                    <div className="grid grid-cols-2 gap-2 mt-1">
                                        <input type="number" min={1} className="input" value={c.quantity}
                                            onChange={(e) => setCart((arr) => arr.map((x, j) => j === i ? { ...x, quantity: parseInt(e.target.value || "1") } : x))} />
                                        <input className="input" placeholder="メモ" value={c.note}
                                            onChange={(e) => setCart((arr) => arr.map((x, j) => j === i ? { ...x, note: e.target.value } : x))} />
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                    <button className="btn-primary w-full" disabled={cart.length === 0 || submit.isPending} onClick={() => submit.mutate()}>
                        {submit.isPending ? "送信中..." : `${cart.length}件まとめて出庫`}
                    </button>
                </div>
            </div>
        </div>
    );
}
