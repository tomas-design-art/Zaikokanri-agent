# 将来性のある改善提案

## フェーズ1: 短期改善（1-2週間）

### 1.1 db.py の段階的分割
現在のリポジトリ層はファサード（re-export）のため、実際の SQL コードは db.py に残っている。  
優先度の高いドメインから順にSQLをリポジトリファイルに移行する。

```
移行順序:
1. user_repo.py (認証・ユーザー管理 - セキュリティ上重要)
2. inventory_repo.py (出庫・入庫 - 最も使用頻度が高い)
3. history_repo.py (履歴・取消)
4. purchase_request_repo.py (発注フロー)
5. 残りのレポジトリ
```

### 1.2 set_menu の統合
現在20ファイルにローカル定義された `set_menu()` を `state/session_manager.py` に統合。

### 1.3 テストの追加
```
tests/
├── unit/
│   ├── test_repositories.py   ← 各リポジトリの単体テスト
│   ├── test_services.py        ← サービス層のテスト
│   └── test_validation.py      ← バリデーションのテスト
└── integration/
    └── test_page_imports.py     ← 全ページのインポートテスト（自動化）
```

## フェーズ2: 中期改善（1-2ヶ月）

### 2.1 API層の追加 (FastAPI)
Streamlit と DB の間に REST API 層を挿入。

```
[Streamlit UI]  ──HTTP──>  [FastAPI]  ──SQL──>  [SQLite]
```

**メリット**:
- UI と ビジネスロジックの完全分離
- モバイルアプリ/外部システム連携が可能
- 負荷テスト・API仕様書(OpenAPI)の自動生成

### 2.2 データベースマイグレーション (Alembic)
現在の `init_tables()` ベースのスキーマ管理を Alembic に移行。

```python
# 現在: init_tables() 内の ALTER TABLE による手動マイグレーション
# 提案: Alembic によるバージョン管理
alembic revision --autogenerate -m "add_received_columns"
alembic upgrade head
```

### 2.3 認証の強化
- bcrypt への完全移行（SHA-256+salt の廃止）
- セッション有効期限の追加
- パスワードポリシー（最小文字数、複雑性要件）
- ログイン試行回数制限

### 2.4 非同期処理
- CSV取り込みのバックグラウンド処理
- 発注メール送信の非同期化
- AI応答のストリーミング表示

## フェーズ3: 長期改善（3-6ヶ月）

### 3.1 UIフレームワークの検討

| フレームワーク | 特徴 | 推奨度 |
|--------------|------|--------|
| **Streamlit** (現行) | 最速のプロトタイピング、Pythonのみ | ✅ 現状維持推奨 |
| **Reflex** | Python-nativeのフルスタック、コンポーネント指向 | ⭐ 次期候補No.1 |
| **NiceGUI** | FastAPIベース、カスタマイズ性が高い | 🟡 API層との相性良 |
| **Dash (Plotly)** | データ可視化に強い、エンタープライズ向け | 🟡 集計画面には適合 |
| **React + FastAPI** | 完全なSPA、最高の自由度 | ❌ 開発コスト大 |

**推奨**: 現時点では **Streamlit を維持**。  
理由: 全ページの UI コードが Streamlit API に密結合しており、  
フレームワーク変更は全ページの書き直しを意味する。  
API層を先に構築すれば、将来的なUI差し替えが容易になる。

### 3.2 PostgreSQL への移行
ユーザー数・データ量の増加に備えて PostgreSQL に移行。

```
移行パス:
SQLite → PostgreSQL (Docker) → PostgreSQL (クラウド)
```

### 3.3 権限管理の高度化 (RBAC → ABAC)
- 属性ベースのアクセス制御
- 部署×カテゴリの掛け合わせ権限
- 時間帯制限（営業時間のみ操作可能）

### 3.4 監査ログ
- 全操作の不可変ログ
- IP アドレス記録
- 変更差分の記録

## 技術的負債の解消

### 即座に対応すべき事項
1. **タイムゾーン混在**: UTC/JST の保存が不統一 → UTC に統一
2. **N+1クエリ**: 一部ページでループ内DB呼び出し → バッチクエリに変更
3. **ハードコードされた定数**: 閾値・上限がコード内に直書き → config に集約
4. **エラーメッセージの統一**: st.error/st.warning の表現揺れ → 共通メッセージ定義

### 中期的に対応する事項
1. **型ヒントの補完**: 関数引数・戻り値の型ヒントを全関数に付与
2. **ログの構造化**: JSON形式のログ出力（ELK Stack連携対応）
3. **キャッシュ戦略**: st.cache_data の TTL 最適化
