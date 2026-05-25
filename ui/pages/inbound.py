"""入庫ページ"""

import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import defaultdict

from utils.auth import require_min_role, get_current_user
from utils.validation import to_int_safe
from utils.date_utils import parse_db_ts_to_jst
from ui.components.refresh_button import show_refresh_button
from repositories.inventory_repo import process_inbound, get_item_by_id
from repositories.inventory_query import get_all_items_for_inbound, get_categories
from repositories.history_repo import get_recent_history_for_undo, can_undo_history, process_undo
from repositories.purchase_request_repo import get_ordered_purchase_requests, receive_purchase_order, get_purchase_requests
from db import get_db_connection


def set_menu(menu_id: str):
    """
    メニューIDを設定して画面遷移（リラン）するヘルパー関数

    【重要】画面遷移は必ずこの関数を使用してください。
    st.session_state.menu_id への直接代入は禁止です。
    """
    st.session_state.menu_id = menu_id
    st.session_state.pending_menu_id = menu_id
    st.session_state.current_page = 1
    st.rerun()


def show_inbound_page():
    """入庫ページ"""
    st.header("➕ 入庫処理")
    
    # 更新ボタン
    show_refresh_button()
    
    # ページ上部のメッセージ領域（取消成功など）
    message_area = st.empty()
    
    # 取消成功メッセージ表示（ページ上部）
    if "last_undo_inbound_success" in st.session_state and st.session_state.last_undo_inbound_success:
        with message_area.container():
            st.success(st.session_state.last_undo_inbound_success)
        st.session_state.last_undo_inbound_success = None
    
    # 権限チェック（共通関数使用）：ADMIN/USERのみ（GUESTは入庫不可）
    if not require_min_role("USER", "入庫処理はUSER以上の権限が必要です（ゲストユーザーは入庫不可）"):
        return
    
    # セクション切り替え（rerun時も保持）
    section = st.radio(
        "表示セクション",
        options=["🚚 発注品入庫", "📦 通常入庫"],
        horizontal=True,
        key="inbound_section",
    )

    if section == "🚚 発注品入庫":
        show_purchase_order_inbound_tab()
    else:
        show_normal_inbound_tab()


