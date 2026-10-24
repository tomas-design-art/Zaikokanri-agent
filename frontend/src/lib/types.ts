export type Role = "GUEST" | "USER" | "ADMIN";

export interface MeResponse {
    id: number;
    username: string;
    display_name: string;
    role: Role;
    department: string | null;
    department_id: number | null;
    must_change_password: boolean;
}

export interface Page<T> { items: T[]; total: number; page: number; per_page: number; }

export interface InventoryRow {
    item_id: number;
    item_name: string;
    item_code: string | null;
    category: string;
    unit: string;
    vendor_name: string | null;
    unit_price: number | null;  // ゲストには出ない
    owner_department_id: number | null;
    is_common: boolean;
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

export interface Todo { guest_outbound: number; disposal: number; purchase: number; receivable: number; disposal_notices: number; }

export interface ItemOut {
    id: number;
    item_name: string;
    item_code: string | null;
    vendor_name: string | null;
    vendor_item_code: string | null;
    category: string;
    unit: string;
    department_tags: string | null;
    unit_price: number | null;  // ゲストには出ない
    owner_department_id: number | null;
    is_common: number;
    expiry_date: string | null;
    location_text: string | null;
    reorder_point: number | null;
    is_inventory_target: number;
    is_active: number;
}

export interface ItemDetail extends ItemOut { quantity: number; threshold: number; }

export interface StockResult {
    item_id: number; item_name: string; change: number; new_quantity: number;
    history_id: number | null; pending: boolean; pending_id: number | null;
}

export interface HistoryRow {
    id: number;
    item_id: number;
    item_name: string;
    unit: string;
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
    can_undo: boolean;
}

export interface VendorOut { id: number; vendor_code: string; vendor_name: string; address: string | null; phone: string | null; email: string | null; is_active: number; }
export interface CategoryOut { id: number; name: string; is_active: number; }
export interface DepartmentOut { id: number; name: string; is_active: number; }

export interface PROut {
    id: number; item_id: number; item_name: string; unit: string; vendor_name: string | null;
    requested_qty: number; priority: string; due_date: string | null;
    note: string | null; requested_by: string; requested_by_user_id: number; requested_by_department: string | null;
    status: string; admin_comment: string | null;
    received_qty: number; remaining_qty: number; received_at: string | null; created_at: string;
}

export interface DROut {
    id: number; item_id: number; item_name: string; unit: string;
    quantity: number; reason: string; requester: string; requester_id: number; department: string | null;
    status: string; reject_reason: string | null; created_at: string;
}

export interface NoticeOut {
    id: number; item_id: number; item_name: string; unit: string; quantity: number; current_stock: number;
    reason: string; reporter: string; reporter_id: number; department_id: number; department: string | null;
    status: string; handled_by: string | null; handled_comment: string | null; disposal_request_id: number | null;
    created_at: string; handled_at: string | null;
}

export interface SummaryGroup {
    item_id: number; item_name: string; unit: string; vendor_name: string | null; current_stock: number; total_qty: number;
    departments: { department: string; qty: number }[];
    requests: PROut[];
}

export interface PendingOut {
    id: number; change_type: string; item_id: number; item_name: string; unit: string;
    quantity: number; current_stock: number; actor_name: string;
    note: string | null; department_id: number; department: string | null; status: string;
    reject_reason: string | null; created_at: string;
}

export interface MyRequest {
    id: number; item_id: number; item_name: string; quantity: number; current_stock: number;
    note: string | null; status: string; reject_reason: string | null; created_at: string; decided_at: string | null;
}

export interface UserRow {
    id: number; username: string; display_name: string; user_role: Role;
    department: string | null; department_id: number | null; is_active: number; must_change_password: number;
    locked: boolean;
}

export interface StocktakeSummary { total: number; counted: number; uncounted: number; matched: number; diff: number; }

export interface StocktakeSession {
    id: number; name: string; start_date: string | null; end_date: string | null; status: string; note: string | null;
    category: string | null; created_by: string | null; created_at: string; closed_at: string | null;
    summary: StocktakeSummary;
}

export interface StocktakeRecord {
    id: number; session_id: number; item_id: number; item_name: string; item_code: string | null; category: string;
    location: string | null; unit: string; system_qty: number; actual_qty: number | null; diff_qty: number | null;
    status: string; note: string | null; counted_by: string | null; counted_at: string | null;
}

export type OrderItem = { item_name: string; item_code: string; vendor_part_no: string; quantity: number; unit_price: number | null; subtotal: number | null; notes: string };
export type OrderPayload = { vendor: string; subject: string; to: string; ordered_at: string; requester: { department: string; name: string }; items: OrderItem[]; total: number | null; has_unpriced_items: boolean };
