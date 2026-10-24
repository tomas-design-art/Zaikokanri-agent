import { expect, test, type Page } from "@playwright/test";
import { apiAs, authFile, createItem, expectToast, stockOf, uniq } from "./helpers";

const row = (page: Page, text: string) => page.getByRole("row").filter({ hasText: text });

test.describe("在庫一覧", () => {
    test.use({ storageState: authFile("user") });

    test("B-03 B-16 B-19 B-20 検索・カテゴリ・単位と保管場所・CSV", async ({ page }) => {
        const admin = await apiAs("admin");
        const item = await createItem(admin, { name: uniq("在庫一覧テスト"), unit: "箱", location: "倉庫Q-1", qty: 20, category: "医療材料" });
        await page.goto("/inventory");
        await page.getByLabel("検索").fill(item.item_name);
        const r = row(page, item.item_name);
        await expect(r).toContainText("20 箱");
        await expect(r).toContainText("倉庫Q-1");
        await page.getByLabel("カテゴリ").selectOption("事務用品");
        await expect(page.getByText("該当するデータはありません")).toBeVisible();
        await page.getByLabel("カテゴリ").selectOption("医療材料");
        await expect(r).toBeVisible();

        const download = page.waitForEvent("download");
        await page.getByRole("button", { name: "CSV ダウンロード" }).click();
        const file = await download;
        expect(file.suggestedFilename()).toBe("在庫一覧.csv");
        const text = (await (await file.createReadStream()).toArray()).join("");
        expect(text).toContain(item.item_name);
    });
});

test.describe("物品マスター（管理者）", () => {
    test.use({ storageState: authFile("admin") });

    test("B-01 B-04 B-13 新規登録：期限を空にしても期限切れに数えない・数値の入力チェック", async ({ page }) => {
        const admin = await apiAs("admin");
        const before = await (await admin.get("/api/inventory/kpi")).json();
        const name = uniq("新規登録テスト");
        await page.goto("/items/new");
        await page.getByLabel("物品名 *").fill(name);
        await page.getByLabel("カテゴリ *").selectOption("消耗品");
        await page.getByLabel("単位 *").fill("箱");
        await page.getByLabel("単価（円）").fill("-1");
        await expect(page.getByText("単価は0以上の数値で入力してください")).toBeVisible();
        await expect(page.getByRole("button", { name: "登録" })).toBeDisabled();
        await page.getByLabel("単価（円）").fill("250");
        // 数量欄は消して打ち直せる（B-13）
        const init = page.getByLabel("初期在庫");
        await init.fill("");
        await expect(page.getByText("初期在庫を入力してください")).toBeVisible();
        await init.pressSequentially("12");
        await expect(init).toHaveValue("12");
        await page.getByLabel("保管場所").fill("倉庫Z-9");
        await page.getByRole("button", { name: "登録" }).click();
        await expectToast(page, `「${name}」を登録しました`);
        await expect(page).toHaveURL(/\/items$/);

        const after = await (await admin.get("/api/inventory/kpi")).json();
        expect(after.expired_count).toBe(before.expired_count);
        expect(after.total_items).toBe(before.total_items + 1);
    });

    test("B-02 B-12 編集：発注点が在庫不足に効く・在庫数の調整・無効化と復帰", async ({ page }) => {
        const admin = await apiAs("admin");
        const item = await createItem(admin, { name: uniq("編集テスト"), qty: 12, reorder: 3 });
        await page.goto(`/items/${item.id}`);
        await page.getByLabel("発注点").fill("50");
        await page.getByRole("button", { name: "保存" }).click();
        await expectToast(page, "更新しました");
        const low: { item_id: number }[] = await (await admin.get("/api/alerts/low-stock")).json();
        expect(low.map((r) => r.item_id)).toContain(item.id);

        await page.goto(`/items/${item.id}`);
        await page.getByLabel("新しい在庫数").fill("10");
        await expect(page.getByText("増減 -2")).toBeVisible();
        await page.getByLabel("理由 *").fill("破損のため");
        await page.getByRole("button", { name: "調整する" }).click();
        await expectToast(page, "在庫数を調整しました");
        expect(await stockOf(admin, item.id)).toBe(10);
        const hist = await (await admin.get("/api/history", { params: { q: item.item_name, change_type: "ADJUST" } })).json();
        expect(hist.items[0].quantity).toBe(-2);

        await page.goto("/items");
        await page.getByLabel("検索").fill(item.item_name);
        await row(page, item.item_name).getByRole("button", { name: "無効にする" }).click();
        await page.getByRole("dialog").getByRole("button", { name: "無効にする" }).click();
        await expectToast(page, "無効にしました");
        await expect(row(page, item.item_name)).toHaveCount(0);
        await page.getByLabel("無効な物品も表示").check();
        await row(page, item.item_name).getByRole("button", { name: "有効に戻す" }).click();
        await expectToast(page, "有効に戻しました");
    });
});

