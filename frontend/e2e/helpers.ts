import { expect, request, type APIRequestContext, type Page } from "@playwright/test";

/** デモデータ（backend/scripts/seed_demo.py）の利用者。パスワードは 8 文字以上の規則に合わせてある。 */
export const USERS = {
    admin: { username: "admin", password: "admin123", name: "管理者A" },
    user: { username: "U001", password: "pass1234", name: "放射線太郎" },
    user2: { username: "U002", password: "pass1234", name: "検査花子" },
    guest: { username: "G001", password: "pass1234", name: "ゲスト放射線" },
} as const;
export type RoleKey = keyof typeof USERS;

export const authFile = (role: RoleKey) => `e2e/.auth/${role}.json`;

export const BASE_URL = "http://localhost:3100";

/** 他のテストとぶつからない名前 */
export function uniq(prefix: string): string {
    return `${prefix}-${Date.now().toString(36)}${Math.floor(Math.random() * 1000)}`;
}

/** 画面を通さずに準備・確認するための API（Next の /api 経由＝画面と同じ経路）。 */
export async function apiAs(role: RoleKey): Promise<APIRequestContext> {
    return request.newContext({ baseURL: BASE_URL, storageState: authFile(role) });
}

export async function login(page: Page, role: RoleKey | { username: string; password: string }) {
    const u = typeof role === "string" ? USERS[role] : role;
    await page.goto("/login");
    await page.getByLabel("ユーザー名").fill(u.username);
    await page.getByLabel("パスワード").fill(u.password);
    await page.getByRole("button", { name: "ログイン" }).click();
}

export interface CreatedItem { id: number; item_name: string }

export async function createItem(
    api: APIRequestContext,
    opts: { name?: string; qty?: number; reorder?: number; category?: string; unit?: string; location?: string; vendor?: string; price?: number } = {},
): Promise<CreatedItem> {
    const res = await api.post("/api/items", {
        data: {
            item_name: opts.name ?? uniq("E2E物品"),
            category: opts.category ?? "消耗品",
            unit: opts.unit ?? "個",
            location_text: opts.location ?? "E2E棚",
            vendor_name: opts.vendor ?? "医療材料C社",
            unit_price: opts.price ?? 100,
            reorder_point: opts.reorder ?? 5,
            initial_quantity: opts.qty ?? 20,
        },
    });
    expect(res.status(), await res.text()).toBe(201);
    return res.json();
}

export async function stockOf(api: APIRequestContext, itemId: number): Promise<number> {
    const res = await api.get(`/api/items/${itemId}`);
    expect(res.ok()).toBeTruthy();
    return (await res.json()).quantity;
}

/** 実施中の棚卸しが残っていたら中止する（前のテストが途中で落ちたとき用） */
export async function cancelOpenStocktake(admin: APIRequestContext) {
    const sessions: { id: number; status: string }[] = await (await admin.get("/api/stocktake/sessions")).json();
    for (const s of sessions.filter((x) => x.status === "OPEN")) await admin.post(`/api/stocktake/sessions/${s.id}/cancel`);
}

/** 画面右上のトースト（通知）に文言が出るのを待つ */
export async function expectToast(page: Page, text: string | RegExp) {
    await expect(page.locator("[data-sonner-toast]").filter({ hasText: text }).first()).toBeVisible();
}
