"""履歴ページ"""

import traceback

import streamlit as st
import pandas as pd
from datetime import datetime
from zoneinfo import ZoneInfo

from utils.auth import get_current_user, get_user_role, is_admin, is_guest
from utils.date_utils import parse_db_ts_to_jst
from ui.components.refresh_button import show_refresh_button
from repositories.history_repo import get_history_list
from repositories.pending_repo import cancel_pending_transaction, get_pending_for_history


def show_history_page():
    """履歴ページ"""
    st.header("📋 履歴")
    
    # 更新ボタン
    show_refresh_button()
    
    st.info("💡 入庫・出庫の履歴を確認できます。")
    
    # 取消処理結果メッセージを表示
    if "cancel_success_message" in st.session_state and st.session_state.cancel_success_message:
        st.success(st.session_state.cancel_success_message)
        st.session_state.cancel_success_message = None
    
    if "cancel_error_message" in st.session_state and st.session_state.cancel_error_message:
        st.error(st.session_state.cancel_error_message)
        st.session_state.cancel_error_message = None
    
    # デバッグ：データ取得タイムスタンプ
    current_time = datetime.now(ZoneInfo('Asia/Tokyo')).strftime("%H:%M:%S")
    st.caption(f"🕒 データ取得時刻: {current_time}")
    
    # セクション切替（rerun時も保持）
    section = st.radio(
        "表示セクション",
        options=["✅ 確定履歴", "📝 申請（承認待ち）"],
        horizontal=True,
        key="history_section",
    )
    
    # ========== タブ1: 確定履歴 ==========
    if section == "✅ 確定履歴":
        # フィルタフォーム
        st.subheader("🔍 履歴検索")
    
        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
        
        with col1:
            period_option = st.selectbox(
                "期間",
                options=["全期間", "今日", "7日間", "30日間", "90日間"],
                key="history_period"
            )
            
            # 期間を日数に変換
            period_map = {
                "全期間": None,
                "今日": 1,
                "7日間": 7,
                "30日間": 30,
                "90日間": 90
            }
            period_days = period_map[period_option]
        
        with col2:
            change_type_filter = st.selectbox(
                "種別",
                options=["すべて", "IN", "OUT", "DISPOSE"],
                format_func=lambda x: {"すべて": "すべて", "IN": "入庫", "OUT": "出庫", "DISPOSE": "廃棄"}[x],
                key="history_change_type"
            )
        
        with col3:
            search_query_history = st.text_input(
                "検索",
                placeholder="品目名、品目コードで検索",
                key="search_query_history"
            )
        
        with col4:
            st.write("")  # スペース調整
            st.write("")
            search_button_history = st.button("🔎 検索", key="search_btn_history", use_container_width=True)
        
        st.divider()
        
        # 履歴データ取得
        history_data = get_history_list(
            period_days=period_days,
            change_type=change_type_filter,
            search_query=search_query_history
        )
        
        if not history_data:
            st.warning("⚠️ 該当する履歴がありません")
        else:
            st.info(f"📊 {len(history_data)} 件の履歴が見つかりました")
            
            try:
                # データフレーム作成
                df = pd.DataFrame(history_data)
                
                # 必要なカラムが存在しない場合は追加（NaNで埋める）
                if 'total_price' not in df.columns:
                    df['total_price'] = None
                if 'unit_price' not in df.columns:
                    df['unit_price'] = None
                if 'vendor_name' not in df.columns:
                    df['vendor_name'] = None
                
                # 数値カラムを安全に変換（NULL/NaN対策）
                df['unit_price'] = pd.to_numeric(df['unit_price'], errors='coerce').fillna(0)
                df['total_price'] = pd.to_numeric(df['total_price'], errors='coerce')
                df['quantity'] = pd.to_numeric(df['quantity'], errors='coerce').fillna(0)
                
                # 金額計算（total_price優先、なければ数量×単価）
                df['amount'] = df.apply(lambda r: 
                    r['total_price'] if pd.notna(r['total_price']) 
                    else abs(r['quantity']) * r['unit_price'], 
                    axis=1
                )
                
                # 円表示用のヘルパー関数
                def yen(x):
                    return f"¥{int(x):,}"
                
                # 表示用に整形
                # created_atをUTCとして解釈し、JSTに変換して表示
                ts_jst = pd.to_datetime(df["created_at"], utc=True).dt.tz_convert("Asia/Tokyo")

                display_df = pd.DataFrame({
                    "日時": ts_jst.dt.strftime("%Y-%m-%d %H:%M"),
                    "種別": df["change_type"].map({
                        "IN": "➕ 入庫", 
                        "OUT": "➖ 出庫", 
                        "DISPOSE": "🗑️ 廃棄"
                    }).fillna(df["change_type"]),  # マップにない値はそのまま表示
                    "品目名": df["item_name"],
                    "品目コード": df["item_code"],
                    "数量": df["quantity"].abs().astype(int).astype(str) + " 個",
                    "単価": df["unit_price"].apply(yen),
                    "金額": df["amount"].apply(yen),
                    "業者名": df["vendor_name"].fillna("-"),
                    "保管場所": df["location"].fillna("未設定"),
                    "担当者": df["user_name"],
                    "部署": df["department"].fillna("-"),
                    "備考": df["note"].fillna("-")
                })
                
                # データフレーム表示
                st.dataframe(
                    display_df,
                    width='stretch',
                    hide_index=True,
                    height=600
                )
            except Exception as e:
                st.error(f"❌ データフレーム作成エラー: {str(e)}")
                st.code(traceback.format_exc())
                st.write("デバッグ: データの最初のレコード")
                if history_data:
                    st.json(history_data[0])
            
            # 統計情報表示
            st.divider()
            st.subheader("📈 統計情報")
            
            col1, col2, col3 = st.columns([3, 3, 3])
            
            with col1:
                total_in = df[df["change_type"] == "IN"]["quantity"].sum()
                st.metric("総入庫数", f"{int(total_in)} 個")
            
            with col2:
                total_out = df[df["change_type"] == "OUT"]["quantity"].sum()
                st.metric("総出庫数", f"{int(total_out)} 個")
            
            with col3:
                net_change = total_in - total_out
                st.metric("純増減", f"{int(net_change):+d} 個", delta=int(net_change))
            
            # CSV出力用データ作成
            # created_atをUTCとして解釈し、JSTに変換して出力
            ts_jst = pd.to_datetime(df["created_at"], utc=True).dt.tz_convert("Asia/Tokyo")

            csv_df = pd.DataFrame({
                "日時": ts_jst.dt.strftime("%Y-%m-%d %H:%M:%S"),
                "種別": df["change_type"].map({"IN": "入庫", "OUT": "出庫", "DISPOSE": "廃棄"}),
                "品目名": df["item_name"],
                "品目コード": df["item_code"],
                "数量": df["quantity"].abs().astype(int),
                "単価": df["unit_price"].astype(int),
                "金額": df["amount"].astype(int),
                "業者名": df["vendor_name"].fillna(""),
                "保管場所": df["location"].fillna("未設定"),
                "担当者": df["user_name"],
                "部署": df["department"].fillna(""),
                "備考": df["note"].fillna("")
            })
            
            # CSVデータをバイトに変換
            csv_data = csv_df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")
            
            # ファイル名生成
            filename = f"history_{datetime.now(ZoneInfo('Asia/Tokyo')).strftime('%Y%m%d')}.csv"
            
            st.download_button(
                label="📥 CSV出力",
                data=csv_data,
                file_name=filename,
                mime="text/csv",
                use_container_width=True,
                type="primary"
            )
    
    # ========== タブ2: 申請（承認待ち） ==========
    if section == "📝 申請（承認待ち）":
        st.subheader("📝 承認待ち申請一覧")
        
        # 表示対象を権限に応じて決定
        current_user = get_current_user()
        user_role = get_user_role()
        
        if is_admin():
            st.info("💡 管理者として全部署の申請を表示しています。")
            pending_list = get_pending_for_history(user_role="ADMIN")
        elif is_guest():
            st.info("💡 自分の申請のみ表示しています。")
            pending_list = get_pending_for_history(
                user_id=current_user.get("id"),
                user_role="GUEST"
            )
        else:
            # USER
            dept_name = current_user.get("department", "")
            st.info(f"💡 「{dept_name}」部署の申請を表示しています。")
            pending_list = get_pending_for_history(
                department_id=current_user.get("department_id"),
                user_role="USER"
            )
        
        if not pending_list:
            st.success("🎉 承認待ちの申請はありません")
        else:
            st.warning(f"⚠️ {len(pending_list)} 件の承認待ち申請があります")
            
            for pending in pending_list:
                created_at = parse_db_ts_to_jst(pending["created_at"])
                time_diff = datetime.now(ZoneInfo('Asia/Tokyo')) - created_at
                minutes_ago = int(time_diff.total_seconds() / 60)
                hours_ago = minutes_ago // 60
                
                # 経過時間表示
                if hours_ago > 0:
                    time_display = f"{hours_ago}時間{minutes_ago % 60}分前"
                else:
                    time_display = f"{minutes_ago}分前"
                
                with st.container(border=True):
                    col1, col2, col3 = st.columns([4, 2, 2])
                    
                    with col1:
                        change_type_label = "➖ 出庫" if pending['change_type'] == 'OUT' else "➕ 入庫"
                        st.markdown(f"**{change_type_label}** {pending['item_name']} ({pending['item_code']})")
                        st.caption(f"⏱️ {time_display} | 数量: {pending['quantity']}個 | 申請者: {pending['actor_name']}")
                        st.caption(f"🏢 部署: {pending.get('department_name', 'N/A')}")
                        if pending.get('note'):
                            st.caption(f"📝 {pending['note']}")
                    
                    with col2:
                        st.markdown("🔶 **承認待ち**")
                    
                    with col3:
                        # GUESTの場合のみ取り下げボタン表示（guest_user_id一致）
                        if is_guest() and pending['guest_user_id'] == current_user.get('id'):
                            confirm_key = f"confirm_cancel_hist_{pending['id']}"
                            if confirm_key not in st.session_state:
                                st.session_state[confirm_key] = False
                            
                            if not st.session_state[confirm_key]:
                                if st.button("🗑️ 取り下げ", key=f"cancel_hist_{pending['id']}", use_container_width=True):
                                    st.session_state[confirm_key] = True
                                    st.rerun()
                            else:
                                st.caption("⬇️ 下に入力欄")
                        else:
                            st.caption("承認待ち中")
                
                # 取り下げ確認フォーム（コンテナの外に配置して見やすく）
                if is_guest() and pending['guest_user_id'] == current_user.get('id'):
                    confirm_key = f"confirm_cancel_hist_{pending['id']}"
                    if confirm_key in st.session_state and st.session_state[confirm_key]:
                        actor_input_key = f"actor_hist_{pending['id']}"
                        st.warning("⚠️ 取り下げるには、申請時に入力した名前を再入力してください")
                        actor_confirm = st.text_input("申請者名（本人確認用）", key=actor_input_key, placeholder="例: 山田太郎")
                        col_yes, col_no = st.columns(2)
                        with col_yes:
                            if st.button("✅ 取り下げ確定", key=f"yes_hist_{pending['id']}", type="primary", use_container_width=True):
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
                            if st.button("❌ キャンセル", key=f"no_hist_{pending['id']}", use_container_width=True):
                                st.session_state[confirm_key] = False
                                st.rerun()
