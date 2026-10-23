"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, apiDelete, apiPatch, apiPost, errorText } from "@/lib/api";
import { ROLE } from "@/lib/labels";
import type { DepartmentOut, Role, UserRow } from "@/lib/types";
import { useMe } from "@/lib/use-me";
import { Badge, ConfirmDialog, Field, Modal, PageHeader, StateRow } from "@/components/ui";

const ROLES: Role[] = ["USER", "GUEST", "ADMIN"];

function useDepts() {
    return useQuery({ queryKey: ["depts"], queryFn: () => api<DepartmentOut[]>("/departments") }).data ?? [];
}

function CreateUser({ onDone }: { onDone: () => void }) {
    const depts = useDepts();
    const [f, setF] = useState({ username: "", password: "", display_name: "", user_role: "USER" as Role, department_id: "" });
    const create = useMutation({
        mutationFn: () => apiPost("/users", { ...f, department_id: f.department_id ? Number(f.department_id) : null }),
        onSuccess: () => { toast.success("登録しました。初回ログイン時にパスワードの変更が求められます"); setF({ username: "", password: "", display_name: "", user_role: "USER", department_id: "" }); onDone(); },
        onError: (e) => toast.error(errorText(e)),
    });
    const short = f.password.length > 0 && f.password.length < 8;
    return (
        <form className="card grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 lg:grid-cols-5" aria-label="ユーザーの追加" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
            <Field label="ユーザー名">{(id) => <input id={id} className="input" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} autoComplete="off" />}</Field>
            <Field label="仮パスワード" error={short ? "8文字以上" : null} hint="本人が初回ログインで変更します">{(id) => <input id={id} type="password" className="input" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} autoComplete="new-password" />}</Field>
            <Field label="表示名">{(id) => <input id={id} className="input" value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} />}</Field>
            <Field label="ロール">{(id) => <select id={id} className="input" value={f.user_role} onChange={(e) => setF({ ...f, user_role: e.target.value as Role })}>{ROLES.map((r) => <option key={r} value={r}>{ROLE[r].label}</option>)}</select>}</Field>
            <Field label="部署" hint={f.user_role === "GUEST" ? "ゲストは部署が必要です" : undefined}>{(id) => <select id={id} className="input" value={f.department_id} onChange={(e) => setF({ ...f, department_id: e.target.value })}>
                <option value="">未設定</option>{depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>}</Field>
            <div className="sm:col-span-2 lg:col-span-5">
                <button className="btn-primary" disabled={!f.username.trim() || f.password.length < 8 || !f.display_name.trim() || (f.user_role === "GUEST" && !f.department_id) || create.isPending}>追加</button>
            </div>
        </form>
    );
}

function EditUser({ user, onClose, onDone }: { user: UserRow; onClose: () => void; onDone: () => void }) {
    const depts = useDepts();
    const [f, setF] = useState({ display_name: user.display_name, user_role: user.user_role, department_id: user.department_id ? String(user.department_id) : "", password: "" });
    const save = useMutation({
        mutationFn: () => apiPatch(`/users/${user.id}`, {
            display_name: f.display_name, user_role: f.user_role, department_id: f.department_id ? Number(f.department_id) : null,
            ...(f.password ? { password: f.password } : {}),
        }),
        onSuccess: () => { toast.success(f.password ? "更新しました（次回ログイン時にパスワード変更が必要です）" : "更新しました"); onDone(); },
        onError: (e) => toast.error(errorText(e)),
    });
    return (
        <Modal open title={`ユーザーの編集：${user.username}`} onClose={onClose} footer={<>
            <button className="btn-secondary" onClick={onClose}>キャンセル</button>
            <button className="btn-primary" disabled={!f.display_name.trim() || (f.password.length > 0 && f.password.length < 8) || save.isPending} onClick={() => save.mutate()}>保存</button>
        </>}>
            <Field label="表示名">{(id) => <input id={id} className="input" value={f.display_name} onChange={(e) => setF({ ...f, display_name: e.target.value })} />}</Field>
            <Field label="ロール">{(id) => <select id={id} className="input" value={f.user_role} onChange={(e) => setF({ ...f, user_role: e.target.value as Role })}>{ROLES.map((r) => <option key={r} value={r}>{ROLE[r].label}</option>)}</select>}</Field>
            <Field label="部署">{(id) => <select id={id} className="input" value={f.department_id} onChange={(e) => setF({ ...f, department_id: e.target.value })}>
                <option value="">未設定</option>{depts.map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}
            </select>}</Field>
            <Field label="パスワードをリセット（任意）" hint="入れると仮パスワードになり、本人が次回ログインで変更します" error={f.password.length > 0 && f.password.length < 8 ? "8文字以上" : null}>
                {(id) => <input id={id} type="password" className="input" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} autoComplete="new-password" />}
            </Field>
        </Modal>
    );
}