test.describe("出庫", () => {
    test("B-11 B-13 B-14 一般ユーザー：カート・在庫超えの警告・直後の取り消し", async ({ browser }) => {
        const admin = await apiAs("admin");
        const user = await apiAs("user");
        const item = await createItem(admin, { name: uniq("出庫テスト"), qty: 10 });
        const page = await (await browser.newContext({ storageState: authFile("user") })).newPage();
        await page.goto("/outbound");
        await page.getByLabel("物品を検索").fill(item.item_name);
        await page.getByRole("button", { name: `${item.item_name}をカートに追加` }).click();
        const qty = page.getByRole("listitem", { name: `カート：${item.item_name}` }).getByLabel("数量（個）");
        await qty.fill("");
        await qty.pressSequentially("5");
        await expect(qty).toHaveValue("5");
        await qty.fill("11");
        await expect(page.getByText("在庫（10 個）を超えています")).toBeVisible();
        await expect(page.getByRole("button", { name: "1件まとめて出庫する" })).toBeDisabled();
        await qty.fill("3");
        await page.getByRole("button", { name: "1件まとめて出庫する" }).click();
        await expectToast(page, "1件を出庫しました");
        expect(await stockOf(user, item.id)).toBe(7);
        await page.getByRole("button", { name: "取り消す" }).click();
        await expectToast(page, "出庫を取り消しました");
        expect(await stockOf(user, item.id)).toBe(10);
    });

    test("B-07 B-09 C-01 C-02 ゲストは申請 → 管理者が承認・却下 → ゲストが結果を見る", async ({ browser }) => {
        const admin = await apiAs("admin");
        const a = await createItem(admin, { name: uniq("ゲスト申請A"), qty: 10 });
        const b = await createItem(admin, { name: uniq("ゲスト申請B"), qty: 10 });
        const guest = await (await browser.newContext({ storageState: authFile("guest") })).newPage();
        await guest.goto("/outbound");
        await expect(guest.getByRole("heading", { level: 1, name: "出庫の申請" })).toBeVisible();
        for (const it of [a, b]) {
            await guest.getByLabel("物品を検索").fill(it.item_name);
            await guest.getByRole("button", { name: `${it.item_name}をカートに追加` }).click();
        }
        await guest.getByRole("listitem", { name: `カート：${a.item_name}` }).getByLabel("数量（個）").fill("2");
        await guest.getByRole("button", { name: "2件の出庫を申請する" }).click();
        await expectToast(guest, "2件を承認待ちとして申請しました");
        expect(await stockOf(admin, a.id)).toBe(10);
        const mine = guest.getByRole("region", { name: "あなたの出庫申請" });
        await expect(mine.getByRole("row").filter({ hasText: a.item_name })).toContainText("承認待ち");

        const adm = await (await browser.newContext({ storageState: authFile("admin") })).newPage();
        await adm.goto("/approvals");
        await adm.getByRole("row").filter({ hasText: a.item_name }).getByRole("button", { name: "承認" }).click();
        await expectToast(adm, "承認しました");
        expect(await stockOf(admin, a.id)).toBe(8);
        await adm.getByRole("row").filter({ hasText: b.item_name }).getByRole("button", { name: "却下" }).click();
        const dialog = adm.getByRole("dialog", { name: "出庫申請を却下" });
        await expect(dialog.getByRole("button", { name: "却下する" })).toBeDisabled();
        await dialog.getByLabel("却下理由").fill("在庫確保のため");
        await dialog.getByRole("button", { name: "却下する" }).click();
        await expectToast(adm, "却下しました");

        await guest.reload();
        await expect(mine.getByRole("row").filter({ hasText: a.item_name })).toContainText("承認済");
        await expect(mine.getByRole("row").filter({ hasText: b.item_name })).toContainText("在庫確保のため");
        const hist = await (await admin.get("/api/history", { params: { q: a.item_name, change_type: "OUT" } })).json();
        expect(hist.items[0].department).toBe("放射線科");
    });
});

