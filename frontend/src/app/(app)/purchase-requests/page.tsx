"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiDelete, apiPatch, apiPost, downloadFile, errorText } from "@/lib/api";
import { fmtDateTime, fmtQty, fmtYen } from "@/lib/format";
import { PRIORITY, REQUEST_STATUS } from "@/lib/labels";
import type { InventoryRow, OrderPayload, Page, PROut, SummaryGroup } from "@/lib/types";
import { useMe } from "@/lib/use-me";
import { useScope } from "@/lib/use-scope";
import { Badge, ConfirmDialog, countError, Field, ItemPicker, Modal, PageHeader, parseCount, ReasonDialog, ScopeToggle, StateRow, Tabs } from "@/components/ui";

const ORDERABLE = new Set(["APPROVED", "ORDERED"]);
const OPEN = new Set(["PENDING", "ON_HOLD"]);

function NewRequest({ onDone }: { onDone: () => void }) {
    const [row, setRow] = useState<InventoryRow | null>(null);
    const [qty, setQty] = useState("1");
    const [priority, setPriority] = useState("NORMAL");
    const [due, setDue] = useState("");
    const [note, setNote] = useState("");
    const qtyErr = countError(qty, { min: 1, max: 100000 });
    const create = useMutation({
        mutationFn: () => apiPost("/purchase-requests", { item_id: row?.item_id, requested_qty: parseCount(qty), priority, due_date: due, note }),
        onSuccess: () => { toast.success("発注を申請しました"); onDone(); },
        onError: (e) => toast.error(errorText(e)),
    });
    return (
        <form className="card max-w-2xl space-y-3 p-4" aria-label="発注の申請" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
            <ItemPicker value={row} onChange={setRow} />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <Field label={`数量${row ? `（${row.unit}）` : ""}`} error={qtyErr}>{(id) => <input id={id} className="input" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} aria-invalid={!!qtyErr} />}</Field>
                <Field label="優先度">
                    {(id) => <select id={id} className="input" value={priority} onChange={(e) => setPriority(e.target.value)}>
                        {Object.entries(PRIORITY).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                    </select>}
                </Field>
                <Field label="希望納期">{(id) => <input id={id} type="date" className="input" value={due} onChange={(e) => setDue(e.target.value)} />}</Field>
            </div>
            <Field label="備考">{(id) => <input id={id} className="input" value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
            <button type="submit" className="btn-primary" disabled={!row || !!qtyErr || create.isPending}>{create.isPending ? "送信中..." : "申請する"}</button>
        </form>
    );
}

function OrderPreview({ payloads, approvedIds, onClose, onOrdered }: {
    payloads: OrderPayload[]; approvedIds: number[]; onClose: () => void; onOrdered: () => void;
}) {
    const [email, setEmail] = useState<string | null>(null);
    const markOrdered = useMutation({
        mutationFn: () => apiPost<{ updated: number }>("/orders/mark-ordered", { request_ids: approvedIds }),
        onSuccess: (r) => { toast.success(`${r.updated}件を「発注済」にしました`); onOrdered(); },
        onError: (e) => toast.error(errorText(e)),
    });
    async function pdf(p: OrderPayload) {
        try { await downloadFile("/orders/pdf", `発注書_${p.vendor}.pdf`, { method: "POST", json: { payload: p } }); } catch (e) { toast.error(errorText(e)); }
    }
    async function excel() {
        try { await downloadFile("/orders/excel", "発注書.xlsx", { method: "POST", json: { payloads } }); } catch (e) { toast.error(errorText(e)); }
    }
    async function showEmail(p: OrderPayload) {
        try { setEmail((await apiPost<{ email_text: string }>("/orders/email", { payload: p })).email_text); } catch (e) { toast.error(errorText(e)); }
    }
    return (
        <>
            <Modal open wide title={`発注書プレビュー（${payloads.length}業者）`} onClose={onClose} footer={<>
                <button className="btn-secondary" onClick={excel}>Excel（全業者）</button>
                {approvedIds.length > 0 && (
                    <button className="btn-primary" disabled={markOrdered.isPending} onClick={() => markOrdered.mutate()}>
                        発注済にする（{approvedIds.length}件）
                    </button>
                )}
            </>}>
                {payloads.map((p) => (
                    <div key={p.vendor} className="space-y-2 rounded border p-3">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                            <div>
                                <div className="font-bold">{p.vendor}</div>
                                <div className="text-xs text-slate-500">{p.ordered_at}／{p.requester.department} {p.requester.name}</div>
                            </div>
                            <div className="flex gap-3">
                                <button className="btn-link" onClick={() => pdf(p)}>PDF</button>
                                <button className="btn-link" onClick={() => showEmail(p)}>メール本文</button>
                            </div>
                        </div>
                        <table className="table-zk">
                            <thead><tr><th>品目</th><th className="text-right">数量</th><th className="text-right">単価</th><th className="text-right">小計</th></tr></thead>
                            <tbody>
                                {p.items.map((it, i) => (
                                    <tr key={i}>
                                        <td>{it.item_name}</td>
                                        <td className="text-right tabular-nums">{it.quantity}</td>
                                        <td className="text-right tabular-nums">{it.unit_price === null ? "未設定" : fmtYen(it.unit_price)}</td>
                                        <td className="text-right tabular-nums">{it.subtotal === null ? "要見積" : fmtYen(it.subtotal)}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                        <div className="text-right text-sm">
                            合計：<b>{p.total === null ? "要見積" : fmtYen(p.total)}</b>
                            {p.has_unpriced_items && <span className="ml-2 text-xs text-amber-700">※単価未設定あり</span>}
                        </div>
                    </div>
                ))}
            </Modal>
            <Modal open={email !== null} title="メール本文" onClose={() => setEmail(null)} wide footer={
                <button className="btn-primary" onClick={async () => {
                    try { await navigator.clipboard.writeText(email ?? ""); toast.success("コピーしました"); } catch { toast.error("コピーできませんでした。本文を選択してコピーしてください"); }
                }}>コピー</button>
            }>
                <textarea aria-label="メール本文" readOnly className="input min-h-80 font-mono text-xs" value={email ?? ""} />
            </Modal>
        </>
    );
}

/** 管理者：同じ物品の申請のまとめ（I-11）。まとめて承認して発注書を作るか、一部の部署の分を却下する。 */
function Summary({ onChanged, onPreview }: { onChanged: () => void; onPreview: (payloads: OrderPayload[], ids: number[]) => void }) {
    const [selected, setSelected] = useState<Set<number>>(new Set());
    const [rejecting, setRejecting] = useState(false);
    const groups = useQuery({ queryKey: ["pr", "summary"], queryFn: () => api<SummaryGroup[]>("/purchase-requests/summary") });
    const ids = [...selected];
    const toggle = (id: number) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
    const decide = useMutation({
        mutationFn: async ({ status, comment, order }: { status: "APPROVED" | "REJECTED"; comment?: string; order?: boolean }) => {
            await apiPost("/purchase-requests/bulk-decide", { ids, status, admin_comment: comment || null });
            return order ? (await apiPost<{ payloads: OrderPayload[] }>("/orders/preview", { request_ids: ids })).payloads : null;
        },
        onSuccess: (payloads, v) => {
            toast.success(v.status === "APPROVED" ? `${ids.length}件を承認しました` : `${ids.length}件を却下しました`);
            setRejecting(false);
            setSelected(new Set());
            onChanged();
            if (payloads) onPreview(payloads, ids);
        },
        onError: (e) => { toast.error(errorText(e)); onChanged(); },
    });
    return (
        <div className="space-y-3">
            <div className="card flex flex-wrap items-center gap-2 p-3">
                <span className="text-sm text-slate-600">承認前の申請を物品ごとにまとめています。{selected.size}件を選択</span>
                <div className="ml-auto flex flex-wrap gap-2">
                    <button className="btn-primary" disabled={!ids.length || decide.isPending} onClick={() => decide.mutate({ status: "APPROVED", order: true })}>承認して発注書を作成</button>
                    <button className="btn-secondary" disabled={!ids.length || decide.isPending} onClick={() => decide.mutate({ status: "APPROVED" })}>承認だけ</button>
                    <button className="btn-danger" disabled={!ids.length || decide.isPending} onClick={() => setRejecting(true)}>却下</button>
                </div>
            </div>
            {groups.isLoading && <p className="text-slate-500">読み込み中...</p>}
            {groups.data?.length === 0 && <p className="card p-4 text-slate-500">承認前の申請はありません</p>}
            {groups.data?.map((g) => {
                const all = g.requests.every((r) => selected.has(r.id));
                return (
                    <section key={g.item_id} className="card space-y-2 p-3" aria-label={`${g.item_name}のまとめ`}>
                        <div className="flex flex-wrap items-baseline justify-between gap-2">
                            <div>
                                <b>{g.item_name}</b> <span className="text-xs text-slate-500">{g.vendor_name || "業者未設定"}・今の在庫 {fmtQty(g.current_stock, g.unit)}</span>
                            </div>
                            <div className="text-sm">合計 <b className="tabular-nums">{fmtQty(g.total_qty, g.unit)}</b>（{g.departments.map((d) => `${d.department} ${d.qty}`).join("・")}）</div>
                        </div>
                        <table className="table-zk">
                            <thead><tr>
                                <th className="w-10"><input type="checkbox" aria-label={`${g.item_name}の申請をすべて選ぶ`} checked={all}
                                    onChange={() => setSelected((s) => { const n = new Set(s); for (const r of g.requests) if (all) n.delete(r.id); else n.add(r.id); return n; })} /></th>
                                <th>部署</th><th>申請者</th><th className="text-right">数量</th><th>優先度</th><th>希望納期</th><th>備考</th>
                            </tr></thead>
                            <tbody>
                                {g.requests.map((r) => (
                                    <tr key={r.id}>
                                        <td><input type="checkbox" aria-label={`${r.requested_by_department || ""} ${r.requested_by} の申請を選ぶ`} checked={selected.has(r.id)} onChange={() => toggle(r.id)} /></td>
                                        <td>{r.requested_by_department || "-"}</td>
                                        <td>{r.requested_by}</td>
                                        <td className="text-right tabular-nums">{fmtQty(r.requested_qty, r.unit)}</td>
                                        <td><Badge map={PRIORITY} value={r.priority} /></td>
                                        <td className="text-xs">{r.due_date || "-"}</td>
                                        <td className="text-xs text-slate-500">{r.note || ""}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </section>
                );
            })}
            <ReasonDialog open={rejecting} title={`${ids.length}件の申請を却下`} label="却下の理由（申請者に表示されます）" confirmText="却下する" danger busy={decide.isPending}
                onClose={() => setRejecting(false)} onSubmit={(comment) => decide.mutate({ status: "REJECTED", comment })} />
        </div>
    );
}

export default function PurchaseRequestsPage() {
    const qc = useQueryClient();
    const { me, isAdmin } = useMe();
    const { scope } = useScope();
    const [tab, setTab] = useState<"list" | "summary">("list");
    const [previewIds, setPreviewIds] = useState<number[] | null>(null);
    const [status, setStatus] = useState("");
    const [mine, setMine] = useState(false);
    const [open, setOpen] = useState(false);
    const [selected, setSelected] = useState<Set<number>>(new Set());
    const [preview, setPreview] = useState<OrderPayload[] | null>(null);
    const [rejecting, setRejecting] = useState<PROut | null>(null);
    const [withdrawing, setWithdrawing] = useState<PROut | null>(null);

    const list = useQuery({
        queryKey: ["pr", status, mine, scope],
        queryFn: () => api<Page<PROut>>("/purchase-requests", { params: { status, mine, scope, per_page: 200 } }),
    });
    const rows = list.data?.items ?? [];
    const refresh = () => { for (const k of ["pr", "todo", "receivable"]) qc.invalidateQueries({ queryKey: [k] }); };

    const decide = useMutation({
        mutationFn: ({ id, status, comment }: { id: number; status: string; comment?: string }) =>
            apiPatch(`/purchase-requests/${id}`, { status, ...(comment !== undefined ? { admin_comment: comment } : {}) }),
        onSuccess: () => { toast.success("更新しました"); setRejecting(null); refresh(); },
        onError: (e) => toast.error(errorText(e)),
    });
    const withdraw = useMutation({
        mutationFn: (id: number) => apiDelete(`/purchase-requests/${id}`),
        onSuccess: () => { toast.success("取り下げました"); setWithdrawing(null); refresh(); },
        onError: (e) => toast.error(errorText(e)),
    });
    const issue = useMutation({
        mutationFn: () => apiPost<{ payloads: OrderPayload[] }>("/orders/preview", { request_ids: [...selected] }),
        onSuccess: (r) => setPreview(r.payloads),
        onError: (e) => toast.error(errorText(e)),
    });
    const toggle = (id: number) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
    const approvedSelected = previewIds ?? rows.filter((r) => selected.has(r.id) && r.status === "APPROVED").map((r) => r.id);

    return (
        <div className="space-y-4">
            <PageHeader title="発注申請" actions={<button className="btn-primary" onClick={() => setOpen((v) => !v)}>{open ? "申請フォームを閉じる" : "＋ 新規申請"}</button>} />
            {open && <NewRequest onDone={() => { setOpen(false); refresh(); }} />}
            {isAdmin && <Tabs tabs={[{ value: "list", label: "申請の一覧" }, { value: "summary", label: "同じ物品のまとめ" }]} value={tab} onChange={setTab} />}
            {isAdmin && tab === "summary" ? (
                <Summary onChanged={refresh} onPreview={(payloads, ids) => { setPreviewIds(ids); setPreview(payloads); }} />
            ) : <>
            <div className="card flex flex-wrap items-end gap-3 p-3">
                <Field label="状態" className="w-40">
                    {(id) => <select id={id} className="input" value={status} onChange={(e) => setStatus(e.target.value)}>
                        <option value="">すべて</option>
                        {["PENDING", "ON_HOLD", "APPROVED", "ORDERED", "RECEIVED", "REJECTED"].map((s) => <option key={s} value={s}>{REQUEST_STATUS[s].label}</option>)}
                    </select>}
                </Field>
                <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={mine} onChange={(e) => setMine(e.target.checked)} />自分の申請のみ</label>
                <ScopeToggle className="mb-1" />
                {isAdmin && (
                    <div className="ml-auto flex items-center gap-2 pb-1">
                        <span className="text-sm text-slate-600">発注書：{selected.size}件を選択</span>
                        <button className="btn-primary" disabled={selected.size === 0 || issue.isPending} onClick={() => issue.mutate()}>{issue.isPending ? "作成中..." : "発注書を作成"}</button>
                    </div>
                )}
            </div>
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr>{isAdmin && <th className="w-10" />}<th>申請日時</th><th>物品</th><th className="text-right">数量</th><th>優先度</th><th>希望納期</th><th>申請者</th><th>部署</th><th>状態</th><th>コメント</th><th /></tr></thead>
                    <tbody>
                        <StateRow colSpan={isAdmin ? 11 : 10} loading={list.isLoading} error={list.error} empty={rows.length === 0} emptyText="申請はありません" />
                        {rows.map((p) => (
                            <tr key={p.id}>
                                {isAdmin && <td>{ORDERABLE.has(p.status) && <input type="checkbox" aria-label={`${p.item_name}を発注書に含める`} checked={selected.has(p.id)} onChange={() => toggle(p.id)} />}</td>}
                                <td className="text-xs text-slate-500">{fmtDateTime(p.created_at)}</td>
                                <td>{p.item_name}<div className="text-xs text-slate-500">{p.vendor_name || ""}</div></td>
                                <td className="text-right tabular-nums">
                                    {fmtQty(p.requested_qty, p.unit)}
                                    {p.received_qty > 0 && <div className="text-xs text-slate-500">受領 {p.received_qty}／残 {p.remaining_qty}</div>}
                                </td>
                                <td><Badge map={PRIORITY} value={p.priority} /></td>
                                <td className="text-xs">{p.due_date || "-"}</td>
                                <td>{p.requested_by}</td>
                                <td>{p.requested_by_department || "-"}</td>
                                <td><Badge map={REQUEST_STATUS} value={p.status} /></td>
                                <td className="text-xs text-slate-500">{p.admin_comment || ""}</td>
                                <td className="space-x-3 whitespace-nowrap">
                                    {isAdmin && OPEN.has(p.status) && <>
                                        <button className="btn-link text-xs text-emerald-700" disabled={decide.isPending} onClick={() => decide.mutate({ id: p.id, status: "APPROVED" })}>承認</button>
                                        {p.status === "PENDING" && <button className="btn-link text-xs text-slate-600" disabled={decide.isPending} onClick={() => decide.mutate({ id: p.id, status: "ON_HOLD" })}>保留</button>}
                                        <button className="btn-link text-xs text-rose-700" onClick={() => setRejecting(p)}>却下</button>
                                    </>}
                                    {OPEN.has(p.status) && p.requested_by_user_id === me?.id && (
                                        <button className="btn-link text-xs text-slate-600" onClick={() => setWithdrawing(p)}>取り下げ</button>
                                    )}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            </>}
            {preview && <OrderPreview payloads={preview} approvedIds={approvedSelected} onClose={() => { setPreview(null); setPreviewIds(null); }}
                onOrdered={() => { setPreview(null); setPreviewIds(null); setSelected(new Set()); refresh(); }} />}
            <ReasonDialog open={!!rejecting} title="発注申請を却下" label="却下の理由（申請者に表示されます）" confirmText="却下する" danger busy={decide.isPending}
                onClose={() => setRejecting(null)} onSubmit={(comment) => rejecting && decide.mutate({ id: rejecting.id, status: "REJECTED", comment })} />
            <ConfirmDialog open={!!withdrawing} title="申請を取り下げる" confirmText="取り下げる" danger busy={withdraw.isPending}
                onClose={() => setWithdrawing(null)} onConfirm={() => withdrawing && withdraw.mutate(withdrawing.id)}>
                「{withdrawing?.item_name}」{withdrawing?.requested_qty}{withdrawing?.unit} の申請を取り下げます。
            </ConfirmDialog>
        </div>
    );
}
