import { expect, test, type Page } from "@playwright/test";
import { apiAs, authFile, createItem, expectToast, login, uniq } from "./helpers";

const row = (page: Page, text: string) => page.getByRole("row").filter({ hasText: text });

test.describe("マスタ管理", () => {
    test.use({ storageState: authFile("admin") });

    test("B-05 重複は日本語で知らせる・E-07 カテゴリ名を変えると物品側も変わる・無効化", async ({ page }) => {
        const admin = await apiAs("admin");
        await page.goto("/masters");
        const vendors = page.getByRole("region", { name: "業者" });
        await vendors.getByLabel("業者コード").fill("V001");
        await vendors.getByLabel("業者名").fill(uniq("重複業者"));
        await vendors.getByRole("button", { name: "追加" }).click();
        await expectToast(page, "同じ内容がすでに登録されています（重複）");

        const cats = page.getByRole("region", { name: "カテゴリ" });
        const cat = uniq("E2Eカテゴリ");
        await cats.getByLabel("カテゴリ名").fill(cat);
        await cats.getByRole("button", { name: "追加" }).click();
        await expectToast(page, "登録しました");
        const item = await createItem(admin, { name: uniq("カテゴリ変更テスト"), category: cat });
        await cats.getByRole("listitem").filter({ hasText: cat }).getByRole("button", { name: "名前を変更" }).click();
        const renamed = `${cat}改`;
        await page.getByRole("dialog").getByLabel("新しい名前").fill(renamed);
        await page.getByRole("dialog").getByRole("button", { name: "保存" }).click();
        await expect(cats.getByRole("listitem").filter({ hasText: renamed })).toBeVisible();
        expect((await (await admin.get(`/api/items/${item.id}`)).json()).category).toBe(renamed);

        await cats.getByRole("listitem").filter({ hasText: renamed }).getByRole("button", { name: "無効にする" }).click();
        await expect(cats.getByRole("listitem").filter({ hasText: renamed })).toHaveCount(0);
        await cats.getByLabel("無効も表示").check();
        await expect(cats.getByRole("listitem").filter({ hasText: renamed }).getByRole("button", { name: "有効に戻す" })).toBeVisible();
    });
});

test.describe("ユーザー管理", () => {
    test("A-02 A-05 A-06 追加・編集・自分は無効にできない・無効にした人はログインできない", async ({ browser }) => {
        const page = await (await browser.newContext({ storageState: authFile("admin") })).newPage();
        await page.goto("/users");
        const form = page.getByRole("form", { name: "ユーザーの追加" });
        const username = uniq("staff");
        await form.getByLabel("ユーザー名").fill(username);
        await form.getByLabel("仮パスワード").fill("1234567");
        await form.getByLabel("表示名").fill("E2E職員");
        await expect(form.getByRole("button", { name: "追加" })).toBeDisabled();
        await form.getByLabel("仮パスワード").fill("12345678");
        await form.getByRole("button", { name: "追加" }).click();
        await expectToast(page, "登録しました");
        await expect(row(page, username)).toContainText("パスワード変更待ち");

        await row(page, username).getByRole("button", { name: "編集" }).click();
        const dialog = page.getByRole("dialog", { name: `ユーザーの編集：${username}` });
        await dialog.getByLabel("表示名").fill("E2E職員（改）");
        await dialog.getByRole("button", { name: "保存" }).click();
        await expectToast(page, "更新しました");
        await expect(row(page, username)).toContainText("E2E職員（改）");

        // 自分（admin）の行には「無効にする」が無い
        await expect(page.getByRole("row").filter({ has: page.getByRole("cell", { name: "admin", exact: true }) }).getByRole("button", { name: "無効にする" })).toHaveCount(0);

        await row(page, username).getByRole("button", { name: "無効にする" }).click();
        await page.getByRole("dialog", { name: "ユーザーを無効にする" }).getByRole("button", { name: "無効にする" }).click();
        await expectToast(page, "無効にしました");
        await expect(row(page, username)).toHaveCount(0);

        const other = await (await browser.newContext()).newPage();
        await login(other, { username, password: "12345678" });
        await expect(other.getByRole("alert").filter({ hasText: "ユーザー名またはパスワードが違います" })).toBeVisible();
    });
});

test.describe("統計・ダッシュボード", () => {
    test.use({ storageState: authFile("admin") });

    test("E-01 出庫ランキングに当月の出庫が出る・C-09 処理待ちの件数が出る", async ({ page }) => {
        const admin = await apiAs("admin");
        const guest = await apiAs("guest");
        const item = await createItem(admin, { name: uniq("統計テスト"), qty: 50 });
        await admin.post("/api/outbound", { data: { item_id: item.id, quantity: 40 } });
        await guest.post("/api/outbound", { data: { item_id: item.id, quantity: 1 } });

        await page.goto("/stats");
        await expect(page.getByRole("region", { name: "出庫の多い物品" }).getByRole("row").filter({ hasText: item.item_name })).toContainText("40");

        await page.goto("/dashboard");
        const todo = page.getByRole("region", { name: "処理待ち" });
        await expect(todo).toContainText("ゲスト出庫の承認待ち");
        await expect(page.getByRole("navigation", { name: "メインメニュー" }).getByLabel(/処理待ち \d+件/).first()).toBeVisible();
    });
});

test.describe("AI・メンテナンス", () => {
    test.use({ storageState: authFile("admin") });

    test("E-02 AI が無効なときは理由を出す・E-05 DB の接続状態と修復", async ({ page }) => {
        await page.goto("/ai");
        await page.getByLabel("質問").fill("在庫が少ない物品は？");
        await page.getByRole("button", { name: "尋ねる" }).click();
        await expect(page.getByRole("status").filter({ hasText: "無効" })).toBeVisible();

        await page.goto("/maintenance");
        await expect(page.getByText("正常に接続できています")).toBeVisible();
        await page.getByRole("button", { name: "修復を実行" }).click();
        await expectToast(page, /在庫レコード/);
    });
});
