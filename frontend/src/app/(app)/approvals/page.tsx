"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiPost, errorText } from "@/lib/api";
import { cn } from "@/lib/cn";
import { fmtDateTime, fmtQty } from "@/lib/format";
import type { Page, PendingOut } from "@/lib/types";
import { PageHeader, ReasonDialog, StateRow } from "@/components/ui";

export default function ApprovalsPage() {
    const qc = useQueryClient();
    const [rejecting, setRejecting] = useState<PendingOut | null>(null);
    const { data, isLoading, error } = useQuery({
        queryKey: ["pending"],
        queryFn: () => api<Page<PendingOut>>("/approvals", { params: { status: "PENDING", per_page: 200 } }),
    });
    const refresh = () => { for (const k of ["pending", "kpi", "todo", "inventory", "history"]) qc.invalidateQueries({ queryKey: [k] }); };
    const decide = useMutation({
        mutationFn: ({ id, approve, reason }: { id: number; approve: boolean; reason?: string }) =>
            apiPost(`/approvals/${id}/decide`, { approve, reject_reason: reason ?? null }),
        onSuccess: (_d, v) => { toast.success(v.approve ? "承認しました（在庫から引きました）" : "却下しました"); setRejecting(null); refresh(); },
        onError: (e) => { toast.error(errorText(e)); refresh(); },
    });

    return (
        <div className="space-y-4">
            <PageHeader title="ゲスト出庫の承認" description="承認すると、その時点の在庫から引かれます" />
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr><th>申請日時</th><th>物品</th><th className="text-right">数量</th><th className="text-right">現在庫</th><th>申請者</th><th>部署</th><th>メモ</th><th /></tr></thead>
                    <tbody>
                        <StateRow colSpan={8} loading={isLoading} error={error} empty={data?.items.length === 0} emptyText="承認待ちの申請はありません" />
                        {data?.items.map((p) => (
                            <tr key={p.id}>
                                <td className="text-xs text-slate-500">{fmtDateTime(p.created_at)}</td>
                                <td>{p.item_name}</td>
                                <td className="text-right tabular-nums">{fmtQty(p.quantity, p.unit)}</td>
                                <td className={cn("text-right tabular-nums", p.current_stock < p.quantity && "font-semibold text-rose-600")}>{p.current_stock}</td>
                                <td>{p.actor_name}</td>
                                <td>{p.department || "-"}</td>
                                <td className="text-xs text-slate-500">{p.note || ""}</td>
                                <td className="space-x-3 whitespace-nowrap">
                                    <button className="btn-link text-xs text-emerald-700" disabled={decide.isPending || p.current_stock < p.quantity}
                                        title={p.current_stock < p.quantity ? "在庫が足りません" : undefined}
                                        onClick={() => decide.mutate({ id: p.id, approve: true })}>承認</button>
                                    <button className="btn-link text-xs text-rose-700" onClick={() => setRejecting(p)}>却下</button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <ReasonDialog open={!!rejecting} title="出庫申請を却下" label="却下理由" confirmText="却下する" danger busy={decide.isPending}
                onClose={() => setRejecting(null)} onSubmit={(reason) => rejecting && decide.mutate({ id: rejecting.id, approve: false, reason })}>
                <p className="text-sm">「{rejecting?.item_name}」{rejecting?.quantity}{rejecting?.unit}（{rejecting?.actor_name}）</p>
            </ReasonDialog>
        </div>
    );
}