export default function UsersPage() {
    const qc = useQueryClient();
    const { me } = useMe();
    const [showInactive, setShowInactive] = useState(false);
    const [edit, setEdit] = useState<UserRow | null>(null);
    const [deact, setDeact] = useState<UserRow | null>(null);
    const users = useQuery({ queryKey: ["users", showInactive], queryFn: () => api<UserRow[]>("/users", { params: { include_inactive: showInactive } }) });
    const refresh = () => qc.invalidateQueries({ queryKey: ["users"] });
    const remove = useMutation({
        mutationFn: (id: number) => apiDelete(`/users/${id}`),
        onSuccess: () => { toast.success("無効にしました"); setDeact(null); refresh(); },
        onError: (e) => toast.error(errorText(e)),
    });
    const unlock = useMutation({
        mutationFn: (id: number) => apiPatch(`/users/${id}`, { unlock: true }),
        onSuccess: () => { toast.success("ロックを解除しました"); refresh(); },
        onError: (e) => toast.error(errorText(e)),
    });
    const reactivate = useMutation({
        mutationFn: (id: number) => apiPatch(`/users/${id}`, { is_active: 1 }),
        onSuccess: () => { toast.success("有効に戻しました"); refresh(); },
        onError: (e) => toast.error(errorText(e)),
    });

    return (
        <div className="space-y-4">
            <PageHeader title="ユーザー管理" />
            <CreateUser onDone={refresh} />
            <label className="flex items-center gap-1 text-sm"><input type="checkbox" checked={showInactive} onChange={(e) => setShowInactive(e.target.checked)} />無効なユーザーも表示</label>
            <div className="card overflow-x-auto">
                <table className="table-zk">
                    <thead><tr><th>ユーザー名</th><th>表示名</th><th>ロール</th><th>部署</th><th>状態</th><th /></tr></thead>
                    <tbody>
                        <StateRow colSpan={6} loading={users.isLoading} error={users.error} empty={users.data?.length === 0} />
                        {users.data?.map((u) => (
                            <tr key={u.id} className={u.is_active ? "" : "text-slate-400"}>
                                <td>{u.username}</td><td>{u.display_name}</td>
                                <td><Badge map={ROLE} value={u.user_role} /></td>
                                <td>{u.department || "-"}</td>
                                <td className="text-xs">{!u.is_active ? "無効" : u.locked ? <span className="badge bg-rose-100 text-rose-700">ロック中</span> : u.must_change_password ? "パスワード変更待ち" : "有効"}</td>
                                <td className="space-x-3 whitespace-nowrap">
                                    <button className="btn-link text-xs" onClick={() => setEdit(u)}>編集</button>
                                    {u.locked && <button className="btn-link text-xs" disabled={unlock.isPending} onClick={() => unlock.mutate(u.id)}>ロック解除</button>}
                                    {u.id !== me?.id && (u.is_active
                                        ? <button className="btn-link text-xs text-rose-700" onClick={() => setDeact(u)}>無効にする</button>
                                        : <button className="btn-link text-xs" onClick={() => reactivate.mutate(u.id)}>有効に戻す</button>)}
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            {edit && <EditUser user={edit} onClose={() => setEdit(null)} onDone={() => { setEdit(null); refresh(); }} />}
            <ConfirmDialog open={!!deact} title="ユーザーを無効にする" confirmText="無効にする" danger busy={remove.isPending}
                onClose={() => setDeact(null)} onConfirm={() => deact && remove.mutate(deact.id)}>
                {deact?.display_name}（{deact?.username}）はログインできなくなります。履歴は残り、あとで有効に戻せます。
            </ConfirmDialog>
        </div>
    );
}
