import { expect, test as setup } from "@playwright/test";
import { authFile, login, USERS, type RoleKey } from "./helpers";

// ロールごとに1回だけ画面からログインして Cookie を保存する（以降のテストで使い回す）
for (const role of Object.keys(USERS) as RoleKey[]) {
    setup(`ログイン状態を作る：${role}`, async ({ page }) => {
        await login(page, role);
        await expect(page).toHaveURL(/\/dashboard/);
        await expect(page.getByTestId("current-user")).toContainText(USERS[role].name);
        await page.context().storageState({ path: authFile(role) });
    });
}
