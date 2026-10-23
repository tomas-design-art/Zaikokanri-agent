"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient, type QueryKey } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiPatch, apiPost, downloadFile, errorText } from "@/lib/api";
import { cn } from "@/lib/cn";
import { fmtDateTime, fmtSigned } from "@/lib/format";
import { RECORD_STATUS, SESSION_STATUS } from "@/lib/labels";
import type { StocktakeRecord, StocktakeSession } from "@/lib/types";
import { useDebouncedValue } from "@/lib/use-debounced-value";
import { useMe } from "@/lib/use-me";
import { StocktakeProgress } from "@/components/StocktakeProgress";
import { Badge, ConfirmDialog, Field, PageHeader, parseCount, StateRow } from "@/components/ui";

type Only = "" | "uncounted" | "diff";
type SaveState = "idle" | "saving" | "saved" | "error";

/** 1行の実数入力。離れたとき・Enter で保存し、保存の結果を行に出す（D-05）。 */
function CountInput({ rec, editable, listKey, onSaved, inputRef, onEnter }: {
    rec: StocktakeRecord; editable: boolean; listKey: QueryKey; onSaved: () => void;
    inputRef: (el: HTMLInputElement | null) => void; onEnter: () => void;
}) {
    const qc = useQueryClient();
    const [text, setText] = useState(rec.actual_qty === null ? "" : String(rec.actual_qty));
    const [state, setState] = useState<SaveState>(rec.actual_qty === null ? "idle" : "saved");
    const [saved, setSaved] = useState<string>(text);
    const invalid = text.trim() !== "" && parseCount(text) === null;

    const save = useMutation({
        mutationFn: (actual: number | null) => apiPatch<StocktakeRecord>(`/stocktake/records/${rec.id}`, { actual_qty: actual }),
        onMutate: () => setState("saving"),
        onSuccess: (updated, actual) => {
            setSaved(actual === null ? "" : String(actual));
            setState(actual === null ? "idle" : "saved");
            qc.setQueryData<StocktakeRecord[]>(listKey, (rows) => rows?.map((r) => (r.id === updated.id ? updated : r)));
            onSaved();
        },
        onError: (e) => { setState("error"); toast.error(`「${rec.item_name}」を保存できませんでした：${errorText(e)}`); },
    });

    function commit() {
        if (invalid || text.trim() === saved) return;
        save.mutate(text.trim() === "" ? null : parseCount(text));
    }

    if (!editable) return <span className="tabular-nums">{rec.actual_qty ?? "-"}</span>;
    return (
        <div className="flex items-center justify-end gap-2">
            <input ref={inputRef} className="input w-24 text-right" inputMode="numeric" enterKeyHint="next" value={text}
                aria-label={`${rec.item_name}の実数`} aria-invalid={invalid}
                onChange={(e) => { setText(e.target.value); if (state !== "saving") setState("idle"); }}
                onBlur={commit}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); commit(); onEnter(); } }} />
            <span className={cn("w-14 text-left text-xs", {
                "text-slate-400": state === "idle", "text-slate-500": state === "saving",
                "text-emerald-700": state === "saved", "text-rose-600": state === "error",
            })} aria-live="polite">
                {invalid ? "数字のみ" : state === "saving" ? "保存中" : state === "saved" && text.trim() === saved ? "保存済" : state === "error" ? "失敗" : ""}
            </span>
        </div>
    );
}

