"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { CategoryOut, DepartmentOut, ItemOut, VendorOut } from "@/lib/types";
import { countError, Field, parseCount } from "@/components/ui";

export type ItemPayload = Record<string, string | number | null>;

type FormState = {
    item_name: string; item_code: string; category: string; unit: string; vendor_name: string; vendor_item_code: string;
    unit_price: string; reorder_point: string; location_text: string; expiry_date: string;
    owner_department_id: string; is_common: boolean; is_inventory_target: boolean; initial_quantity: string;
};

function initial(item?: ItemOut): FormState {
    return {
        item_name: item?.item_name ?? "",
        item_code: item?.item_code ?? "",
        category: item?.category ?? "",
        unit: item?.unit ?? "個",
        vendor_name: item?.vendor_name ?? "",
        vendor_item_code: item?.vendor_item_code ?? "",
        unit_price: String(item?.unit_price ?? 0),
        reorder_point: item?.reorder_point == null ? "10" : String(item.reorder_point),
        location_text: item?.location_text ?? "",
        expiry_date: item?.expiry_date ?? "",
        owner_department_id: item?.owner_department_id == null ? "" : String(item.owner_department_id),
        is_common: item ? item.is_common === 1 : true,
        is_inventory_target: (item?.is_inventory_target ?? 1) === 1,
        initial_quantity: "0",
    };
}

