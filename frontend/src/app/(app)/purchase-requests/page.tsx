"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiJson, apiPatch, apiBlob, downloadBlob } from "@/lib/api";
import type { InventoryRow, Page, PROut } from "@/lib/types";
import { useAuth } from "@/lib/auth-store";

type OrderItem = { item_name: string; item_code: string; vendor_part_no: string; quantity: number; unit_price: number | null; subtotal: number | null; notes: string };
type OrderPayload = { vendor: string; subject: string; to: string; ordered_at: string; requester: { department: string; name: string }; items: OrderItem[]; total: number | null; has_unpriced_items: boolean };

export default function PurchaseRequestsPage() {
    const qc = useQueryClient();
    const isAdmin = useAuth((s) => s.user?.role === "ADMIN");
    const [status, setStatus] = useState<string>("");
    const [mine, setMine] = useState(false);

    const list = useQuery({
        queryKey: ["pr", status, mine],
        queryFn: () => api<Page<PROut>>("/purchase-requests", { params: { status, mine, per_page: 100 } }),
    });

    const [open, setOpen] = useState(false);
    const [q, setQ] = useState("");
    const [itemId, setItemId] = useState<number | null>(null);
    const [itemName, setItemName] = useState("");
    const [qty, setQty] = useState(1);
    const [priority, setPriority] = useState("NORMAL");
    const [note, setNote] = useState("");

    const search = useQuery({
        queryKey: ["pr-item-search", q],
        queryFn: () => api<Page<InventoryRow>>("/inventory", { params: { q, per_page: 15 } }),
        enabled: q.length > 0,
    });

    const create = useMutation({
        mutationFn: () => apiJson("/purchase-requests", { item_id: itemId, requested_qty: qty, priority, note: note || null }),
        onSuccess: () => {
            toast.success("申請しました");
            setOpen(false); setItemId(null); setItemName(""); setQty(1); setNote("");
            qc.invalidateQueries({ queryKey: ["pr"] });
        },
        onError: (e: Error) => toast.error(e.message),
    });

    const decide = useMutation({
        mutationFn: ({ id, status, comment }: { id: number; status: string; comment?: string }) =>
            apiPatch(`/purchase-requests/${id}`, { status, admin_comment: comment || null }),
        onSuccess: () => { toast.success("更新しました"); qc.invalidateQueries({ queryKey: ["pr"] }); },
        onError: (e: Error) => toast.error(e.message),
    });

    // 発注書発行 (admin専用)
    const [selected, setSelected] = useState<Set<number>>(new Set());
    const [orderPayloads, setOrderPayloads] = useState<OrderPayload[] | null>(null);
    const [issuing, setIssuing] = useState(false);
    const toggleSelect = (id: number) =>
        setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
    const issueOrder = async () => {
        if (selected.size === 0) return;
        setIssuing(true);
        try {
            const res = await apiJson<{ payloads: OrderPayload[] }>("/orders/preview", { request_ids: Array.from(selected) });
            setOrderPayloads(res.payloads);
        } catch (e) { toast.error((e as Error).message); }
        finally { setIssuing(false); }
    };
    const downloadPdf = async (p: OrderPayload) => {
        try { downloadBlob(await apiBlob("/orders/pdf", { payload: p }), `order_${p.vendor}.pdf`); }
        catch (e) { toast.error((e as Error).message); }
    };
    const downloadExcel = async () => {
        if (!orderPayloads) return;
        try { downloadBlob(await apiBlob("/orders/excel", { payloads: orderPayloads }), "orders.xlsx"); }
        catch (e) { toast.error((e as Error).message); }
    };
    const showEmail = async (p: OrderPayload) => {
        try {
            const res = await apiJson<{ email_text: string }>("/orders/email", { payload: p });
            await navigator.clipboard.writeText(res.email_text).catch(() => { });
            toast.success("メール本文をコピーしました");
            window.alert(res.email_text);
        } catch (e) { toast.error((e as Error).message); }
    };

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <h1 className="text-2xl font-bold">発注申請</h1>
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
                                        {r.item_name}
                                    </button>
                                ))}
                            </div>
                        )}
                    </div>
                    {itemId && <div className="text-sm">選択: <b>{itemName}</b></div>}
                    <div className="grid grid-cols-2 gap-3">
                        <div><label className="label">数量</label><input type="number" min={1} className="input" value={qty} onChange={(e) => setQty(parseInt(e.target.value || "1"))} /></div>
                        <div><label className="label">優先度</label>
                            <select className="input" value={priority} onChange={(e) => setPriority(e.target.value)}>
                                <option value="LOW">低</option><option value="NORMAL">通常</option><option value="HIGH">高</option><option value="URGENT">緊急</option>
                            </select>
                        </div>
                    </div>
                    <div><label className="label">備考</label><input className="input" value={note} onChange={(e) => setNote(e.target.value)} /></div>
                    <button className="btn-primary" disabled={!itemId || create.isPending} onClick={() => create.mutate()}>
                        {create.isPending ? "送信中..." : "申請する"}
                    </button>
                </div>
            )}

            <div className="card p-3 flex gap-2 items-center">
                <select className="input max-w-[160px]" value={status} onChange={(e) => setStatus(e.target.value)}>
                    <option value="">全状態</option>
                    <option value="PENDING">保留中</option>
                    <option value="APPROVED">承認済</option>
                    <option value="REJECTED">却下</option>
                    <option value="ORDERED">発注済</option>
                </select>
                <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />自分の申請のみ</label>
            </div>

            {isAdmin && (
                <div className="card p-3 flex items-center gap-2">
                    <span className="text-sm text-slate-600">承認済から発注書を生成: 選択 {selected.size} 件</span>
                    <button className="btn-primary" disabled={selected.size === 0 || issuing} onClick={issueOrder}>
                        {issuing ? "生成中..." : "発注書を発行"}
                    </button>
                </div>
            )}

            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr>{isAdmin && <th></th>}<th>日時</th><th>物品</th><th className="text-right">数量</th><th>優先度</th><th>申請者</th><th>状態</th><th>コメント</th>{isAdmin && <th></th>}</tr></thead>
                    <tbody>
                        {list.data?.items.map((p) => (
                            <tr key={p.id}>
                                {isAdmin && (
                                    <td>
                                        {p.status === "APPROVED" && (
                                            <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggleSelect(p.id)} />
                                        )}
                                    </td>
                                )}
                                <td className="text-xs text-slate-500">{p.created_at?.replace("T", " ").slice(0, 16)}</td>
                                <td>{p.item_name}</td>
                                <td className="text-right tabular-nums">{p.requested_qty}</td>
                                <td>{p.priority}</td>
                                <td>{p.requested_by}</td>
                                <td>{p.status}</td>
                                <td className="text-xs text-slate-500">{p.admin_comment || ""}</td>
                                {isAdmin && (
                                    <td>
                                        {p.status === "PENDING" && (
                                            <div className="flex gap-1">
                                                <button className="text-xs text-emerald-700" onClick={() => decide.mutate({ id: p.id, status: "APPROVED" })}>承認</button>
                                                <button className="text-xs text-rose-700" onClick={() => decide.mutate({ id: p.id, status: "REJECTED" })}>却下</button>
                                            </div>
                                        )}
                                    </td>
                                )}
                            </tr>
                        )) || <tr><td colSpan={isAdmin ? 9 : 7} className="text-center py-6 text-slate-500">読み込み中...</td></tr>}
                    </tbody>
                </table>
            </div>

            {orderPayloads && (
                <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4" onClick={() => setOrderPayloads(null)}>
                    <div className="bg-white rounded-lg shadow-xl max-w-3xl w-full max-h-[85vh] overflow-y-auto p-5 space-y-4" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-between">
                            <h2 className="text-xl font-bold">発注書プレビュー ({orderPayloads.length}業者)</h2>
                            <div className="flex gap-2">
                                <button className="btn-primary" onClick={downloadExcel}>Excel一括</button>
                                <button className="text-slate-600" onClick={() => setOrderPayloads(null)}>閉じる</button>
                            </div>
                        </div>
                        {orderPayloads.map((p, idx) => (
                            <div key={idx} className="border rounded p-3 space-y-2">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <div className="font-bold">{p.vendor}</div>
                                        <div className="text-xs text-slate-500">{p.ordered_at} / {p.requester.department} {p.requester.name}</div>
                                    </div>
                                    <div className="flex gap-1">
                                        <button className="text-sm text-blue-700" onClick={() => downloadPdf(p)}>PDF</button>
                                        <button className="text-sm text-emerald-700" onClick={() => showEmail(p)}>メール本文</button>
                                    </div>
                                </div>
                                <table className="table-zk text-sm">
                                    <thead><tr><th>品目</th><th className="text-right">数量</th><th className="text-right">単価</th><th className="text-right">小計</th></tr></thead>
                                    <tbody>
                                        {p.items.map((it, i) => (
                                            <tr key={i}>
                                                <td>{it.item_name}</td>
                                                <td className="text-right tabular-nums">{it.quantity}</td>
                                                <td className="text-right tabular-nums">{it.unit_price === null ? "未設定" : `¥${it.unit_price.toLocaleString()}`}</td>
                                                <td className="text-right tabular-nums">{it.subtotal === null ? "要見積" : `¥${it.subtotal.toLocaleString()}`}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                                <div className="text-right text-sm">
                                    合計: <b>{p.total === null ? "要見積" : `¥${p.total.toLocaleString()}`}</b>
                                    {p.has_unpriced_items && <span className="text-amber-700 text-xs ml-2">※単価未設定あり</span>}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