export default function StocktakeDetailPage() {
    const qc = useQueryClient();
    const { isAdmin } = useMe();
    const sid = Number(useParams<{ id: string }>().id);
    const [q, setQ] = useState("");
    const [only, setOnly] = useState<Only>("");
    const [confirm, setConfirm] = useState<"apply" | "cancel" | null>(null);
    const qDeb = useDebouncedValue(q, 300);
    const inputs = useRef<(HTMLInputElement | null)[]>([]);

    const session = useQuery({ queryKey: ["st-session", sid], queryFn: () => api<StocktakeSession>(`/stocktake/sessions/${sid}`) });
    const listKey: QueryKey = ["st-records", sid, qDeb, only];
    const records = useQuery({
        queryKey: listKey,
        queryFn: () => api<StocktakeRecord[]>(`/stocktake/sessions/${sid}/records`, { params: { q: qDeb, only } }),
        staleTime: Infinity,
    });
    const s = session.data;
    const editable = s?.status === "OPEN";
    const refreshSession = () => { qc.invalidateQueries({ queryKey: ["st-session", sid] }); qc.invalidateQueries({ queryKey: ["st-sessions"] }); };
    const refreshAll = () => { refreshSession(); qc.invalidateQueries({ queryKey: ["st-records", sid] }); for (const k of ["inventory", "kpi", "history"]) qc.invalidateQueries({ queryKey: [k] }); };

    const refreshItems = useMutation({
        mutationFn: () => apiPost<{ added: number }>(`/stocktake/sessions/${sid}/refresh-items`),
        onSuccess: (r) => { toast.success(r.added ? `${r.added}品目を追加しました` : "追加する物品はありません"); refreshAll(); },
        onError: (e) => toast.error(errorText(e)),
    });
    const apply = useMutation({
        mutationFn: () => apiPost<{ applied: number; adjusted: number; uncounted: number }>(`/stocktake/sessions/${sid}/apply`),
        onSuccess: (r) => { toast.success(`確定しました：${r.adjusted}品目の在庫を修正（未カウント ${r.uncounted}品目は変更なし）`); setConfirm(null); refreshAll(); },
        onError: (e) => { toast.error(errorText(e)); refreshAll(); },
    });
    const cancel = useMutation({
        mutationFn: () => apiPost(`/stocktake/sessions/${sid}/cancel`),
        onSuccess: () => { toast.success("棚卸しを中止しました（在庫は変わっていません）"); setConfirm(null); refreshAll(); },
        onError: (e) => toast.error(errorText(e)),
    });
    async function exportExcel() {
        try { await downloadFile(`/stocktake/sessions/${sid}/export.xlsx`, `棚卸し_${s?.name ?? sid}.xlsx`); } catch (e) { toast.error(errorText(e)); }
    }

    if (session.error) return <p className="text-rose-600">{(session.error as Error).message}</p>;
    if (!s) return <div className="text-slate-500">読み込み中...</div>;
    const rows = records.data ?? [];

    return (
        <div className="space-y-4">
            <PageHeader title={s.name} description={<>
                <Badge map={SESSION_STATUS} value={s.status} /> 対象：{s.category || "すべて"}／開始 {fmtDateTime(s.created_at)}{s.closed_at && `／完了 ${fmtDateTime(s.closed_at)}`}
            </>} actions={<>
                <Link className="btn-secondary" href="/stocktake">一覧へ</Link>
                <button className="btn-secondary" onClick={exportExcel}>Excel 出力</button>
                {isAdmin && editable && <>
                    <button className="btn-secondary" disabled={refreshItems.isPending} onClick={() => refreshItems.mutate()}>対象を更新</button>
                    <button className="btn-secondary text-rose-700" onClick={() => setConfirm("cancel")}>中止</button>
                    <button className="btn-primary" onClick={() => setConfirm("apply")}>確定して在庫に反映</button>
                </>}
            </>} />

            <section className="card flex flex-wrap items-center gap-6 p-3" aria-label="進捗">
                <StocktakeProgress s={s.summary} />
                <dl className="flex flex-wrap gap-4 text-sm">
                    {([["対象", s.summary.total], ["カウント済", s.summary.counted], ["未カウント", s.summary.uncounted], ["一致", s.summary.matched], ["差異あり", s.summary.diff]] as const).map(([k, v]) => (
                        <div key={k}><dt className="text-xs text-slate-500">{k}</dt><dd className="text-lg font-semibold tabular-nums">{v}</dd></div>
                    ))}
                </dl>
            </section>

            <div className="card flex flex-wrap items-end gap-3 p-3">
                <Field label="物品名・コードで探す" className="w-full sm:w-64">{(id) => <input id={id} className="input" value={q} onChange={(e) => setQ(e.target.value)} />}</Field>
                <div role="radiogroup" aria-label="表示する行" className="flex gap-1 pb-1">
                    {([["", "すべて"], ["uncounted", "未カウントのみ"], ["diff", "差異ありのみ"]] as const).map(([v, label]) => (
                        <button key={v} role="radio" aria-checked={only === v} onClick={() => setOnly(v)} className={cn("btn text-xs", only === v ? "bg-brand-600 text-white" : "btn-secondary")}>{label}</button>
                    ))}
                </div>
                {editable && <p className="w-full text-xs text-slate-500">実数を入れて Enter（またはほかの欄へ移動）で保存されます。空にすると未カウントに戻ります。帳簿数は数えた時点の在庫で記録されます。</p>}
            </div>

            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr><th>保管場所</th><th>物品</th><th className="text-right">帳簿数</th><th className="text-right">実数</th><th className="text-right">差異</th><th>状態</th><th>数えた人</th></tr></thead>
                    <tbody>
                        <StateRow colSpan={7} loading={records.isLoading} error={records.error} empty={rows.length === 0} emptyText="該当する物品はありません" />
                        {rows.map((r, i) => (
                            <tr key={r.id}>
                                <td className="text-slate-600">{r.location || "-"}</td>
                                <td>{r.item_name}<div className="text-xs text-slate-500">{r.item_code || ""} {r.unit}</div></td>
                                <td className="text-right tabular-nums">{r.system_qty}</td>
                                <td className="text-right">
                                    <CountInput rec={r} editable={editable} listKey={listKey} onSaved={refreshSession}
                                        inputRef={(el) => { inputs.current[i] = el; }}
                                        onEnter={() => inputs.current[i + 1]?.focus()} />
                                </td>
                                <td className={cn("text-right font-semibold tabular-nums", r.diff_qty ? (r.diff_qty > 0 ? "text-emerald-700" : "text-rose-600") : "text-slate-400")}>{fmtSigned(r.diff_qty)}</td>
                                <td><Badge map={RECORD_STATUS} value={r.status} /></td>
                                <td className="text-xs text-slate-500">{r.counted_by || ""}<div>{fmtDateTime(r.counted_at)}</div></td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            <ConfirmDialog open={confirm === "apply"} title="棚卸しを確定して在庫に反映" confirmText="確定する" busy={apply.isPending}
                onClose={() => setConfirm(null)} onConfirm={() => apply.mutate()}>
                <ul className="list-disc space-y-1 pl-5">
                    <li>差異のある <b>{s.summary.diff}</b> 品目の在庫を、数えた結果に合わせて修正します（履歴に「棚卸し」として残ります）。</li>
                    {s.summary.uncounted > 0 && <li className="text-amber-800">未カウントの <b>{s.summary.uncounted}</b> 品目は在庫を変えません。</li>}
                    <li>確定後は入力を変更できません。</li>
                </ul>
            </ConfirmDialog>
            <ConfirmDialog open={confirm === "cancel"} title="棚卸しを中止" confirmText="中止する" danger busy={cancel.isPending}
                onClose={() => setConfirm(null)} onConfirm={() => cancel.mutate()}>
                入力した実数は在庫に反映されません。中止すると新しい棚卸しを始められます。
            </ConfirmDialog>
        </div>
    );
}
