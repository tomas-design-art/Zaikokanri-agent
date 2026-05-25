import "./globals.css";
import type { Metadata } from "next";
import { Providers } from "./providers";

export const metadata: Metadata = {
    title: "在庫管理システム",
    description: "Inventory Management System",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
    return (
        <html lang="ja">
            <body>
                <Providers>{children}</Providers>
            </body>
        </html>
    );
}
