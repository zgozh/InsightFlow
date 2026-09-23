# InsightFlow

InsightFlow は DeerFlow v2.1.0-rc0 の Agent ランタイムを基にした、管理された経営分析ワークベンチです。上流の MIT ライセンスと著作権表示を保持しています。条件は [LICENSE](LICENSE)、上流プロジェクトは [DeerFlow](https://github.com/bytedance/deer-flow) を参照してください。

## 機能

- 登録済みデータソース、指標、レポート、監査履歴を対象とした統制付き分析。
- ストリーミング応答、成果物、通常のサブエージェントタスク、スケジュール実行に対応するスレッド型分析。
- DuckDuckGo 検索と Jina Fetch による限定的な Web 調査。
- 運用者が管理する MCP サーバーとスキル。スキルのインストール時に SkillScan を実行。
- Agent のファイル・コマンド用に Local と AIO のサンドボックスを提供。

ワークベンチには分析、チャット、データソース、指標、レポート、履歴、スケジュールタスクの画面があります。削除済みの IM 連携、Custom Agent 編集画面、プロジェクト/ドキュメント/ゴミ箱画面、対話型ブラウザー操作は含みません。

## クイックスタート

Docker Compose、Python 3.12 以降、Node.js 22 以降、uv、pnpm 10.26.2 以降が必要です。

1. ローカル設定を作成して依存関係をインストールします。

   ~~~sh
   make config
   make install
   ~~~

2. Git 管理外の config.yaml を編集し、models に少なくとも 1 つのモデルを設定します。OPENAI_API_KEY や DEEPSEEK_API_KEY は環境変数で管理してください。
3. 開発環境を起動します。

   ~~~sh
   make dev
   ~~~

http://localhost:2026 を開きます。Nginx の公開ポートは既定でローカルループバックにバインドされます。本番相当のローカル環境は make start、Docker 本番環境は make up で起動します。

config.yaml、extensions_config.json、.env、プロバイダー資格情報をコミットしないでください。[設定ガイド](backend/docs/CONFIGURATION.md)と[インストールガイド](Install.md)を参照してください。

## 分析と Agent の境界

Analytics のクエリは統制サービスを通ります。データソース資格情報はサーバー側の参照として保持され、クエリ計画は認可後に実行され、監査履歴も保存されます。Agent ツールからこの経路を迂回することはできません。

Lead Agent は通常タスクを組み込みサブエージェントへ委譲できます。スケジュール実行も標準 Gateway run ライフサイクルを使います。Local サンドボックスのコマンドは Gateway ホスト権限で実行され、AIO は独立したサンドボックスサービスを使います。外部 AIO provisioner は設定されたクライアント接続先であり、このリポジトリにはサービス本体も起動処理も含まれません。

MCP サーバー、拡張、モデルプロバイダー、サンドボックス接続先は信頼できるものとして扱ってください。Gateway を信頼できないネットワークに直接公開しないでください。

## 開発

~~~sh
make check
cd backend
make test
make lint
cd ../frontend
pnpm check
pnpm test
pnpm test:e2e
~~~

バックエンドの標準テストはオフラインです。実プロバイダーのテストは明示的な有効化が必要です。[Backend guide](backend/AGENTS.md)、[Frontend guide](frontend/AGENTS.md)、[受け入れシナリオ](docs/acceptance/acceptance-scenarios.md)を参照してください。

## ライセンスと帰属

本リポジトリは DeerFlow v2.1.0-rc0 から派生し、MIT ライセンスと著作権表示を保持しています。InsightFlow 固有の変更は本リポジトリで管理します。[LICENSE](LICENSE)を参照してください。
