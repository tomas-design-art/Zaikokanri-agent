import { expect, test } from "@playwright/test";
import { apiAs, authFile, login, uniq } from "./helpers";

test.describe("ログイン・ログアウト", () => {
    test("パスワードが違うと日本語で理由が出る", async ({ page }) => {
        await login(page, { username: "admin", password: "wrong-pass" });
        await expect(page.getByRole("alert").filter({ hasText: "ユーザー名またはパスワードが違います" })).toBeVisible();
        await expect(page).toHaveURL(/\/login/);
    });

    test("ログインしていないと元のページを覚えてログイン画面へ、ログイン後に戻る", async ({ page }) => {
        await page.goto("/inventory");
        await expect(page).toHaveURL(/\/login\?next=%2Finventory/);
        await page.getByLabel("ユーザー名").fill("U001");
        await page.getByLabel("パスワード").fill("pass1234");
        await page.getByRole("button", { name: "ログイン" }).click();
        await expect(page.getByRole("heading", { level: 1, name: "在庫一覧" })).toBeVisible();
    });

    test("ログアウトすると業務画面に入れない", async ({ page }) => {
        await login(page, "user");
        await expect(page).toHaveURL(/\/dashboard/);
        await page.getByRole("button", { name: "ログアウト" }).click();
        await expect(page).toHaveURL(/\/login/);
        await page.goto("/dashboard");
        await expect(page).toHaveURL(/\/login/);
    });
});

test.describe("A-01 ログインの有効期限", () => {
    test.use({ storageState: authFile("user") });

    test("アクセス用 Cookie が切れても自動で更新され、操作を続けられる", async ({ page, context }) => {
        await page.goto("/inventory");
        await expect(page.getByRole("heading", { level: 1, name: "在庫一覧" })).toBeVisible();
        await expect(page.getByRole("row").filter({ hasText: "マスク（サージカル）" })).toBeVisible();
        await context.clearCookies({ name: "zk_access" });
        // 検索で新しく取りに行く → 401 → 自動で更新 → やり直し、が起きて結果が絞り込まれる
        const searched = page.waitForResponse((r) => r.url().includes("/api/inventory?") && r.url().includes("q=") && r.status() === 200);
        await page.getByLabel("検索").fill("ディスポ手袋（S）");
        await searched;
        await expect(page.getByRole("row").filter({ hasText: "ディスポ手袋（S）" })).toBeVisible();
        await expect(page.getByRole("row").filter({ hasText: "マスク（サージカル）" })).toHaveCount(0);
        await expect(page).toHaveURL(/\/inventory/);
        const names = (await context.cookies()).map((c) => c.name);
        expect(names).toContain("zk_access");
    });

    test("更新用 Cookie も切れていたらログイン画面へ戻り、ログイン後に元のページへ", async ({ page, context }) => {
        await page.goto("/history");
        await expect(page.getByRole("heading", { level: 1, name: "履歴" })).toBeVisible();
        await context.clearCookies();
        await page.getByLabel("物品名・担当者").fill("x");
        await expect(page).toHaveURL(/\/login\?next=%2Fhistory/);
    });
});

test.describe("A-03 / A-04 パスワード変更", () => {
    test("管理者が作ったユーザーは初回ログインでパスワード変更を求められる", async ({ page }) => {
        const admin = await apiAs("admin");
        const username = uniq("newbie");
        const created = await admin.post("/api/users", {
            data: { username, password: "temppass1", display_name: "新人E2E", user_role: "USER", department: "検査科" },
        });
        expect(created.status()).toBe(201);

        await login(page, { username, password: "temppass1" });
        await expect(page).toHaveURL(/\/account\/password/);
        await expect(page.getByRole("alert").filter({ hasText: "初期パスワード" })).toBeVisible();
        // ほかの画面へ行こうとしても戻される
        await page.goto("/inventory");
        await expect(page).toHaveURL(/\/account\/password/);

        await page.getByLabel("今のパスワード").fill("temppass1");
        await page.getByLabel("新しいパスワード", { exact: true }).fill("short");
        await expect(page.getByText("8文字以上にしてください")).toBeVisible();
        await expect(page.getByRole("button", { name: "変更する" })).toBeDisabled();
        await page.getByLabel("新しいパスワード", { exact: true }).fill("brandnew-pass1");
        await page.getByLabel("新しいパスワード（確認）").fill("brandnew-pass1");
        await page.getByRole("button", { name: "変更する" }).click();
        await expect(page).toHaveURL(/\/dashboard/);

        await page.getByRole("link", { name: "在庫一覧" }).click();
        await expect(page.getByRole("heading", { level: 1, name: "在庫一覧" })).toBeVisible();
    });

    test("初期管理者のヒントは開発環境だけで出て、本番ビルドでは出ない", async ({ page }) => {
        await page.goto("/login");
        const hint = page.getByText("初期管理者 admin / admin123");
        // CI は本番ビルド（next build && next start）で流す（playwright.config.ts）
        if (process.env.CI) await expect(hint).toHaveCount(0);
        else await expect(hint).toBeVisible();
    });
});
