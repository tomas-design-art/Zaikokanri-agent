# -*- coding: utf-8 -*-
import sys

# Read file
with open('app.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace lines
content = content.replace(
    'st.markdown("# � 在庫管理システム")',
    'st.markdown(\'<h1 style="font-size: 4rem; text-align: center; margin-bottom: 2rem;">📦 在庫管理システム</h1>\', unsafe_allow_html=True)'
)

content = content.replace(
    'st.markdown("## �🔐 ログイン")',
    'st.markdown("## 🔐 ログイン")'
)

content = content.replace(
    'st.markdown("### 在庫管理システムにログインしてください。")',
    'st.write("在庫管理システムにログインしてください。")'
)

# Write file
with open('app.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Complete!")
