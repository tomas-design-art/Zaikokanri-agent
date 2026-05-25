"""デモモードページ"""

import streamlit as st

from utils.auth import is_logged_in, is_admin
from repositories.demo_repo import (
    insert_demo_data,
    reset_demo_data,
    get_demo_data_counts,
)


def show_demo_mode_page():
    """デモモード管理ページ（管理者専用）"""
    st.header("🎭 デモモード")
    
    # 権限チェック：ADMINのみ
    if not is_logged_in():
        st.warning("⚠️ デモモードを利用するにはログインが必要です")
        return
    
    if not is_admin():
        st.error("🚫 この機能は管理者のみ使用できます")
        return
    
    st.info("💡 テスト用のサンプルデータを一括投入・リセットできます")
    
    # 現在のデータ件数を表示
    st.subheader("📊 現在のデータ件数")
    
    counts = get_demo_data_counts()
    
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("部署", counts.get("departments", 0))
        st.metric("ユーザー", counts.get("users", 0))
    with col2:
        st.metric("業者", counts.get("vendors", 0))
        st.metric("カテゴリ", counts.get("categories", 0))
    with col3:
        st.metric("物品", counts.get("items", 0))
        st.metric("在庫", counts.get("inventory", 0))
    with col4:
        st.metric("履歴", counts.get("inventory_history", 0))
        st.metric("承認待ち", counts.get("approval_queue", 0))
    with col5:
        st.metric("棚卸しセッション", counts.get("stocktake_sessions", 0))
        st.metric("棚卸しレコード", counts.get("stocktake_records", 0))
    
    st.divider()
    
    # セクション切替（rerun時も保持）
    section = st.radio(
        "表示セクション",
        options=["➕ デモデータ投入", "🗑️ デモリセット"],
        horizontal=True,
        key="demo_section",
    )
    
    # ========== タブ1: デモデータ投入 ==========
    if section == "➕ デモデータ投入":
        st.subheader("➕ デモデータ一括投入")
        
        st.markdown("""
        **投入されるデータ:**
        - 📂 部署: 5件（総務部、営業部、開発部、経理部、人事部）
        - 👥 ユーザー: 7名（管理者1、一般4、ゲスト2）
        - 🏢 業者: 5社（文具センター、電子部品商事、家具プロ等）
        - 🏷️ カテゴリ: 5種類（文房具、電子機器、家具、消耗品、工具）
        - 📦 物品: 20件（各カテゴリに4件ずつ）
        - 📊 在庫: 全物品に在庫設定
        - 📝 履歴: 10件の物品に入出庫履歴
        - ✋ 承認待ち: 3件の出庫申請
        - 📋 棚卸し: セッション1件 + 対象物品レコード（医薬品・電子機器・家具・工具）
          - 未入力(PENDING)、入力済(COUNTED)、確認済(VERIFIED)、承認済(APPROVED)が混在
          - 差異データ（一致・過剰・不足）を含む
        """)
        
        st.warning("⚠️ 既存データと重複する場合はスキップされます")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("✅ デモデータを投入", type="primary", use_container_width=True):
                with st.spinner("投入中..."):
                    result = insert_demo_data()
                    
                    if result["success"]:
                        st.success(result["message"])
                        
                        # 投入された件数を表示
                        inserted_counts = result.get("counts", {})
                        st.markdown("**投入された件数:**")
                        
                        col_a, col_b, col_c = st.columns(3)
                        with col_a:
                            st.write(f"- 部署: {inserted_counts.get('departments', 0)}件")
                            st.write(f"- ユーザー: {inserted_counts.get('users', 0)}件")
                            st.write(f"- 業者: {inserted_counts.get('vendors', 0)}件")
                            st.write(f"- カテゴリ: {inserted_counts.get('categories', 0)}件")
                        with col_b:
                            st.write(f"- 物品: {inserted_counts.get('items', 0)}件")
                            st.write(f"- 在庫: {inserted_counts.get('inventory', 0)}件")
                            st.write(f"- 履歴: {inserted_counts.get('history', 0)}件")
                            st.write(f"- 承認待ち: {inserted_counts.get('approvals', 0)}件")
                        with col_c:
                            st.write(f"- 棚卸しセッション: {inserted_counts.get('stocktake_sessions', 0)}件")
                            st.write(f"- 棚卸しレコード: {inserted_counts.get('stocktake_records', 0)}件")
                        
                        st.balloons()
                        
                        # 各ページへのリンク
                        st.info("💡 各管理画面で確認できます")
                        
                        # 自動リロード用のセッションステート
                        if st.button("🔄 データ件数を更新", use_container_width=True):
                            st.rerun()
                    else:
                        st.error(result["message"])
        
        with col2:
            # ページ遷移ボタン
            st.write("**確認ページへ移動:**")
            
            if st.button("📦 物品マスター", use_container_width=True):
                st.session_state.page = "item_master"
                st.rerun()
            
            if st.button("🏢 業者管理", use_container_width=True):
                st.session_state.page = "vendor"
                st.rerun()
            
            if st.button("👥 ユーザー管理", use_container_width=True):
                st.session_state.page = "user"
                st.rerun()
            
            if st.button("📊 在庫一覧", use_container_width=True):
                st.session_state.page = "inventory"
                st.rerun()
            
            if st.button("📋 棚卸しセッション", use_container_width=True):
                st.session_state.page = "stocktake_sessions"
                st.rerun()
    
    # ========== タブ2: デモリセット ==========
    if section == "🗑️ デモリセット":
        st.subheader("🗑️ デモデータリセット")
        
        st.warning("⚠️ この操作は取り消せません。注意して実行してください。")
        
        # リセットオプション
        keep_users = st.checkbox(
            "ユーザーと部署は残す",
            value=True,
            help="チェックを入れると、在庫系・履歴系のみ削除します"
        )
        
        if keep_users:
            st.markdown("""
            **削除されるデータ:**
            - 📋 棚卸しレコード・セッション
            - 📦 物品マスター
            - 🏢 業者
            - 🏷️ カテゴリ
            - 📊 在庫
            - 📝 在庫履歴
            - ✋ 承認待ち
            
            **保持されるデータ:**
            - 👥 ユーザー
            - 📂 部署
            """)
        else:
            st.markdown("""
            **削除されるデータ:**
            - 📋 棚卸しレコード・セッション
            - 📦 物品マスター
            - 🏢 業者
            - 🏷️ カテゴリ
            - 📊 在庫
            - 📝 在庫履歴
            - ✋ 承認待ち
            - 👥 ユーザー
            - 📂 部署
            """)
        
        # 確認用のセッションステート
        if "demo_reset_confirm" not in st.session_state:
            st.session_state.demo_reset_confirm = False
        
        col1, col2 = st.columns(2)
        
        with col1:
            if not st.session_state.demo_reset_confirm:
                if st.button("🗑️ リセット実行", type="secondary", use_container_width=True):
                    st.session_state.demo_reset_confirm = True
                    st.rerun()
            else:
                st.error("⚠️ 本当にリセットしますか？")
                
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("✅ はい", type="primary", use_container_width=True):
                        with st.spinner("リセット中..."):
                            result = reset_demo_data(keep_users_and_depts=keep_users)
                            
                            if result["success"]:
                                st.success(result["message"])
                                
                                # 削除された件数を表示
                                deleted_counts = result.get("counts", {})
                                st.markdown("**削除された件数:**")
                                
                                col_a, col_b, col_c = st.columns(3)
                                with col_a:
                                    if not keep_users:
                                        st.write(f"- 部署: {deleted_counts.get('departments', 0)}件")
                                        st.write(f"- ユーザー: {deleted_counts.get('users', 0)}件")
                                    st.write(f"- 業者: {deleted_counts.get('vendors', 0)}件")
                                    st.write(f"- カテゴリ: {deleted_counts.get('categories', 0)}件")
                                with col_b:
                                    st.write(f"- 物品: {deleted_counts.get('items', 0)}件")
                                    st.write(f"- 在庫: {deleted_counts.get('inventory', 0)}件")
                                    st.write(f"- 履歴: {deleted_counts.get('history', 0)}件")
                                    st.write(f"- 承認待ち: {deleted_counts.get('approvals', 0)}件")
                                with col_c:
                                    st.write(f"- 棚卸しセッション: {deleted_counts.get('stocktake_sessions', 0)}件")
                                    st.write(f"- 棚卸しレコード: {deleted_counts.get('stocktake_records', 0)}件")
                                
                                st.session_state.demo_reset_confirm = False
                                
                                # 自動リロード
                                if st.button("🔄 データ件数を更新", use_container_width=True):
                                    st.rerun()
                            else:
                                st.error(result["message"])
                                st.session_state.demo_reset_confirm = False
                
                with col_no:
                    if st.button("❌ いいえ", use_container_width=True):
                        st.session_state.demo_reset_confirm = False
                        st.rerun()
        
        with col2:
            if st.button("🔄 キャンセル", use_container_width=True):
                st.session_state.demo_reset_confirm = False
                st.rerun()
