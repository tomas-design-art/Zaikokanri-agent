"use client";

import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import {
    LayoutDashboard, Package, ArrowUpFromLine, ArrowDownToLine,
    History as HistoryIcon, AlertTriangle, ShoppingCart, Trash2,
    ClipboardList, BarChart3, Building2, Users, Sparkles, Wrench, LogOut, CheckSquare,
    type LucideIcon,
} from "lucide-react";
import { api, apiJson } from "@/lib/api";
import type { MeResponse } from "@/lib/types";
import { useAuth } from "@/lib/auth-store";
import { cn } from "@/lib/cn";

interface NavItem { href: string; label: string; icon: LucideIcon; role?: "USER" | "ADMIN"; }

const NAV: NavItem[] = [
    { href: "/dashboard", label: "ダッシュボード", icon: LayoutDashboard },
    { href: "/inventory", label: "在庫一覧", icon: Package },
    { href: "/outbound", label: "出庫", icon: ArrowUpFromLine },
    { href: "/inbound", label: "入庫", icon: ArrowDownToLine, role: "USER" },
    { href: "/history", label: "履歴", icon: HistoryIcon },
    { href: "/alerts", label: "アラート", icon: AlertTriangle },
    { href: "/purchase-requests", label: "発注申請", icon: ShoppingCart, role: "USER" },
    { href: "/approvals", label: "出庫承認", icon: CheckSquare, role: "ADMIN" },
    { href: "/disposal", label: "廃棄申請", icon: Trash2 },
    { href: "/stocktake", label: "棚卸", icon: ClipboardList, role: "USER" },
    { href: "/stats", label: "統計", icon: BarChart3 },
    { href: "/items", label: "物品マスター", icon: Package, role: "ADMIN" },
    { href: "/masters", label: "業者/部署", icon: Building2, role: "ADMIN" },
    { href: "/users", label: "ユーザー管理", icon: Users, role: "ADMIN" },
    { href: "/ai", label: "AIアシスタント", icon: Sparkles },
    { href: "/maintenance", label: "メンテナンス", icon: Wrench, role: "ADMIN" },
];

export default function AppShell({ children }: { children: React.ReactNode }) {
    const router = useRouter();
    const pathname = usePathname();
    const { user, setUser, setLoading, loading, hasRole } = useAuth();

    const { data, isLoading, error } = useQuery({
        queryKey: ["me"],
        queryFn: () => api<MeResponse>("/auth/me"),
        retry: false,
    });

    useEffect(() => {
        setLoading(isLoading);
        if (data) setUser(data);
        if (error) {
            setUser(null);
            router.replace("/login");
        }
    }, [data, error, isLoading, setUser, setLoading, router]);

    async function logout() {
        try { await apiJson("/auth/logout", {}); } catch { /* ignore */ }
        setUser(null);
        router.replace("/login");
    }

    if (loading || !user) {
        return <div className="min-h-screen flex items-center justify-center text-slate-500">読み込み中...</div>;
    }

    return (
        <div className="min-h-screen flex">
            <aside className="w-60 shrink-0 bg-slate-900 text-slate-100 flex flex-col">
                <div className="px-4 py-4 border-b border-slate-800">
                    <div className="font-bold">在庫管理</div>
                    <div className="text-xs text-slate-400 mt-0.5">
                        {user.display_name} <span className="badge bg-slate-700 text-slate-200 ml-1">{user.role}</span>
                    </div>
                    {user.department && <div className="text-xs text-slate-500 mt-0.5">{user.department}</div>}
                </div>
                <nav className="flex-1 overflow-y-auto py-2">
                    {NAV.filter((n) => !n.role || hasRole(n.role)).map((n) => {
                        const Icon = n.icon;
                        const active = pathname === n.href || pathname.startsWith(n.href + "/");
                        return (
                            <Link
                                key={n.href}
                                href={n.href}
                                className={cn(
                                    "flex items-center gap-2 px-4 py-2 text-sm hover:bg-slate-800 transition",
                                    active && "bg-slate-800 border-l-2 border-brand-500"
                                )}
                            >
                                <Icon size={16} className="text-slate-400" />
                                <span>{n.label}</span>
                            </Link>
                        );
                    })}
                </nav>
                <button onClick={logout} className="flex items-center gap-2 px-4 py-3 text-sm hover:bg-slate-800 border-t border-slate-800">
                    <LogOut size={16} /> ログアウト
                </button>
            </aside>
            <main className="flex-1 overflow-x-hidden">
                <div className="p-6 max-w-screen-2xl mx-auto">{children}</div>
            </main>
        </div>
    );
}
