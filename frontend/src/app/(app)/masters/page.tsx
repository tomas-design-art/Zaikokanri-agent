"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiJson } from "@/lib/api";
import type { CategoryOut, DepartmentOut, VendorOut } from "@/lib/types";

export default function MastersPage() {
    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">マスタ管理</h1>
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <VendorPanel />
                <CategoryPanel />
                <DepartmentPanel />
            </div>
        </div>
    );
}

function VendorPanel() {
    const qc = useQueryClient();
    const { data } = useQuery({ queryKey: ["m-vendors"], queryFn: () => api<VendorOut[]>("/vendors") });
    const [code, setCode] = useState("");
    const [name, setName] = useState("");
    const create = useMutation({
        mutationFn: () => apiJson("/vendors", { vendor_code: code, vendor_name: name }),
        onSuccess: () => { toast.success("登録"); setCode(""); setName(""); qc.invalidateQueries({ queryKey: ["m-vendors"] }); },
        onError: (e: Error) => toast.error(e.message),
    });
    return (
        <div className="card p-3 space-y-2">
            <h2 className="font-semibold">業者</h2>
            <div className="flex gap-1"><input className="input" placeholder="コード" value={code} onChange={(e) => setCode(e.target.value)} />
                <input className="input" placeholder="名称" value={name} onChange={(e) => setName(e.target.value)} />
                <button className="btn-primary" disabled={!code || !name} onClick={() => create.mutate()}>追加</button></div>
            <ul className="text-sm divide-y">
                {data?.map((v) => <li key={v.id} className="py-1">{v.vendor_code} - {v.vendor_name}</li>)}
            </ul>
        </div>
    );
}

function CategoryPanel() {
    const qc = useQueryClient();
    const { data } = useQuery({ queryKey: ["m-cats"], queryFn: () => api<CategoryOut[]>("/categories") });
    const [name, setName] = useState("");
    const create = useMutation({
        mutationFn: () => apiJson("/categories", { name }),
        onSuccess: () => { toast.success("登録"); setName(""); qc.invalidateQueries({ queryKey: ["m-cats"] }); },
        onError: (e: Error) => toast.error(e.message),
    });
    return (
        <div className="card p-3 space-y-2">
            <h2 className="font-semibold">カテゴリ</h2>
            <div className="flex gap-1"><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="名称" />
                <button className="btn-primary" disabled={!name} onClick={() => create.mutate()}>追加</button></div>
            <ul className="text-sm divide-y">{data?.map((c) => <li key={c.id} className="py-1">{c.name}</li>)}</ul>
        </div>
    );
}

function DepartmentPanel() {
    const qc = useQueryClient();
    const { data } = useQuery({ queryKey: ["m-depts"], queryFn: () => api<DepartmentOut[]>("/departments") });
    const [name, setName] = useState("");
    const create = useMutation({
        mutationFn: () => apiJson("/departments", { name }),
        onSuccess: () => { toast.success("登録"); setName(""); qc.invalidateQueries({ queryKey: ["m-depts"] }); },
        onError: (e: Error) => toast.error(e.message),
    });
    return (
        <div className="card p-3 space-y-2">
            <h2 className="font-semibold">部署</h2>
            <div className="flex gap-1"><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="名称" />
                <button className="btn-primary" disabled={!name} onClick={() => create.mutate()}>追加</button></div>
            <ul className="text-sm divide-y">{data?.map((d) => <li key={d.id} className="py-1">{d.name}</li>)}</ul>
        </div>
    );
}
