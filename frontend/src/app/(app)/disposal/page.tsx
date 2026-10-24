"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiDelete, apiPost, errorText } from "@/lib/api";
import { fmtDateTime, fmtQty } from "@/lib/format";
import { NOTICE_STATUS, REQUEST_STATUS } from "@/lib/labels";
import type { DROut, InventoryRow, ItemDetail, NoticeOut, Page } from "@/lib/types";
import { useMe } from "@/lib/use-me";
import { useScope } from "@/lib/use-scope";
import { Badge, countError, Field, ItemPicker, Modal, PageHeader, parseCount, ReasonDialog, ScopeToggle, StateRow } from "@/components/ui";

const REASONS = ["期限切れ", "破損", "汚損", "不要", "その他"];
const REFRESH_KEYS = ["dr", "notices", "kpi", "inventory", "todo", "history"];

function toRow(d: ItemDetail): InventoryRow {
    return {
        item_id: d.id, item_name: d.item_name, item_code: d.item_code, category: d.category, unit: d.unit, vendor_name: d.vendor_name,
        unit_price: d.unit_price, owner_department_id: d.owner_department_id, is_common: !!d.is_common, quantity: d.quantity,
        threshold: d.threshold, location: d.location_text, expiry_date: d.expiry_date,
        is_low_stock: false, is_expired: false, is_expiring_soon: false,
    };
}

/** 廃棄の申請（一般以上）と、ゲストの「部署への連絡」（I-08）で同じ入力欄を使う。 */
function NewRequest({ initial, notice, onDone }: { initial: InventoryRow | null; notice: boolean; onDone: () => void }) {
    const [row, setRow] = useState<InventoryRow | null>(initial);
    const [qty, setQty] = useState("1");
    const [kind, setKind] = useState(initial?.expiry_date ? "期限切れ" : "");
    const [detail, setDetail] = useState("");
    const qtyErr = row ? countError(qty, { min: 1, max: Math.max(row.quantity, 1) }) : null;
    const reason = [kind, detail.trim()].filter(Boolean).join("：");
    const create = useMutation({
        mutationFn: () => apiPost(notice ? "/disposal-notices" : "/disposal-requests", { item_id: row?.item_id, quantity: parseCount(qty), reason }),
        onSuccess: () => { toast.success(notice ? "部署の正社員に連絡しました" : "廃棄を申請しました"); onDone(); },
        onError: (e) => toast.error(errorText(e)),
    });
    return (
        <form className="card max-w-2xl space-y-3 p-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }} aria-label={notice ? "廃棄の連絡" : "廃棄の申請"}>
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
            <button type="submit" className="btn-primary" disabled={!row || !!qtyErr || !kind || create.isPending}>{notice ? "部署に連絡する" : "申請する"}</button>
        </form>
    );
}

