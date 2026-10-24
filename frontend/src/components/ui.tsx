"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { LoaderCircle, Search, X } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import type { LabelMap } from "@/lib/labels";
import { fmtQty } from "@/lib/format";
import type { DepartmentOut, InventoryRow, Page } from "@/lib/types";
import { useDebouncedValue } from "@/lib/use-debounced-value";
import { useScope } from "@/lib/use-scope";

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
    return (
        <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
                <h1 className="text-2xl font-bold">{title}</h1>
                {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
            </div>
            {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
    );
}

export function Badge({ map, value, className }: { map: LabelMap; value: string | null | undefined; className?: string }) {
    if (!value) return null;
    const m = map[value];
    return <span className={cn("badge", m?.cls ?? "bg-slate-100 text-slate-600", className)}>{m?.label ?? value}</span>;
}

/** 表の「読み込み中 / エラー / 0件」の行。どれにも当たらなければ何も出さない（E-03）。 */
export function StateRow({ colSpan, loading, error, empty, emptyText = "該当するデータはありません" }: {
    colSpan: number; loading?: boolean; error?: unknown; empty?: boolean; emptyText?: string;
}) {
    let content: ReactNode = null;
    if (loading) content = <span className="inline-flex items-center gap-2"><LoaderCircle className="animate-spin" size={16} />読み込み中...</span>;
    else if (error) content = <span className="text-rose-600">{error instanceof Error ? error.message : "読み込みに失敗しました"}</span>;
    else if (empty) content = emptyText;
    if (!content) return null;
    return <tr><td colSpan={colSpan} className="py-8 text-center text-slate-500">{content}</td></tr>;
}

export function Pager({ page, perPage, total, onChange }: { page: number; perPage: number; total: number; onChange: (p: number) => void }) {
    const pages = Math.max(1, Math.ceil(total / perPage));
    if (total <= perPage) return null;
    return (
        <nav className="flex items-center justify-end gap-2" aria-label="ページ送り">
            <button className="btn-secondary" disabled={page <= 1} onClick={() => onChange(page - 1)}>前へ</button>
            <span className="text-sm text-slate-500">{page} / {pages} ページ（{total}件）</span>
            <button className="btn-secondary" disabled={page >= pages} onClick={() => onChange(page + 1)}>次へ</button>
        </nav>
    );
}

export function Field({ label, hint, error, className, children }: {
    label: string; hint?: ReactNode; error?: string | null; className?: string; children: (id: string) => ReactNode;
}) {
    const id = useId();
    return (
        <div className={className}>
            <label htmlFor={id} className="label">{label}</label>
            {children(id)}
            {error ? <p className="mt-1 text-xs text-rose-600">{error}</p> : hint ? <p className="mt-1 text-xs text-slate-500">{hint}</p> : null}
        </div>
    );
}

/** 数量の文字列を整数にする。空・小数・範囲外は null。 */
export function parseCount(text: string, { min = 0, max = 10_000_000 }: { min?: number; max?: number } = {}): number | null {
    const t = text.trim().replace(/[０-９]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0));
    if (!/^\d+$/.test(t)) return null;
    const n = Number(t);
    return n >= min && n <= max ? n : null;
}

export function countError(text: string, opts: { min?: number; max?: number; label?: string } = {}): string | null {
    const { min = 0, max = 10_000_000, label = "数量" } = opts;
    if (text.trim() === "") return `${label}を入力してください`;
    return parseCount(text, { min, max }) === null ? `${label}は${min}〜${max.toLocaleString()}の整数で入力してください` : null;
}

