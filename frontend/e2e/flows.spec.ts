import { expect, test, type Page } from "@playwright/test";
import { apiAs, authFile, createItem, expectToast, uniq } from "./helpers";

const row = (page: Page, text: string) => page.getByRole("row").filter({ hasText: text });

test.describe("P-01 / P-02 画面で出庫すると全部の画面に反映され、取消で全部元に戻る", () => {
    test.use({ storageState: authFile("user") });

    test("在庫一覧・ダッシュボード・アラート・履歴・統計", async ({ page }) => {
        const admin = await apiAs("admin");
        const item = await createItem(admin, { name: uniq("反映E2E"), qty: 12, reorder: 5, unit: "箱" });
        const before = await (await admin.get("/api/inventory/kpi")).json();

        // 出庫 8 箱（12 → 4、発注点5を下回る）
        await page.goto("/outbound");
        await page.getByLabel("物品を検索").fill(item.item_name);
        await page.getByRole("button", { name: `${item.item_name}をカートに追加` }).click();
        await page.getByRole("listitem", { name: `カート：${item.item_name}` }).getByLabel("数量（箱）").fill("8");
        await page.getByRole("button", { name: "1件まとめて出庫する" }).click();
        await expectToast(page, "1件を出庫しました");

        await page.goto("/inventory");
        await page.getByLabel("検索").fill(item.item_name);
        await expect(row(page, item.item_name)).toContainText("4 箱");
        await expect(row(page, item.item_name)).toContainText("在庫不足");

        await page.goto("/dashboard");
        await expect(page.getByRole("link", { name: /在庫不足/ })).toContainText(String(before.low_stock_count + 1));

        await page.goto("/alerts");
        await expect(page.getByRole("region", { name: "在庫不足" }).getByRole("row").filter({ hasText: item.item_name })).toBeVisible();

        await page.goto("/history");
        await page.getByLabel("物品名・担当者").fill(item.item_name);
        const h = row(page, item.item_name).filter({ hasText: "出庫" });
        await expect(h).toContainText("8");
        await expect(h).toContainText("放射線太郎");
        await expect(h).toContainText("放射線科");

        await page.goto("/stats");
        await expect(page.getByRole("region", { name: "出庫の多い物品" }).getByRole("row").filter({ hasText: item.item_name })).toContainText("8");

        // 取消で全部元に戻る
        await page.goto("/history");
        await page.getByLabel("物品名・担当者").fill(item.item_name);
        await h.getByRole("button", { name: "取消" }).click();
        await page.getByRole("dialog", { name: "操作を取り消す" }).getByRole("button", { name: "取り消す" }).click();
        await expectToast(page, "取り消しました");

        await page.goto("/inventory");
        await page.getByLabel("検索").fill(item.item_name);
        await expect(row(page, item.item_name)).toContainText("12 箱");
        await expect(row(page, item.item_name)).not.toContainText("在庫不足");
        await page.goto("/alerts");
        await expect(page.getByRole("region", { name: "在庫不足" }).getByRole("row").filter({ hasText: item.item_name })).toHaveCount(0);
        await page.goto("/stats");
        await expect(page.getByRole("region", { name: "出庫の多い物品" }).getByRole("row").filter({ hasText: item.item_name })).toHaveCount(0);
    });
});

const FORBIDDEN = "この画面を使う権限がありません";

test.describe("R 権限のない画面は URL で直接開いても使えない", () => {
    test.describe("ゲスト", () => {
        test.use({ storageState: authFile("guest") });
        for (const path of ["/inbound", "/purchase-requests", "/stocktake", "/items", "/items/new", "/users", "/approvals", "/masters", "/maintenance"]) {
            test(path, async ({ page }) => {
                await page.goto(path);
                await expect(page.getByRole("alert").filter({ hasText: FORBIDDEN })).toBeVisible();
            });
        }
    });
    test.describe("一般ユーザー", () => {
        test.use({ storageState: authFile("user") });
        for (const path of ["/items", "/items/new", "/users", "/approvals", "/masters", "/maintenance"]) {
            test(path, async ({ page }) => {
                await page.goto(path);
                await expect(page.getByRole("alert").filter({ hasText: FORBIDDEN })).toBeVisible();
            });
        }
        test("使える画面には出ない", async ({ page }) => {
            for (const path of ["/inbound", "/stocktake", "/purchase-requests"]) {
                await page.goto(path);
                await expect(page.getByText(FORBIDDEN)).toHaveCount(0);
            }
        });
    });
});