def show_normal_inbound_tab():
    """通常入庫タブの内容"""
    # 前回の入庫成功メッセージをセッションから移動して rerun で表示
    if "last_inbound_success" in st.session_state and st.session_state.last_inbound_success:
        st.session_state.inbound_success_display = st.session_state.last_inbound_success.copy()
        st.session_state.last_inbound_success = None
        st.rerun()
    
    st.info("💡 在庫を増やす処理です。入庫すると自動的に履歴に記録されます。")
    
    # デバッグ：データ取得タイムスタンプ
    current_time = datetime.now(ZoneInfo('Asia/Tokyo')).strftime("%H:%M:%S")
    st.caption(f"🕒 データ取得時刻: {current_time}")

    # 取消エラーメッセージはその場で表示
    if "last_undo_inbound_error" in st.session_state and st.session_state.last_undo_inbound_error:
        st.error(st.session_state.last_undo_inbound_error)
        st.session_state.last_undo_inbound_error = None
    
    # 検索フォーム
    st.subheader("🔍 物品検索")
    
    col1, col2, col3 = st.columns([3, 2, 1])
    
    with col1:
        search_query_inbound = st.text_input(
            "検索",
            placeholder="品目名、品目コード、業者名などで検索",
            key="search_query_inbound"
        )
    
    with col2:
        categories = ["すべて"] + get_categories()
        category_filter_inbound = st.selectbox(
            "カテゴリ",
            options=categories,
            key="category_filter_inbound"
        )
    
    with col3:
        st.write("")  # スペース調整
        st.write("")
        search_button_inbound = st.button("🔎 検索", key="search_btn_inbound", use_container_width=True)
    
    st.divider()
    
    # 入庫可能な物品を取得（検索条件適用）
    items = get_all_items_for_inbound(search_query_inbound, category_filter_inbound)
    
    if not items:
        st.warning("⚠️ 検索条件に該当する物品がありません")
        return
    
    st.info(f"📊 {len(items)} 件の物品が見つかりました")
    
    # 【重要】物品選択をフォームの外に出す（リアルタイム反映のため）
    st.subheader("📝 入庫情報入力")
    
    # 物品選択（フォーム外）
    item_options = {
        f"{item['item_name']} (現在在庫: {item.get('quantity', 0)}個) [{item.get('category', '-')}]": item['id']
        for item in items
    }
    
    selected_item_display = st.selectbox(
        "物品を選択",
        options=list(item_options.keys()),
        help="全ての物品が表示されています",
        key="item_select_inbound"
    )
    
    selected_item_id = item_options[selected_item_display]
    
    # 選択された物品の詳細表示
    selected_item = next(item for item in items if item['id'] == selected_item_id)
    
    # DBから最新の在庫数を再取得（キャッシュ対策）
    fresh_item = get_item_by_id(selected_item_id)
    if fresh_item:
        selected_item['quantity'] = fresh_item.get('quantity', 0)
        st.caption(f"🔄 最新DB在庫: {fresh_item.get('quantity', 0)} 個") 
    
    # 在庫数を安全に取得
    current_quantity = selected_item.get('quantity', 0)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("現在在庫", f"{current_quantity} 個")
    with col2:
        st.metric("保管場所", selected_item.get('location') or "未設定")
    with col3:
        st.metric("カテゴリ", selected_item.get('category', '-'))
    
    st.divider()
    
    # 連打防止フラグの確認（成功直後はTrue、次回のrerunでFalseに戻す）
    button_disabled = st.session_state.get("inbound_button_disabled", False)
    if button_disabled:
        st.session_state.inbound_button_disabled = False  # 次回はrerun後に有効化
    
    # フォーム作成（物品選択以外の入力項目）
    with st.form("inbound_form", clear_on_submit=True):
        # 入庫数量入力（正の整数のみ）
        quantity = st.number_input(
            "入庫数量",
            min_value=1,
            max_value=10000,
            value=1,
            step=1,
            help="入庫する数量を入力してください"
        )
        
        # ユーザー情報表示（ログインユーザーから自動取得）
        current_user = get_current_user()
        col1, col2 = st.columns(2)
        
        with col1:
            st.text_input(
                "入庫者名",
                value=current_user.get("display_name", ""),
                disabled=True,
                help="ログインユーザー名が自動で設定されます"
            )
            user_name = current_user.get("display_name", "")
        
        with col2:
            st.text_input(
                "部署名",
                value=current_user.get("department", ""),
                disabled=True,
                help="ログインユーザーの部署が自動で設定されます"
            )
            department = current_user.get("department", "")
        
        # 備考
        note = st.text_area(
            "備考",
            placeholder="入庫理由や仕入先など（任意）",
            height=100
        )
        
        st.divider()
        
        # 送信ボタン
        col1, col2 = st.columns([3, 1])
        with col1:
            st.info("💡 入力内容を確認して「入庫を実行」ボタンを押してください")
        with col2:
            submitted = st.form_submit_button(
                "✅ 入庫を実行",
                type="primary",
                use_container_width=True,
                disabled=button_disabled
            )
        
        if submitted:
            # === バリデーション実行 ===
            ok, validated_qty, error_msg = to_int_safe(quantity, "入庫数量", min_value=1, allow_zero=False)
            if not ok:
                st.error(error_msg)
                return
            
            # 入庫処理実行（ユーザー名はログインユーザーから自動取得済み）
            result = process_inbound(
                item_id=selected_item_id,
                quantity=validated_qty,
                user_name=user_name,
                department=department,
                note=note.strip()
            )
            
            if result["success"]:
                # 成功データをsession_stateに保存
                st.session_state.last_inbound_success = {
                    'item_name': selected_item['item_name'],
                    'quantity': validated_qty,
                    'user_name': user_name,
                    'department': department,
                    'note': note.strip(),
                    'before_quantity': current_quantity,
                    'after_quantity': result['new_quantity']
                }
                # フォーム付近通知用フラグもセット
                st.session_state.inbound_form_success = {
                    'item_name': selected_item['item_name'],
                    'quantity': validated_qty,
                    'after_quantity': result['new_quantity']
                }
                # 連打防止
                st.session_state.inbound_button_disabled = True
                
                # ページをリロードして成功メッセージを表示
                st.rerun()
            else:
                st.error(f"### ❌ 入庫処理に失敗しました")
                st.error(result["message"])
    
    # 短い成功通知（フォーム終了後、詳細カードの直前）
    form_notification = st.empty()
    if "inbound_form_success" in st.session_state and st.session_state.inbound_form_success:
        success_msg = st.session_state.inbound_form_success
        with form_notification.container():
            st.success(f"✅ **入庫が完了しました！** {success_msg['item_name']} x {success_msg['quantity']}個 → 在庫{success_msg['after_quantity']}個")
        # フラグクリア（表示後に削除）
        del st.session_state.inbound_form_success
    
    # 成功内容カード表示（フォームの下、直近履歴の上）
    if "inbound_success_display" in st.session_state:
        success_data = st.session_state.inbound_success_display
        st.divider()
        with st.container(border=True):
            st.subheader("📋 入庫完了内容")
            st.balloons()

            col1, col2 = st.columns(2)
            with col1:
                st.metric("入庫物品", success_data['item_name'])
                st.metric("入庫数量", f"{success_data['quantity']} 個", delta=f"+{success_data['quantity']}")
                st.metric("入庫者", success_data['user_name'])

            with col2:
                st.metric("入庫前在庫", f"{success_data['before_quantity']} 個")
                st.metric("入庫後在庫", f"{success_data['after_quantity']} 個")
                if success_data.get('department'):
                    st.metric("部署", success_data['department'])

            if success_data.get('note'):
                st.info(f"📝 備考: {success_data['note']}")
        
        # フラグをクリア
        del st.session_state.inbound_success_display
        if "inbound_success_shown" in st.session_state:
            del st.session_state.inbound_success_shown
    
    # 直近の入庫履歴を表示（最下部に配置）
    st.divider()
    st.subheader("⏪ 直近の入庫を取り消す")
    st.caption("※ 直近5件を表示")
    
    recent_inbound = get_recent_history_for_undo("IN", limit=5)
    if recent_inbound:
        for record in recent_inbound:
            created_at = parse_db_ts_to_jst(record["created_at"])
            time_diff = datetime.now(ZoneInfo('Asia/Tokyo')) - created_at
            minutes_ago = int(time_diff.total_seconds() / 60)
            
            # 取消可能かチェック（10分以内）
            can_undo, reason = can_undo_history(record['id'], minutes=10)
            
            with st.container(border=True):
                col1, col2 = st.columns([5, 2])
                
                with col1:
                    st.markdown(f"**📦 {record['item_name']}** ({record['item_code']})")
                    st.caption(f"⏱️ {minutes_ago}分前 | 数量: {record['quantity']}個 | 担当: {record['user_name']}")
                
                with col2:
                    if not can_undo:
                        # 取消不可（10分超過または取消済み）
                        st.button(f"🚫 {reason}", key=f"undo_in_{record['id']}", disabled=True, use_container_width=True)
                    else:
                        # 確認ダイアログ付き取消ボタン
                        if f"confirm_undo_in_{record['id']}" not in st.session_state:
                            st.session_state[f"confirm_undo_in_{record['id']}"] = False
                        
                        if not st.session_state[f"confirm_undo_in_{record['id']}"]:
                            if st.button("↩️ 取消", key=f"undo_in_{record['id']}", use_container_width=True):
                                st.session_state[f"confirm_undo_in_{record['id']}"] = True
                                st.rerun()
                        else:
                            st.error("本当に取り消しますか？")
                            col_yes, col_no = st.columns(2)
                            with col_yes:
                                if st.button("✅ はい", key=f"yes_in_{record['id']}", type="primary"):
                                    result = process_undo(record['id'], record['user_name'])
                                    st.session_state[f"confirm_undo_in_{record['id']}"] = False
                                    if result["success"]:
                                        st.session_state.last_undo_inbound_success = result["message"]
                                    else:
                                        st.session_state.last_undo_inbound_error = result["message"]
                                    st.rerun()
                            with col_no:
                                if st.button("❌ いいえ", key=f"no_in_{record['id']}"):
                                    st.session_state[f"confirm_undo_in_{record['id']}"] = False
                                    st.rerun()
    else:
        st.info("📭 入庫履歴がありません")


