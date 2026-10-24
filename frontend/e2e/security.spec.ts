import { expect, request, test } from "@playwright/test";
import { apiAs, authFile, BASE_URL, expectToast, login, uniq } from "./helpers";

/** 画面のテストで使い回すデモ利用者のパスワードは変えないよう、ここではその場で作った利用者を使う */
async function freshUser(password = "firstpass1") {
    const admin = await apiAs("admin");
    const username = uniq("sec");
    const r = await admin.post("/api/users", { data: { username, password, display_name: "セキュリティ確認", user_role: "USER", department: "検査科" } });
    expect(r.status()).toBe(201);
    return { username, password, id: (await r.json()).id as number };
}

test("G-06 全ページにセキュリティヘッダーが付く", async ({ page }) => {
    const res = await page.goto("/login");
    const h = res!.headers();
    expect(h["content-security-policy"]).toContain("frame-ancestors 'none'");
    expect(h["content-security-policy"]).toContain("object-src 'none'");
    expect(h["x-frame-options"]).toBe("DENY");
    expect(h["x-content-type-options"]).toBe("nosniff");
    expect(h["x-powered-by"]).toBeUndefined();
});

test("G-08 ログイン後の戻り先に外部のサイトは使わない", async ({ page }) => {
    // "/\evil" は URL の解釈で "//evil"（外部）になる。"/<タブ>/evil" はタブが取り除かれて同じく外部になる
    for (const next of ["//evil.example/login", "https://evil.example/", "/\\evil.example/", "/\t/evil.example/"]) {
        await page.context().clearCookies();
        await page.goto(`/login?next=${encodeURIComponent(next)}`);
        await page.getByLabel("ユーザー名").fill("U001");
        await page.getByLabel("パスワード").fill("pass1234");
        await page.getByRole("button", { name: "ログイン" }).click();
        await expect(page).toHaveURL(`${BASE_URL}/dashboard`);
    }
});

test("G-02 10回続けて失敗するとロックされ、管理者が解除できる", async ({ browser }) => {
    const u = await freshUser();
    const anon = await request.newContext({ baseURL: BASE_URL });
    for (let i = 0; i < 10; i++) await anon.post("/api/auth/login", { data: { username: u.username, password: "wrong-pass" } });

    const page = await (await browser.newContext()).newPage();
    await login(page, { username: u.username, password: u.password });
    await expect(page.getByRole("alert").filter({ hasText: "一時的にロック" })).toBeVisible();

    const admin = await (await browser.newContext({ storageState: authFile("admin") })).newPage();
    await admin.goto("/users");
    const row = admin.getByRole("row").filter({ hasText: u.username });
    await expect(row).toContainText("ロック中");
    await row.getByRole("button", { name: "ロック解除" }).click();
    await expectToast(admin, "ロックを解除しました");

    await login(page, { username: u.username, password: u.password });
    await expect(page).toHaveURL(/\/account\/password/);
});

test("G-03 パスワードを変えると、ほかの端末のログインは無効になる", async ({ browser }) => {
    const u = await freshUser();
    const pc = await (await browser.newContext()).newPage();
    const phone = await (await browser.newContext()).newPage();
    for (const p of [pc, phone]) {
        await login(p, { username: u.username, password: u.password });
        await expect(p).toHaveURL(/\/account\/password/);
    }
    await pc.getByLabel("今のパスワード").fill(u.password);
    await pc.getByLabel("新しいパスワード", { exact: true }).fill("secondpass2");
    await pc.getByLabel("新しいパスワード（確認）").fill("secondpass2");
    await pc.getByRole("button", { name: "変更する" }).click();
    await expect(pc).toHaveURL(/\/dashboard/);
    // 変えた本人はそのまま使える
    await pc.getByRole("link", { name: "在庫一覧" }).click();
    await expect(pc.getByRole("heading", { level: 1, name: "在庫一覧" })).toBeVisible();
    // もう一方の端末は次の操作でログイン画面へ
    await phone.goto("/inventory");
    await expect(phone).toHaveURL(/\/login/);
});
