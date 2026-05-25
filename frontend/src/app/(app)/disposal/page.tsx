"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiJson } from "@/lib/api";
import type { DROut, InventoryRow, Page } from "@/lib/types";
import { useAuth } from "@/lib/auth-store";

export default function DisposalPage() {
    const qc = useQueryClient();
    const isAdmin = useAuth((s) => s.user?.role === "ADMIN");

    const [open, setOpen] = useState(false);
    const [q, setQ] = useState("");
    const [itemId, setItemId] = useState<number | null>(null);
    const [itemName, setItemName] = useState("");
    const [qty, setQty] = useState(1);
    const [reason, setReason] = useState("");

    const search = useQuery({
        queryKey: ["dr-search", q],
        queryFn: () => api<Page<InventoryRow>>("/inventory", { params: { q, per_page: 15 } }),
        enabled: q.length > 0,
    });

    const list = useQuery({
        queryKey: ["dr"],
        queryFn: () => api<Page<DROut>>("/disposal-requests", { params: { per_page: 100 } }),
    });

    const create = useMutation({
        mutationFn: () => apiJson("/disposal-requests", { item_id: itemId, quantity: qty, reason }),
        onSuccess: () => {
            toast.success("申請しました");
            setOpen(false); setItemId(null); setItemName(""); setQty(1); setReason("");
            qc.invalidateQueries({ queryKey: ["dr"] });
        },
        onError: (e: Error) => toast.error(e.message),
    });

    const decide = useMutation({
        mutationFn: ({ id, approve, reject }: { id: number; approve: boolean; reject?: string }) =>
            apiJson(`/disposal-requests/${id}/approve`, { approve, reject_reason: reject || null }),
        onSuccess: () => { toast.success("処理しました"); qc.invalidateQueries({ queryKey: ["dr"] }); qc.invalidateQueries({ queryKey: ["kpi"] }); },
        onError: (e: Error) => toast.error(e.message),
    });

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h1 className="text-2xl font-bold">廃棄申請</h1>
                <button className="btn-primary" onClick={() => setOpen((v) => !v)}>{open ? "閉じる" : "＋ 新規申請"}</button>
            </div>

            {open && (
                <div className="card p-4 space-y-3">
                    <div>
                        <label className="label">物品検索</label>
                        <input className="input" value={q} onChange={(e) => setQ(e.target.value)} />
                        {search.data && itemId === null && (
                            <div className="mt-1 border rounded max-h-40 overflow-y-auto bg-white">
                                {search.data.items.map((r) => (
                                    <button key={r.item_id} className="block w-full text-left px-3 py-1.5 text-sm hover:bg-slate-100"
                                        onClick={() => { setItemId(r.item_id); setItemName(r.item_name); setQ(""); }}>
                                        {r.item_name} ({r.quantity})
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                    {itemId && <div className="text-sm">選択: <b>{itemName}</b></div>}
                    <div><label className="label">数量</label><input type="number" min={1} className="input" value={qty} onChange={(e) => setQty(parseInt(e.target.value || "1"))} /></div>
                    <div><label className="label">理由 (必須)</label><textarea className="input" value={reason} onChange={(e) => setReason(e.target.value)} /></div>
                    <button className="btn-primary" disabled={!itemId || !reason || create.isPending} onClick={() => create.mutate()}>申請する</button>
                </div>
            )}

            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr><th>日時</th><th>物品</th><th className="text-right">数量</th><th>理由</th><th>申請者</th><th>状態</th>{isAdmin && <th></th>}</tr></thead>
                    <tbody>
                        {list.data?.items.map((d) => (
                            <tr key={d.id}>
                                <td className="text-xs text-slate-500">{d.created_at?.replace("T", " ").slice(0, 16)}</td>
                                <td>{d.item_name}</td>
                                <td className="text-right tabular-nums">{d.quantity}</td>
                                <td className="text-xs">{d.reason}</td>
                                <td>{d.requester}</td>
                                <td>{d.status}</td>
                                {isAdmin && (
                                    <td>
                                        {d.status === "PENDING" && (
                                            <div className="flex gap-1">
                                                <button className="text-xs text-emerald-700" onClick={() => decide.mutate({ id: d.id, approve: true })}>承認</button>
                                                <button className="text-xs text-rose-700" onClick={() => {
                                                    const r = window.prompt("却下理由") || "";
                                                    if (r) decide.mutate({ id: d.id, approve: false, reject: r });
                                                }}>却下</button>
                                            </div>
                                        )}
                                    </td>
                                )}
                            </tr>
                        )) || <tr><td colSpan={isAdmin ? 7 : 6} className="text-center py-6 text-slate-500">読み込み中...</td></tr>}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
