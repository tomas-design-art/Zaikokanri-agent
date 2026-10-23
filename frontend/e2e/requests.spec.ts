import { expect, test, type Page } from "@playwright/test";
import { apiAs, authFile, createItem, expectToast, stockOf, uniq } from "./helpers";

const row = (page: Page, text: string) => page.getByRole("row").filter({ hasText: text });

async function pickItem(page: Page, name: string) {
    await page.getByLabel("物品を検索").fill(name);
    await page.getByRole("option", { name: new RegExp(name) }).click();
}

test.describe("発注申請", () => {
    test("C-06 C-07 申請（優先度・希望納期）→ 承認 → 発注書（メール本文）→ 発注済", async ({ browser }) => {
        const admin = await apiAs("admin");
        const item = await createItem(admin, { name: uniq("発注テスト"), qty: 1, price: 150 });

        const user = await (await browser.newContext({ storageState: authFile("user") })).newPage();
        await user.goto("/purchase-requests");
        await user.getByRole("button", { name: "＋ 新規申請" }).click();
        const form = user.getByRole("form", { name: "発注の申請" });
        await pickItem(user, item.item_name);
        await form.getByLabel("数量（個）").fill("7");
        await form.getByLabel("優先度").selectOption({ label: "高" });
        await form.getByLabel("希望納期").fill("2026-12-01");
        await form.getByRole("button", { name: "申請する" }).click();
        await expectToast(user, "発注を申請しました");
        await expect(row(user, item.item_name)).toContainText("承認待ち");
        await expect(row(user, item.item_name)).toContainText("2026-12-01");

        const adm = await (await browser.newContext({ storageState: authFile("admin") })).newPage();
        await adm.goto("/purchase-requests");
        await row(adm, item.item_name).getByRole("button", { name: "承認" }).click();
        await expect(row(adm, item.item_name)).toContainText("承認済");
        await adm.getByLabel(`${item.item_name}を発注書に含める`).check();
        await adm.getByRole("button", { name: "発注書を作成" }).click();
        const preview = adm.getByRole("dialog", { name: /発注書プレビュー/ });
        await expect(preview).toContainText("¥1,050");
        await preview.getByRole("button", { name: "メール本文" }).click();
        await expect(adm.getByRole("textbox", { name: "メール本文" })).toHaveValue(/物品発注のお願い/);
        await adm.getByRole("dialog", { name: "メール本文" }).getByRole("button", { name: "閉じる" }).click();
        const pdf = adm.waitForEvent("download");
        await preview.getByRole("button", { name: "PDF" }).click();
        expect((await pdf).suggestedFilename()).toMatch(/\.pdf$/);
        await preview.getByRole("button", { name: "発注済にする（1件）" }).click();
        await expectToast(adm, "1件を「発注済」にしました");
        await expect(row(adm, item.item_name)).toContainText("発注済");
    });

    test("C-02 C-04 却下にはコメントが要り、申請者は保留中なら取り下げられる", async ({ browser }) => {
        const admin = await apiAs("admin");
        const user = await apiAs("user");
        const a = await createItem(admin, { name: uniq("却下テスト") });
        const b = await createItem(admin, { name: uniq("取下テスト") });
        await user.post("/api/purchase-requests", { data: { item_id: a.id, requested_qty: 3 } });
        await user.post("/api/purchase-requests", { data: { item_id: b.id, requested_qty: 3 } });

        const adm = await (await browser.newContext({ storageState: authFile("admin") })).newPage();
        await adm.goto("/purchase-requests");
        await row(adm, a.item_name).getByRole("button", { name: "却下" }).click();
        const dialog = adm.getByRole("dialog", { name: "発注申請を却下" });
        await expect(dialog.getByRole("button", { name: "却下する" })).toBeDisabled();
        await dialog.getByLabel(/却下の理由/).fill("予算超過のため来月に");
        await dialog.getByRole("button", { name: "却下する" }).click();
        await expect(row(adm, a.item_name)).toContainText("却下");
        await expect(row(adm, a.item_name)).toContainText("予算超過のため来月に");

        const page = await (await browser.newContext({ storageState: authFile("user") })).newPage();
        await page.goto("/purchase-requests");
        await expect(row(page, a.item_name).getByRole("button", { name: "取り下げ" })).toHaveCount(0);
        await row(page, b.item_name).getByRole("button", { name: "取り下げ" }).click();
        await page.getByRole("dialog", { name: "申請を取り下げる" }).getByRole("button", { name: "取り下げる" }).click();
        await expectToast(page, "取り下げました");
        await expect(row(page, b.item_name)).toHaveCount(0);
    });
});

test.describe("アラート", () => {
    test.use({ storageState: authFile("user") });

    test("C-08 在庫不足の行を選んで、推奨数量入りでまとめて発注申請", async ({ page }) => {
        const admin = await apiAs("admin");
        const user = await apiAs("user");
        const item = await createItem(admin, { name: uniq("不足テスト"), qty: 2, reorder: 5 });
        await page.goto("/alerts");
        const low = page.getByRole("region", { name: "在庫不足" });
        await low.getByLabel(`${item.item_name}を発注する`).check();
        await expect(low.getByLabel(`${item.item_name}の発注数`)).toHaveValue("8");
        await page.getByRole("button", { name: "選んだ1件の発注を申請" }).click();
        await expectToast(page, "1件の発注を申請しました");
        const prs = await (await user.get("/api/purchase-requests", { params: { mine: true, status: "PENDING" } })).json();
        expect(prs.items.find((p: { item_id: number }) => p.item_id === item.id)?.requested_qty).toBe(8);
    });
});

test.describe("廃棄申請", () => {
    test("C-03 申請（理由を選ぶ）→ 取り下げ／管理者の承認で在庫が減る", async ({ browser }) => {
        const admin = await apiAs("admin");
        const item = await createItem(admin, { name: uniq("廃棄テスト"), qty: 10 });

        const page = await (await browser.newContext({ storageState: authFile("user") })).newPage();
        await page.goto("/disposal");
        await page.getByRole("button", { name: "＋ 新規申請" }).click();
        const form = page.getByRole("form", { name: "廃棄の申請" });
        await pickItem(page, item.item_name);
        await form.getByLabel("数量（個）").fill("11");
        await expect(form.getByRole("button", { name: "申請する" })).toBeDisabled();
        await form.getByLabel("数量（個）").fill("2");
        await form.getByLabel("理由 *").selectOption("破損");
        await form.getByLabel("詳しい理由（任意）").fill("落下");
        await form.getByRole("button", { name: "申請する" }).click();
        await expectToast(page, "廃棄を申請しました");
        await expect(row(page, item.item_name)).toContainText("承認待ち");
        await expect(row(page, item.item_name)).toContainText("破損：落下");

        const adm = await (await browser.newContext({ storageState: authFile("admin") })).newPage();
        await adm.goto("/disposal");
        await row(adm, item.item_name).getByRole("button", { name: "承認" }).click();
        await expectToast(adm, "承認しました");
        expect(await stockOf(admin, item.id)).toBe(8);

        // 2件目は申請者が取り下げる
        const user = await apiAs("user");
        await user.post("/api/disposal-requests", { data: { item_id: item.id, quantity: 1, reason: "不要" } });
        await page.reload();
        await page.getByRole("row").filter({ hasText: "不要" }).filter({ hasText: item.item_name }).getByRole("button", { name: "取り下げ" }).click();
        await expectToast(page, "取り下げました");
        await expect(page.getByRole("row").filter({ hasText: "不要" }).filter({ hasText: item.item_name })).toContainText("取り下げ");
    });
});
