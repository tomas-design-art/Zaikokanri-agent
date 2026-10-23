"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiPatch, apiPost, errorText } from "@/lib/api";
import { fmtQty, fmtSigned } from "@/lib/format";
import type { ItemDetail } from "@/lib/types";
import { ItemForm, type ItemPayload } from "@/components/ItemForm";
import { countError, Field, PageHeader, parseCount } from "@/components/ui";

/** 在庫数の直接修正（B-12）。理由は必須で、履歴には「調整」として残る。 */
function AdjustPanel({ item, onDone }: { item: ItemDetail; onDone: () => void }) {
    const [qty, setQty] = useState(String(item.quantity));
    const [reason, setReason] = useState("");
    const err = countError(qty, { label: "新しい在庫数" });
    const next = parseCount(qty);
    const diff = next === null ? null : next - item.quantity;
    const adjust = useMutation({
        mutationFn: () => apiPost("/adjust", { item_id: item.id, new_quantity: next, reason }),
        onSuccess: () => { toast.success("在庫数を調整しました"); setReason(""); onDone(); },
        onError: (e) => toast.error(errorText(e)),
    });
    return (
        <section className="card space-y-3 p-4" aria-label="在庫数の調整">
            <h2 className="font-semibold">在庫数の調整</h2>
            <p className="text-sm text-slate-600">現在の在庫：<b>{fmtQty(item.quantity, item.unit)}</b>。破損・紛失・数え直しなどで実際の数と違うときに使います。</p>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                <Field label="新しい在庫数" error={err} hint={diff !== null && diff !== 0 ? `増減 ${fmtSigned(diff)}` : undefined}>
                    {(id) => <input id={id} className="input" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} aria-invalid={!!err} />}
                </Field>
                <Field label="理由 *" className="sm:col-span-2">{(id) => <input id={id} className="input" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="例：破損のため" />}</Field>
            </div>
            <button className="btn-secondary" disabled={!!err || !reason.trim() || diff === 0 || adjust.isPending} onClick={() => adjust.mutate()}>調整する</button>
        </section>
    );
}

export default function ItemEditPage() {
    const router = useRouter();
    const qc = useQueryClient();
    const params = useParams<{ id: string }>();
    const id = Number(params.id);
    const { data: item, error, refetch } = useQuery({ queryKey: ["item", id], queryFn: () => api<ItemDetail>(`/items/${id}`), enabled: Number.isFinite(id) });

    const save = useMutation({
        mutationFn: (body: ItemPayload) => apiPatch(`/items/${id}`, body),
        onSuccess: () => {
            toast.success("更新しました");
            for (const key of [["item", id], ["items"], ["inventory"], ["kpi"]]) qc.invalidateQueries({ queryKey: key });
            router.push("/items");
        },
        onError: (e) => toast.error(errorText(e)),
    });

    if (error) return <p className="text-rose-600">{(error as Error).message}</p>;
    if (!item) return <div className="text-slate-500">読み込み中...</div>;
    return (
        <div className="max-w-3xl space-y-4">
            <PageHeader title="物品の編集" description={item.is_active ? undefined : "この物品は無効になっています"} />
            <ItemForm key={item.id} item={item} submitLabel="保存" busy={save.isPending} onSubmit={(b) => save.mutate(b)} onCancel={() => router.push("/items")} />
            {item.is_active === 1 && (
                <AdjustPanel key={item.quantity} item={item} onDone={() => { refetch(); qc.invalidateQueries({ queryKey: ["inventory"] }); }} />
            )}
        </div>
    );
}
