"use client";

/**
 * Browser-side API client. Uses Next.js rewrites (`/api/*` → FastAPI)
 * so cookies are same-origin and httpOnly.
 */

type FetchOpts = RequestInit & { params?: Record<string, string | number | boolean | undefined | null> };

export class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, detail: string) {
        super(`API ${status}: ${detail}`);
        this.status = status;
        this.detail = detail;
    }
}

export async function api<T = unknown>(path: string, opts: FetchOpts = {}): Promise<T> {
    const { params, ...init } = opts;
    let url = path.startsWith("/api") ? path : `/api${path.startsWith("/") ? path : `/${path}`}`;
    if (params) {
        const usp = new URLSearchParams();
        for (const [k, v] of Object.entries(params)) {
            if (v !== undefined && v !== null && v !== "") usp.set(k, String(v));
        }
        const qs = usp.toString();
        if (qs) url += `?${qs}`;
    }
    const res = await fetch(url, {
        credentials: "include",
        headers: {
            "Content-Type": "application/json",
            ...(init.headers || {}),
        },
        ...init,
    });
    if (!res.ok) {
        let detail = res.statusText;
        try {
            const j = await res.json();
            detail = j.detail || JSON.stringify(j);
        } catch { /* ignore */ }
        throw new ApiError(res.status, detail);
    }
    if (res.status === 204) return undefined as T;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) return res.json() as Promise<T>;
    return res.text() as unknown as Promise<T>;
}

export const apiJson = <T,>(path: string, body: unknown, init: Omit<FetchOpts, "body"> = {}) =>
    api<T>(path, { method: "POST", body: JSON.stringify(body), ...init });

export const apiPatch = <T,>(path: string, body: unknown) =>
    api<T>(path, { method: "PATCH", body: JSON.stringify(body) });

export const apiDelete = <T,>(path: string) => api<T>(path, { method: "DELETE" });

/** POSTでバイナリ(Blob)を取得。PDF/Excelダウンロード用。 */
export async function apiBlob(path: string, body: unknown): Promise<Blob> {
    const url = path.startsWith("/api") ? path : `/api${path.startsWith("/") ? path : `/${path}`}`;
    const res = await fetch(url, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        let detail = res.statusText;
        try { detail = (await res.json()).detail || detail; } catch { /* ignore */ }
        throw new ApiError(res.status, detail);
    }
    return res.blob();
}

export function downloadBlob(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click();
    document.body.removeChild(a); URL.revokeObjectURL(url);
}
