"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiPost, errorText } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { SESSION_STATUS } from "@/lib/labels";
import type { CategoryOut, StocktakeSession } from "@/lib/types";
import { useMe } from "@/lib/use-me";
import { StocktakeProgress } from "@/components/StocktakeProgress";
import { Badge, Field, PageHeader, StateRow } from "@/components/ui";

function CreateSession() {
    const router = useRouter();
    const qc = useQueryClient();
    const [name, setName] = useState(() => {
        const d = new Date(Date.now() + 9 * 3600_000);
        return `${d.getUTCFullYear()}年${d.getUTCMonth() + 1}月 棚卸し`;
    });
    const [category, setCategory] = useState("");
    const cats = useQuery({ queryKey: ["cats"], queryFn: () => api<CategoryOut[]>("/categories") });
    const create = useMutation({
        mutationFn: () => apiPost<StocktakeSession>("/stocktake/sessions", { name, category }),
        onSuccess: (s) => {
            toast.success(`「${s.name}」を始めました（対象 ${s.summary.total} 品目）`);
            qc.invalidateQueries({ queryKey: ["st-sessions"] });
            router.push(`/stocktake/${s.id}`);
        },
        onError: (e) => toast.error(errorText(e)),
    });
    return (
        <form className="card flex flex-wrap items-end gap-3 p-3" aria-label="棚卸しを始める" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
            <Field label="棚卸しの名前" className="w-full sm:w-72">{(id) => <input id={id} className="input" value={name} onChange={(e) => setName(e.target.value)} required />}</Field>
            <Field label="対象カテゴリ" className="w-full sm:w-48">
                {(id) => <select id={id} className="input" value={category} onChange={(e) => setCategory(e.target.value)}>
                    <option value="">すべて</option>
                    {cats.data?.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
                </select>}
            </Field>
            <button type="submit" className="btn-primary" disabled={!name.trim() || create.isPending}>{create.isPending ? "準備中..." : "棚卸しを始める"}</button>
            <p className="w-full text-xs text-slate-500">始めた時点の「棚卸し対象」の物品が一覧になります。実施中の棚卸しは1つだけです。</p>
        </form>
    );
}

export default function StocktakePage() {
    const { isAdmin } = useMe();
    const sessions = useQuery({ queryKey: ["st-sessions"], queryFn: () => api<StocktakeSession[]>("/stocktake/sessions") });
    const hasOpen = sessions.data?.some((s) => s.status === "OPEN");
    return (
        <div className="space-y-4">
            <PageHeader title="棚卸し" description="実際の数を数えて入力し、管理者が確定すると差異が在庫に反映されます" />
            {isAdmin && !hasOpen && <CreateSession />}
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr><th>名前</th><th>対象</th><th>状態</th><th>進捗</th><th>開始</th><th>完了</th><th /></tr></thead>
                    <tbody>
                        <StateRow colSpan={7} loading={sessions.isLoading} error={sessions.error} empty={sessions.data?.length === 0} emptyText="棚卸しはまだありません" />
                        {sessions.data?.map((s) => (
                            <tr key={s.id} className={s.status === "OPEN" ? "bg-brand-50" : ""}>
                                <td className="font-medium">{s.name}</td>
                                <td>{s.category || "すべて"}</td>
                                <td><Badge map={SESSION_STATUS} value={s.status} /></td>
                                <td><StocktakeProgress s={s.summary} /></td>
                                <td className="text-xs text-slate-500">{fmtDateTime(s.created_at)}<div>{s.created_by}</div></td>
                                <td className="text-xs text-slate-500">{fmtDateTime(s.closed_at)}</td>
                                <td><Link className="btn-secondary text-xs" href={`/stocktake/${s.id}`}>{s.status === "OPEN" ? "数える" : "結果を見る"}</Link></td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
