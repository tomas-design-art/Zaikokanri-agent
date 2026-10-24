"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiDelete, apiPatch, apiPost, errorText } from "@/lib/api";
import type { CategoryOut, DepartmentOut, VendorOut } from "@/lib/types";
import { Field, Modal, PageHeader } from "@/components/ui";

function useMasterMutations(path: string, keys: string[]) {
    const qc = useQueryClient();
    const done = (msg: string) => () => { toast.success(msg); for (const k of keys) qc.invalidateQueries({ queryKey: [k] }); };
    const onError = (e: Error) => toast.error(errorText(e));
    return {
        create: useMutation({ mutationFn: (body: object) => apiPost(path, body), onSuccess: done("登録しました"), onError }),
        update: useMutation({ mutationFn: ({ id, body }: { id: number; body: object }) => apiPatch(`${path}/${id}`, body), onSuccess: done("更新しました"), onError }),
        remove: useMutation({ mutationFn: (id: number) => apiDelete(`${path}/${id}`), onSuccess: done("無効にしました"), onError }),
    };
}

function VendorPanel() {
    const [showInactive, setShowInactive] = useState(false);
    const { data } = useQuery({ queryKey: ["vendors-all", showInactive], queryFn: () => api<VendorOut[]>("/vendors", { params: { include_inactive: showInactive } }) });
    const m = useMasterMutations("/vendors", ["vendors-all", "vendors", "items", "inventory"]);
    const [code, setCode] = useState("");
    const [name, setName] = useState("");
    const [edit, setEdit] = useState<VendorOut | null>(null);
    return (
        <section className="card space-y-3 p-3" aria-label="業者">
            <h2 className="font-semibold">業者</h2>
            <form className="grid grid-cols-[1fr_2fr_auto] items-end gap-2" onSubmit={(e) => { e.preventDefault(); m.create.mutate({ vendor_code: code, vendor_name: name }, { onSuccess: () => { setCode(""); setName(""); } }); }}>
                <Field label="業者コード">{(id) => <input id={id} className="input" value={code} onChange={(e) => setCode(e.target.value)} />}</Field>
                <Field label="業者名">{(id) => <input id={id} className="input" value={name} onChange={(e) => setName(e.target.value)} />}</Field>
                <button className="btn-primary" disabled={!code.trim() || !name.trim()}>追加</button>
            </form>
            <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />無効も表示</label>
            <ul className="divide-y text-sm">
                {data?.map((v) => (
                    <li key={v.id} className={`flex items-center justify-between gap-2 py-1.5 ${v.is_active ? "" : "text-slate-400"}`}>
                        <span>{v.vendor_code}・{v.vendor_name}</span>
                        <span className="space-x-3 whitespace-nowrap">
                            <button className="btn-link text-xs" onClick={() => setEdit(v)}>編集</button>
                            <button className="btn-link text-xs" onClick={() => m.update.mutate({ id: v.id, body: { is_active: v.is_active ? 0 : 1 } })}>{v.is_active ? "無効にする" : "有効に戻す"}</button>
                        </span>
                    </li>
                ))}
            </ul>
            {edit && <VendorEdit vendor={edit} onClose={() => setEdit(null)} onSave={(body) => m.update.mutate({ id: edit.id, body }, { onSuccess: () => setEdit(null) })} />}
        </section>
    );
}

function VendorEdit({ vendor, onClose, onSave }: { vendor: VendorOut; onClose: () => void; onSave: (b: object) => void }) {
    const [f, setF] = useState({ vendor_code: vendor.vendor_code, vendor_name: vendor.vendor_name, address: vendor.address ?? "", phone: vendor.phone ?? "", email: vendor.email ?? "" });
    const fields: [keyof typeof f, string][] = [["vendor_code", "業者コード"], ["vendor_name", "業者名"], ["address", "住所"], ["phone", "電話"], ["email", "メール"]];
    return (
        <Modal open title="業者の編集" onClose={onClose} footer={<>
            <button className="btn-secondary" onClick={onClose}>キャンセル</button>
            <button className="btn-primary" disabled={!f.vendor_code.trim() || !f.vendor_name.trim()} onClick={() => onSave(f)}>保存</button>
        </>}>
            {fields.map(([k, label]) => <Field key={k} label={label}>{(id) => <input id={id} className="input" value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} />}</Field>)}
            <p className="text-xs text-slate-500">業者名を変えると、その業者の物品の業者名も同じ名前に変わります。</p>
        </Modal>
    );
}

function NamePanel({ title, path, queryKey }: { title: string; path: string; queryKey: string }) {
    const [showInactive, setShowInactive] = useState(false);
    const { data } = useQuery({ queryKey: [queryKey, showInactive], queryFn: () => api<(CategoryOut | DepartmentOut)[]>(path, { params: { include_inactive: showInactive } }) });
    const m = useMasterMutations(path, [queryKey, "cats", "depts", "items", "inventory"]);
    const [name, setName] = useState("");
    const [edit, setEdit] = useState<{ id: number; name: string } | null>(null);
    return (
        <section className="card space-y-3 p-3" aria-label={title}>
            <h2 className="font-semibold">{title}</h2>
            <form className="flex items-end gap-2" onSubmit={(e) => { e.preventDefault(); m.create.mutate({ name }, { onSuccess: () => setName("") }); }}>
                <Field label={`${title}名`} className="flex-1">{(id) => <input id={id} className="input" value={name} onChange={(e) => setName(e.target.value)} />}</Field>
                <button className="btn-primary" disabled={!name.trim()}>追加</button>
            </form>
            <label className="flex items-center gap-1 text-xs"><input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />無効も表示</label>
            <ul className="divide-y text-sm">
                {data?.map((c) => (
                    <li key={c.id} className={`flex items-center justify-between gap-2 py-1.5 ${c.is_active ? "" : "text-slate-400"}`}>
                        <span>{c.name}</span>
                        <span className="space-x-3 whitespace-nowrap">
                            <button className="btn-link text-xs" onClick={() => setEdit({ id: c.id, name: c.name })}>名前を変更</button>
                            <button className="btn-link text-xs" onClick={() => m.update.mutate({ id: c.id, body: { is_active: c.is_active ? 0 : 1 } })}>{c.is_active ? "無効にする" : "有効に戻す"}</button>
                        </span>
                    </li>
                ))}
            </ul>
            {edit && (
                <Modal open title={`${title}名の変更`} onClose={() => setEdit(null)} footer={<>
                    <button className="btn-secondary" onClick={() => setEdit(null)}>キャンセル</button>
                    <button className="btn-primary" disabled={!edit.name.trim()} onClick={() => m.update.mutate({ id: edit.id, body: { name: edit.name } }, { onSuccess: () => setEdit(null) })}>保存</button>
                </>}>
                    <Field label="新しい名前">{(id) => <input id={id} className="input" value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} />}</Field>
                    <p className="text-xs text-slate-500">使っている物品・ユーザーの表示も新しい名前に変わります。</p>
                </Modal>
            )}
        </section>
    );
}

export default function MastersPage() {
    return (
        <div className="space-y-6">
            <PageHeader title="業者・カテゴリ・部署" description="使わなくなったものは削除ではなく「無効」にします（過去の記録は残ります）" />
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
                <VendorPanel />
                <NamePanel title="カテゴリ" path="/categories" queryKey="m-cats" />
                <NamePanel title="部署" path="/departments" queryKey="m-depts" />
            </div>
        </div>
    );
}
