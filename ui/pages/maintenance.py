"""メンテナンスページ"""

import streamlit as st
import pandas as pd

from utils.auth import is_logged_in, is_admin
from repositories.maintenance_repo import (
    check_history_change_types,
    backup_inventory_history_to_csv,
    cleanup_history_change_types,
)


def show_maintenance_page():
    """🛠️ メンテナンスページ（ADMIN専用）"""
    st.header("🛠️ データメンテナンス")
    
    # 権限チェック：ADMINのみ
    if not is_logged_in():
        st.warning("⚠️ メンテナンス機能を利用するにはログインが必要です")
        return
    
    if not is_admin():
        st.error("🚫 この機能は管理者のみ使用できます")
        return
    
    st.info("💡 データベースの整合性チェックとクリーンアップを実行できます")
    
    # 入庫履歴のchange_type統一
    st.subheader("📦 入庫履歴のchange_type統一")
    st.markdown("""
    **目的**: inventory_historyテーブルのchange_typeを標準化します
    - **残すべき値**: `IN` (入庫), `OUT` (出庫), `DISPOSE` (廃棄), `UNDO` (取消)
    - **削除対象**: `ORDER` (発注記録), `INBOUND` (重複納品記録)
    - **変換**: `INBOUND` → `IN` に統一
    """)
    
    # 現在の状態を表示
    with st.expander("📊 現在のchange_type分布", expanded=True):
        try:
            type_counts = check_history_change_types()
            if type_counts:
                df_counts = pd.DataFrame([
                    {"change_type": k, "件数": v}
                    for k, v in sorted(type_counts.items(), key=lambda x: -x[1])
                ])
                st.dataframe(df_counts, use_container_width=True)
                
                # 問題がある場合は警告
                problematic = {k: v for k, v in type_counts.items() 
                             if k not in ['IN', 'OUT', 'DISPOSE', 'UNDO']}
                if problematic:
                    st.warning(f"⚠️ 標準外のchange_type: {', '.join(problematic.keys())}")
                else:
                    st.success("✅ すべてのchange_typeが標準値です")
            else:
                st.info("履歴データがありません")
        except Exception as e:
            st.error(f"エラー: {e}")
    
    # バックアップ
    st.subheader("💾 バックアップ")
    if st.button("📥 履歴データをCSVにバックアップ"):
        try:
            csv_path = backup_inventory_history_to_csv()
            st.success(f"✅ バックアップ完了: {csv_path}")
        except Exception as e:
            st.error(f"❌ バックアップ失敗: {e}")
    
    # ドライラン
    st.subheader("🔍 クリーンアップ予行（変更なし）")
    if st.button("🧹 ドライラン実行"):
        try:
            with st.spinner("チェック中..."):
                result = cleanup_history_change_types(dry_run=True)
            
            st.info("**変更内容（実際には変更されていません）**")
            st.write(f"- INBOUND → IN 変換: {result['converted']}件")
            st.write(f"- ORDER 削除: {result['deleted']}件")
            st.write(f"- 合計処理: {result['total_affected']}件")
            
            if result['total_affected'] > 0:
                st.warning("⚠️ 上記の変更を実行するには、下の「実行」ボタンを押してください")
            else:
                st.success("✅ クリーンアップ不要です")
                
        except Exception as e:
            st.error(f"❌ ドライラン失敗: {e}")
    
    # 実行
    st.subheader("✅ クリーンアップ実行")
    st.warning("⚠️ この操作は **元に戻せません**。必ずバックアップを取ってから実行してください。")
    
    confirm_text = st.text_input("実行するには「実行する」と入力してください:")
    
    if st.button("🚨 クリーンアップ実行", type="primary", disabled=(confirm_text != "実行する")):
        if confirm_text == "実行する":
            try:
                with st.spinner("処理中..."):
                    result = cleanup_history_change_types(dry_run=False)
                
                st.success("✅ クリーンアップ完了")
                st.write(f"- INBOUND → IN 変換: {result['converted']}件")
                st.write(f"- ORDER 削除: {result['deleted']}件")
                st.write(f"- 合計処理: {result['total_affected']}件")
                
                # 実行後の状態確認
                with st.expander("📊 実行後のchange_type分布", expanded=True):
                    after_counts = check_history_change_types()
                    if after_counts:
                        df_after = pd.DataFrame([
                            {"change_type": k, "件数": v}
                            for k, v in sorted(after_counts.items(), key=lambda x: -x[1])
                        ])
                        st.dataframe(df_after, use_container_width=True)
                        
                        # ORDER/INBOUND が残っていないか確認
                        if 'ORDER' in after_counts or 'INBOUND' in after_counts:
                            st.error("⚠️ ORDER または INBOUND が残っています！")
                        else:
                            st.success("✅ ORDER と INBOUND は完全に削除されました")
                            st.info("履歴ページで「🔄 更新」ボタンを押すと最新データが表示されます")
                
                # 結果を再表示（2秒後）
                import time
                time.sleep(2)
                st.rerun()
                
            except Exception as e:
                st.error(f"❌ クリーンアップ失敗: {e}")
                import traceback
                st.code(traceback.format_exc())
        else:
            st.info("確認テキストを入力してください")
