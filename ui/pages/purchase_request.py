"""発注申請ページ"""

import streamlit as st

from utils.auth import require_min_role, get_current_user, is_admin
from utils.validation import to_int_safe, validate_date_string, clean_string
from repositories.department_repo import get_all_departments
from repositories.inventory_query import get_inventory_list
from repositories.purchase_request_repo import (
    create_purchase_request,
    get_purchase_requests,
    check_items_ordered_status,
    reset_purchase_request_to_pending,
    delete_purchase_request,
)
from repositories.purchase_candidate_repo import get_reorder_candidates
from ui.components.refresh_button import show_refresh_button


def show_purchase_request_page():
    """📝 発注申請ページ（USER/ADMIN）"""
    st.header("📝 発注申請")
    show_refresh_button()

    # 権限チェック（共通関数使用）：USER以上
    if not require_min_role("USER", "発注申請はUSER/ADMINのみ利用できます"):
        return

    current_user = get_current_user()
    user_dept = current_user.get("department")

    # ADMINは対象部署を選べる
    if is_admin():
        depts = get_all_departments()
        dept_names = [d['name'] for d in depts]
        default_idx = dept_names.index(user_dept) if user_dept in dept_names else 0
        selected_dept = st.selectbox("申請先部署", options=dept_names, index=default_idx)
        department_filter = selected_dept
    else:
        department_filter = user_dept
        st.info(f"📍 申請部署: {user_dept}")

    # 参考情報：自動発注候補
    with st.expander("参考: 発注点割れ物品（参考情報）", expanded=False):
        st.info("発注点を下回っている物品の一覧です。申請は下のフォームから行ってください。")
        try:
            candidates = get_reorder_candidates(department_name=department_filter)
            if candidates:
                st.metric("発注候補件数", f"{len(candidates)}件")
                st.write("**発注候補物品:**")
                
                # 申請・発注済み状態をチェック
                item_ids = [item['item_id'] for item in candidates[:10]]
                order_status = check_items_ordered_status(item_ids)
                
                for idx, item in enumerate(candidates[:10], 1):  # 最大10件表示
                    item_id = item['item_id']
                    item_info = order_status.get(item_id)
                    
                    status_text = ""
                    if item_info:
                        status = item_info.get('status')
                        qty = item_info.get('qty', 0)
                        if status == 'ordered':
                            status_text = f" 申請済 ✅ 発注済（{qty}個）。到着までしばらくお待ちください。"
                        elif status == 'pending':
                            status_text = f" 申請済（{qty}個）"
                    
                    st.write(f"{idx}. {item['item_name']} (在庫: {item['current_stock']}, 発注点: {item['threshold']}){status_text}")
                if len(candidates) > 10:
                    st.caption(f"...他 {len(candidates) - 10}件")
            else:
                st.success("✅ 発注候補はありません")
        except Exception:
            pass

    st.divider()

    # 申請フォーム
    st.subheader("📋 申請フォーム")
    
    # アラート画面から事前選択された物品情報を取得
    prefill_item_id = st.session_state.get("prefill_purchase_item_id")
    prefill_qty = st.session_state.get("prefill_purchase_quantity")
    prefill_reason = st.session_state.get("prefill_purchase_reason", "")
    
    # アラートから来た場合は目立つ通知を表示
    if prefill_item_id:
        st.info(f"📌 **在庫不足アラートから選択されました**")
    
    # 申請成功メッセージの表示（rerun前に設定されたデータ）
    if "last_purchase_request_success" in st.session_state and st.session_state.last_purchase_request_success:
        # 事前選択情報をクリア（アラートページへの戻りを防ぐ）
        if "prefill_purchase_item_id" in st.session_state:
            del st.session_state.prefill_purchase_item_id
        if "prefill_purchase_quantity" in st.session_state:
            del st.session_state.prefill_purchase_quantity
        if "prefill_purchase_reason" in st.session_state:
            del st.session_state.prefill_purchase_reason
        
        # データを保存用キーに移動してrerun
        st.session_state.purchase_request_success_display = st.session_state.last_purchase_request_success.copy()
        st.session_state.last_purchase_request_success = None
        
        # ★重要★ st.session_state.menuは変更しない（= 申請ページのまま留まる）
        st.rerun()
    
    # 二重送信防止: 最後の申請情報を保存
    if "last_pr_submission" not in st.session_state:
        st.session_state.last_pr_submission = None
    
    # 物品選択（自部署タグの範囲）- フォームの外で取得
    items_df = get_inventory_list(department_name=department_filter)
    if items_df.empty:
        st.warning("対象の物品が見つかりません")
        return
    
    with st.form("purchase_request_form"):
        options = [f"{int(r['id'])} - {r['item_name']} ({r.get('item_code','')})" for _, r in items_df.iterrows()]

        # デフォルト選択インデックス
        default_index = 0
        if prefill_item_id is not None:
            for idx, opt in enumerate(options):
                try:
                    if int(opt.split(" - ")[0]) == int(prefill_item_id):
                        default_index = idx
                        break
                except Exception:
                    continue

        selected = st.selectbox("物品", options=options, index=default_index)
        selected_item_id = int(selected.split(" - ")[0])

        # 希望数量
        qty_default = str(prefill_qty) if prefill_qty is not None else ""
        qty_text = st.text_input("希望数量（必須）", value=qty_default, help="全角数字も半角に変換します")
        
        # 希望納期
        due_date_text = st.text_input("希望納期（任意）", placeholder="YYYY-MM-DD")
        
        # 優先度
        priority_display = st.selectbox("優先度", options=["通常", "至急"])
        priority = "normal" if priority_display == "通常" else "urgent"
        
        # 備考
        note = st.text_area("備考（任意）", placeholder="例: 今月造影増えてる")

        submitted = st.form_submit_button("📝 申請する", type="primary")

        if submitted:
            import time
            import hashlib
            
            # デバッグ用ログ
            print(f"[DEBUG] Purchase request form submitted: item_id={selected_item_id}, qty={qty_text}")
            
            # === バリデーション実行（現場向けシンプルAPI使用）===
            validation_errors = []
            
            # 数量（必須・正の整数）
            ok_qty, validated_qty, error_msg_qty = to_int_safe(qty_text, "希望数量", min_value=1, allow_zero=False)
            if not ok_qty:
                validation_errors.append(error_msg_qty)
            
            # 日付（任意・形式チェック）
            ok_date, validated_date, error_msg_date = validate_date_string(due_date_text, field_name="希望納期", required=False)
            if not ok_date:
                validation_errors.append(error_msg_date)
            
            # エラーがあれば表示して終了
            if validation_errors:
                for err in validation_errors:
                    st.error(err)
                st.stop()
            
            # 二重送信チェック: 同じ内容の申請を3秒以内に重複送信しないようにする
            current_time = time.time()
            submission_hash = hashlib.md5(
                f"{selected_item_id}_{validated_qty}_{priority}_{clean_string(note) if note else ''}".encode()
            ).hexdigest()
            
            if st.session_state.last_pr_submission:
                last_time, last_hash = st.session_state.last_pr_submission
                if current_time - last_time < 3 and last_hash == submission_hash:
                    st.warning("⚠️ 同じ内容の申請が処理中です。しばらくお待ちください。")
                    return

            # 申請処理
            print(f"[DEBUG] Creating purchase request: item_id={selected_item_id}, qty={validated_qty}, user_id={current_user.get('id')}")
            res = create_purchase_request(
                item_id=selected_item_id,
                requested_qty=validated_qty,
                user_id=current_user.get('id'),
                department=department_filter,
                priority=priority,
                due_date=validated_date,
                note=clean_string(note) if note else None
            )

            print(f"[DEBUG] Purchase request result: {res}")
            
            if res.get('success'):
                # 成功データを保存（rerun後に表示）
                st.session_state.last_purchase_request_success = {
                    'item_id': selected_item_id,
                    'quantity': validated_qty,
                    'priority': priority,
                    'note': clean_string(note) if note else None
                }
                
                # 最後の申請情報を記録
                st.session_state.last_pr_submission = (current_time, submission_hash)
                
                # 事前選択情報をクリア（アラートページへの戻りを防ぐ）
                if "prefill_purchase_item_id" in st.session_state:
                    del st.session_state.prefill_purchase_item_id
                if "prefill_purchase_quantity" in st.session_state:
                    del st.session_state.prefill_purchase_quantity
                if "prefill_purchase_reason" in st.session_state:
                    del st.session_state.prefill_purchase_reason
                
                # ★重要★ st.session_state.menuは変更しない（= 申請ページのまま留まる）
                print(f"[DEBUG] Purchase request submitted - staying on request page (menu={st.session_state.get('menu')})")
                st.rerun()
            else:
                st.error(f"❌ 申請に失敗しました: {res.get('message')}")
    
    # ========== 成功メッセージ表示（フォームの下） ==========
    if "purchase_request_success_display" in st.session_state:
        success_data = st.session_state.purchase_request_success_display
        st.divider()
        with st.container(border=True):
            st.success("✅ 発注申請を送信しました！")
            st.balloons()
            
            col1, col2 = st.columns(2)
            with col1:
                st.write("**申請内容:**")
                st.write(f"- 数量: {success_data.get('quantity')}個")
                priority_label = "🔴 至急" if success_data.get('priority') == 'urgent' else "通常"
                st.write(f"- 優先度: {priority_label}")
            
            with col2:
                st.info("💡 承認をお待ちください")
                st.caption("承認状況は下の申請一覧で確認できます")
            
            if success_data.get('note'):
                st.write(f"**備考:** {success_data.get('note')}")
        
        # フラグをクリア
        del st.session_state.purchase_request_success_display

    # ========== 自分の申請一覧 ==========
    st.divider()
    st.subheader("📋 自分の申請一覧")
    
    # 自分の申請を取得（全ステータス）
    my_requests = get_purchase_requests(requester_id=current_user.get('id'))
    
    if not my_requests:
        st.info("申請履歴はありません")
    else:
        status_labels = {
            'PENDING': '⏳ 承認待ち',
            'APPROVED': '✅ 承認済み',
            'ON_HOLD': '🔴 保留中',
            'REJECTED': '❌ 却下',
            'ORDERED': '✅ 発注完了',
            'RECEIVED': '🎉 入庫完了'
        }
        
        for req in my_requests:
            status = req.get('status')
            status_label = status_labels.get(status, status)
            priority_badge = "🔴至急 " if req.get('priority') == 'urgent' else ""
            
            with st.container(border=True):
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"**{priority_badge}{req.get('item_name', '')}** — {req.get('requested_qty')}個")
                    st.caption(f"申請日: {req.get('created_at', '')[:10] if req.get('created_at') else ''}")
                    if req.get('note'):
                        st.caption(f"📝 {req.get('note')}")
                with col2:
                    st.markdown(f"**{status_label}**")
                    if status == 'RECEIVED':
                        # 入庫完了の場合：入庫日時と数量を表示
                        if req.get('received_at'):
                            st.success(f"入庫完了: {req.get('received_at')[:10]}")
                        if req.get('received_qty'):
                            st.info(f"入庫数: {req.get('received_qty')}個")
                        if req.get('received_note'):
                            st.caption(f"📝 {req.get('received_note')}")
                    elif status == 'ORDERED':
                        st.success("発注完了しました。到着までしばらくお待ちください。")
                    elif req.get('admin_comment'):
                        st.caption(f"💬 {req.get('admin_comment')}")


