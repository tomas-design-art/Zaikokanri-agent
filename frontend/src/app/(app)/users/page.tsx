"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiJson } from "@/lib/api";
import type { DepartmentOut } from "@/lib/types";

interface UserRow { id: number; username: string; display_name: string; user_role: string; department: string | null; department_id: number | null; is_active: number; }

export default function UsersPage() {
    const qc = useQueryClient();
    const { data: users } = useQuery({ queryKey: ["users"], queryFn: () => api<UserRow[]>("/users") });
    const { data: depts } = useQuery({ queryKey: ["depts-all"], queryFn: () => api<DepartmentOut[]>("/departments") });
    const [form, setForm] = useState({ username: "", password: "", display_name: "", user_role: "USER", department_id: undefined as number | undefined });

    const create = useMutation({
        mutationFn: () => apiJson("/users", form),
        onSuccess: () => { toast.success("登録"); setForm({ username: "", password: "", display_name: "", user_role: "USER", department_id: undefined }); qc.invalidateQueries({ queryKey: ["users"] }); },
        onError: (e: Error) => toast.error(e.message),
    });

    const deact = useMutation({
        mutationFn: (id: number) => api(`/users/${id}`, { method: "DELETE" }),
        onSuccess: () => { toast.success("無効化"); qc.invalidateQueries({ queryKey: ["users"] }); },
        onError: (e: Error) => toast.error(e.message),
    });

    return (
        <div className="space-y-4">
            <h1 className="text-2xl font-bold">ユーザー管理</h1>
            <div className="card p-4 grid grid-cols-2 lg:grid-cols-5 gap-2">
                <input className="input" placeholder="username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
                <input className="input" type="password" placeholder="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
                <input className="input" placeholder="表示名" value={form.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
                <select className="input" value={form.user_role} onChange={(e) => setForm({ ...form, user_role: e.target.value })}>
                    <option value="GUEST">GUEST</option><option value="USER">USER</option><option value="ADMIN">ADMIN</option>
                </select>
                <select className="input" value={form.department_id ?? ""} onChange={(e) => setForm({ ...form, department_id: e.target.value ? parseInt(e.target.value) : undefined })}>
                    <option value="">部署未選択</option>
                    {depts?.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
                </select>
                <button className="btn-primary col-span-2 lg:col-span-5" disabled={!form.username || !form.password || !form.display_name || create.isPending} onClick={() => create.mutate()}>追加</button>
            </div>
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr><th>username</th><th>表示名</th><th>ロール</th><th>部署</th><th></th></tr></thead>
                    <tbody>
                        {users?.map((u) => (
                            <tr key={u.id}>
                                <td>{u.username}</td><td>{u.display_name}</td><td>{u.user_role}</td><td>{u.department || "-"}</td>
                                <td><button className="text-xs text-rose-600" onClick={() => { if (confirm("無効化しますか?")) deact.mutate(u.id); }}>無効化</button></td>
                            </tr>
                        )) || <tr><td colSpan={5} className="text-center py-6">読み込み中...</td></tr>}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
