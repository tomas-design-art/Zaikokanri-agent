import { expect, test, type Page } from "@playwright/test";
import { apiAs, authFile, createItem, expectToast, stockOf, uniq } from "./helpers";

/**
 * 部署ごとの機能（受け入れ条件 I 章）。
 * デモの人：一般 U001＝放射線科／一般 U002＝検査科／ゲスト G001＝放射線科。
 * デモの物品：X線フィルム・造影剤＝放射線科、生化学試薬セット・血液凝固検査試薬＝検査科、ほかは共通。
 */
const row = (page: Page, text: string) => page.getByRole("row").filter({ hasText: text });

async function pickItem(page: Page, name: string) {
    await page.getByLabel("物品を検索").fill(name);
    await page.getByRole("option", { name: new RegExp(name) }).click();
}

test.describe("見える範囲", () => {
    test("I-03 一般は自分の部署＋共通が既定で、全部署に切り替えられる", async ({ browser }) => {
        const page = await (await browser.newContext({ storageState: authFile("user2") })).newPage();
        await page.goto("/inventory");
        await expect(row(page, "生化学試薬セット")).toContainText("検査科");
        await expect(row(page, "ディスポ手袋（S）")).toContainText("共通");
        await expect(row(page, "X線フィルム")).toHaveCount(0);
        await page.getByRole("button", { name: "全部署" }).click();
        await expect(row(page, "X線フィルム")).toContainText("放射線科");
        // 切り替えは画面を移っても続く
        await page.getByRole("link", { name: "アラート" }).click();
        await expect(page.getByRole("button", { name: "全部署" })).toHaveAttribute("aria-pressed", "true");
    });

    test("I-03 I-09 ゲストは切り替えられず、業者の列も出ない", async ({ browser }) => {
        const page = await (await browser.newContext({ storageState: authFile("guest") })).newPage();
        await page.goto("/inventory");
        await expect(page.getByText("表示：自分の部署＋共通")).toBeVisible();
        await expect(page.getByRole("button", { name: "全部署" })).toHaveCount(0);
        await expect(row(page, "X線フィルム")).toContainText("放射線科");
        await expect(row(page, "生化学試薬セット")).toHaveCount(0);
        await expect(page.getByRole("columnheader", { name: "業者" })).toHaveCount(0);
        await expect(page.getByRole("link", { name: "AIアシスタント" })).toHaveCount(0);
    });

    test("I-01 物品の登録で所属部署を選ぶと、その部署の人の一覧だけに出る", async ({ browser }) => {
        const name = uniq("検査科の物品");
        const adm = await (await browser.newContext({ storageState: authFile("admin") })).newPage();
        await adm.goto("/items/new");
        await adm.getByLabel("物品名 *").fill(name);
        await adm.getByLabel("カテゴリ *").selectOption("消耗品");
        await adm.getByLabel(/全社共通/).uncheck();
        await expect(adm.getByText("所属部署を選ぶか、全社共通にしてください")).toBeVisible();
        await expect(adm.getByRole("button", { name: "登録" })).toBeDisabled();
        await adm.getByLabel("所属部署").selectOption({ label: "検査科" });
        await adm.getByRole("button", { name: "登録" }).click();
        await expectToast(adm, `「${name}」を登録しました`);
        await expect(row(adm, name)).toContainText("検査科");

        const kensa = await apiAs("user2");
        const housha = await apiAs("user");
        const names = async (api: typeof kensa) => (await (await api.get("/api/inventory", { params: { q: name } })).json()).items.map((r: { item_name: string }) => r.item_name);
        expect(await names(kensa)).toEqual([name]);
        expect(await names(housha)).toEqual([]);
    });
});