/** ゲスト本人の連絡の一覧（結果が分かる）。 */
function MyNotices() {
    const qc = useQueryClient();
    const list = useQuery({ queryKey: ["notices", "mine"], queryFn: () => api<Page<NoticeOut>>("/disposal-notices", { params: { per_page: 200 } }) });
    const withdraw = useMutation({
        mutationFn: (id: number) => apiDelete(`/disposal-notices/${id}`),
        onSuccess: () => { toast.success("取り下げました"); qc.invalidateQueries({ queryKey: ["notices"] }); },
        onError: (e) => toast.error(errorText(e)),
    });
    return (
        <div className="card overflow-x-auto">
            <table className="table-zk">
                <thead><tr><th>日時</th><th>物品</th><th className="text-right">数量</th><th>理由</th><th>状態</th><th>対応した人</th><th /></tr></thead>
                <tbody>
                    <StateRow colSpan={7} loading={list.isLoading} error={list.error} empty={list.data?.items.length === 0} emptyText="連絡はありません" />
                    {list.data?.items.map((n) => (
                        <tr key={n.id}>
                            <td className="text-xs text-slate-500">{fmtDateTime(n.created_at)}</td>
                            <td>{n.item_name}</td>
                            <td className="text-right tabular-nums">{fmtQty(n.quantity, n.unit)}</td>
                            <td className="text-xs">{n.reason}{n.handled_comment && <div className="text-slate-600">コメント：{n.handled_comment}</div>}</td>
                            <td><Badge map={NOTICE_STATUS} value={n.status} /></td>
                            <td>{n.handled_by || "-"}</td>
                            <td>{n.status === "OPEN" && <button className="btn-link text-xs text-slate-600" disabled={withdraw.isPending} onClick={() => withdraw.mutate(n.id)}>取り下げ</button>}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

/** 正式な申請に上げるときに数量・理由を直す。 */
function PromoteDialog({ notice, busy, onClose, onSubmit }: {
    notice: NoticeOut; busy: boolean; onClose: () => void; onSubmit: (body: { quantity: number | null; reason: string }) => void;
}) {
    const [qty, setQty] = useState(String(notice.quantity));
    const [reason, setReason] = useState(notice.reason);
    const qtyErr = countError(qty, { min: 1, max: Math.max(notice.current_stock, 1) });
    return (
        <Modal open title="廃棄の申請に上げる" onClose={onClose} footer={<>
            <button className="btn-secondary" onClick={onClose}>キャンセル</button>
            <button className="btn-primary" disabled={!!qtyErr || !reason.trim() || busy} onClick={() => onSubmit({ quantity: parseCount(qty), reason: reason.trim() })}>申請する</button>
        </>}>
            <p className="text-sm">「{notice.item_name}」（{notice.reporter} さんの連絡・在庫 {fmtQty(notice.current_stock, notice.unit)}）</p>
            <Field label={`数量（${notice.unit}）`} error={qtyErr}>{(id) => <input id={id} className="input" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} aria-invalid={!!qtyErr} />}</Field>
            <Field label="理由 *">{(id) => <textarea id={id} className="input" value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>
        </Modal>
    );
}

/** 一般・管理者：自分の部署のゲストからの連絡（未対応）。 */
function DepartmentNotices({ onChanged }: { onChanged: () => void }) {
    const { isAdmin } = useMe();
    const { scope } = useScope();
    const [promoting, setPromoting] = useState<NoticeOut | null>(null);
    const [dismissing, setDismissing] = useState<NoticeOut | null>(null);
    const list = useQuery({
        queryKey: ["notices", "open", scope],
        queryFn: () => api<Page<NoticeOut>>("/disposal-notices", { params: { status: "OPEN", per_page: 200, scope } }),
    });
    const done = (msg: string) => { toast.success(msg); setPromoting(null); setDismissing(null); onChanged(); };
    const promote = useMutation({
        mutationFn: ({ id, body }: { id: number; body: { quantity: number | null; reason: string } }) => apiPost(`/disposal-notices/${id}/promote`, body),
        onSuccess: () => done(isAdmin ? "廃棄の申請に上げました" : "廃棄の申請に上げました（管理者の承認待ちになります）"),
        onError: (e) => { toast.error(errorText(e)); onChanged(); },
    });
    const dismiss = useMutation({
        mutationFn: ({ id, comment }: { id: number; comment: string }) => apiPost(`/disposal-notices/${id}/dismiss`, { comment: comment || null }),
        onSuccess: () => done("対応不要にしました"),
        onError: (e) => { toast.error(errorText(e)); onChanged(); },
    });
    if (!list.data?.items.length && !list.isLoading) return null;
    return (
        <section aria-label="ゲストからの廃棄の連絡" className="space-y-2">
            <h2 className="font-semibold">ゲストからの廃棄の連絡（未対応 {list.data?.total ?? 0} 件）</h2>
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr><th>日時</th><th>物品</th><th className="text-right">数量</th><th className="text-right">現在庫</th><th>理由</th><th>連絡した人</th><th>部署</th><th /></tr></thead>
                    <tbody>
                        <StateRow colSpan={8} loading={list.isLoading} error={list.error} empty={false} />
                        {list.data?.items.map((n) => (
                            <tr key={n.id}>
                                <td className="text-xs text-slate-500">{fmtDateTime(n.created_at)}</td>
                                <td>{n.item_name}</td>
                                <td className="text-right tabular-nums">{fmtQty(n.quantity, n.unit)}</td>
                                <td className="text-right tabular-nums">{n.current_stock}</td>
                                <td className="text-xs">{n.reason}</td>
                                <td>{n.reporter}</td>
                                <td>{n.department || "-"}</td>
                                <td className="space-x-3 whitespace-nowrap">
                                    <button className="btn-link text-xs text-emerald-700" onClick={() => setPromoting(n)}>申請に上げる</button>
                                    <button className="btn-link text-xs text-slate-600" onClick={() => setDismissing(n)}>対応不要</button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            {promoting && <PromoteDialog notice={promoting} busy={promote.isPending} onClose={() => setPromoting(null)}
                onSubmit={(body) => promote.mutate({ id: promoting.id, body })} />}
            <ReasonDialog open={!!dismissing} title="対応不要にする" label="コメント（任意・連絡した人に見えます）" confirmText="対応不要にする" required={false}
                busy={dismiss.isPending} onClose={() => setDismissing(null)} onSubmit={(comment) => dismissing && dismiss.mutate({ id: dismissing.id, comment })}>
                <p className="text-sm">「{dismissing?.item_name}」{dismissing?.quantity}{dismissing?.unit}（{dismissing?.reporter}）</p>
            </ReasonDialog>
        </section>
    );
}

function DisposalInner() {
    const qc = useQueryClient();
    const { me, isAdmin, isGuest } = useMe();
    const { scope } = useScope();
    const search = useSearchParams();
    const presetId = Number(search.get("item")) || null;
    const preset = useQuery({ queryKey: ["item", presetId], queryFn: () => api<ItemDetail>(`/items/${presetId}`), enabled: !!presetId });
    const [open, setOpen] = useState(!!presetId);
    const [status, setStatus] = useState("");
    const [mine, setMine] = useState(false);
    const [rejecting, setRejecting] = useState<DROut | null>(null);

    const list = useQuery({
        queryKey: ["dr", status, mine, scope],
        queryFn: () => api<Page<DROut>>("/disposal-requests", { params: { status, mine, scope, per_page: 200 } }),
        enabled: !!me && !isGuest,
    });
    const refresh = () => { for (const k of REFRESH_KEYS) qc.invalidateQueries({ queryKey: [k] }); };
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

    const form = open && (presetId && !preset.data ? <p className="text-slate-500">読み込み中...</p> :
        <NewRequest key={presetId ?? "new"} notice={isGuest} initial={preset.data ? toRow(preset.data) : null} onDone={() => { setOpen(false); refresh(); }} />);
    const toggleForm = <button className="btn-primary" onClick={() => setOpen((v) => !v)}>{open ? "フォームを閉じる" : isGuest ? "＋ 新しく連絡する" : "＋ 新規申請"}</button>;

    if (isGuest) {
        return (
            <div className="space-y-4">
                <PageHeader title="廃棄が要りそうな物の連絡" description="同じ部署の正社員に届きます。正社員が確認して、廃棄を申請するか決めます" actions={toggleForm} />
                {form}
                <MyNotices />
            </div>
        );
    }

    return (
        <div className="space-y-4">
            <PageHeader title="廃棄申請" actions={toggleForm} />
            {form}
            <DepartmentNotices onChanged={refresh} />
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
                <ScopeToggle className="mb-1" />
            </div>
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr><th>日時</th><th>物品</th><th className="text-right">数量</th><th>理由</th><th>申請者</th><th>部署</th><th>状態</th><th /></tr></thead>
                    <tbody>
                        <StateRow colSpan={8} loading={list.isLoading} error={list.error} empty={list.data?.items.length === 0} emptyText="申請はありません" />
                        {list.data?.items.map((d) => (
                            <tr key={d.id}>
                                <td className="text-xs text-slate-500">{fmtDateTime(d.created_at)}</td>
                                <td>{d.item_name}</td>
                                <td className="text-right tabular-nums">{fmtQty(d.quantity, d.unit)}</td>
                                <td className="text-xs">{d.reason}{d.reject_reason && <div className="text-rose-700">却下理由：{d.reject_reason}</div>}</td>
                                <td>{d.requester}</td>
                                <td>{d.department || "-"}</td>
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
