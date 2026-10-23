"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { Toaster } from "sonner";
import { ApiError } from "@/lib/api";

export function Providers({ children }: { children: React.ReactNode }) {
    const [qc] = useState(() => new QueryClient({
        defaultOptions: {
            queries: {
                // 4xx（権限・入力の誤り）はやり直しても同じなので再試行しない
                retry: (count, err) => count < 2 && (!(err instanceof ApiError) || err.status === 0 || err.status >= 500),
                refetchOnWindowFocus: false,
                staleTime: 15_000,
            },
        },
    }));
    return (
        <QueryClientProvider client={qc}>
            {children}
            <Toaster richColors position="top-right" closeButton />
        </QueryClientProvider>
    );
}