test.describe("入庫", () => {
    test.use({ storageState: authFile("user") });

    test("B-21 通常の入庫：業者と単価が初期入力される", async ({ page }) => {
        const admin = await apiAs("admin");
        const item = await createItem(admin, { name: uniq("入庫テスト"), qty: 5, price: 320, vendor: "医薬品卸A社" });
        await page.goto("/inbound");
        await page.getByLabel("物品を検索").fill(item.item_name);
        await page.getByRole("option", { name: new RegExp(item.item_name) }).click();
        await expect(page.getByLabel("業者名（任意）")).toHaveValue("医薬品卸A社");
        await expect(page.getByLabel("単価（円・任意）")).toHaveValue("320");
        await page.getByLabel("数量（個）").fill("4");
        await page.getByRole("button", { name: "入庫を登録" }).click();
        await expectToast(page, `「${item.item_name}」を入庫しました（在庫 9）`);
        expect(await stockOf(admin, item.id)).toBe(9);
    });

    test("C-05 発注品の受領：一部 → 残り全部で受領済", async ({ page }) => {
        const admin = await apiAs("admin");
        const user = await apiAs("user");
        const item = await createItem(admin, { name: uniq("受領テスト"), qty: 0 });
        const pr = await (await user.post("/api/purchase-requests", { data: { item_id: item.id, requested_qty: 6 } })).json();
        await admin.patch(`/api/purchase-requests/${pr.id}`, { data: { status: "APPROVED" } });

        await page.goto("/inbound?tab=receive");
        await expect(page.getByRole("tab", { name: "発注品の受領" })).toHaveAttribute("aria-selected", "true");
        const qty = page.getByLabel(`${item.item_name}の受領数`);
        await expect(qty).toHaveValue("6");
        await qty.fill("2");
        await row(page, item.item_name).getByRole("button", { name: "受領" }).click();
        await expectToast(page, `「${item.item_name}」を受領しました`);
        await expect(page.getByLabel(`${item.item_name}の受領数`)).toHaveValue("4");
        await row(page, item.item_name).getByRole("button", { name: "受領" }).click();
        await expect(row(page, item.item_name)).toHaveCount(0);
        expect(await stockOf(admin, item.id)).toBe(6);
        const after = await (await user.get("/api/purchase-requests", { params: { mine: true } })).json();
        expect(after.items.find((x: { id: number }) => x.id === pr.id).status).toBe("RECEIVED");
    });
});

test.describe("履歴", () => {
    test.use({ storageState: authFile("user") });

    test("B-10 B-11 E-04 区分の絞り込み・取消・CSV", async ({ page }) => {
        const admin = await apiAs("admin");
        const user = await apiAs("user");
        const item = await createItem(admin, { name: uniq("履歴テスト"), qty: 10 });
        await user.post("/api/outbound", { data: { item_id: item.id, quantity: 4 } });

        await page.goto("/history");
        await page.getByLabel("区分").selectOption({ label: "出庫" });
        await page.getByLabel("物品名・担当者").fill(item.item_name);
        const r = row(page, item.item_name);
        await expect(r).toContainText("出庫");
        await r.getByRole("button", { name: "取消" }).click();
        await page.getByRole("dialog", { name: "操作を取り消す" }).getByRole("button", { name: "取り消す" }).click();
        await expectToast(page, "取り消しました");
        await expect(r).toContainText("取消済");
        await expect(r.getByRole("button", { name: "取消" })).toHaveCount(0);
        expect(await stockOf(admin, item.id)).toBe(10);

        const download = page.waitForEvent("download");
        await page.getByRole("button", { name: "CSV ダウンロード" }).click();
        expect((await download).suggestedFilename()).toBe("履歴.csv");
    });
});
