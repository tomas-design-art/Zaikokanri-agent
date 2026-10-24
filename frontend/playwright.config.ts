import path from "node:path";
import { defineConfig, devices } from "@playwright/test";

/**
 * E2E（画面を人と同じように操作するテスト）。
 *
 * 毎回ゼロから実行する：バックエンドは起動のたびに空の SQLite へマイグレーション→デモデータ投入
 * （backend/scripts/e2e_server.py）。既存のサーバーは使い回さない＝前回の結果に左右されない。
 * 開発中の画面（3000）や API（8000）とぶつからないよう、ポートは 3100 / 8100。
 *
 *   npm run e2e:install   # 初回だけ：ブラウザ（Chromium）を入れる
 *   npm run e2e           # 実行
 */
const isCI = !!process.env.CI;
const API_PORT = 8100;
const WEB_PORT = 3100;
const baseURL = `http://localhost:${WEB_PORT}`;
const backendDir = path.resolve(__dirname, "../backend");
const python = process.env.E2E_PYTHON
    ?? (process.platform === "win32" ? path.join(backendDir, ".venv", "Scripts", "python.exe") : "python");

export default defineConfig({
    testDir: "./e2e",
    fullyParallel: false,
    workers: 1, // 1つの DB を共有するので順番に流す
    forbidOnly: isCI,
    retries: isCI ? 1 : 0,
    timeout: 60_000,
    expect: { timeout: 10_000 },
    reporter: isCI ? [["list"], ["html", { open: "never" }]] : [["list"]],
    use: {
        baseURL,
        locale: "ja-JP",
        timezoneId: "Asia/Tokyo",
        trace: "retain-on-failure",
        screenshot: "only-on-failure",
        // E2E_VIDEO=1 で全テストを録画（中身を目で確かめたいとき）。普段は失敗したものだけ残す
        video: process.env.E2E_VIDEO ? "on" : "retain-on-failure",
    },
    projects: [
        { name: "setup", testMatch: /auth\.setup\.ts/ },
        { name: "chromium", use: { ...devices["Desktop Chrome"] }, dependencies: ["setup"] },
    ],
    webServer: [
        {
            name: "API",
            command: `"${python}" scripts/e2e_server.py`,
            cwd: backendDir,
            url: `http://127.0.0.1:${API_PORT}/readyz`,
            env: { E2E_API_PORT: String(API_PORT), E2E_FRONT_ORIGIN: baseURL },
            reuseExistingServer: false,
            timeout: 120_000,
            stdout: "pipe",
        },
        {
            name: "Web",
            command: isCI ? `npm run build && npx next start -p ${WEB_PORT}` : `npx next dev -p ${WEB_PORT}`,
            url: `${baseURL}/login`,
            env: { NEXT_PUBLIC_API_BASE: `http://127.0.0.1:${API_PORT}` },
            reuseExistingServer: false,
            timeout: 240_000,
        },
    ],
});
