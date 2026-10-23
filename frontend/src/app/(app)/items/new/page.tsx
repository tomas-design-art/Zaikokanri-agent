"use client";

import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiPost, errorText } from "@/lib/api";
import type { ItemOut } from "@/lib/types";
import { ItemForm, type ItemPayload } from "@/components/ItemForm";
import { PageHeader } from "@/components/ui";

export default function NewItemPage() {
    const router = useRouter();
    const qc = useQueryClient();
    const create = useMutation({
        mutationFn: (body: ItemPayload) => apiPost<ItemOut>("/items", body),
        onSuccess: (created) => {
            toast.success(`「${created.item_name}」を登録しました`);
            qc.invalidateQueries({ queryKey: ["items"] });
            qc.invalidateQueries({ queryKey: ["inventory"] });
            qc.invalidateQueries({ queryKey: ["kpi"] });
            router.push("/items");
        },
        onError: (e) => toast.error(errorText(e)),
    });
    return (
        <div className="max-w-3xl space-y-4">
            <PageHeader title="物品を新規登録" />
            <ItemForm submitLabel="登録" busy={create.isPending} onSubmit={(b) => create.mutate(b)} onCancel={() => router.push("/items")} />
        </div>
    );
}