export function Modal({ open, title, onClose, children, footer, wide }: {
    open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean;
}) {
    const titleId = useId();
    useEffect(() => {
        if (!open) return;
        const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
        window.addEventListener("keydown", onKey);
        return () => window.removeEventListener("keydown", onKey);
    }, [open, onClose]);
    if (!open) return null;
    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onClick={onClose}>
            <div
                role="dialog" aria-modal="true" aria-labelledby={titleId}
                className={cn("max-h-[90vh] w-full overflow-y-auto rounded-lg bg-white p-5 shadow-xl", wide ? "max-w-3xl" : "max-w-md")}
                onClick={(e) => e.stopPropagation()}
            >
                <div className="mb-4 flex items-center justify-between gap-2">
                    <h2 id={titleId} className="text-lg font-bold">{title}</h2>
                    <button className="rounded p-1 text-slate-500 hover:bg-slate-100" onClick={onClose} aria-label="閉じる"><X size={18} /></button>
                </div>
                <div className="space-y-3">{children}</div>
                {footer && <div className="mt-5 flex justify-end gap-2">{footer}</div>}
            </div>
        </div>
    );
}

type ReasonDialogProps = {
    open: boolean; title: string; label: string; confirmText: string; danger?: boolean; required?: boolean; busy?: boolean;
    onSubmit: (text: string) => void; onClose: () => void; children?: ReactNode;
};

/** 理由・コメントを入れて確定するダイアログ（window.prompt の置き換え：C-02）。開くたびに入力は空から。 */
export function ReasonDialog(props: ReasonDialogProps) {
    return props.open ? <ReasonDialogBody {...props} /> : null;
}

function ReasonDialogBody({ title, label, confirmText, danger, required = true, busy, onSubmit, onClose, children }: ReasonDialogProps) {
    const [text, setText] = useState("");
    const invalid = required && !text.trim();
    return (
        <Modal open title={title} onClose={onClose} footer={<>
            <button className="btn-secondary" onClick={onClose}>キャンセル</button>
            <button className={danger ? "btn-danger" : "btn-primary"} disabled={invalid || busy} onClick={() => onSubmit(text.trim())}>{confirmText}</button>
        </>}>
            {children}
            <Field label={label}>{(id) => <textarea id={id} className="input min-h-24" value={text} onChange={(e) => setText(e.target.value)} autoFocus />}</Field>
        </Modal>
    );
}

export function ConfirmDialog({ open, title, confirmText, danger, busy, onConfirm, onClose, children }: {
    open: boolean; title: string; confirmText: string; danger?: boolean; busy?: boolean; onConfirm: () => void; onClose: () => void; children: ReactNode;
}) {
    return (
        <Modal open={open} title={title} onClose={onClose} footer={<>
            <button className="btn-secondary" onClick={onClose}>キャンセル</button>
            <button className={danger ? "btn-danger" : "btn-primary"} disabled={busy} onClick={onConfirm}>{busy ? "処理中..." : confirmText}</button>
        </>}>
            <div className="text-sm text-slate-700">{children}</div>
        </Modal>
    );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { value: T; label: string }[]; value: T; onChange: (v: T) => void }) {
    return (
        <div role="tablist" className="flex gap-1 border-b border-slate-200">
            {tabs.map((t) => (
                <button key={t.value} role="tab" aria-selected={value === t.value} onClick={() => onChange(t.value)}
                    className={cn("-mb-px border-b-2 px-4 py-2 text-sm font-medium", value === t.value ? "border-brand-600 text-brand-700" : "border-transparent text-slate-500 hover:text-slate-800")}>
                    {t.label}
                </button>
            ))}
        </div>
    );
}

