import { expect, test } from "@playwright/test";
import { authFile } from "./helpers";

const PAGES: [string, string][] = [
    ["/dashboard", "ダッシュボード"],
    ["/inventory", "在庫一覧"],
    ["/outbound", "出庫"],
    ["/inbound", "入庫"],
    ["/history", "履歴"],
    ["/alerts", "アラート"],
    ["/purchase-requests", "発注申請"],
    ["/approvals", "ゲスト出庫の承認"],
    ["/disposal", "廃棄申請"],
    ["/stocktake", "棚卸し"],
    ["/stats", "統計"],
    ["/items", "物品マスター"],
    ["/items/new", "物品を新規登録"],
    ["/masters", "業者・カテゴリ・部署"],
    ["/users", "ユーザー管理"],
    ["/ai", "AIアシスタント"],
    ["/maintenance", "メンテナンス"],
    ["/account/password", "パスワード変更"],
];

test.describe("全画面が開ける（管理者）", () => {
    test.use({ storageState: authFile("admin") });

    for (const [path, heading] of PAGES) {
        test(`${heading}（${path}）`, async ({ page }) => {
            const errors: string[] = [];
            page.on("pageerror", (e) => errors.push(e.message));
            await page.goto(path);
            await expect(page.getByRole("heading", { level: 1, name: heading, exact: true })).toBeVisible();
            await expect(page.getByText("読み込みに失敗しました")).toHaveCount(0);
            await expect(page.getByText("サーバーでエラーが発生しました")).toHaveCount(0);
            expect(errors).toEqual([]);
        });
    }
});

const menu = (page: import("@playwright/test").Page) => page.getByRole("navigation", { name: "メインメニュー" });

test.describe("B-18 ロールごとに出すメニュー", () => {
    test.describe("ゲスト", () => {
        test.use({ storageState: authFile("guest") });
        test("申請だけができ、管理のメニューは出ない", async ({ page }) => {
            await page.goto("/dashboard");
            for (const name of ["在庫一覧", "出庫", "履歴", "廃棄申請"]) await expect(menu(page).getByRole("link", { name, exact: true })).toBeVisible();
            for (const name of ["入庫", "発注申請", "棚卸し", "物品マスター", "ユーザー管理", "出庫承認"]) await expect(menu(page).getByRole("link", { name, exact: true })).toHaveCount(0);
            await expect(page.getByRole("link", { name: "出庫を申請する" })).toBeVisible();
        });
    });
    test.describe("一般ユーザー", () => {
        test.use({ storageState: authFile("user") });
        test("入庫・発注申請・棚卸しはできるが、マスター管理は出ない", async ({ page }) => {
            await page.goto("/dashboard");
            for (const name of ["入庫", "発注申請", "棚卸し"]) await expect(menu(page).getByRole("link", { name, exact: true })).toBeVisible();
            for (const name of ["物品マスター", "ユーザー管理", "出庫承認", "メンテナンス"]) await expect(menu(page).getByRole("link", { name, exact: true })).toHaveCount(0);
            await page.goto("/inventory");
            await expect(page.getByRole("link", { name: "＋ 物品を登録" })).toHaveCount(0);
            await expect(page.getByRole("link", { name: "編集・調整" })).toHaveCount(0);
        });
    });
});

test.describe("D-11 スマホ・タブレット", () => {
    test.use({ storageState: authFile("user"), viewport: { width: 390, height: 844 } });
    test("メニューは折りたたまれ、開いて画面を移動できる", async ({ page }) => {
        await page.goto("/dashboard");
        await expect(menu(page).getByRole("link", { name: "在庫一覧" })).not.toBeInViewport();
        await page.getByRole("button", { name: "メニューを開く" }).click();
        await menu(page).getByRole("link", { name: "棚卸し" }).click();
        await expect(page.getByRole("heading", { level: 1, name: "棚卸し" })).toBeVisible();
        await expect(menu(page).getByRole("link", { name: "在庫一覧" })).not.toBeInViewport();
        // 横にはみ出さない
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        expect(overflow).toBeLessThanOrEqual(1);
    });
});