# =============================================================================
# 発注申請管理ページ（ADMIN向け）
# =============================================================================

def handle_purchase_request_error(result: dict, request_id: int, user_id: int):
    """
    発注申請の処理エラーを適切にハンドリングし、対処オプションを表示
    
    Args:
        result: 処理結果の辞書
        request_id: 申請ID
        user_id: 管理者ID
    """
    error_code = result.get("error_code")
    current_status = result.get("current_status")
    
    if error_code == "NOT_FOUND":
        st.error("⚠️ 申請が見つかりません")
        st.info("💡 この申請は既に削除された可能性があります。ページを更新してください。")
        
    elif error_code == "ALREADY_ORDERED":
        st.warning("⚠️ この申請は既に発注済みです")
        st.info("💡 発注済みの申請は変更できません。")
        
    elif error_code == "ALREADY_APPROVED":
        st.warning("⚠️ この申請は既に承認済みです")
        with st.expander("🔧 対処オプション"):
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 承認待ちに戻す", key=f"reset_pending_{request_id}", use_container_width=True):
                    res = reset_purchase_request_to_pending(request_id, user_id, "承認済みから承認待ちに戻しました")
                    if res.get("success"):
                        st.success("✅ 承認待ちに戻しました")
                        st.rerun()
                    else:
                        st.error(res.get("message"))
            with col2:
                if st.button("🗑️ この申請を削除", key=f"delete_{request_id}", use_container_width=True):
                    res = delete_purchase_request(request_id)
                    if res.get("success"):
                        st.success("✅ 削除しました")
                        st.rerun()
                    else:
                        st.error(res.get("message"))
    
    elif error_code == "UPDATE_FAILED":
        st.error(f"⚠️ {result.get('message')}")
        st.info(f"💡 現在のステータス: {current_status}")
        with st.expander("🔧 対処オプション"):
            st.caption("この申請に対して以下の対処ができます：")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 承認待ちに戻す", key=f"reset_pending_fail_{request_id}", use_container_width=True):
                    res = reset_purchase_request_to_pending(request_id, user_id, "処理失敗のため承認待ちに戻しました")
                    if res.get("success"):
                        st.success("✅ 承認待ちに戻しました")
                        st.rerun()
                    else:
                        st.error(res.get("message"))
            with col2:
                if st.button("🗑️ この申請を削除", key=f"delete_fail_{request_id}", use_container_width=True):
                    res = delete_purchase_request(request_id)
                    if res.get("success"):
                        st.success("✅ 削除しました")
                        st.rerun()
                    else:
                        st.error(res.get("message"))
    else:
        st.error(f"❌ {result.get('message')}")
