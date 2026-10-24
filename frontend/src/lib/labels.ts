/** 画面に出すラベル（コードのまま出さない：C-07 / E-04）。 */

export type LabelMap = Record<string, { label: string; cls: string }>;

const green = "bg-emerald-100 text-emerald-700";
const blue = "bg-blue-100 text-blue-700";
const red = "bg-rose-100 text-rose-700";
const amber = "bg-amber-100 text-amber-800";
const gray = "bg-slate-100 text-slate-600";
const violet = "bg-violet-100 text-violet-700";

export const CHANGE_TYPE: LabelMap = {
    IN: { label: "入庫", cls: green },
    OUT: { label: "出庫", cls: blue },
    DISPOSE: { label: "廃棄", cls: red },
    ADJUST: { label: "調整", cls: amber },
    STOCKTAKE: { label: "棚卸し", cls: violet },
    ORDER: { label: "発注", cls: gray },
};

export const HISTORY_STATUS: LabelMap = {
    CONFIRMED: { label: "確定", cls: gray },
    REJECTED: { label: "取消済", cls: red },
    PENDING: { label: "保留", cls: amber },
};

export const REQUEST_STATUS: LabelMap = {
    PENDING: { label: "承認待ち", cls: amber },
    ON_HOLD: { label: "保留", cls: gray },
    APPROVED: { label: "承認済", cls: green },
    REJECTED: { label: "却下", cls: red },
    ORDERED: { label: "発注済", cls: blue },
    RECEIVED: { label: "受領済", cls: violet },
    CANCELLED: { label: "取り下げ", cls: gray },
};

export const PRIORITY: LabelMap = {
    LOW: { label: "低", cls: gray },
    NORMAL: { label: "通常", cls: gray },
    HIGH: { label: "高", cls: amber },
    URGENT: { label: "緊急", cls: red },
};

export const SESSION_STATUS: LabelMap = {
    OPEN: { label: "実施中", cls: blue },
    CLOSED: { label: "完了", cls: green },
    CANCELLED: { label: "中止", cls: gray },
};

export const RECORD_STATUS: LabelMap = {
    PENDING: { label: "未カウント", cls: gray },
    COUNTED: { label: "カウント済", cls: blue },
    APPLIED: { label: "反映済", cls: green },
};

export const ROLE: LabelMap = {
    ADMIN: { label: "管理者", cls: violet },
    USER: { label: "一般", cls: blue },
    GUEST: { label: "ゲスト", cls: gray },
};

export function labelOf(map: LabelMap, code: string | null | undefined): string {
    if (!code) return "";
    return map[code]?.label ?? code;
}