/** 物品を検索して1つ選ぶ。選んだら行を返す。 */
export function ItemPicker({ label = "物品", value, onChange, autoFocus }: {
    label?: string; value: InventoryRow | null; onChange: (row: InventoryRow | null) => void; autoFocus?: boolean;
}) {
    const [q, setQ] = useState("");
    const qDeb = useDebouncedValue(q, 250);
    const inputRef = useRef<HTMLInputElement>(null);
    const { scope } = useScope();
    const search = useQuery({
        queryKey: ["item-picker", qDeb, scope],
        queryFn: () => api<Page<InventoryRow>>("/inventory", { params: { q: qDeb, per_page: 20, scope } }),
        enabled: qDeb.trim().length > 0 && !value,
    });
    if (value) {
        return (
            <div>
                <span className="label">{label}</span>
                <div className="flex items-center justify-between gap-2 rounded-md bg-brand-50 px-3 py-2 text-sm">
                    <span>選択中：<b>{value.item_name}</b> <span className="text-slate-500">（在庫 {fmtQty(value.quantity, value.unit)}）</span></span>
                    <button className="btn-link text-rose-700" onClick={() => { onChange(null); setQ(""); setTimeout(() => inputRef.current?.focus(), 0); }}>選び直す</button>
                </div>
            </div>
        );
    }
    return (
        <Field label={`${label}を検索`} hint="物品名・コード・業者名の一部を入力して、候補から選びます（ほかの部署の物品は、画面の上の切り替えで「全部署」にすると出ます）">
            {(id) => (
                <div className="relative">
                    <Search size={16} className="pointer-events-none absolute top-2.5 left-2.5 text-slate-400" />
                    <input id={id} ref={inputRef} className="input pl-8" value={q} autoFocus={autoFocus} autoComplete="off"
                        placeholder="例：手袋" onChange={(e) => setQ(e.target.value)} />
                    {qDeb.trim() && (
                        <ul className="absolute z-20 mt-1 max-h-60 w-full overflow-y-auto rounded-md border bg-white shadow-lg" role="listbox" aria-label="検索結果">
                            {search.isLoading && <li className="px-3 py-2 text-sm text-slate-500">検索中...</li>}
                            {search.data?.items.length === 0 && <li className="px-3 py-2 text-sm text-slate-500">見つかりません</li>}
                            {search.data?.items.map((r) => (
                                <li key={r.item_id}>
                                    <button type="button" role="option" aria-selected={false} className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-100"
                                        onClick={() => { onChange(r); setQ(""); }}>
                                        {r.item_name} <span className="text-xs text-slate-500">（{r.category}・在庫 {fmtQty(r.quantity, r.unit)}）</span>
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}
        </Field>
    );
}

/** 「自分の部署＋共通」と「全部署」の切り替え（I-03）。ゲストには切り替えを出さない。 */
export function ScopeToggle({ className }: { className?: string }) {
    const { scope, canSwitch, hasDepartment, setScope } = useScope();
    const mine = hasDepartment ? "自分の部署＋共通" : "共通の物品";
    if (!canSwitch) return <span className={cn("text-xs text-slate-500", className)}>表示：{mine}</span>;
    return (
        <div role="group" aria-label="表示する範囲" className={cn("inline-flex overflow-hidden rounded-md border border-slate-300 text-sm", className)}>
            {([["dept", mine], ["all", "全部署"]] as const).map(([value, label]) => (
                <button key={value} type="button" aria-pressed={scope === value} onClick={() => setScope(value)}
                    className={cn("px-3 py-1.5", scope === value ? "bg-brand-600 text-white" : "bg-white text-slate-600 hover:bg-slate-50")}>
                    {label}
                </button>
            ))}
        </div>
    );
}

/** 部署IDから部署名を引く（物品の所属の表示用）。 */
export function useDepartmentNames(): Map<number, string> {
    const { data } = useQuery({ queryKey: ["departments"], queryFn: () => api<DepartmentOut[]>("/departments", { params: { include_inactive: true } }) });
    return new Map((data ?? []).map((d) => [d.id, d.name]));
}

/** 物品の所属：「検査科」「共通」「総務部・共通」。 */
export function ownerLabel(names: Map<number, string>, ownerId: number | null, isCommon: boolean | number): string {
    const parts = [ownerId != null ? names.get(ownerId) ?? "（不明な部署）" : null, isCommon ? "共通" : null].filter(Boolean);
    return parts.join("・") || "-";
}
