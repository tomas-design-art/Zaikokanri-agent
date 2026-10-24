"use client";

import { useSyncExternalStore } from "react";
import { useMe } from "@/lib/use-me";

/**
 * 部署の見える範囲（受け入れ条件 I-03）。
 * 一般・ゲストは「自分の部署＋共通」、管理者は「全部署」から始まる。一般と管理者は切り替えられ、
 * 切り替えは画面を移っても続く（ページを読み直すと既定に戻る）。ゲストは切り替えられない。
 */
export type Scope = "dept" | "all";

let chosen: Scope | null = null;
const listeners = new Set<() => void>();

/** ログアウトしたら既定に戻す（次の人に前の人の切り替えを持ち越さない）。 */
export function resetScope() {
    chosen = null;
    for (const fn of listeners) fn();
}

function subscribe(fn: () => void) {
    listeners.add(fn);
    return () => { listeners.delete(fn); };
}

export function useScope() {
    const { me, isAdmin, isGuest } = useMe();
    const picked = useSyncExternalStore(subscribe, () => chosen, () => null);
    const scope: Scope = isGuest ? "dept" : picked ?? (isAdmin ? "all" : "dept");
    return {
        scope,
        canSwitch: !!me && !isGuest,
        hasDepartment: me?.department_id != null,
        setScope(next: Scope) {
            chosen = next;
            for (const fn of listeners) fn();
        },
    };
}
