"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiPost, errorText } from "@/lib/api";
import { fmtQty } from "@/lib/format";
import type { InventoryRow, PROut } from "@/lib/types";
import { useMe } from "@/lib/use-me";
import { useScope } from "@/lib/use-scope";
import { PageHeader, parseCount, ScopeToggle, StateRow } from "@/components/ui";

/** 推奨数量：発注点の2倍まで戻す数（最低1） */
const suggested = (r: InventoryRow) => Math.max(r.threshold * 2 - r.quantity, 1);

export default function AlertsPage() {
    const qc = useQueryClient();
    const router = useRouter();
    const { can } = useMe();
    const canRequest = can("USER");
    const { scope } = useScope();
    const low = useQuery({ queryKey: ["alert-low", scope], queryFn: () => api<InventoryRow[]>("/alerts/low-stock", { params: { scope } }) });
    const exp = useQuery({ queryKey: ["alert-exp", scope], queryFn: () => api<InventoryRow[]>("/alerts/expiring", { params: { days: 30, scope } }) });
    const [picked, setPicked] = useState<Record<number, string>>({});
    const pickedIds = Object.keys(picked).map(Number);
    const invalid = pickedIds.some((id) => parseCount(picked[id], { min: 1, max: 100000 }) === null);

    const create = useMutation({
        mutationFn: () => apiPost<PROut[]>("/purchase-requests/bulk", {
            items: pickedIds.map((id) => ({ item_id: id, requested_qty: parseCount(picked[id], { min: 1 }) })),
        }),
        onSuccess: (rows) => {
            toast.success(`${rows.length}件の発注を申請しました`, { action: { label: "発注申請を開く", onClick: () => router.push("/purchase-requests") } });
            setPicked({});
            qc.invalidateQueries({ queryKey: ["pr"] });
            qc.invalidateQueries({ queryKey: ["todo"] });
        },
        onError: (e) => toast.error(errorText(e)),
    });

    function toggle(r: InventoryRow, on: boolean) {
        setPicked((p) => {
            const n = { ...p };
            if (on) n[r.item_id] = String(suggested(r));
            else delete n[r.item_id];
            return n;
        });
    }

    return (
        <div className="space-y-6">
            <PageHeader title="アラート" actions={<ScopeToggle />} />
            <section aria-label="在庫不足">
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <h2 className="font-semibold">在庫不足（{low.data?.length ?? 0}件）</h2>
                    {canRequest && (
                        <button className="btn-primary" disabled={pickedIds.length === 0 || invalid || create.isPending} onClick={() => create.mutate()}>
                            選んだ{pickedIds.length}件の発注を申請
                        </button>
                    )}
                </div>
                <div className="card overflow-x-auto">
                    <table className="table-zk">
                        <thead><tr>{canRequest && <th className="w-10" />}<th>物品</th><th>カテゴリ</th><th>業者</th><th className="text-right">在庫</th><th className="text-right">発注点</th>{canRequest && <th>発注する数</th>}</tr></thead>
                        <tbody>
                            <StateRow colSpan={canRequest ? 7 : 5} loading={low.isLoading} error={low.error} empty={low.data?.length === 0} emptyText="在庫不足の物品はありません" />
                            {low.data?.map((r) => (
                                <tr key={r.item_id}>
                                    {canRequest && <td><input type="checkbox" aria-label={`${r.item_name}を発注する`} checked={r.item_id in picked} onChange={(e) => toggle(r, e.target.checked)} /></td>}
                                    <td>{r.item_name}</td><td>{r.category}</td><td className="text-slate-600">{r.vendor_name || "-"}</td>
                                    <td className="text-right font-semibold text-amber-600 tabular-nums">{fmtQty(r.quantity, r.unit)}</td>
                                    <td className="text-right tabular-nums">{r.threshold}</td>
                                    {canRequest && (
                                        <td className="w-32">
                                            {r.item_id in picked && (
                                                <input className="input" inputMode="numeric" aria-label={`${r.item_name}の発注数`} value={picked[r.item_id]}
                                                    onChange={(e) => setPicked((p) => ({ ...p, [r.item_id]: e.target.value }))} />
                                            )}
                                        </td>
                                    )}
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </section>
            <section aria-label="期限">
                <h2 className="mb-2 font-semibold">期限切れ・期限間近（30日以内）（{exp.data?.length ?? 0}件）</h2>
                <div className="card overflow-x-auto">
                    <table className="table-zk">
                        <thead><tr><th>物品</th><th>カテゴリ</th><th className="text-right">在庫</th><th>有効期限</th><th>状態</th><th /></tr></thead>
                        <tbody>
                            <StateRow colSpan={6} loading={exp.isLoading} error={exp.error} empty={exp.data?.length === 0} emptyText="期限切れ・期限間近の物品はありません" />
                            {exp.data?.map((r) => (
                                <tr key={r.item_id}>
                                    <td>{r.item_name}</td><td>{r.category}</td>
                                    <td className="text-right tabular-nums">{fmtQty(r.quantity, r.unit)}</td>
                                    <td>{r.expiry_date}</td>
                                    <td>
                                        {r.is_expired && <span className="badge bg-red-100 text-red-700">期限切れ</span>}
                                        {r.is_expiring_soon && <span className="badge bg-orange-100 text-orange-700">期限間近</span>}
                                    </td>
                                    <td>{r.is_expired && r.quantity > 0 && <Link className="btn-link text-xs" href={`/disposal?item=${r.item_id}`}>廃棄を申請</Link>}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </section>
        </div>
    );
}
