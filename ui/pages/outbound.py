"""出庫ページ"""

import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

from utils.auth import require_login, is_guest, get_current_user, get_user_role
from utils.validation import to_int_safe, validate_required_text
from utils.date_utils import parse_db_ts_to_jst
from ui.components.refresh_button import show_refresh_button
from repositories.inventory_repo import process_outbound
from repositories.inventory_query import get_all_items_for_outbound, get_categories
from repositories.inventory_repo import get_item_by_id
from repositories.history_repo import get_recent_history_for_undo, can_undo_history, process_undo, process_undo_pending
from repositories.pending_repo import create_pending_transaction, get_my_pending_transactions, cancel_pending_transaction
from repositories.stats_repo import get_top_outbound_items, get_outbound_trend_data


def set_menu(menu_id: str):
    """
    メニューIDを設定して画面遷移（リラン）するヘルパー関数

    【重要】画面遷移は必ずこの関数を使用してください。
    st.session_state.menu_id への直接代入は禁止です。
    """
    st.session_state.menu_id = menu_id
    st.session_state.pending_menu_id = menu_id
    st.session_state.current_page = 1  # ページネーションリセット
    st.rerun()


def show_outbound_page():
    """出庫ページ"""
    st.header("➖ 出庫処理")
    
    # 更新ボタン
    show_refresh_button()
    
    # ページ上部のメッセージ領域（取消成功など）
    message_area = st.empty()
    
    # 取消成功メッセージ表示（ページ上部）
    if "last_undo_outbound_success" in st.session_state and st.session_state.last_undo_outbound_success:
        with message_area.container():
            st.success(st.session_state.last_undo_outbound_success)
        st.session_state.last_undo_outbound_success = None
    
    # 権限チェック（共通関数使用）：ログイン必須
    if not require_login("出庫処理を行うにはログインが必要です"):
        return
    
    # ========== ミニダッシュボード（現場向け消費ペース表示） ==========
    with st.expander("📊 今月の出庫状況（消費ペース）", expanded=False):
        # ロール判定（GUESTは部署フィルタあり）
        current_user = get_current_user()
        user_role = current_user.get("user_role")
        user_dept = current_user.get("department")
        department_filter = user_dept if user_role == "GUEST" else None
        
        # GUEST向けに表示範囲を明示
        if user_role == "GUEST":
            st.info(f"📍 表示範囲: **{user_dept}** のみ")
        
        # ========== 1) 絞り込みUI ==========
        st.subheader("🔍 絞り込み条件")
        
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        
        with filter_col1:
            categories = ["すべて"] + get_categories()
            selected_category = st.selectbox(
                "カテゴリ",
                options=categories,
                key="dashboard_category"
            )
        
        with filter_col2:
            selected_period = st.selectbox(
                "期間",
                options=[3, 6, 12],
                index=1,  # デフォルト6ヶ月
                format_func=lambda x: f"過去{x}ヶ月",
                key="dashboard_period"
            )
        
        with filter_col3:
            keyword_search = st.text_input(
                "キーワード検索",
                placeholder="物品名、品目コード",
                key="dashboard_keyword"
            )
        
        st.divider()
        
        # ========== 2) 今月の出庫量TOP10を取得 ==========
        st.subheader("📈 今月の出庫量 TOP10")
        
        top_items = get_top_outbound_items(
            category=selected_category if selected_category != "すべて" else None,
            keyword=keyword_search,
            department_name=department_filter,
            limit=10
        )
        
        if not top_items:
            st.warning("⚠️ 絞り込み条件に該当する出庫データがありません（今月）")
        else:
            st.caption(f"💡 絞り込み条件で今月の出庫量が多い順にTOP10を表示しています")
            
            # TOP10をテーブル表示（チェックボックス付き）
            top_df = pd.DataFrame(top_items)
            top_df["monthly_out"] = top_df["monthly_out"].fillna(0).astype(int)
            top_df["quantity"] = top_df["quantity"].fillna(0).astype(int)
            top_df["threshold"] = top_df["threshold"].fillna(0).astype(int)
            
            # 表示用DataFrame
            display_top = top_df[["item_name", "item_code", "category", "monthly_out", "quantity", "threshold"]].copy()
            display_top.columns = ["物品名", "品目コード", "カテゴリ", "今月OUT", "現在庫", "発注点"]
            
            st.dataframe(display_top, width="stretch", hide_index=True)
            
            st.divider()
            
            # ========== 3) 物品選択（最大5件） ==========
            st.subheader("🔢 比較する物品を選択（最大5件）")
            
            # チェックボックス形式で選択
            selected_item_ids = []
            
            # 2列レイアウトでチェックボックス表示
            checkbox_cols = st.columns(2)
            for idx, item in enumerate(top_items):
                col_idx = idx % 2
                with checkbox_cols[col_idx]:
                    is_selected = st.checkbox(
                        f"{item['item_name']} ({item['item_code']})",
                        key=f"dashboard_item_{item['item_id']}",
                        disabled=len(selected_item_ids) >= 5 and item['item_id'] not in selected_item_ids
                    )
                    if is_selected:
                        selected_item_ids.append(item['item_id'])
            
            if not selected_item_ids:
                st.info("🔍 物品を選択すると、詳細KPIとグラフが表示されます")
            else:
                st.divider()
                
                # ========== 4) 物品別KPI表示 ==========
                st.subheader("📊 選択物品の詳細")
                
                # 選択した物品のみを抽出
                selected_top = top_df[top_df["item_id"].isin(selected_item_ids)].copy()
                
                # 物品別テーブル
                detail_display = selected_top[["item_name", "monthly_out", "quantity", "threshold"]].copy()
                detail_display.columns = ["物品名", "今月OUT", "現在庫", "発注点"]
                
                st.dataframe(detail_display, width="stretch", hide_index=True)
                
                # 合計値（補助）
                total_monthly_out = selected_top["monthly_out"].sum()
                total_stock = selected_top["quantity"].sum()
                
                summary_col1, summary_col2 = st.columns(2)
                with summary_col1:
                    st.metric("📤 今月OUT（合計）", f"{total_monthly_out:,}")
                with summary_col2:
                    st.metric("📦 現在庫（合計）", f"{total_stock:,}")
                
                st.divider()
                
                # ========== 5) 折れ線グラフ（必須） ==========
                st.subheader("📉 出庫量の推移（月別）")
                
                # グラフデータ取得
                trend_data = get_outbound_trend_data(
                    selected_item_ids,
                    months=selected_period,
                    department_name=department_filter
                )
                
                if trend_data:
                    # DataFrameに変換
                    trend_df = pd.DataFrame(trend_data)
                    
                    # ピボットして折れ線グラフ用に整形（欠け月を0補完）
                    pivot_df = trend_df.pivot_table(
                        index="ym",
                        columns="item_name",
                        values="qty",
                        fill_value=0
                    )
                    
                    # Streamlitの折れ線グラフ
                    st.line_chart(pivot_df, width="stretch")
                    
                    st.caption(f"💡 選択した物品の月別出庫数量（過去{selected_period}ヶ月）。欠けている月は0として表示されます。")
                else:
                    st.info(f"📭 選択した期間（過去{selected_period}ヶ月）に出庫データがありません")
    
    st.divider()
    
    # ========== 以下、既存の出庫フォーム ==========
    
    # GUESTの場合は仮入力モードであることを表示
    if is_guest():
        st.warning("👻 **ゲストモード**: 出庫は「仮入力」となり、管理者の承認後に反映されます")

    # 前回の出庫成功メッセージをセッションから移動して rerun で表示
    if "last_outbound_success" in st.session_state and st.session_state.last_outbound_success:
        st.session_state.outbound_success_display = st.session_state.last_outbound_success.copy()
        st.session_state.last_outbound_success = None
        st.rerun()
    
    if is_guest():
        st.info("💡 在庫を減らす処理です。ゲストユーザーは「仮入力」として記録され、管理者の承認を待ちます。")
    else:
        st.info("💡 在庫を減らす処理です。出庫すると自動的に履歴に記録されます。")
    
    # デバッグ：データ取得タイムスタンプ
    current_time = datetime.now(ZoneInfo('Asia/Tokyo')).strftime("%H:%M:%S")
    st.caption(f"🕒 データ取得時刻: {current_time}")

    # 取消エラーメッセージはその場で表示
    if "last_undo_outbound_error" in st.session_state and st.session_state.last_undo_outbound_error:
        st.error(st.session_state.last_undo_outbound_error)
        st.session_state.last_undo_outbound_error = None
    
    # ゲストユーザーは単品出庫のみ表示
    if is_guest():
        show_single_outbound()
    else:
        # セクション切替（rerun時も保持）
        section = st.radio(
            "出庫モード",
            options=["📦 単品出庫", "⚡ クイック出庫（まとめて出庫）"],
            horizontal=True,
            key="outbound_section",
        )

        if section == "📦 単品出庫":
            show_single_outbound()
        else:
            show_quick_outbound()


