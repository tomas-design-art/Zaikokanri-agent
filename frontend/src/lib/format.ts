/** "2026-10-23T14:05:09" → "2026-10-23 14:05" */
export function fmtDateTime(iso: string | null | undefined): string {
    if (!iso) return "";
    return iso.replace("T", " ").slice(0, 16);
}

export function fmtYen(n: number | null | undefined): string {
    if (n === null || n === undefined) return "-";
    return `¥${n.toLocaleString("ja-JP")}`;
}

export function fmtQty(n: number, unit?: string | null): string {
    return `${n.toLocaleString("ja-JP")}${unit ? ` ${unit}` : ""}`;
}

export function fmtSigned(n: number | null | undefined): string {
    if (n === null || n === undefined) return "-";
    return n > 0 ? `+${n}` : String(n);
}

/** 日本時間の今日（YYYY-MM-DD） */
export function todayJst(): string {
    return new Date(Date.now() + 9 * 3600_000).toISOString().slice(0, 10);
}
