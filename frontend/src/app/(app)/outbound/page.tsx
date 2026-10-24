"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiPost, errorText } from "@/lib/api";
import { fmtDateTime, fmtQty } from "@/lib/format";
import { REQUEST_STATUS } from "@/lib/labels";
import type { InventoryRow, MyRequest, Page, StockResult } from "@/lib/types";
import { useDebouncedValue } from "@/lib/use-debounced-value";
import { useMe } from "@/lib/use-me";
import { useScope } from "@/lib/use-scope";
import { Badge, Field, PageHeader, parseCount, ScopeToggle, StateRow } from "@/components/ui";

interface CartLine { row: InventoryRow; qty: string; note: string }

function lineError(l: CartLine): string | null {
    const n = parseCount(l.qty, { min: 1, max: 1000 });
    if (n === null) return "数量は1〜1000の整数で入力してください";
    if (n > l.row.quantity) return `在庫（${fmtQty(l.row.quantity, l.row.unit)}）を超えています`;
    return null;
}

function MyRequests() {
    const mine = useQuery({ queryKey: ["my-requests"], queryFn: () => api<MyRequest[]>("/outbound/my-requests") });
    return (
        <section className="card overflow-x-auto" aria-label="あなたの出庫申請">
            <h2 className="p-3 font-semibold">あなたの出庫申請</h2>
            <table className="table-zk">
                <thead><tr><th>申請日時</th><th>物品</th><th className="text-right">数量</th><th>状態</th><th>却下理由</th></tr></thead>
                <tbody>
                    <StateRow colSpan={5} loading={mine.isLoading} error={mine.error} empty={mine.data?.length === 0} emptyText="申請はまだありません" />
                    {mine.data?.map((r) => (
                        <tr key={r.id}>
                            <td className="text-xs text-slate-500">{fmtDateTime(r.created_at)}</td>
                            <td>{r.item_name}</td>
                            <td className="text-right tabular-nums">{r.quantity}</td>
                            <td><Badge map={REQUEST_STATUS} value={r.status} /></td>
                            <td className="text-xs text-rose-700">{r.reject_reason || ""}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </section>
    );
}

export default function OutboundPage() {
    const qc = useQueryClient();
    const { isGuest } = useMe();
    const { scope } = useScope();
    const [q, setQ] = useState("");
    const [cart, setCart] = useState<CartLine[]>([]);
    const qDeb = useDebouncedValue(q, 250);
    const search = useQuery({
        queryKey: ["outbound-search", qDeb, scope],
        queryFn: () => api<Page<InventoryRow>>("/inventory", { params: { q: qDeb, per_page: 30, scope } }),
    });

    const refresh = () => { for (const k of ["outbound-search", "inventory", "kpi", "history", "my-requests", "todo"]) qc.invalidateQueries({ queryKey: [k] }); };

    const undo = useMutation({
        mutationFn: async (ids: number[]) => { for (const id of ids) await apiPost(`/history/${id}/undo`); },
        onSuccess: () => { toast.success("出庫を取り消しました"); refresh(); },
        onError: (e) => { toast.error(errorText(e)); refresh(); },
    });

    const submit = useMutation({
        mutationFn: () => apiPost<StockResult[]>("/outbound/bulk", {
            items: cart.map((c) => ({ item_id: c.row.item_id, quantity: parseCount(c.qty), note: c.note || null })),
        }),
        onSuccess: (results) => {
            setCart([]);
            refresh();
            if (results.every((r) => r.pending)) {
                toast.success(`${results.length}件を承認待ちとして申請しました。管理者の承認後に在庫から引かれます`);
                return;
            }
            const ids = results.map((r) => r.history_id).filter((x): x is number => x !== null);
            toast.success(`${results.length}件を出庫しました`, {
                description: "10分以内なら取り消せます",
                action: { label: "取り消す", onClick: () => undo.mutate(ids) },
                duration: 15_000,
            });
        },
        onError: (e) => toast.error(errorText(e)),
    });

    function add(r: InventoryRow) {
        if (cart.some((c) => c.row.item_id === r.item_id)) return toast.info("すでにカートに入っています");
        setCart((c) => [...c, { row: r, qty: "1", note: "" }]);
    }
    const update = (id: number, patch: Partial<CartLine>) => setCart((arr) => arr.map((x) => (x.row.item_id === id ? { ...x, ...patch } : x)));
    const hasError = cart.some((c) => lineError(c) !== null);

    return (
        <div className="space-y-4">
            <PageHeader title={isGuest ? "出庫の申請" : "出庫"}
                description={isGuest ? "ゲストの出庫は、同じ部署の正社員か管理者の承認後に在庫から引かれます" : "使う物品をカートに入れて、まとめて出庫します"}
                actions={<ScopeToggle />} />
            <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
                <section className="card space-y-3 p-3" aria-label="物品の検索">
                    <Field label="物品を検索">{(id) => <input id={id} className="input" placeholder="物品名 / コード / 業者" value={q} onChange={(e) => setQ(e.target.value)} />}</Field>
                    <div className="max-h-[520px] overflow-y-auto">
                        <table className="table-zk">
                            <thead><tr><th>物品名</th><th className="text-right">在庫</th><th /></tr></thead>
                            <tbody>
                                <StateRow colSpan={3} loading={search.isLoading} error={search.error} empty={search.data?.items.length === 0} emptyText="見つかりません" />
                                {search.data?.items.map((r) => (
                                    <tr key={r.item_id}>
                                        <td>{r.item_name}<div className="text-xs text-slate-500">{r.category}{r.location ? `・${r.location}` : ""}</div></td>
                                        <td className="text-right tabular-nums">{fmtQty(r.quantity, r.unit)}</td>
                                        <td className="text-right">
                                            <button className="btn-secondary text-xs" disabled={r.quantity <= 0} onClick={() => add(r)} aria-label={`${r.item_name}をカートに追加`}>
                                                {r.quantity <= 0 ? "在庫なし" : "追加"}
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </section>
                <section className="card space-y-3 p-3" aria-label="カート">
                    <h2 className="font-semibold">カート（{cart.length}件）</h2>
                    {cart.length === 0 ? (
                        <p className="text-sm text-slate-500">左の一覧から物品を追加してください</p>
                    ) : (
                        <ul className="space-y-2">
                            {cart.map((c) => {
                                const err = lineError(c);
                                return (
                                    <li key={c.row.item_id} className="rounded border p-2" aria-label={`カート：${c.row.item_name}`}>
                                        <div className="flex items-center justify-between gap-2">
                                            <span className="text-sm font-medium">{c.row.item_name}<span className="ml-1 text-xs text-slate-500">在庫 {fmtQty(c.row.quantity, c.row.unit)}</span></span>
                                            <button className="btn-link text-xs text-rose-700" onClick={() => setCart((arr) => arr.filter((x) => x.row.item_id !== c.row.item_id))}>削除</button>
                                        </div>
                                        <div className="mt-1 grid grid-cols-2 gap-2">
                                            <Field label={`数量（${c.row.unit}）`} error={err}>
                                                {(id) => <input id={id} className="input" inputMode="numeric" value={c.qty} aria-invalid={!!err} onChange={(e) => update(c.row.item_id, { qty: e.target.value })} />}
                                            </Field>
                                            <Field label="メモ">{(id) => <input id={id} className="input" value={c.note} onChange={(e) => update(c.row.item_id, { note: e.target.value })} />}</Field>
                                        </div>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                    <button className="btn-primary w-full" disabled={cart.length === 0 || hasError || submit.isPending} onClick={() => submit.mutate()}>
                        {submit.isPending ? "送信中..." : isGuest ? `${cart.length}件の出庫を申請する` : `${cart.length}件まとめて出庫する`}
                    </button>
                </section>
            </div>
            {isGuest && <MyRequests />}
        </div>
    );
}
