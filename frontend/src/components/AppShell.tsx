"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
    ArrowDownToLine, ArrowUpFromLine, Building2, ChartColumn, ClipboardList, History as HistoryIcon, KeyRound,
    LayoutDashboard, LogOut, Menu, Package, PackageCheck, ShoppingCart, Sparkles, SquareCheck, Trash2,
    TriangleAlert, Users, Wrench, X, type LucideIcon,
} from "lucide-react";
import { api, apiPost } from "@/lib/api";
import { cn } from "@/lib/cn";
import { labelOf, ROLE } from "@/lib/labels";
import type { Role, Todo } from "@/lib/types";
import { hasRole, useMeQuery } from "@/lib/use-me";

interface NavItem { href: string; label: string; icon: LucideIcon; role?: Role; todo?: keyof Todo }
interface NavGroup { title: string; items: NavItem[] }

const NAV: NavGroup[] = [
    {
        title: "日々の操作",
        items: [
            { href: "/dashboard", label: "ダッシュボード", icon: LayoutDashboard },
            { href: "/inventory", label: "在庫一覧", icon: Package },
            { href: "/outbound", label: "出庫", icon: ArrowUpFromLine },
            { href: "/inbound", label: "入庫", icon: ArrowDownToLine, role: "USER", todo: "receivable" },
            { href: "/history", label: "履歴", icon: HistoryIcon },
            { href: "/alerts", label: "アラート", icon: TriangleAlert },
        ],
    },
    {
        title: "申請・承認",
        items: [
            { href: "/purchase-requests", label: "発注申請", icon: ShoppingCart, role: "USER", todo: "purchase" },
            { href: "/approvals", label: "出庫承認", icon: SquareCheck, role: "ADMIN", todo: "guest_outbound" },
            { href: "/disposal", label: "廃棄申請", icon: Trash2, todo: "disposal" },
        ],
    },
    {
        title: "管理",
        items: [
            { href: "/stocktake", label: "棚卸し", icon: ClipboardList, role: "USER" },
            { href: "/stats", label: "統計", icon: ChartColumn },
            { href: "/items", label: "物品マスター", icon: PackageCheck, role: "ADMIN" },
            { href: "/masters", label: "業者・カテゴリ・部署", icon: Building2, role: "ADMIN" },
            { href: "/users", label: "ユーザー管理", icon: Users, role: "ADMIN" },
            { href: "/maintenance", label: "メンテナンス", icon: Wrench, role: "ADMIN" },
        ],
    },
    {
        title: "その他",
        items: [
            { href: "/ai", label: "AIアシスタント", icon: Sparkles },
            { href: "/account/password", label: "パスワード変更", icon: KeyRound },
        ],
    },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
    const router = useRouter();
    const pathname = usePathname();
    const qc = useQueryClient();
    const [open, setOpen] = useState(false);
    const { data: user, isLoading, error, refetch } = useMeQuery();
    const canTodo = hasRole(user, "USER");
    const todo = useQuery({
        queryKey: ["todo"],
        queryFn: () => api<Todo>("/stats/todo"),
        enabled: canTodo && !user?.must_change_password,
        refetchInterval: 60_000,
    });

    useEffect(() => {
        if (user?.must_change_password && pathname !== "/account/password") router.replace("/account/password");
    }, [user, pathname, router]);

    async function logout() {
        try { await apiPost("/auth/logout"); } catch { /* ignore */ }
        qc.clear();
        router.replace("/login");
    }

    if (isLoading) return <div className="flex min-h-screen items-center justify-center text-slate-500">読み込み中...</div>;
    if (error || !user) {
        return (
            <div className="flex min-h-screen flex-col items-center justify-center gap-3 text-slate-600">
                <p>{error instanceof Error ? error.message : "ログイン情報を確認できませんでした"}</p>
                <div className="flex gap-2">
                    <button className="btn-secondary" onClick={() => refetch()}>再読み込み</button>
                    <Link className="btn-primary" href="/login">ログイン画面へ</Link>
                </div>
            </div>
        );
    }

    // 権限のない画面を URL で直接開いたときは中身を出さない（メニューに出さないだけでは足りない）
    const required = NAV.flatMap((g) => g.items).find((n) => pathname === n.href || pathname.startsWith(n.href + "/"))?.role;
    const forbidden = !!required && !hasRole(user, required);

    const nav = (
        <nav className="flex-1 overflow-y-auto py-2" aria-label="メインメニュー">
            {NAV.map((g) => {
                const items = g.items.filter((n) => !n.role || hasRole(user, n.role));
                if (items.length === 0) return null;
                return (
                    <div key={g.title} className="mb-2">
                        <div className="px-4 pt-2 pb-1 text-xs text-slate-500">{g.title}</div>
                        {items.map((n) => {
                            const Icon = n.icon;
                            const active = pathname === n.href || pathname.startsWith(n.href + "/");
                            const count = n.todo && user.role === "ADMIN" ? todo.data?.[n.todo] ?? 0 : 0;
                            return (
                                <Link key={n.href} href={n.href} onClick={() => setOpen(false)}
                                    aria-current={active ? "page" : undefined}
                                    className={cn("flex items-center gap-2 border-l-2 border-transparent px-4 py-2 text-sm transition hover:bg-slate-800",
                                        active && "border-brand-500 bg-slate-800")}>
                                    <Icon size={16} className="text-slate-400" />
                                    <span className="flex-1">{n.label}</span>
                                    {count > 0 && <span className="badge bg-amber-400 text-slate-900" aria-label={`処理待ち ${count}件`}>{count}</span>}
                                </Link>
                            );
                        })}
                    </div>
                );
            })}
        </nav>
    );

    return (
        <div className="min-h-screen md:flex">
            {/* スマホ・タブレット：上部バー＋引き出しメニュー（D-11） */}
            <header className="sticky top-0 z-30 flex items-center justify-between bg-slate-900 px-3 py-2 text-slate-100 md:hidden">
                <button className="rounded p-2 hover:bg-slate-800" onClick={() => setOpen(true)} aria-label="メニューを開く"><Menu size={20} /></button>
                <span className="font-bold">在庫管理</span>
                <span className="w-9 truncate text-right text-xs text-slate-400">{user.display_name}</span>
            </header>
            {open && <div className="fixed inset-0 z-40 bg-black/40 md:hidden" onClick={() => setOpen(false)} />}
            <aside className={cn(
                "fixed inset-y-0 left-0 z-50 flex w-64 shrink-0 flex-col bg-slate-900 text-slate-100 transition-transform md:sticky md:top-0 md:h-screen md:translate-x-0",
                open ? "translate-x-0" : "-translate-x-full",
            )}>
                <div className="flex items-start justify-between border-b border-slate-800 px-4 py-4">
                    <div>
                        <div className="font-bold">在庫管理</div>
                        <div className="mt-0.5 text-xs text-slate-300" data-testid="current-user">
                            {user.display_name}
                            <span className="badge ml-1 bg-slate-700 text-slate-200">{labelOf(ROLE, user.role)}</span>
                        </div>
                        {user.department && <div className="mt-0.5 text-xs text-slate-500">{user.department}</div>}
                    </div>
                    <button className="rounded p-1 hover:bg-slate-800 md:hidden" onClick={() => setOpen(false)} aria-label="メニューを閉じる"><X size={18} /></button>
                </div>
                {nav}
                <button onClick={logout} className="flex items-center gap-2 border-t border-slate-800 px-4 py-3 text-sm hover:bg-slate-800">
                    <LogOut size={16} /> ログアウト
                </button>
            </aside>
            <main className="min-w-0 flex-1">
                <div className="mx-auto max-w-screen-2xl p-4 md:p-6">
                    {forbidden ? (
                        <div role="alert" className="card mx-auto mt-10 max-w-md space-y-2 p-6 text-center">
                            <h1 className="text-lg font-bold">この画面を使う権限がありません</h1>
                            <p className="text-sm text-slate-600">必要な場合は管理者に依頼してください。</p>
                            <Link href="/dashboard" className="btn-secondary">ダッシュボードへ</Link>
                        </div>
                    ) : children}
                </div>
            </main>
        </div>
    );
}
