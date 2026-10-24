"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiPost, errorText } from "@/lib/api";
import { fmtDateTime, fmtQty } from "@/lib/format";
import { PRIORITY, REQUEST_STATUS } from "@/lib/labels";
import type { InventoryRow, Page, PROut, StockResult } from "@/lib/types";
import { Badge, countError, Field, ItemPicker, PageHeader, parseCount, StateRow, Tabs } from "@/components/ui";

type Tab = "normal" | "receive";

function useRefresh() {
    const qc = useQueryClient();
    return () => { for (const k of ["inventory", "kpi", "history", "receivable", "pr", "todo", "item-picker"]) qc.invalidateQueries({ queryKey: [k] }); };
}

function NormalInbound() {
    const refresh = useRefresh();
    const [row, setRow] = useState<InventoryRow | null>(null);
    const [qty, setQty] = useState("1");
    const [vendor, setVendor] = useState("");
    const [price, setPrice] = useState("");
    const [note, setNote] = useState("");
    const qtyErr = countError(qty, { min: 1, max: 10000 });
    const priceNum = price.trim() === "" ? null : Number(price);
    const priceErr = priceNum !== null && (Number.isNaN(priceNum) || priceNum < 0) ? "単価は0以上の数値で入力してください" : null;

    function select(r: InventoryRow | null) {
        setRow(r);
        // 物品を選んだら業者・単価をマスターの値で初期入力する（B-21）
        setVendor(r?.vendor_name ?? "");
        setPrice(r && r.unit_price ? String(r.unit_price) : "");
    }

    const undo = useMutation({
        mutationFn: (id: number) => apiPost(`/history/${id}/undo`),
        onSuccess: () => { toast.success("入庫を取り消しました"); refresh(); },
        onError: (e) => toast.error(errorText(e)),
    });
    const submit = useMutation({
        mutationFn: () => apiPost<StockResult>("/inbound", {
            item_id: row?.item_id, quantity: parseCount(qty), vendor_name: vendor || null, unit_price: priceNum, note: note || null,
        }),
        onSuccess: (r) => {
            toast.success(`「${r.item_name}」を入庫しました（在庫 ${r.new_quantity}）`, {
                action: r.history_id ? { label: "取り消す", onClick: () => undo.mutate(r.history_id!) } : undefined,
                duration: 15_000,
            });
            select(null); setQty("1"); setNote("");
            refresh();
        },
        onError: (e) => toast.error(errorText(e)),
    });

    return (
        <form className="card max-w-2xl space-y-3 p-4" onSubmit={(e) => { e.preventDefault(); submit.mutate(); }}>
            <ItemPicker value={row} onChange={select} />
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Field label={`数量${row ? `（${row.unit}）` : ""}`} error={qtyErr}>{(id) => <input id={id} className="input" inputMode="numeric" value={qty} onChange={(e) => setQty(e.target.value)} aria-invalid={!!qtyErr} />}</Field>
                <Field label="単価（円・任意）" error={priceErr}>{(id) => <input id={id} className="input" inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value)} aria-invalid={!!priceErr} />}</Field>
            </div>
            <Field label="業者名（任意）">{(id) => <input id={id} className="input" value={vendor} onChange={(e) => setVendor(e.target.value)} />}</Field>
            <Field label="備考（任意）">{(id) => <input id={id} className="input" value={note} onChange={(e) => setNote(e.target.value)} />}</Field>
            <button type="submit" className="btn-primary w-full" disabled={!row || !!qtyErr || !!priceErr || submit.isPending}>
                {submit.isPending ? "送信中..." : "入庫を登録"}
            </button>
        </form>
    );
}

function ReceiveRow({ pr }: { pr: PROut }) {
    const refresh = useRefresh();
    const [qty, setQty] = useState(String(pr.remaining_qty));
    const err = countError(qty, { min: 1, max: pr.remaining_qty, label: "受領数" });
    const receive = useMutation({
        mutationFn: () => apiPost("/inbound/receive", { purchase_request_id: pr.id, received_qty: parseCount(qty) }),
        onSuccess: () => { toast.success(`「${pr.item_name}」を受領しました`); refresh(); },
        onError: (e) => toast.error(errorText(e)),
    });
    return (
        <tr>
            <td className="text-xs text-slate-500">#{pr.id}<br />{fmtDateTime(pr.created_at)}</td>
            <td>{pr.item_name}<div className="text-xs text-slate-500">{pr.vendor_name || ""}</div></td>
            <td><Badge map={REQUEST_STATUS} value={pr.status} /> <Badge map={PRIORITY} value={pr.priority === "NORMAL" ? null : pr.priority} /></td>
            <td className="text-right tabular-nums">{fmtQty(pr.requested_qty, pr.unit)}</td>
            <td className="text-right tabular-nums">{pr.received_qty}</td>
            <td className="w-32">
                <input className="input" inputMode="numeric" aria-label={`${pr.item_name}の受領数`} value={qty} onChange={(e) => setQty(e.target.value)} aria-invalid={!!err} title={err ?? undefined} />
            </td>
            <td><button className="btn-primary text-xs" disabled={!!err || receive.isPending} onClick={() => receive.mutate()}>受領</button></td>
        </tr>
    );
}

function Receive() {
    const list = useQuery({
        queryKey: ["receivable"],
        queryFn: () => api<Page<PROut>>("/purchase-requests", { params: { receivable: true, per_page: 200 } }),
    });
    return (
        <section className="card overflow-x-auto" aria-label="発注品の受領">
            <p className="p-3 text-sm text-slate-600">承認済・発注済の申請です。届いた数を入れて「受領」を押すと在庫に入ります。全数そろうと「受領済」になります。</p>
            <table className="table-zk">
                <thead><tr><th>申請</th><th>物品</th><th>状態</th><th className="text-right">申請数</th><th className="text-right">受領済</th><th>今回の受領数</th><th /></tr></thead>
                <tbody>
                    <StateRow colSpan={7} loading={list.isLoading} error={list.error} empty={list.data?.items.length === 0} emptyText="受領を待っている発注はありません" />
                    {list.data?.items.map((pr) => <ReceiveRow key={`${pr.id}-${pr.received_qty}`} pr={pr} />)}
                </tbody>
            </table>
        </section>
    );
}

function InboundInner() {
    const router = useRouter();
    const search = useSearchParams();
    const tab: Tab = search.get("tab") === "receive" ? "receive" : "normal";
    return (
        <div className="space-y-4">
            <PageHeader title="入庫" />
            <Tabs<Tab> tabs={[{ value: "normal", label: "通常の入庫" }, { value: "receive", label: "発注品の受領" }]} value={tab}
                onChange={(t) => router.replace(t === "receive" ? "/inbound?tab=receive" : "/inbound")} />
            {tab === "normal" ? <NormalInbound /> : <Receive />}
        </div>
    );
}

export default function InboundPage() {
    return <Suspense fallback={null}><InboundInner /></Suspense>;
}
