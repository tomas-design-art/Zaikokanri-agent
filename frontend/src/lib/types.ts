export type Role = "GUEST" | "USER" | "ADMIN";

export interface MeResponse {
    id: number;
    username: string;
    display_name: string;
    role: Role;
    department: string | null;
    department_id: number | null;
}

export interface Page<T> { items: T[]; total: number; page: number; per_page: number; }

export interface InventoryRow {
    item_id: number;
    item_name: string;
    item_code: string | null;
    category: string;
    vendor_name: string | null;
    quantity: number;
    threshold: number;
    location: string | null;
    expiry_date: string | null;
    is_low_stock: boolean;
    is_expired: boolean;
    is_expiring_soon: boolean;
}

export interface InventoryKPI {
    total_items: number;
    total_quantity: number;
    low_stock_count: number;
    expired_count: number;
    expiring_soon_count: number;
}

export interface ItemOut {
    id: number;
    item_name: string;
    item_code: string | null;
    vendor_name: string | null;
    vendor_item_code: string | null;
    category: string;
    department_tags: string | null;
    unit_price: number;
    is_asset: number;
    frequency_tag: string | null;
    expiry_date: string | null;
    is_active: number;
    location_text: string | null;
    reorder_point: number | null;
    is_inventory_target: number;
}

export interface HistoryRow {
    id: number;
    item_id: number;
    item_name: string;
    change_type: string;
    quantity: number;
    user_name: string;
    department: string | null;
    status: string;
    note: string | null;
    vendor_name: string | null;
    unit_price: number | null;
    total_price: number | null;
    created_at: string;
}

export interface VendorOut { id: number; vendor_code: string; vendor_name: string; address: string | null; phone: string | null; email: string | null; is_active: number; }
export interface CategoryOut { id: number; name: string; is_active: number; }
export interface DepartmentOut { id: number; name: string; is_active: number; }

export interface PROut {
    id: number; item_id: number; item_name: string;
    requested_qty: number; priority: string; due_date: string | null;
    note: string | null; requested_by: string; requested_by_department: string | null;
    status: string; admin_comment: string | null;
    received_qty: number; received_at: string | null; created_at: string;
}

export interface DROut {
    id: number; item_id: number; item_name: string;
    quantity: number; reason: string; requester: string;
    status: string; reject_reason: string | null; created_at: string;
}

export interface PendingOut {
    id: number; change_type: string; item_id: number; item_name: string;
    quantity: number; current_stock: number; actor_name: string;
    note: string | null; department_id: number; status: string;
    reject_reason: string | null; created_at: string;
}