def show_purchase_order_inbound_tab():
    """発注品入庫タブの内容"""
    st.info("💡 発注済みで到着待ちの物品を入庫処理します。")
    
    # 成功メッセージの表示（前回の処理結果）
    if "receive_success_message" in st.session_state and st.session_state.receive_success_message:
        msg = st.session_state.receive_success_message
        st.success(f"✅ {msg['title']}")
        st.info(f"📦 {msg['item_name']} - {msg['qty']}個を入庫しました")
        st.info(f"📊 新しい在庫数: {msg['new_quantity']}個")
        if msg.get('history_id'):
            st.caption(f"📝 履歴ID: {msg['history_id']} として記録されました")
            
            # デバッグ: 実際にDBに保存されたか確認
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM inventory_history WHERE id = ?", (msg['history_id'],))
                saved_record = cursor.fetchone()
                if saved_record:
                    st.success(f"✅ データベース確認: 履歴ID {msg['history_id']} は正常に保存されています")
                    with st.expander("🔍 保存データの詳細"):
                        st.json(dict(saved_record))
                else:
                    st.error(f"❌ データベースエラー: 履歴ID {msg['history_id']} が見つかりません")
        
        st.balloons()
        # メッセージをクリア
        st.session_state.receive_success_message = None
    
    # 現在のユーザー情報を取得
    current_user = get_current_user()
    user_role = current_user.get("user_role", "GUEST")
    department_name = current_user.get("department")
    
    # デバッグ情報
    st.caption(f"🔍 デバッグ: ユーザー権限={user_role}, 部署={department_name}")
    
    # 発注済み申請を取得（ADMINは全体、それ以外は自部署のみ）
    if user_role == "ADMIN":
        ordered_requests = get_ordered_purchase_requests()
        st.caption(f"🔍 デバッグ: ADMIN として全体検索 → {len(ordered_requests) if ordered_requests else 0}件取得")
    else:
        ordered_requests = get_ordered_purchase_requests(department_name=department_name)
        st.caption(f"🔍 デバッグ: {department_name} で検索 → {len(ordered_requests) if ordered_requests else 0}件取得")
    
    # デバッグ: 比較用に get_purchase_requests でも取得
    comparison_requests = get_purchase_requests(status="ORDERED", department=None if user_role == "ADMIN" else department_name)
    st.caption(f"🔍 比較: get_purchase_requests(ORDERED) → {len(comparison_requests) if comparison_requests else 0}件取得")
    
    if not ordered_requests:
        st.warning("📭 現在、入庫待ちの発注品はありません。")
        # デバッグ: 実際のステータスを確認
        if comparison_requests:
            st.error(f"⚠️ データ不整合: get_purchase_requests では {len(comparison_requests)}件 見つかっています")
            with st.expander("🔍 詳細確認"):
                for req in comparison_requests[:3]:  # 最初の3件のみ表示
                    st.json(req)
        return
    
    # ADMINの場合は全部署の入庫待ちを部署ごとに表示
    if user_role == "ADMIN":
        st.success(f"📦 **全部署で {len(ordered_requests)}件** の発注品が到着待ちです")
        
        # 部署ごとにグループ化
        requests_by_department = defaultdict(list)
        for req in ordered_requests:
            dept = req.get('requested_by_department', '部署未設定')
            requests_by_department[dept].append(req)
        
        # 部署ごとに表示
        for dept_name in sorted(requests_by_department.keys()):
            dept_requests = requests_by_department[dept_name]
            with st.expander(f"🏢 **{dept_name}** - {len(dept_requests)}件の入庫待ち", expanded=True):
                for req in dept_requests:
                    display_purchase_order_card(req, current_user, user_role)
    else:
        st.success(f"📦 **{len(ordered_requests)}件** の発注品が到着待ちです")
        for req in ordered_requests:
            display_purchase_order_card(req, current_user, user_role)