def show_single_outbound():
    """単品出庫（従来の処理）"""
    # 検索フォーム
    st.subheader("🔍 物品検索")
    
    col1, col2, col3 = st.columns([3, 2, 1])
    
    with col1:
        search_query_outbound = st.text_input(
            "検索",
            placeholder="品目名、品目コード、業者名などで検索",
            key="search_query_outbound"
        )
    
    with col2:
        categories = ["すべて"] + get_categories()
        category_filter_outbound = st.selectbox(
            "カテゴリ",
            options=categories,
            key="category_filter_outbound"
        )
    
    with col3:
        st.write("")  # スペース調整
        st.write("")
        search_button_outbound = st.button("🔎 検索", key="search_btn_outbound", use_container_width=True)
    
    st.divider()
    
    # 出庫可能な物品を取得（検索条件適用）
    # GUESTユーザーの場合は自部署タグのみ表示
    department_name_filter = None
    if is_guest():
        current_user = get_current_user()
        user_dept = current_user.get("department")
        if user_dept:
            department_name_filter = user_dept
            st.info(f"📋 表示範囲：**{user_dept}** のみ")
    
    items = get_all_items_for_outbound(search_query_outbound, category_filter_outbound, department_name=department_name_filter)
    
    if not items:
        st.warning("⚠️ 検索条件に該当する在庫がありません")
        return
    
    st.info(f"📊 {len(items)} 件の物品が見つかりました")
    
    # 【重要】物品選択をフォームの外に出す（リアルタイム反映のため）
    st.subheader("📝 出庫情報入力")
    
    # 物品選択（フォーム外）
    item_options = {
        f"{item['item_name']} (在庫: {item.get('quantity', 0)}個) [{item.get('category', '-')}]": item['id']
        for item in items
    }
    
    selected_item_display = st.selectbox(
        "物品を選択",
        options=list(item_options.keys()),
        help="在庫がある物品のみ表示されています",
        key="item_select"
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

    # 出庫ページから発注申請への導線ボタン（USER/ADMINのみ）
    if not is_guest():
        btn_col1, btn_col2 = st.columns([1, 5])
        with btn_col1:
            if st.button("📝 発注申請", help="この物品で発注申請フォームを開きます"):
                # プレフィル用セッションにセットして申請ページへ遷移
                st.session_state.pr_prefill_item_id = selected_item_id
                # 推奨数量は在庫差分（閾値超過分）または1をセット
                try:
                    thresh = int(fresh_item.get('threshold', 0)) if fresh_item else 0
                    stock = int(current_quantity or 0)
                    rec = max(1, thresh - stock) if thresh and stock < thresh else 1
                except Exception:
                    rec = 1
                st.session_state.pr_prefill_qty = rec
                set_menu("purchase_request")
    
    st.divider()
    
    # 連打防止フラグの確認（成功直後はTrue、次回のrerunでFalseに戻す）
    button_disabled = st.session_state.get("outbound_button_disabled", False)
    if button_disabled:
        st.session_state.outbound_button_disabled = False  # 次回はrerun後に有効化
    
    # フォーム作成（物品選択以外の入力項目）
    with st.form("outbound_form", clear_on_submit=True):
        # 出庫数量入力
        quantity = st.number_input(
            "出庫数量",
            min_value=1,
            max_value=max(1, current_quantity),
            value=1,
            step=1,
            help=f"最大 {current_quantity} 個まで出庫できます"
        )
        
        # ユーザー情報（GUESTは手入力、それ以外は自動）
        current_user = get_current_user()
        col1, col2 = st.columns(2)
        
        with col1:
            if is_guest():
                # GUEST: 実行者名は手入力必須
                actor_name_input = st.text_input(
                    "出庫者名 *（必須）",
                    value="",
                    placeholder="例: 山田太郎",
                    help="複数人で共有IDを使用するため、実際の出庫者名を入力してください"
                )
                user_name = actor_name_input
            else:
                # USER/ADMIN: 自動入力
                st.text_input(
                    "出庫者名",
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
            placeholder="出庫理由や用途など（任意）",
            height=100
        )
        
        st.divider()
        
        # 送信ボタン（GUESTは「仮入力」表記）
        col1, col2 = st.columns([3, 1])
        with col1:
            if is_guest():
                st.info("💡 入力内容を確認して「出庫を申請」ボタンを押してください（承認待ちになります）")
            else:
                st.info("💡 入力内容を確認して「出庫を実行」ボタンを押してください")
        with col2:
            button_label = "📝 出庫を申請" if is_guest() else "✅ 出庫を実行"
            submitted = st.form_submit_button(
                button_label,
                type="primary",
                use_container_width=True,
                disabled=button_disabled
            )
        
        if submitted:
            # === バリデーション実行 ===
            ok, validated_qty, error_msg = to_int_safe(quantity, "出庫数量", min_value=1, allow_zero=False)
            if not ok:
                st.error(error_msg)
                return
            
            # 出庫者名のバリデーション（GUESTの場合）
            if is_guest():
                ok_name, validated_name, error_msg_name = validate_required_text(user_name, "出庫者名")
                if not ok_name:
                    st.error(error_msg_name)
                    st.info("複数人で共有IDを使用するため、実際の出庫者名が必須です。")
                    return
                user_name = validated_name
            
            # GUESTの場合は仮出庫処理、それ以外は通常出庫処理
            if is_guest():
                # pending_transactionsテーブルに仮登録
                result = create_pending_transaction(
                    change_type="OUT",
                    item_id=selected_item_id,
                    quantity=validated_qty,
                    actor_name=user_name,
                    note=note.strip(),
                    guest_user_id=current_user.get("id"),
                    department_id=current_user.get("department_id")
                )
                
                if result["success"]:
                    st.session_state.last_outbound_success = {
                        'item_name': selected_item['item_name'],
                        'quantity': validated_qty,
                        'user_name': user_name,
                        'department': department,
                        'note': note.strip(),
                        'before_quantity': current_quantity,
                        'after_quantity': current_quantity,  # 仮入力なので変更なし
                        'is_low_stock': False,
                        'is_pending': True  # 仮入力フラグ
                    }
                    # フォーム付近通知用フラグもセット
                    st.session_state.outbound_form_success = {
                        'item_name': selected_item['item_name'],
                        'quantity': validated_qty,
                        'after_quantity': current_quantity,
                        'is_pending': True
                    }
                    # 連打防止
                    st.session_state.outbound_button_disabled = True
                    st.rerun()
                else:
                    st.error(f"### ❌ 出庫申請に失敗しました")
                    st.error(result["message"])
            else:
                # 通常の出庫処理
                result = process_outbound(
                    item_id=selected_item_id,
                    quantity=validated_qty,
                    user_name=user_name,
                    department=department,
                    note=note.strip()
                )
                
                if result["success"]:
                    st.session_state.last_outbound_success = {
                        'item_name': selected_item['item_name'],
                        'quantity': validated_qty,
                        'user_name': user_name,
                        'department': department,
                        'note': note.strip(),
                        'before_quantity': current_quantity,
                        'after_quantity': result['remaining_quantity'],
                        'is_low_stock': result['remaining_quantity'] <= fresh_item.get('threshold', 10) if fresh_item else False,
                        'is_pending': False
                    }
                    # フォーム付近通知用フラグもセット
                    st.session_state.outbound_form_success = {
                        'item_name': selected_item['item_name'],
                        'quantity': validated_qty,
                        'after_quantity': result['remaining_quantity'],
                        'is_pending': False
                    }
                    # 連打防止
                    st.session_state.outbound_button_disabled = True
                    st.rerun()
                else:
                    st.error(f"### ❌ 出庫処理に失敗しました")
                    st.error(result["message"])
    
    # 短い成功通知（フォーム終了後、詳細カードの直前）
    form_notification = st.empty()
    if "outbound_form_success" in st.session_state and st.session_state.outbound_form_success:
        success_msg = st.session_state.outbound_form_success
        with form_notification.container():
            if success_msg.get('is_pending'):
                st.info(f"✅ **出庫申請が完了しました！** {success_msg['item_name']} x {success_msg['quantity']}個（承認待ち）")
            else:
                st.success(f"✅ **出庫が完了しました！** {success_msg['item_name']} x {success_msg['quantity']}個 → 残り{success_msg['after_quantity']}個")
        # フラグクリア（表示後に削除）
        del st.session_state.outbound_form_success
    
    # 成功内容カード表示（フォームの下、直近履歴の上）
    if "outbound_success_display" in st.session_state:
        success_data = st.session_state.outbound_success_display
        st.divider()
        with st.container(border=True):
            if success_data.get('is_pending'):
                st.subheader("📋 出庫申請内容")
            else:
                st.subheader("📋 出庫完了内容")
                st.balloons()

            col1, col2 = st.columns(2)
            with col1:
                st.metric("出庫物品", success_data['item_name'])
                st.metric("出庫数量", f"{success_data['quantity']} 個", delta=f"-{success_data['quantity']}")
                st.metric("出庫者", success_data['user_name'])

            with col2:
                if success_data.get('is_pending'):
                    st.metric("状態", "⏳ 承認待ち")
                    st.metric("現在在庫", f"{success_data['before_quantity']} 個")
                else:
                    st.metric("出庫前在庫", f"{success_data['before_quantity']} 個")
                    st.metric("出庫後在庫", f"{success_data['after_quantity']} 個")
                if success_data.get('department'):
                    st.metric("部署", success_data['department'])

            if success_data.get('note'):
                st.info(f"📝 備考: {success_data['note']}")

            if not success_data.get('is_pending') and success_data.get('is_low_stock'):
                st.warning(f"⚠️ 在庫が閾値以下になりました！発注をご検討ください。")
        
        # フラグをクリア
        del st.session_state.outbound_success_display
        if "outbound_success_shown" in st.session_state:
            del st.session_state.outbound_success_shown
    
    # 直近の出庫履歴を表示（最下部に配置）
    st.divider()
    st.subheader("⏪ 直近の出庫・申請")
    
    # 取消処理結果メッセージを表示（このセクションの直下）
    if "cancel_success_message" in st.session_state and st.session_state.cancel_success_message:
        st.success(st.session_state.cancel_success_message)
        st.session_state.cancel_success_message = None
    
    if "cancel_error_message" in st.session_state and st.session_state.cancel_error_message:
        st.error(st.session_state.cancel_error_message)
        st.session_state.cancel_error_message = None
    
    # === 承認待ち申請（PENDING）を表示 ===
    current_user = get_current_user()
    user_role = get_user_role()
    my_pending = get_my_pending_transactions(
        user_id=current_user.get("id"),
        department_id=current_user.get("department_id"),
        change_type="OUT",
        user_role=user_role
    )
    
    if my_pending:
        st.markdown("#### 📝 承認待ち申請（PENDING）")
        for pending in my_pending:
            created_at = parse_db_ts_to_jst(pending["created_at"])
            time_diff = datetime.now(ZoneInfo('Asia/Tokyo')) - created_at
            minutes_ago = int(time_diff.total_seconds() / 60)
            
            with st.container(border=True):
                col1, col2 = st.columns([5, 2])
                
                with col1:
                    st.markdown(f"**📦 {pending['item_name']}** ({pending['item_code']}) 🔶 **承認申請中**")
                    st.caption(f"⏱️ {minutes_ago}分前 | 数量: {pending['quantity']}個 | 申請者: {pending['actor_name']}")
                    if pending.get('note'):
                        st.caption(f"📝 {pending['note']}")
                
                with col2:
                    # 取り下げボタン（GUESTの場合のみ、guest_user_id一致の場合）
                    if is_guest() and pending['guest_user_id'] == current_user.get('id'):
                        confirm_key = f"confirm_cancel_pending_{pending['id']}"
                        if confirm_key not in st.session_state:
                            st.session_state[confirm_key] = False
                        
                        if not st.session_state[confirm_key]:
                            if st.button("🗑️ 取り下げ", key=f"cancel_pending_{pending['id']}", use_container_width=True):
                                st.session_state[confirm_key] = True
                                st.rerun()
                        else:
                            st.caption("⬇️ 下に入力欄")
                    else:
                        st.info("承認待ち")
                
                # 取り下げ確認フォーム（カラムの外に配置して見やすく）
                if is_guest() and pending['guest_user_id'] == current_user.get('id'):
                    confirm_key = f"confirm_cancel_pending_{pending['id']}"
                    if confirm_key in st.session_state and st.session_state[confirm_key]:
                        actor_input_key = f"actor_confirm_{pending['id']}"
                        st.warning("⚠️ 取り下げるには、申請時に入力した名前を再入力してください")
                        actor_confirm = st.text_input("申請者名（本人確認用）", key=actor_input_key, placeholder="例: 山田太郎")
                        col_yes, col_no = st.columns(2)
                        with col_yes:
                            if st.button("✅ 取り下げ確定", key=f"yes_cancel_{pending['id']}", type="primary", use_container_width=True):
                                if not actor_confirm.strip():
                                    st.session_state.cancel_error_message = "❌ 名前を入力してください"
                                    st.rerun()
                                elif actor_confirm.strip() != pending['actor_name']:
                                    st.session_state.cancel_error_message = "❌ 申請者名が一致しません。申請者本人でなければ取消処理はできません。"
                                    st.session_state[confirm_key] = False
                                    st.rerun()
                                else:
                                    result = cancel_pending_transaction(pending['id'], current_user['id'], actor_confirm.strip())
                                    st.session_state[confirm_key] = False
                                    if result["success"]:
                                        st.session_state.cancel_success_message = f"✅ 申請を取り下げました: {pending['item_name']} {pending['quantity']}個"
                                    else:
                                        st.session_state.cancel_error_message = result["message"]
                                    st.rerun()
                        with col_no:
                            if st.button("❌ キャンセル", key=f"no_cancel_{pending['id']}", use_container_width=True):
                                st.session_state[confirm_key] = False
                                st.rerun()
    
    # === 確定済み履歴（直近5件）===
    st.markdown("#### ✅ 確定済み履歴（直近5件）")
    st.caption("※ 10分以内なら取消可能")
    
    recent_outbound = get_recent_history_for_undo("OUT", limit=5)
    if recent_outbound:
        for record in recent_outbound:
            created_at = parse_db_ts_to_jst(record["created_at"])
            time_diff = datetime.now(ZoneInfo('Asia/Tokyo')) - created_at
            minutes_ago = int(time_diff.total_seconds() / 60)
            
            # 取消可能かチェック（10分以内）
            can_undo_flag, reason = can_undo_history(record['id'], minutes=10)
            
            with st.container(border=True):
                col1, col2 = st.columns([5, 2])
                
                with col1:
                    st.markdown(f"**📦 {record['item_name']}** ({record['item_code']})")
                    st.caption(f"⏱️ {minutes_ago}分前 | 数量: {record['quantity']}個 | 担当: {record['user_name']}")
                
                with col2:
                    if not can_undo_flag:
                        # 取消不可（10分超過または取消済み）
                        st.button(f"🚫 {reason}", key=f"undo_out_{record['id']}", disabled=True, use_container_width=True)
                    else:
                        # 確認ダイアログ付き取消ボタン
                        if f"confirm_undo_out_{record['id']}" not in st.session_state:
                            st.session_state[f"confirm_undo_out_{record['id']}"] = False
                        
                        # GUESTは「申請」、それ以外は「取消」
                        button_label = "📝 取消申請" if is_guest() else "↩️ 取消"
                        confirm_msg = "取消を申請しますか？" if is_guest() else "本当に取り消しますか？"
                        
                        if not st.session_state[f"confirm_undo_out_{record['id']}"]:
                            if st.button(button_label, key=f"undo_out_{record['id']}", use_container_width=True):
                                st.session_state[f"confirm_undo_out_{record['id']}"] = True
                                st.rerun()
                        else:
                            st.error(confirm_msg)
                            col_yes, col_no = st.columns(2)
                            with col_yes:
                                if st.button("✅ はい", key=f"yes_out_{record['id']}", type="primary"):
                                    # GUESTは申請、それ以外は即時取消
                                    if is_guest():
                                        result = process_undo_pending(
                                            record['id'], 
                                            current_user.get("display_name", ""),
                                            current_user.get("department", "")
                                        )
                                    else:
                                        result = process_undo(record['id'], record['user_name'])
                                    
                                    st.session_state[f"confirm_undo_out_{record['id']}"] = False
                                    if result["success"]:
                                        st.session_state.last_undo_outbound_success = result["message"]
                                    else:
                                        st.session_state.last_undo_outbound_error = result["message"]
                                    st.rerun()
                            with col_no:
                                if st.button("❌ いいえ", key=f"no_out_{record['id']}"):
                                    st.session_state[f"confirm_undo_out_{record['id']}"] = False
                                    st.rerun()
    else:
        st.info("📭 確定済みの出庫履歴がありません")


def show_quick_outbound():
    """クイック出庫（まとめて出庫）- st.data_editorで表形式"""
    st.subheader("⚡ クイック出庫")
    st.info("💡 カテゴリを選択し、複数の物品を一度に出庫できます。")
    
    # カテゴリ選択
    categories = get_categories()
    if not categories:
        st.warning("⚠️ カテゴリが登録されていません")
        return
    
    selected_category = st.selectbox(
        "カテゴリを選択",
        options=categories,
        key="quick_outbound_category"
    )
    
    # 選択カテゴリの物品を取得
    items = get_all_items_for_outbound("", selected_category)
    
    if not items:
        st.warning(f"⚠️ 「{selected_category}」カテゴリに在庫がある物品がありません")
        return
    
    st.caption(f"📊 {len(items)} 件の物品")
    
    # まとめて出庫の成功メッセージ
    if "quick_outbound_success" in st.session_state and st.session_state.quick_outbound_success:
        success_count = st.session_state.quick_outbound_success
        st.success(f"✅ **{success_count} 件の出庫が完了しました！**")
        del st.session_state.quick_outbound_success
    
    # 現在のユーザー情報
    current_user = get_current_user()
    user_name = current_user.get("display_name", "")
    department = current_user.get("department", "")
    
    # GUEST用の出庫者名入力
    if is_guest():
        st.warning("👻 **ゲストモード**: 出庫者名を入力してください（必須）")
        actor_name_input = st.text_input(
            "出庫者名 *（必須）",
            value="",
            placeholder="例: 山田太郎",
            help="複数人で共有IDを使用するため、実際の出庫者名を入力してください",
            key="quick_outbound_actor_name"
        )
    
    # DataFrameに変換
    df_data = []
    for item in items:
        df_data.append({
            "id": item['id'],
            "品目名": item['item_name'],
            "在庫": item.get('quantity', 0),
            "保管場所": item.get('location') or "-",
            "業者名": item.get('vendor_name') or "-",
            "出庫数量": 0
        })
    
    df = pd.DataFrame(df_data)
    
    st.caption("💡 表の「出庫数量」列を編集してください（在庫数上限）")
    
    # st.data_editorで編集可能な表を表示（列幅は自動調整でレスポンシブ対応）
    # 列順：品目名→業者名→在庫→出庫数量（保管場所は非表示）
    edited_df = st.data_editor(
        df,
        column_config={
            "id": None,  # 非表示
            "品目名": st.column_config.TextColumn(
                "品目名",
                disabled=True,
                help="物品名"
            ),
            "業者名": st.column_config.TextColumn(
                "業者名",
                disabled=True,
                help="業者名"
            ),
            "在庫": st.column_config.NumberColumn(
                "在庫",
                disabled=True,
                format="%d",
                help="現在の在庫数"
            ),
            "出庫数量": st.column_config.NumberColumn(
                "出庫数量",
                min_value=0,
                max_value=None,  # 各行で在庫数上限は後でチェック
                step=1,
                format="%d",
                required=True,
                help="出庫する数量を入力"
            ),
            "保管場所": None  # 非表示
        },
        column_order=["品目名", "業者名", "在庫", "出庫数量"],
        hide_index=True,
        use_container_width=True,  # 画面幅に合わせてレスポンシブ対応
        num_rows="fixed",
        key="quick_outbound_editor"
    )
    
    # 備考と送信ボタン
    note = st.text_area(
        "備考（全体共通）",
        placeholder="出庫理由や用途など（任意）",
        height=60,
        key="quick_outbound_note"
    )
    
    # 送信ボタン
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption("💡 出庫数量が1以上の物品のみが処理されます")
    with col2:
        submitted = st.button(
            "✅ まとめて出庫",
            type="primary",
            use_container_width=True,
            key="quick_outbound_submit"
        )
    
    if submitted:
        # === GUEST時の名前バリデーション ===
        if is_guest():
            ok_name, validated_name, error_msg_name = validate_required_text(actor_name_input, "出庫者名")
            if not ok_name:
                st.error(error_msg_name)
                st.info("複数人で共有IDを使用するため、実際の出庫者名が必須です。")
                return
            user_name = validated_name
        
        # 編集後のDataFrameから出庫数量が1以上の行を抽出
        outbound_rows = edited_df[edited_df['出庫数量'] > 0]
        
        if outbound_rows.empty:
            st.warning("⚠️ 出庫数量が1以上の物品を選択してください")
        else:
            # === バリデーションエラーを収集 ===
            validation_errors = []
            for idx, row in outbound_rows.iterrows():
                # 数量のバリデーション
                ok, validated_qty, error_msg = to_int_safe(row['出庫数量'], f"{row['品目名']}の出庫数量", min_value=1, allow_zero=False)
                if not ok:
                    validation_errors.append(f"❌ {row['品目名']}: {error_msg}")
                elif validated_qty > row['在庫']:
                    validation_errors.append(f"❌ {row['品目名']}: 出庫数量({validated_qty})が在庫数({row['在庫']})を超えています")
            
            if validation_errors:
                st.error("### ⚠️ 入力エラー")
                for err in validation_errors:
                    st.error(err)
            else:
                success_count = 0
                error_messages = []
                
                # 各物品を出庫処理
                for idx, row in outbound_rows.iterrows():
                    item_id = int(row['id'])
                    qty = int(row['出庫数量'])
                    
                    if is_guest():
                        # GUEST: 仮入力
                        result = create_pending_transaction(
                            change_type="OUT",
                            item_id=item_id,
                            quantity=qty,
                            actor_name=user_name,
                            note=note,
                            guest_user_id=current_user.get("id"),
                            department_id=current_user.get("department_id")
                        )
                    else:
                        # 通常出庫
                        result = process_outbound(
                            item_id=item_id,
                            quantity=qty,
                            user_name=user_name,
                            department=department,
                            note=note
                        )
                    
                    if result["success"]:
                        success_count += 1
                    else:
                        error_messages.append(f"❌ {row['品目名']}: {result['message']}")
                
                # 結果を表示
                if success_count > 0:
                    st.session_state.quick_outbound_success = success_count
                
                if error_messages:
                    st.error("### ⚠️ 一部の出庫処理に失敗しました")
                    for msg in error_messages:
                        st.error(msg)
                
                if success_count > 0:
                    st.rerun()
