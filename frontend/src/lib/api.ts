"use client";

/**
 * Browser-side API client. Next.js の rewrites（`/api/*` → FastAPI）を通すので
 * Cookie は同じオリジンの httpOnly のまま使える。
 *
 * - 401 を受けたら `/auth/refresh` を1回だけ試し、成功したら元の操作をやり直す（A-01）
 * - リフレッシュも失敗したらログイン画面へ（ログイン後に元のページへ戻る）
 * - パスワード変更が必須のときはパスワード変更画面へ（A-03）
 * - エラーはサーバーの日本語メッセージ（detail）をそのまま message にする（B-06）
 */

type Params = Record<string, string | number | boolean | undefined | null>;
type FetchOpts = Omit<RequestInit, "body"> & { params?: Params; body?: BodyInit | null; json?: unknown };

export class ApiError extends Error {
    status: number;
    constructor(status: number, message: string) {
        super(message);
        this.status = status;
    }
}

const NO_REFRESH = new Set(["/auth/login", "/auth/refresh", "/auth/logout"]);
const PASSWORD_PAGE = "/account/password";

export function apiUrl(path: string, params?: Params): string {
    let url = path.startsWith("/api") ? path : `/api${path.startsWith("/") ? path : `/${path}`}`;
    if (params) {
        const usp = new URLSearchParams();
        for (const [k, v] of Object.entries(params)) {
            if (v !== undefined && v !== null && v !== "" && v !== false) usp.set(k, String(v));
        }
        const qs = usp.toString();
        if (qs) url += `?${qs}`;
    }
    return url;
}

let refreshing: Promise<boolean> | null = null;

function refreshOnce(): Promise<boolean> {
    if (!refreshing) {
        refreshing = fetch("/api/auth/refresh", { method: "POST", credentials: "include" })
            .then((r) => r.ok)
            .catch(() => false)
            .finally(() => {
                setTimeout(() => {
                    refreshing = null;
                }, 1000);
            });
    }
    return refreshing;
}

function goTo(path: string) {
    if (typeof window === "undefined" || window.location.pathname === path) return;
    const back = window.location.pathname + window.location.search;
    window.location.assign(path === "/login" ? `/login?next=${encodeURIComponent(back)}` : path);
}

async function errorMessage(res: Response): Promise<string> {
    try {
        const j = await res.json();
        if (typeof j.detail === "string") return j.detail;
        if (Array.isArray(j.detail)) return j.detail.map((d: { msg?: string }) => d.msg ?? "").join(" / ");
    } catch {
        /* JSON でない応答 */
    }
    if (res.status >= 500) return "サーバーでエラーが発生しました。時間をおいてもう一度お試しください。";
    return `通信に失敗しました（${res.status}）`;
}

async function send(path: string, opts: FetchOpts = {}, retried = false): Promise<Response> {
    const { params, json, headers, ...init } = opts;
    const isJson = json !== undefined;
    let res: Response;
    try {
        res = await fetch(apiUrl(path, params), {
            credentials: "include",
            ...init,
            headers: { ...(isJson ? { "Content-Type": "application/json" } : {}), ...(headers || {}) },
            body: isJson ? JSON.stringify(json) : init.body,
        });
    } catch {
        throw new ApiError(0, "サーバーに接続できません。ネットワークを確認してください");
    }
    if (res.status === 401 && !NO_REFRESH.has(path)) {
        if (!retried && (await refreshOnce())) return send(path, opts, true);
        goTo("/login");
        throw new ApiError(401, "ログインの有効期限が切れました。もう一度ログインしてください");
    }
    if (!res.ok) {
        const message = await errorMessage(res);
        if (res.status === 403 && message.includes("パスワードの変更が必要")) goTo(PASSWORD_PAGE);
        throw new ApiError(res.status, message);
    }
    return res;
}

export async function api<T = unknown>(path: string, opts: FetchOpts = {}): Promise<T> {
    const res = await send(path, opts);
    if (res.status === 204) return undefined as T;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return (await res.json()) as T;
    return (await res.text()) as unknown as T;
}

export const apiPost = <T,>(path: string, body: unknown = {}) => api<T>(path, { method: "POST", json: body });
export const apiPatch = <T,>(path: string, body: unknown) => api<T>(path, { method: "PATCH", json: body });
export const apiDelete = <T,>(path: string) => api<T>(path, { method: "DELETE" });

/** ファイルを取得して保存する（CSV / Excel / PDF）。401 のときもリフレッシュしてやり直す。 */
export async function downloadFile(path: string, filename: string, opts: FetchOpts = {}): Promise<void> {
    const res = await send(path, opts);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

export function errorText(e: unknown): string {
    return e instanceof Error ? e.message : "エラーが発生しました";
}
