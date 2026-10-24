"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiDelete, apiPost, errorText } from "@/lib/api";
import { fmtDateTime, fmtQty } from "@/lib/format";
import { REQUEST_STATUS } from "@/lib/labels";
import type { DROut, InventoryRow, ItemDetail, Page } from "@/lib/types";
import { useMe } from "@/lib/use-me";
import { Badge, countError, Field, ItemPicker, PageHeader, parseCount, ReasonDialog, StateRow } from "@/components/ui";

const REASONS = ["期限切れ", "破損", "汚損", "不要", "その他"];

function toRow(d: ItemDetail): InventoryRow {
    return {
        item_id: d.id, item_name: d.item_name, item_code: d.item_code, category: d.category, unit: d.unit, vendor_name: d.vendor_name,
        unit_price: d.unit_price, quantity: d.quantity, threshold: d.threshold, location: d.location_text, expiry_date: d.expiry_date,
        is_low_stock: false, is_expired: false, is_expiring_soon: false,
    };
}

function NewRequest({ initial, onDone }: { initial: InventoryRow | null; onDone: () => void }) {
    const [row, setRow] = useState<InventoryRow | null>(initial);
    const [qty, setQty] = useState("1");
    const [kind, setKind] = useState(initial?.expiry_date ? "期限切れ" : "");
    const [detail, setDetail] = useState("");
    const qtyErr = row ? countError(qty, { min: 1, max: Math.max(row.quantity, 1) }) : null;
    const reason = [kind, detail.trim()].filter(Boolean).join("：");
    const create = useMutation({
        mutationFn: () => apiPost("/disposal-requests", { item_id: row?.item_id, quantity: parseCount(qty), reason }),
        onSuccess: () => { toast.success("廃棄を申請しました"); onDone(); },
        onError: (e) => toast.error(errorText(e)),
    });
    return (
        <form className="card max-w-2xl space-y-3 p-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }} aria-label="廃棄の申請">
            <ItemPicker value={row} onChange={setRow} />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field label={`数量${row ? `（${row.unit}）` : ""}`} error={qtyErr}>{(id) => <input id={id} className="input" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} aria-invalid={!!qtyErr} />}</Field>
                <Field label="理由 *">
                    {(id) => (
                        <select id={id} className="input" value={kind} onChange={(e) => setKind(e.target.value)}>
                            <option value="">選択してください</option>
                            {REASONS.map((r) => <option key={r} value={r}>{r}</option>)}
                        </select>
                    )}
                </Field>
            </div>
            <Field label="詳しい理由（任意）">{(id) => <textarea id={id} className="input" value={detail} onChange={(e) => setDetail(e.target.value)} />}</Field>
            <button type="submit" className="btn-primary" disabled={!row || !!qtyErr || !kind || create.isPending}>申請する</button>
        </form>
    );
}

function DisposalInner() {
    const qc = useQueryClient();
    const { me, isAdmin } = useMe();
    const search = useSearchParams();
    const presetId = Number(search.get("item")) || null;
    const preset = useQuery({ queryKey: ["item", presetId], queryFn: () => api<ItemDetail>(`/items/${presetId}`), enabled: !!presetId });
    const [open, setOpen] = useState(!!presetId);
    const [status, setStatus] = useState("");
    const [mine, setMine] = useState(false);
    const [rejecting, setRejecting] = useState<DROut | null>(null);

    const list = useQuery({
        queryKey: ["dr", status, mine],
        queryFn: () => api<Page<DROut>>("/disposal-requests", { params: { status, mine, per_page: 200 } }),
    });
    const refresh = () => { for (const k of ["dr", "kpi", "inventory", "todo", "history"]) qc.invalidateQueries({ queryKey: [k] }); };
    const decide = useMutation({
        mutationFn: ({ id, approve, reason }: { id: number; approve: boolean; reason?: string }) =>
            apiPost(`/disposal-requests/${id}/approve`, { approve, reject_reason: reason ?? null }),
        onSuccess: (_d, v) => { toast.success(v.approve ? "承認しました（在庫から引きました）" : "却下しました"); setRejecting(null); refresh(); },
        onError: (e) => { toast.error(errorText(e)); refresh(); },
    });
    const cancel = useMutation({
        mutationFn: (id: number) => apiDelete(`/disposal-requests/${id}`),
        onSuccess: () => { toast.success("取り下げました"); refresh(); },
        onError: (e) => toast.error(errorText(e)),
    });

    return (
        <div className="space-y-4">
            <PageHeader title="廃棄申請" actions={<button className="btn-primary" onClick={() => setOpen((v) => !v)}>{open ? "申請フォームを閉じる" : "＋ 新規申請"}</button>} />
            {open && (presetId && !preset.data ? <p className="text-slate-500">読み込み中...</p> :
                <NewRequest key={presetId ?? "new"} initial={preset.data ? toRow(preset.data) : null} onDone={() => { setOpen(false); refresh(); }} />)}
            <div className="card flex flex-wrap items-end gap-3 p-3">
                <Field label="状態" className="w-40">
                    {(id) => (
                        <select id={id} className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
                            <option value="">すべて</option>
                            {["PENDING", "APPROVED", "REJECTED", "CANCELLED"].map((s) => <option key={s} value={s}>{REQUEST_STATUS[s].label}</option>)}
                        </select>
                    )}
                </Field>
                <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />自分の申請のみ</label>
            </div>
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr><th>日時</th><th>物品</th><th className="text-right">数量</th><th>理由</th><th>申請者</th><th>状態</th><th /></tr></thead>
                    <tbody>
                        <StateRow colSpan={7} loading={list.isLoading} error={list.error} empty={list.data?.items.length === 0} emptyText="申請はありません" />
                        {list.data?.items.map((d) => (
                            <tr key={d.id}>
                                <td className="text-xs text-slate-500">{fmtDateTime(d.created_at)}</td>
                                <td>{d.item_name}</td>
                                <td className="text-right tabular-nums">{fmtQty(d.quantity, d.unit)}</td>
                                <td className="text-xs">{d.reason}{d.reject_reason && <div className="text-rose-700">却下理由：{d.reject_reason}</div>}</td>
                                <td>{d.requester}</td>
                                <td><Badge map={REQUEST_STATUS} value={d.status} /></td>
                                <td className="space-x-3 whitespace-nowrap">
                                    {d.status === "PENDING" && isAdmin && <>
                                        <button className="btn-link text-xs text-emerald-700" disabled={decide.isPending} onClick={() => decide.mutate({ id: d.id, approve: true })}>承認</button>
                                        <button className="btn-link text-xs text-rose-700" onClick={() => setRejecting(d)}>却下</button>
                                    </>}
                                    {d.status === "PENDING" && d.requester_id === me?.id && (
                                        <button className="btn-link text-xs text-slate-600" disabled={cancel.isPending} onClick={() => cancel.mutate(d.id)}>取り下げ</button>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <ReasonDialog open={!!rejecting} title="廃棄申請を却下" label="却下理由" confirmText="却下する" danger busy={decide.isPending}
                onClose={() => setRejecting(null)} onSubmit={(reason) => rejecting && decide.mutate({ id: rejecting.id, approve: false, reason })}>
                <p className="text-sm">「{rejecting?.item_name}」{rejecting?.quantity}{rejecting?.unit}（{rejecting?.requester}）</p>
            </ReasonDialog>
        </div>
    );
}

export default function DisposalPage() {
    return <Suspense fallback={null}><DisposalInner /></Suspense>;
}
