"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiPost, downloadFile, errorText } from "@/lib/api";
import { fmtDateTime, fmtSigned } from "@/lib/format";
import { CHANGE_TYPE, HISTORY_STATUS } from "@/lib/labels";
import type { HistoryRow, Page } from "@/lib/types";
import { useDebouncedValue } from "@/lib/use-debounced-value";
import { useScope } from "@/lib/use-scope";
import { Badge, ConfirmDialog, Field, PageHeader, Pager, ScopeToggle, StateRow } from "@/components/ui";

const PER_PAGE = 50;
const SIGNED = new Set(["ADJUST", "STOCKTAKE"]);

export default function HistoryPage() {
    const qc = useQueryClient();
    const [q, setQ] = useState("");
    const [changeType, setChangeType] = useState("");
    const [from, setFrom] = useState("");
    const [to, setTo] = useState("");
    const [mine, setMine] = useState(false);
    const [page, setPage] = useState(1);
    const [target, setTarget] = useState<HistoryRow | null>(null);
    const qDeb = useDebouncedValue(q, 300);
    const { scope } = useScope();
    const params = { q: qDeb, change_type: changeType, date_from: from, date_to: to, mine, scope };
    const reset = <T,>(set: (v: T) => void) => (v: T) => { set(v); setPage(1); };

    const { data, isLoading, error } = useQuery({
        queryKey: ["history", params, page],
        queryFn: () => api<Page<HistoryRow>>("/history", { params: { ...params, page, per_page: PER_PAGE } }),
    });
    const undo = useMutation({
        mutationFn: (id: number) => apiPost(`/history/${id}/undo`),
        onSuccess: () => {
            toast.success("取り消しました");
            setTarget(null);
            for (const k of ["history", "inventory", "kpi"]) qc.invalidateQueries({ queryKey: [k] });
        },
        onError: (e) => toast.error(errorText(e)),
    });

    async function exportCsv() {
        try { await downloadFile("/history/export.csv", "履歴.csv", { params }); } catch (e) { toast.error(errorText(e)); }
    }

    return (
        <div className="space-y-4">
            <PageHeader title="履歴" actions={<button className="btn-secondary" onClick={exportCsv}>CSV ダウンロード</button>} />
            <div className="card flex flex-wrap items-end gap-3 p-3">
                <Field label="物品名・担当者" className="w-full sm:w-64">{(id) => <input id={id} className="input" value={q} onChange={(e) => reset(setQ)(e.target.value)} />}</Field>
                <Field label="区分" className="w-40">
                    {(id) => (
                        <select id={id} className="input" value={changeType} onChange={(e) => reset(setChangeType)(e.target.value)}>
                            <option value="">すべて</option>
                            {Object.entries(CHANGE_TYPE).filter(([k]) => k !== "ORDER").map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                        </select>
                    )}
                </Field>
                <Field label="開始日" className="w-40">{(id) => <input id={id} type="date" className="input" value={from} onChange={(e) => reset(setFrom)(e.target.value)} />}</Field>
                <Field label="終了日" className="w-40">{(id) => <input id={id} type="date" className="input" value={to} onChange={(e) => reset(setTo)(e.target.value)} />}</Field>
                <label className="flex items-center gap-1 pb-2 text-sm"><input type="checkbox" checked={mine} onChange={(e) => reset(setMine)(e.target.checked)} />自分の操作だけ</label>
                <div className="pb-1">
                    <ScopeToggle />
                    <p className="mt-1 text-xs text-slate-500">自分の部署＝部署の人の操作と、部署の物品への操作</p>
                </div>
            </div>
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr><th>日時</th><th>物品</th><th>区分</th><th className="text-right">数量</th><th>担当</th><th>部署</th><th>状態</th><th>備考</th><th /></tr></thead>
                    <tbody>
                        <StateRow colSpan={9} loading={isLoading} error={error} empty={data?.items.length === 0} />
                        {data?.items.map((h) => (
                            <tr key={h.id} className={h.status === "REJECTED" ? "text-slate-400 line-through decoration-slate-300" : ""}>
                                <td className="text-xs whitespace-nowrap text-slate-500">{fmtDateTime(h.created_at)}</td>
                                <td>{h.item_name}</td>
                                <td><Badge map={CHANGE_TYPE} value={h.change_type} /></td>
                                <td className="text-right tabular-nums">{SIGNED.has(h.change_type) ? fmtSigned(h.quantity) : h.quantity} <span className="text-xs text-slate-500">{h.unit}</span></td>
                                <td>{h.user_name}</td>
                                <td>{h.department || "-"}</td>
                                <td><Badge map={HISTORY_STATUS} value={h.status} /></td>
                                <td className="text-xs text-slate-500">{h.note || ""}</td>
                                <td>{h.can_undo && <button className="btn-link text-xs text-rose-700" onClick={() => setTarget(h)}>取消</button>}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            {data && <Pager page={page} perPage={PER_PAGE} total={data.total} onChange={setPage} />}
            <ConfirmDialog open={!!target} title="操作を取り消す" confirmText="取り消す" danger busy={undo.isPending}
                onClose={() => setTarget(null)} onConfirm={() => target && undo.mutate(target.id)}>
                「{target?.item_name}」の{target ? CHANGE_TYPE[target.change_type]?.label : ""} {target?.quantity}{target?.unit} を取り消し、在庫を元に戻します。
            </ConfirmDialog>
        </div>
    );
}
