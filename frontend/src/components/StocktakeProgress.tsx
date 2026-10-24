import type { StocktakeSummary } from "@/lib/types";

/** 棚卸しの進捗（D-06） */
export function StocktakeProgress({ s }: { s: StocktakeSummary }) {
    const pct = s.total ? Math.round((s.counted / s.total) * 100) : 0;
    return (
        <div className="min-w-32">
            <div className="h-2 overflow-hidden rounded bg-slate-200" role="progressbar" aria-label="カウントの進捗" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
                <div className="h-full bg-brand-600" style={{ width: `${pct}%` }} />
            </div>
            <div className="mt-1 text-xs text-slate-500">{s.counted} / {s.total}（{pct}%）{s.diff > 0 && <span className="text-rose-600">・差異 {s.diff}</span>}</div>
        </div>
    );
}