/** 物品の登録・編集フォーム。数値は文字列で持ち、送る直前に確かめる（B-04 / B-13）。 */
export function ItemForm({ item, submitLabel, busy, onSubmit, onCancel }: {
    item?: ItemOut; submitLabel: string; busy?: boolean; onSubmit: (body: ItemPayload) => void; onCancel: () => void;
}) {
    const isNew = !item;
    const [f, setF] = useState<FormState>(() => initial(item));
    const cats = useQuery({ queryKey: ["cats"], queryFn: () => api<CategoryOut[]>("/categories") });
    const vendors = useQuery({ queryKey: ["vendors"], queryFn: () => api<VendorOut[]>("/vendors") });
    const depts = useQuery({ queryKey: ["depts"], queryFn: () => api<DepartmentOut[]>("/departments") });
    const set = <K extends keyof FormState>(k: K, v: FormState[K]) => setF((s) => ({ ...s, [k]: v }));

    const price = Number(f.unit_price);
    const priceErr = f.unit_price.trim() === "" || Number.isNaN(price) || price < 0 ? "単価は0以上の数値で入力してください" : null;
    const reorderErr = f.reorder_point.trim() === "" ? null : countError(f.reorder_point, { label: "発注点" });
    const initErr = isNew ? countError(f.initial_quantity, { label: "初期在庫" }) : null;
    // 所属部署か全社共通のどちらかは必ず（I-01）
    const ownerErr = !f.owner_department_id && !f.is_common ? "所属部署を選ぶか、全社共通にしてください" : null;
    const invalid = !f.item_name.trim() || !f.category || !f.unit.trim() || !!priceErr || !!reorderErr || !!initErr || !!ownerErr;

    function submit(e: React.FormEvent) {
        e.preventDefault();
        if (invalid) return;
        const body: ItemPayload = {
            item_name: f.item_name, item_code: f.item_code, category: f.category, unit: f.unit, vendor_name: f.vendor_name,
            vendor_item_code: f.vendor_item_code, unit_price: price,
            reorder_point: f.reorder_point.trim() === "" ? null : parseCount(f.reorder_point),
            location_text: f.location_text, expiry_date: f.expiry_date,
            owner_department_id: f.owner_department_id ? Number(f.owner_department_id) : null, is_common: f.is_common ? 1 : 0,
            is_inventory_target: f.is_inventory_target ? 1 : 0,
        };
        if (isNew) body.initial_quantity = parseCount(f.initial_quantity);
        onSubmit(body);
    }

    return (
        <form className="card grid grid-cols-1 gap-3 p-4 sm:grid-cols-2" onSubmit={submit}>
            <Field label="物品名 *" className="sm:col-span-2">{(id) => <input id={id} className="input" value={f.item_name} onChange={(e) => set("item_name", e.target.value)} required />}</Field>
            <Field label="物品コード">{(id) => <input id={id} className="input" value={f.item_code} onChange={(e) => set("item_code", e.target.value)} />}</Field>
            <Field label="カテゴリ *" hint={cats.data?.length === 0 ? "先に「業者・カテゴリ・部署」でカテゴリを登録してください" : undefined}>
                {(id) => (
                    <select id={id} className="input" value={f.category} onChange={(e) => set("category", e.target.value)} required>
                        <option value="">選択してください</option>
                        {cats.data?.map((c) => <option key={c.id} value={c.name}>{c.name}</option>)}
                        {f.category && !cats.data?.some((c) => c.name === f.category) && <option value={f.category}>{f.category}（無効）</option>}
                    </select>
                )}
            </Field>
            <Field label="単位 *" hint="個・箱・本 など">{(id) => <input id={id} className="input" value={f.unit} onChange={(e) => set("unit", e.target.value)} required maxLength={16} />}</Field>
            <Field label="業者">
                {(id) => (
                    <select id={id} className="input" value={f.vendor_name} onChange={(e) => set("vendor_name", e.target.value)}>
                        <option value="">未設定</option>
                        {vendors.data?.map((v) => <option key={v.id} value={v.vendor_name}>{v.vendor_name}</option>)}
                        {f.vendor_name && !vendors.data?.some((v) => v.vendor_name === f.vendor_name) && <option value={f.vendor_name}>{f.vendor_name}</option>}
                    </select>
                )}
            </Field>
            <Field label="業者品番">{(id) => <input id={id} className="input" value={f.vendor_item_code} onChange={(e) => set("vendor_item_code", e.target.value)} />}</Field>
            <Field label="単価（円）" error={priceErr}>{(id) => <input id={id} className="input" inputMode="decimal" value={f.unit_price} onChange={(e) => set("unit_price", e.target.value)} aria-invalid={!!priceErr} />}</Field>
            <Field label="発注点" hint="在庫がこの数以下になると「在庫不足」になります" error={reorderErr}>
                {(id) => <input id={id} className="input" inputMode="numeric" value={f.reorder_point} onChange={(e) => set("reorder_point", e.target.value)} aria-invalid={!!reorderErr} />}
            </Field>
            {isNew && (
                <Field label="初期在庫" hint="今ある数。0 のままでも後から入庫できます" error={initErr}>
                    {(id) => <input id={id} className="input" inputMode="numeric" value={f.initial_quantity} onChange={(e) => set("initial_quantity", e.target.value)} aria-invalid={!!initErr} />}
                </Field>
            )}
            <Field label="保管場所" hint="棚卸しはこの順に並びます">{(id) => <input id={id} className="input" value={f.location_text} onChange={(e) => set("location_text", e.target.value)} placeholder="例：倉庫A-1" />}</Field>
            <Field label="有効期限">{(id) => <input id={id} type="date" className="input" value={f.expiry_date} onChange={(e) => set("expiry_date", e.target.value)} />}</Field>
            <Field label="所属部署" hint="この部署の人の一覧に最初から出ます" error={ownerErr}>
                {(id) => (
                    <select id={id} className="input" value={f.owner_department_id} onChange={(e) => set("owner_department_id", e.target.value)} aria-invalid={!!ownerErr}>
                        <option value="">なし（全社共通の物品）</option>
                        {depts.data?.map((d) => <option key={d.id} value={String(d.id)}>{d.name}</option>)}
                        {f.owner_department_id && !depts.data?.some((d) => String(d.id) === f.owner_department_id) && <option value={f.owner_department_id}>（無効な部署）</option>}
                    </select>
                )}
            </Field>
            <label className="flex items-center gap-2 self-end pb-2 text-sm">
                <input type="checkbox" checked={f.is_common} onChange={(e) => set("is_common", e.target.checked)} />
                全社共通（どの部署の一覧にも出す。文具など）
            </label>
            <label className="flex items-center gap-2 text-sm sm:col-span-2">
                <input type="checkbox" checked={f.is_inventory_target} onChange={(e) => set("is_inventory_target", e.target.checked)} />
                棚卸しの対象にする
            </label>
            <div className="flex gap-2 sm:col-span-2">
                <button type="submit" className="btn-primary" disabled={invalid || busy}>{busy ? "保存中..." : submitLabel}</button>
                <button type="button" className="btn-secondary" onClick={onCancel}>キャンセル</button>
            </div>
        </form>
    );
}