def display_purchase_order_card(req, current_user, user_role):
    """発注品の入庫カード表示（共通化）"""
    with st.container(border=True):
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 2, 2])
            
            with col1:
                st.markdown(f"### 📦 {req['item_name']}")
                st.caption(f"品目コード: {req['item_code']}")
                if req.get('vendor_name'):
                    st.caption(f"業者: {req['vendor_name']}")
            
            with col2:
                st.metric("発注数量", f"{req['requested_qty']} 個")
                if req.get('unit_price'):
                    total = req['requested_qty'] * req['unit_price']
                    st.caption(f"金額: ¥{total:,}")
            
            with col3:
                if req.get('ordered_at'):
                    ordered_date = parse_db_ts_to_jst(req['ordered_at'])
                    days_ago = (datetime.now(ZoneInfo('Asia/Tokyo')) - ordered_date).days
                    st.metric("発注日", f"{days_ago}日前")
            
            # 詳細情報を展開表示
            with st.expander("📋 詳細情報"):
                info_col1, info_col2 = st.columns(2)
                with info_col1:
                    st.write(f"**申請者:** {req.get('requester_name', '不明')}")
                    st.write(f"**部署:** {req.get('requested_by_department', '不明')}")
                    if req.get('priority'):
                        st.write(f"**優先度:** {req['priority']}")
                with info_col2:
                    if req.get('approver_name'):
                        st.write(f"**承認者:** {req['approver_name']}")
                    if req.get('order_channel'):
                        st.write(f"**発注方法:** {req['order_channel']}")
                    if req.get('generated_document_name'):
                        st.write(f"**発注書:** {req['generated_document_name']}")
                
                if req.get('note'):
                    st.info(f"📝 申請メモ: {req['note']}")
            
            # 入庫処理フォーム
            with st.form(f"receive_form_{req['id']}"):
                st.subheader("📥 入庫処理")
                
                form_col1, form_col2 = st.columns(2)
                
                with form_col1:
                    received_qty = st.number_input(
                        "入庫数量",
                        min_value=1,
                        max_value=10000,
                        value=req['requested_qty'],
                        step=1,
                        help="実際に入庫した数量を入力してください（発注数量と異なる場合は修正可）",
                        key=f"qty_{req['id']}"
                    )
                
                with form_col2:
                    st.text_input(
                        "入庫担当者",
                        value=current_user.get("display_name", ""),
                        disabled=True,
                        help="ログインユーザーが自動設定されます",
                        key=f"user_{req['id']}"
                    )
                
                received_note = st.text_area(
                    "入庫メモ（任意）",
                    placeholder="例: 一部破損あり、検品完了、など",
                    height=80,
                    key=f"note_{req['id']}"
                )
                
                col_submit, col_info = st.columns([1, 3])
                with col_submit:
                    submitted = st.form_submit_button(
                        "📦 納品を完了する",
                        type="primary",
                        use_container_width=True
                    )
                with col_info:
                    if req['requested_qty'] != received_qty:
                        st.warning(f"⚠️ 発注数と入庫数が異なります（発注: {req['requested_qty']}個）")
                
                if submitted:
                    # 入庫処理実行
                    result = receive_purchase_order(
                        request_id=req['id'],
                        received_qty=received_qty,
                        received_note=received_note.strip(),
                        user_id=current_user['id']
                    )
                    
                    if result['success']:
                        # セッション状態に成功メッセージを保存
                        st.session_state.receive_success_message = {
                            'title': '納品完了しました！',
                            'item_name': req['item_name'],
                            'qty': received_qty,
                            'new_quantity': result['new_quantity'],
                            'history_id': result.get('history_id')
                        }
                        # ページをリロード
                        st.rerun()
                    else:
                        st.error(f"❌ 納品処理に失敗しました: {result['message']}")
        
        st.divider()