test.describe("同じ部署の承認と連絡", () => {
    test("I-07 ゲストの出庫申請は同じ部署の一般が承認する（ほかの部署には出ない）", async ({ browser }) => {
        const admin = await apiAs("admin");
        const guest = await apiAs("guest");
        const item = await createItem(admin, { name: uniq("部署承認"), qty: 10 });
        expect((await guest.post("/api/outbound", { data: { item_id: item.id, quantity: 2 } })).status()).toBe(201);

        const other = await (await browser.newContext({ storageState: authFile("user2") })).newPage();
        await other.goto("/approvals");
        await expect(row(other, item.item_name)).toHaveCount(0);

        const page = await (await browser.newContext({ storageState: authFile("user") })).newPage();
        await page.goto("/dashboard");
        await expect(page.getByRole("link", { name: /出庫承認/ })).toBeVisible();
        await page.goto("/approvals");
        await expect(row(page, item.item_name)).toContainText("放射線科");
        await row(page, item.item_name).getByRole("button", { name: "承認" }).click();
        await expectToast(page, "承認しました");
        expect(await stockOf(admin, item.id)).toBe(8);
    });

    test("I-08 ゲストの廃棄の連絡 → 同じ部署の一般が申請に上げる → 管理者が承認", async ({ browser }) => {
        const admin = await apiAs("admin");
        const item = await createItem(admin, { name: uniq("廃棄連絡"), qty: 10 });

        const guest = await (await browser.newContext({ storageState: authFile("guest") })).newPage();
        await guest.goto("/disposal");
        await expect(guest.getByRole("heading", { level: 1, name: "廃棄が要りそうな物の連絡" })).toBeVisible();
        await guest.getByRole("button", { name: "＋ 新しく連絡する" }).click();
        const form = guest.getByRole("form", { name: "廃棄の連絡" });
        await pickItem(guest, item.item_name);
        await form.getByLabel("数量（個）").fill("3");
        await form.getByLabel("理由 *").selectOption("破損");
        await form.getByRole("button", { name: "部署に連絡する" }).click();
        await expectToast(guest, "部署の正社員に連絡しました");
        await expect(row(guest, item.item_name)).toContainText("未対応");

        const user = await (await browser.newContext({ storageState: authFile("user") })).newPage();
        await user.goto("/disposal");
        const notices = user.getByRole("region", { name: "ゲストからの廃棄の連絡" });
        await notices.getByRole("row").filter({ hasText: item.item_name }).getByRole("button", { name: "申請に上げる" }).click();
        const dialog = user.getByRole("dialog", { name: "廃棄の申請に上げる" });
        await dialog.getByLabel("数量（個）").fill("2");
        await dialog.getByRole("button", { name: "申請する" }).click();
        await expectToast(user, "廃棄の申請に上げました");
        await expect(row(user, item.item_name)).toContainText("承認待ち");
        await expect(row(user, item.item_name)).toContainText("放射線科");
        expect(await stockOf(admin, item.id)).toBe(10);

        const adm = await (await browser.newContext({ storageState: authFile("admin") })).newPage();
        await adm.goto("/disposal");
        await adm.getByRole("table").last().getByRole("row").filter({ hasText: item.item_name }).getByRole("button", { name: "承認" }).click();
        await expectToast(adm, "承認しました");
        expect(await stockOf(admin, item.id)).toBe(8);

        await guest.reload();
        await expect(row(guest, item.item_name)).toContainText("申請済");
    });
});

test.describe("申請のまとめ", () => {
    test("I-11 I-12 同じ物品の申請を部署ごとに見て、まとめて承認すると発注書は1行", async ({ browser }) => {
        const admin = await apiAs("admin");
        const item = await createItem(admin, { name: uniq("まとめ発注"), qty: 1, price: 100 });
        for (const role of ["user", "user2"] as const) {
            const api = await apiAs(role);
            expect((await api.post("/api/purchase-requests", { data: { item_id: item.id, requested_qty: 10 } })).status()).toBe(201);
        }

        const adm = await (await browser.newContext({ storageState: authFile("admin") })).newPage();
        await adm.goto("/purchase-requests");
        await adm.getByRole("tab", { name: "同じ物品のまとめ" }).click();
        const group = adm.getByRole("region", { name: `${item.item_name}のまとめ` });
        await expect(group).toContainText("合計 20");
        await expect(group).toContainText("放射線科 10");
        await expect(group).toContainText("検査科 10");
        await group.getByLabel(`${item.item_name}の申請をすべて選ぶ`).check();
        await adm.getByRole("button", { name: "承認して発注書を作成" }).click();
        await expectToast(adm, "2件を承認しました");
        const preview = adm.getByRole("dialog", { name: /発注書プレビュー/ });
        const lines = preview.getByRole("row").filter({ hasText: item.item_name });
        await expect(lines).toHaveCount(1);
        await expect(lines).toContainText("20");
        await expect(preview).toContainText("¥2,000");
    });
});
