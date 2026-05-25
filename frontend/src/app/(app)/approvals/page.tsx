"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiJson } from "@/lib/api";
import type { Page, PendingOut } from "@/lib/types";

export default function ApprovalsPage() {
    const qc = useQueryClient();
    const { data } = useQuery({
        queryKey: ["pending"],
        queryFn: () => api<Page<PendingOut>>("/approvals", { params: { status: "PENDING" } }),
    });
    const decide = useMutation({
        mutationFn: ({ id, approve, reason }: { id: number; approve: boolean; reason?: string }) =>
            apiJson(`/approvals/${id}/decide`, { approve, reject_reason: reason || null }),
        onSuccess: () => {
            toast.success("処理しました");
            qc.invalidateQueries({ queryKey: ["pending"] });
            qc.invalidateQueries({ queryKey: ["kpi"] });
        },
        onError: (e: Error) => toast.error(e.message),
    });

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-bold">ゲスト出庫承認</h1>
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr><th>申請日時</th><th>物品</th><th className="text-right">数量</th><th className="text-right">現在庫</th><th>申請者</th><th>備考</th><th></th></tr></thead>
                    <tbody>
                        {data?.items.length === 0 ? (
                            <tr><td colSpan={7} className="text-center py-6 text-slate-500">保留中の申請はありません</td></tr>
                        ) : data?.items.map((p) => (
                            <tr key={p.id}>
                                <td className="text-xs text-slate-500">{p.created_at?.replace("T", " ").slice(0, 16)}</td>
                                <td>{p.item_name}</td>
                                <td className="text-right tabular-nums">{p.quantity}</td>
                                <td className="text-right tabular-nums">{p.current_stock}</td>
                                <td>{p.actor_name}</td>
                                <td className="text-xs text-slate-500">{p.note || ""}</td>
                                <td className="flex gap-1">
                                    <button className="text-xs text-emerald-700" onClick={() => decide.mutate({ id: p.id, approve: true })}>承認</button>
                                    <button className="text-xs text-rose-700" onClick={() => {
                                        const r = window.prompt("却下理由を入力してください") || "";
                                        if (r) decide.mutate({ id: p.id, approve: false, reason: r });
                                    }}>却下</button>
                                </td>
                            </tr>
                        )) || <tr><td colSpan={7} className="text-center py-6">読み込み中...</td></tr>}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
