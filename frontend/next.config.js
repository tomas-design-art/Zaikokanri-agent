/** @type {import('next').NextConfig} */

const isDev = process.env.NODE_ENV !== "production";

// 画面のセキュリティヘッダー（G-06）。画面は同じオリジンの /api だけと通信する。
// Next.js の初期表示用スクリプトのため script-src に 'unsafe-inline' が要る（開発中は再読み込み用に 'unsafe-eval' と ws: も）。
const csp = [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src 'self'${isDev ? " ws: wss:" : ""}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
].join("; ");

const securityHeaders = [
    { key: "Content-Security-Policy", value: csp },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    { key: "Permissions-Policy", value: "geolocation=(), microphone=(), camera=()" },
    // HTTPS で開いたときだけブラウザが従う（社内 LAN の http では無視される）
    ...(isDev ? [] : [{ key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" }]),
];

const nextConfig = {
    reactStrictMode: true,
    poweredByHeader: false,
    async rewrites() {
        const apiBase = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
        return [{ source: "/api/:path*", destination: `${apiBase}/:path*` }];
    },
    async headers() {
        return [{ source: "/:path*", headers: securityHeaders }];
    },
};
module.exports = nextConfig;
