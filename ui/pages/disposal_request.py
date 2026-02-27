"""廃棄申請ページ"""

import hashlib
import subprocess

import pandas as pd
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from db import get_db_connection
from repositories.disposal_repo import (
    create_disposal_request,
    get_disposal_requests,
)
from utils.auth import (
    get_current_user,
    is_admin,
    is_guest,
    is_logged_in,
)
from ui.components.refresh_button import show_refresh_button


def set_menu(menu_id: str):
    st.session_state.menu_id = menu_id
    st.session_state.pending_menu_id = menu_id
    st.session_state.current_page = 1
    st.rerun()


def show_disposal_request_page():
    """廃棄申請画面（USER/ADMIN）"""
    st.header("🗑️ 廃棄申請")

    # 更新ボタン
    show_refresh_button()

    # 権限チェック（GUESTはアクセス不可）
    if not is_logged_in():
        st.warning("⚠️ 廃棄申請にはログインが必要です")
        return

    if is_guest():
        st.warning("⚠️ ゲストユーザーは廃棄申請を行うことができません。")
        st.info("📍 ゲストユーザーは出庫申請のみ可能です。廃棄申請がUSERまたはADMINに依頼してください。")
        return

    current_user = get_current_user()
    user_id = current_user.get("id")

    # タブ: 新規申請 / 申請履歴
    tab1, tab2 = st.tabs(["📝 新規申請", "📋 申請履歴"])

    with tab1:
        st.subheader("📝 新規廃棄申請")
        st.caption("期限切れや破損した薬品・造影剤などを廃棄申請します")

        # 薬品カテゴリの物品を取得（部署フィルタリング適用）
        user_dept = current_user.get("department")

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()

                # ADMINは全物品、USER/GUESTは自部署のみ
                # カテゴリ条件を緩和：「薬品」「医薬品」「造影剤」を含むものを対象
                if is_admin():
                    cursor.execute("""
                        SELECT i.id, i.item_name, i.item_code, i.expiry_date, inv.quantity, i.department_tags, i.category
                        FROM items i
                        JOIN inventory inv ON i.id = inv.item_id
                        WHERE (i.category LIKE '%薬品%' OR i.category LIKE '%造影剤%')
                          AND i.is_active = 1
                          AND i.is_asset = 0
                          AND inv.quantity > 0
                        ORDER BY i.item_name
                    """)
                else:
                    cursor.execute("""
                        SELECT i.id, i.item_name, i.item_code, i.expiry_date, inv.quantity, i.department_tags, i.category
                        FROM items i
                        JOIN inventory inv ON i.id = inv.item_id
                        WHERE (i.category LIKE '%薬品%' OR i.category LIKE '%造影剤%')
                          AND i.is_active = 1
                          AND i.is_asset = 0
                          AND inv.quantity > 0
                          AND i.department_tags LIKE ?
                        ORDER BY i.item_name
                    """, (f'%{user_dept}%',))

                medicine_items = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            st.error(f"❌ 物品取得エラー: {e}")
            return

        if not is_admin() and user_dept:
            st.info(f"📍 表示対象: {user_dept} の薬品・造影剤のみ")

        st.caption(f"🔍 検索結果: {len(medicine_items)}件の物品が見つかりました")

        if not medicine_items:
            st.warning("⚠️ 廃棄可能な物品がありません")
            st.info("💡 以下を確認してください：")
            st.markdown("""
            - カテゴリが「薬品」「医薬品」「造影剤」のいずれかの物品が登録されているか
            - 在庫数が0より大きいか
            - 物品が有効化されているか
            - 自部署タグが設定されているか（USER権限の場合）
            """)

            # デモデータの再投入を提案
            with st.expander("🔧 デモデータを再投入する", expanded=False):
                st.caption("デモデータを再投入すると、薬品・造影剤のサンプルデータが登録されます")
                if st.button("📥 デモデータ再投入", key="reload_demo"):
                    try:
                        result = subprocess.run(
                            ["python", "init_production_demo.py"],
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        if result.returncode == 0:
                            st.success("✅ デモデータの投入が完了しました")
                            st.rerun()
                        else:
                            st.error(f"❌ エラー: {result.stderr}")
                    except Exception as e:
                        st.error(f"❌ エラー: {e}")
            return

        # アラート画面から事前選択された物品情報を取得
        preselect_item_id = st.session_state.get("prefill_disposal_item_id")
        preselect_quantity = st.session_state.get("prefill_disposal_quantity", 1)
        preselect_reason = st.session_state.get("prefill_disposal_reason", "")

        # デバッグ情報を表示
        with st.expander("🔧 デバッグ情報", expanded=False):
            st.write(f"- 事前選択ID: {preselect_item_id}")
            st.write(f"- ユーザー部署: {user_dept}")
            st.write(f"- 権限: {'ADMIN' if is_admin() else 'USER'}")
            st.write(f"- 物品件数: {len(medicine_items)}")
            if medicine_items:
                st.write(f"- 物品例: {medicine_items[0]['item_name']} (ID: {medicine_items[0]['id']})")

        # アラートから来た場合は目立つ通知を表示
        if preselect_item_id:
            # 物品名を取得
            preselect_item = next((item for item in medicine_items if item['id'] == preselect_item_id), None)
            if preselect_item:
                st.info(f"📌 **アラートから選択:** {preselect_item['item_name']} （{preselect_item['item_code']}）")
            else:
                st.warning(f"⚠️ 選択された物品が見つかりません。在庫がない、または無効化されている可能性があります。")
                # 事前選択情報をクリア
                if "prefill_disposal_item_id" in st.session_state:
                    del st.session_state.prefill_disposal_item_id
                if "prefill_disposal_quantity" in st.session_state:
                    del st.session_state.prefill_disposal_quantity
                if "prefill_disposal_reason" in st.session_state:
                    del st.session_state.prefill_disposal_reason
                preselect_item_id = None

        default_index = 0
        if preselect_item_id:
            for i, item in enumerate(medicine_items):
                if item['id'] == preselect_item_id:
                    default_index = i
                    break

        # 申請成功メッセージの表示
        if "last_disposal_success" in st.session_state:
            st.success("✅ 申請しました！管理者の承認をお待ちください")
            st.info("💡 別の物品を申請する場合は、下記のフォームから選択してください")
            # 一度表示したらクリア
            del st.session_state.last_disposal_success
            # 事前選択情報もクリア（二重申請防止）
            if "prefill_disposal_item_id" in st.session_state:
                del st.session_state.prefill_disposal_item_id
            if "prefill_disposal_quantity" in st.session_state:
                del st.session_state.prefill_disposal_quantity
            if "prefill_disposal_reason" in st.session_state:
                del st.session_state.prefill_disposal_reason

        # フォームで入力を包む
        with st.form(key="disposal_request_form", clear_on_submit=False):
            # 物品選択
            item_options = [
                f"{item['item_name']} ({item['item_code']}) - 在庫: {item['quantity']} - 期限: {item.get('expiry_date') or 'なし'}"
                for item in medicine_items
            ]

            selected_idx = st.selectbox(
                "廃棄する薬品を選択",
                range(len(item_options)),
                format_func=lambda i: item_options[i],
                index=default_index
            )

            selected_item = medicine_items[selected_idx]

            # 事前選択された数量を初期値として使用（最大在庫数を超えないように）
            initial_quantity = min(preselect_quantity, selected_item['quantity']) if preselect_quantity else 1

            col1, col2 = st.columns(2)
            with col1:
                quantity = st.number_input(
                    "廃棄数量",
                    min_value=1,
                    max_value=selected_item['quantity'],
                    value=initial_quantity
                )

            with col2:
                st.metric("現在庫", selected_item['quantity'])

            # 廃棄理由（事前選択されている場合は初期値を設定）
            reason_default = preselect_reason if preselect_reason else ""
            reason = st.text_area(
                "廃棄理由",
                value=reason_default,
                placeholder="例: 期限切れのため、破損のため、汚染のため"
            )

            submitted = st.form_submit_button("📤 廃棄申請を提出", type="primary")

        # フォーム外で処理（エラーメッセージが表示されるように）
        if submitted:
            # === バリデーション実行 ===
            if len(reason.strip()) < 5:
                st.error("❌ 廃棄理由を5文字以上で入力してください")
            else:
                # 重複申請チェック
                request_hash = hashlib.md5(
                    f"{selected_item['id']}_{quantity}_{reason.strip()}".encode()
                ).hexdigest()

                last_request_hash = st.session_state.get("last_disposal_request_hash")

                if last_request_hash == request_hash:
                    st.warning("⚠️ 同じ内容の申請が既に提出されています。内容を変更してください。")
                else:
                    try:
                        result = create_disposal_request(
                            item_id=selected_item['id'],
                            quantity=int(quantity),
                            reason=reason.strip(),
                            requester_id=user_id
                        )

                        if result['success']:
                            # 申請成功を記録
                            st.session_state.last_disposal_request_hash = request_hash
                            st.session_state.last_disposal_success = True
                            st.rerun()
                        else:
                            st.error(f"❌ 申請失敗: {result['message']}")
                    except Exception as e:
                        st.error(f"❌ エラーが発生しました: {e}")

    with tab2:
        st.subheader("📋 申請履歴")

        # 自分の申請を取得
        requests = get_disposal_requests(requester_id=user_id)

        if not requests:
            st.info("申請履歴がありません")
        else:
            df = pd.DataFrame(requests)

            # ステータス表示を整形
            status_map = {
                'PENDING': '⏳ 承認待ち',
                'APPROVED': '✅ 承認済み',
                'REJECTED': '❌ 却下'
            }
            df['status_display'] = df['status'].map(status_map)

            display_df = df[[
                'item_name', 'quantity', 'reason', 'status_display',
                'created_at', 'approver_name', 'reject_reason'
            ]].copy()

            display_df.columns = [
                '物品名', '数量', '廃棄理由', 'ステータス',
                '申請日時', '承認者', '却下理由'
            ]

            st.dataframe(
                display_df,
                use_container_width=True,
                height=400
            )
