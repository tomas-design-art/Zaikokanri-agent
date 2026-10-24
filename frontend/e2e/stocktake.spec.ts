import { expect, test, type Page } from "@playwright/test";
import { apiAs, authFile, cancelOpenStocktake, createItem, expectToast, stockOf, uniq, type CreatedItem } from "./helpers";

// 実施中の棚卸しは1つだけなので、このファイルは順番に流す
test.describe.configure({ mode: "serial" });

const row = (page: Page, text: string) => page.getByRole("row").filter({ hasText: text });
let a: CreatedItem;
let b: CreatedItem;
let sessionUrl = "";

test.beforeAll(async () => {
    const admin = await apiAs("admin");
    await cancelOpenStocktake(admin);
    a = await createItem(admin, { name: uniq("棚卸A"), qty: 10, location: "AAA-E2E棚1", category: "消耗品" });
    b = await createItem(admin, { name: uniq("棚卸B"), qty: 5, location: "AAA-E2E棚2", category: "消耗品" });
});

test("D-07 管理者が対象カテゴリを決めて棚卸しを始める（実施中は1つだけ）", async ({ browser }) => {
    const page = await (await browser.newContext({ storageState: authFile("admin") })).newPage();
    await page.goto("/stocktake");
    const form = page.getByRole("form", { name: "棚卸しを始める" });
    await form.getByLabel("棚卸しの名前").fill("E2E 定期棚卸し");
    await form.getByLabel("対象カテゴリ").selectOption("消耗品");
    await form.getByRole("button", { name: "棚卸しを始める" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "E2E 定期棚卸し" })).toBeVisible();
    sessionUrl = new URL(page.url()).pathname;
    expect(sessionUrl).toMatch(/^\/stocktake\/\d+$/);
    await page.goto("/stocktake");
    await expect(page.getByRole("form", { name: "棚卸しを始める" })).toHaveCount(0);
    await expect(row(page, "E2E 定期棚卸し")).toContainText("実施中");
});

test("D-02 D-04 D-05 D-06 担当者が数える：保管場所順・保存状態・Enterで次へ・数えた後の出庫", async ({ browser }) => {
    const user = await apiAs("user");
    const page = await (await browser.newContext({ storageState: authFile("user") })).newPage();
    await page.goto("/stocktake");
    await row(page, "E2E 定期棚卸し").getByRole("link", { name: "数える" }).click();
    await expect(page).toHaveURL(sessionUrl);
    // 保管場所順（AAA-E2E棚1 → AAA-E2E棚2）で先頭に並ぶ
    const firstRows = page.getByRole("row").nth(1);
    await expect(firstRows).toContainText(a.item_name);

    const inputA = page.getByLabel(`${a.item_name}の実数`);
    await inputA.fill("8");
    await inputA.press("Enter");
    await expect(row(page, a.item_name)).toContainText("保存済");
    await expect(row(page, a.item_name)).toContainText("-2");
    // Enter で次の行（B）に移っている
    await expect(page.getByLabel(`${b.item_name}の実数`)).toBeFocused();
    await page.getByLabel(`${b.item_name}の実数`).fill("abc");
    await expect(row(page, b.item_name)).toContainText("数字のみ");
    await page.getByLabel(`${b.item_name}の実数`).fill("5");
    await page.getByLabel(`${b.item_name}の実数`).press("Tab");
    await expect(row(page, b.item_name)).toContainText("保存済");

    // 数えた後に1個出庫（帳簿 10→9）。確定時に失われないこと（D-02）
    await user.post("/api/outbound", { data: { item_id: a.id, quantity: 1 } });

    await page.getByRole("radio", { name: "差異ありのみ" }).click();
    await expect(row(page, a.item_name)).toBeVisible();
    await expect(row(page, b.item_name)).toHaveCount(0);
    await page.getByRole("radio", { name: "すべて" }).click();
    await page.getByLabel("物品名・コードで探す").fill(b.item_name);
    await expect(page.getByRole("row").filter({ hasText: "棚卸" })).toHaveCount(1);
    await expect(page.getByRole("progressbar", { name: "カウントの進捗" })).toBeVisible();
    // 一般ユーザーには確定ボタンが出ない
    await expect(page.getByRole("button", { name: "確定して在庫に反映" })).toHaveCount(0);
});

test("D-01 D-09 D-10 管理者が確定すると差異が在庫に反映され、Excel に出せる", async ({ browser }) => {
    const admin = await apiAs("admin");
    const page = await (await browser.newContext({ storageState: authFile("admin") })).newPage();
    await page.goto(sessionUrl);
    await page.getByRole("button", { name: "確定して在庫に反映" }).click();
    const dialog = page.getByRole("dialog", { name: "棚卸しを確定して在庫に反映" });
    await expect(dialog).toContainText("差異のある 1 品目");
    await expect(dialog).toContainText("未カウントの");
    await dialog.getByRole("button", { name: "確定する" }).click();
    await expectToast(page, "確定しました：1品目の在庫を修正");
    await expect(page.getByText("完了", { exact: true })).toBeVisible();
    // 実数8 ＋ 数えた後の出庫 −1 ＝ 7
    expect(await stockOf(admin, a.id)).toBe(7);
    expect(await stockOf(admin, b.id)).toBe(5);
    const hist = await (await admin.get("/api/history", { params: { q: a.item_name, change_type: "STOCKTAKE" } })).json();
    expect(hist.items[0].quantity).toBe(-2);
    // 完了後は入力できない
    await expect(page.getByLabel(`${a.item_name}の実数`)).toHaveCount(0);

    const download = page.waitForEvent("download");
    await page.getByRole("button", { name: "Excel 出力" }).click();
    expect((await download).suggestedFilename()).toBe("棚卸し_E2E 定期棚卸し.xlsx");
});

test("D-08 D-11 中止できる・スマホでも数えられる", async ({ browser }) => {
    const admin = await apiAs("admin");
    const created = await (await admin.post("/api/stocktake/sessions", { data: { name: "E2E 中止テスト", category: "消耗品" } })).json();

    const phone = await (await browser.newContext({ storageState: authFile("user"), viewport: { width: 390, height: 844 } })).newPage();
    await phone.goto(`/stocktake/${created.id}`);
    await phone.getByLabel("物品名・コードで探す").fill(a.item_name);
    const input = phone.getByLabel(`${a.item_name}の実数`);
    await input.scrollIntoViewIfNeeded();
    await expect(input).toBeInViewport();
    await input.fill("7");
    await input.press("Enter");
    await expect(row(phone, a.item_name)).toContainText("保存済");

    const page = await (await browser.newContext({ storageState: authFile("admin") })).newPage();
    await page.goto(`/stocktake/${created.id}`);
    await page.getByRole("button", { name: "中止" }).click();
    await page.getByRole("dialog", { name: "棚卸しを中止" }).getByRole("button", { name: "中止する" }).click();
    await expectToast(page, "棚卸しを中止しました");
    await page.goto("/stocktake");
    await expect(row(page, "E2E 中止テスト")).toContainText("中止");
    await expect(page.getByRole("form", { name: "棚卸しを始める" })).toBeVisible();
    expect(await stockOf(admin, a.id)).toBe(7);
});
