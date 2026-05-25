"""廃棄承認ページ"""

import pandas as pd
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from repositories.disposal_repo import (
    get_disposal_requests,
    approve_disposal_request,
    reject_disposal_request,
)
from utils.auth import (
    get_current_user,
    require_role,
)
from ui.components.refresh_button import show_refresh_button


def set_menu(menu_id: str):
    st.session_state.menu_id = menu_id
    st.session_state.pending_menu_id = menu_id
    st.session_state.current_page = 1
    st.rerun()


def show_disposal_approval_page():
    """廃棄承認画面（ADMIN専用）"""
    st.header("✅ 廃棄承認管理")

    # 更新ボタン
    show_refresh_button()

    # 権限チェック（共通関数使用）：ADMINのみ
    if not require_role("ADMIN", "廃棄承認は管理者のみ使用できます"):
        return

    current_user = get_current_user()
    approver_id = current_user.get("id")

    # セクション切替（rerun時も保持）
    section = st.radio(
        "表示セクション",
        options=["⏳ 承認待ち", "📋 処理済み"],
        horizontal=True,
        key="disposal_approval_section",
    )

    if section == "⏳ 承認待ち":
        st.subheader("⏳ 承認待ち廃棄申請")

        pending_requests = get_disposal_requests(status='PENDING')

        if not pending_requests:
            st.success("✅ 承認待ちの廃棄申請はありません")
        else:
            st.warning(f"⚠️ {len(pending_requests)}件の廃棄申請が承認待ちです")

            for req in pending_requests:
                with st.expander(
                    f"【{req['item_name']}】 {req['quantity']}個 - 申請者: {req['requester_name']} ({req['created_at']})",
                    expanded=True
                ):
                    col1, col2 = st.columns([2, 1])

                    with col1:
                        st.write(f"**物品コード:** {req['item_code']}")
                        st.write(f"**カテゴリ:** {req['category']}")
                        st.write(f"**廃棄数量:** {req['quantity']}個")
                        st.write(f"**廃棄理由:**")
                        st.info(req['reason'])
                        st.write(f"**申請者:** {req['requester_name']}")
                        st.write(f"**申請日時:** {req['created_at']}")

                    with col2:
                        st.write("### 承認/却下")

                        # 処理中フラグで二重送信防止
                        processing_key = f"processing_{req['id']}"
                        is_processing = st.session_state.get(processing_key, False)

                        if st.button(
                            "✅ 承認",
                            key=f"approve_{req['id']}",
                            type="primary",
                            disabled=is_processing
                        ):
                            st.session_state[processing_key] = True
                            result = approve_disposal_request(req['id'], approver_id)
                            if result['success']:
                                st.success(result['message'])
                                if processing_key in st.session_state:
                                    del st.session_state[processing_key]
                                st.rerun()
                            else:
                                st.error(result['message'])
                                if processing_key in st.session_state:
                                    del st.session_state[processing_key]

                        if st.button(
                            "❌ 却下",
                            key=f"reject_btn_{req['id']}",
                            disabled=is_processing
                        ):
                            st.session_state[f"show_reject_{req['id']}"] = True
                            st.rerun()

                        # 却下理由入力フォーム
                        if st.session_state.get(f"show_reject_{req['id']}", False):
                            reject_reason = st.text_area(
                                "却下理由",
                                placeholder="却下する理由を入力してください",
                                key=f"reject_reason_{req['id']}"
                            )

                            col_a, col_b = st.columns(2)
                            with col_a:
                                # 処理中フラグで二重送信防止
                                reject_processing_key = f"reject_processing_{req['id']}"
                                is_reject_processing = st.session_state.get(reject_processing_key, False)

                                if st.button(
                                    "確定",
                                    key=f"reject_confirm_{req['id']}",
                                    disabled=is_reject_processing
                                ):
                                    if not reject_reason or len(reject_reason.strip()) < 5:
                                        st.error("却下理由を5文字以上で入力してください")
                                    else:
                                        st.session_state[reject_processing_key] = True
                                        result = reject_disposal_request(
                                            req['id'],
                                            approver_id,
                                            reject_reason.strip()
                                        )
                                        if result['success']:
                                            st.success(result['message'])
                                            if f"show_reject_{req['id']}" in st.session_state:
                                                del st.session_state[f"show_reject_{req['id']}"]
                                            if reject_processing_key in st.session_state:
                                                del st.session_state[reject_processing_key]
                                            st.rerun()
                                        else:
                                            st.error(result['message'])
                                            if reject_processing_key in st.session_state:
                                                del st.session_state[reject_processing_key]

                            with col_b:
                                if st.button("キャンセル", key=f"reject_cancel_{req['id']}"):
                                    del st.session_state[f"show_reject_{req['id']}"]
                                    st.rerun()

    if section == "📋 処理済み":
        st.subheader("📋 処理済み廃棄申請")

        # 承認済みと却下済みを取得
        approved_requests = get_disposal_requests(status='APPROVED')
        rejected_requests = get_disposal_requests(status='REJECTED')

        all_processed = approved_requests + rejected_requests

        if not all_processed:
            st.info("処理済みの廃棄申請はありません")
        else:
            df = pd.DataFrame(all_processed)

            # ステータス表示を整形
            status_map = {
                'APPROVED': '✅ 承認済み',
                'REJECTED': '❌ 却下'
            }
            df['status_display'] = df['status'].map(status_map)

            # 廃棄金額を計算
            df['disposal_amount'] = df['quantity'] * df['unit_price'].fillna(0)

            display_df = df[[
                'item_name', 'category', 'quantity', 'unit_price', 'disposal_amount',
                'reason', 'requester_name', 'status_display', 'approved_at', 'approver_name', 'reject_reason'
            ]].copy()

            display_df.columns = [
                '物品名', 'カテゴリ', '数量', '単価', '廃棄金額',
                '廃棄理由', '申請者', 'ステータス', '処理日時', '承認者', '却下理由'
            ]

            st.dataframe(
                display_df,
                use_container_width=True,
                height=400
            )

            # CSV出力ボタン
            # 廃棄金額を計算（単価 × 数量）
            df['disposal_amount'] = df['quantity'] * df['unit_price'].fillna(0)

            csv_df = pd.DataFrame({
                "物品名": df['item_name'],
                "カテゴリ": df['category'],
                "数量": df['quantity'],
                "単価": df['unit_price'].fillna(0),
                "廃棄金額": df['disposal_amount'],
                "廃棄理由": df['reason'],
                "申請者": df['requester_name'],
                "ステータス": df['status_display'],
                "処理日時": df['approved_at'],
                "承認者": df['approver_name'].fillna(""),
                "却下理由": df['reject_reason'].fillna("")
            })

            csv_data = csv_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")

            filename = f"disposal_processed_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d')}.csv"

            st.download_button(
                label="📥 CSV出力",
                data=csv_data,
                file_name=filename,
                mime="text/csv",
                use_container_width=False,
                help="処理済み廃棄申請をCSV出力します"
            )
