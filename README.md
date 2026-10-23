# 豆電球をつけたり消したりするだけ

豆電球の点灯・消灯を切り替えるだけの Flask アプリです。状態とボタンを押した回数を Cloud SQL に保存します。Cloud SQL は PostgreSQL / MySQL に対応しています。

## ローカルで実行

Python 3.12 と Node.js 24 を使い、依存関係とブラウザー用 JavaScript を準備して起動します。Node.js はビルド・検証にだけ使用し、アプリのサーバーは引き続き Flask / Gunicorn です。

```powershell
python -m pip install -r requirements.txt
npm ci
npm run build
python app.py
```

Cloud SQL の接続情報を設定しない場合は、ローカルの `bulb.db` (SQLite) に保存します。

自作ブラウザーコードは `src/bulb.ts`、`src/chat.ts`、`src/three-bulb.ts` を編集し、変更後に `npm run build` を実行してください。生成先は従来と同じ `static/*.js` の3ファイルで、Git 管理・手編集の対象にはしません。`bulb.js` と `chat.js` は従来どおり `defer` 付きの通常の script、`three-bulb.js` はブラウザー向け ESM です。CSS・画像・`static/vendor/` は生成物ではありません。

TypeScript は `strict` を有効にし、同梱 Three.js r180 の型だけを `@types/three` で補います。ブラウザーが読み込む Three.js 本体・相対 import・ライセンスは `static/vendor/` のままです。Node.js は `.node-version`、CI、Docker ビルドで 24 系を使用し、npm の依存関係は `package-lock.json` で固定します。

## 豆電球チャット

画面右上のチャットで、このアプリや豆電球の操作について質問できます。回答には Vertex AI の Gemini を使います。会話履歴はブラウザー内だけで保持され、ページを再読み込みすると消去されます。

ローカルで試す場合は、Google Cloud プロジェクトで Vertex AI API を有効にし、ADC (Application Default Credentials) を設定します。

```powershell
gcloud auth application-default login
$env:GOOGLE_CLOUD_PROJECT = "あなたのプロジェクトID"
$env:VERTEX_AI_LOCATION = "global"
python app.py
```

既定モデルは、低コスト向けの `gemini-3.1-flash-lite` です。`GEMINI_MODEL` 環境変数で変更できます。`VERTEX_AI_LOCATION` は既定で `global` です。モデルの提供状況・単価はリージョンや時期で変わるため、利用前に [Vertex AI の料金](https://cloud.google.com/vertex-ai/generative-ai/pricing) と[モデルの提供状況](https://cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/3-1-flash-lite)を確認してください。global endpoint では処理されるリージョンを指定できないため、データ所在地の要件があれば対応リージョンを設定してください。

利用量を抑えるため、質問は最大1,000文字、履歴は直近6メッセージ、回答は最大256トークンに制限し、Gemini 3 の思考レベルも `MINIMAL` にしています。Vertex AI はトークン量に応じて課金されます。Google Cloud の予算アラートも設定してください (アラートは利用停止を保証する上限ではありません)。Cloud SQL を使っている場合、そのインスタンス料金はチャットの利用量とは別に発生します。

Cloud Run は現在 unauthenticated (認証なし) で公開する設定です。上記の制限は1リクエストあたりの上限で、月間の利用総額を止めるものではありません。公開利用の前に認証やレート制限を追加してください。まず試すだけならローカルで動かしてください。

## 3D電球

現在の画面の電球は HTML / CSS で描画しています。Three.js 用の `src/three-bulb.ts` は移行後も生成しますが、現在のテンプレートからは読み込まず、canvas 要素も追加していません。ライブラリは `static/vendor/` に同梱しており、実行時に外部 CDN への接続は不要です。Three.js は MIT License で、ライセンス文を `static/vendor/THREE-LICENSE.txt` に含めています。

## SQL

データベース操作は `app.py` 内に SQL 文として記述しています。`bulb_state` テーブルに現在の点灯状態 (`is_on`) と累計押下回数 (`press_count`) を保存します。テーブル作成、初期行登録、状態取得、切り替え更新に使う SQL は `BulbDatabase` クラス内で確認できます。初期行の重複防止構文だけは PostgreSQL / SQLite と MySQL で異なります。

## 検証

Python の依存をインストールした環境で実行します。アプリ、Playwright の設定とテストをそれぞれ型検査し、生成・HTTP 配信された JavaScript を Chromium で検証します。

```sh
npm ci
npm run typecheck
npm run build
env -u K_SERVICE -u CLOUD_SQL_CONNECTION_NAME -u GOOGLE_CLOUD_PROJECT \
  DATABASE_URL=sqlite:///:memory: \
  python -m unittest discover -s tests -v
npx playwright install chromium
npm run test:frontend
```

Linux でブラウザーのシステム依存も必要な場合は `npx playwright install --with-deps chromium` を使用します。ブラウザーテストは専用サーバーを起動し、一時 SQLite ファイルとチャットの通信モックを使用します。実 Cloud SQL / Vertex AI には接続しません。仮想環境の Python を使う場合は、仮想環境を有効化するか `PYTHON=/path/to/python npm run test:frontend` を指定できます。

### 本番イメージの検証

Dockerfile の Node.js ステージが `npm ci --include=dev` とビルドを実行し、生成した3つの JavaScript を Python の最終イメージへコピーします。ローカル生成済み JS や `node_modules` はビルドコンテキストから除外するため、クリーンな checkout だけでイメージを作れます。起動時の npm インストールやビルドは不要です。

```sh
docker build --no-cache --progress=plain -t salmon-ts:verify .
bash scripts/verify-container.sh salmon-ts:verify
```

検証スクリプトには、上の npm / Python 環境、Chromium、Docker、curl が必要です。ローカルの生成 JS とイメージからの配信内容を比較し、静的資産・API の応答・ブラウザー操作を確認します。検証用コンテナは localhost の空きポートで起動し、終了時にそのコンテナだけを削除します。既存の SQLite フォールバックを利用するため、この検証は実クラウド接続の確認ではありません。

`.gcloudignore` は `.gitignore` を取り込み、TS ソース・型宣言・npm lockfile・tsconfig・Dockerfile をアップロードに残し、生成 JS・依存ディレクトリ・ローカル DB・認証ファイルを除外します。アップロード対象は、デプロイせずに `gcloud meta list-files-for-upload` で確認できます。

## GitHub Actions から Cloud Run にデプロイ

`.github/workflows/deploy.yml` の `validate` job は、`main` 宛ての PR、`main` への push、手動実行で同じコミットの型検査・既存 Python テスト・Docker ビルド・ブラウザーテストを実行します。PR では GitHub の合成マージ結果を検証します。クリーンな `git archive` に対して、認証不要の `gcloud meta list-files-for-upload` で送信対象を列挙し、そのファイルだけから Docker イメージをビルドします。ブラウザーテストはその最終イメージに対して実行します。

PR の検証には Google Cloud の Secrets や OIDC 権限は不要です。フォークからの初回 PR などで workflow の実行承認が必要な場合は、upstream 管理者による承認を待ちます。

`main` への push、または手動実行では、検証に成功した後にだけ `deploy` job が実行されます。OIDC の `id-token: write` はこの job に限定し、PR ではデプロイしません。従来の `gcloud run deploy --source .`、サービス名、リージョン、環境変数、Cloud SQL / VPC / Secret 設定を維持しており、TypeScript 移行のための新しいクラウド認証設定は不要です。

### Google Cloud の準備

1. Google Cloud プロジェクトで課金を有効にし、次の API を有効にします。
   - Cloud Run Admin API
   - Cloud Build API
   - Artifact Registry API
   - Cloud SQL Admin API
   - Secret Manager API
   - Vertex AI API
2. Cloud SQL インスタンスを作成し、その中にデータベースとアプリ用ユーザーを作成します。PostgreSQL または MySQL を使用できます。
   - プライベートIPのみを使う場合、Cloud Run はインスタンスのプライベートIPと同じVPCネットワークへ接続できる必要があります。このリポジトリのデプロイ設定は `default` VPC の `default` サブネットからプライベートレンジへ egress します。
3. Secret Manager に `applearning-db-password` という名前のシークレットを作成し、アプリ用ユーザーのパスワードを登録します。
4. GitHub Actions 用の Workload Identity Federation とサービスアカウントを作成します。サービスアカウントには以下のロールが必要です。
   - Cloud Run Admin (`roles/run.admin`)
   - Service Account User (`roles/iam.serviceAccountUser`)
   - Storage Admin (`roles/storage.admin`)
   - Cloud Build Editor (`roles/cloudbuild.builds.editor`)
   - Artifact Registry Writer (`roles/artifactregistry.writer`)
   - Cloud SQL Client (`roles/cloudsql.client`)
   - Secret Manager Secret Accessor (`roles/secretmanager.secretAccessor`)
   - Vertex AI User (`roles/aiplatform.user`) — Cloud Run の実行サービスアカウントに付与

### Workload Identity Federation の設定例

Google Cloud SDK でログインした後、PowerShell で実行します。`OWNER/REPO` は GitHub の所有者とリポジトリ名に置き換えてください。

```powershell
gcloud auth login
$PROJECT_ID = "あなたのプロジェクトID"
$GITHUB_REPO = "OWNER/REPO"
$POOL_ID = "github-actions"
$PROVIDER_ID = "github"
$SERVICE_ACCOUNT = "github-actions"

gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com iamcredentials.googleapis.com sts.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com

gcloud iam service-accounts create $SERVICE_ACCOUNT --project $PROJECT_ID
$SERVICE_ACCOUNT_EMAIL = "$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/run.admin
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/storage.admin
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/cloudbuild.builds.editor
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/artifactregistry.writer
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/iam.serviceAccountUser
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/cloudsql.client
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/secretmanager.secretAccessor
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/aiplatform.user

gcloud iam workload-identity-pools create $POOL_ID --project $PROJECT_ID --location global --display-name "GitHub Actions"
gcloud iam workload-identity-pools providers create-oidc $PROVIDER_ID --project $PROJECT_ID --location global --workload-identity-pool $POOL_ID --display-name "GitHub" --issuer-uri "https://token.actions.githubusercontent.com" --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.actor=assertion.actor" --attribute-condition "assertion.repository == '$GITHUB_REPO'"

$PROJECT_NUMBER = gcloud projects describe $PROJECT_ID --format="value(projectNumber)"
$PROVIDER = "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_ID/providers/$PROVIDER_ID"
$MEMBER = "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_ID/attribute.repository/$GITHUB_REPO"
gcloud iam service-accounts add-iam-policy-binding $SERVICE_ACCOUNT_EMAIL --project $PROJECT_ID --role roles/iam.workloadIdentityUser --member $MEMBER

Write-Output "GCP_WORKLOAD_IDENTITY_PROVIDER=$PROVIDER"
Write-Output "GCP_SERVICE_ACCOUNT_EMAIL=$SERVICE_ACCOUNT_EMAIL"
```

本番環境では、サービスアカウントのロールをプロジェクト全体に付与するのではなく、可能な限り対象リソースに絞ってください。特に Secret Manager Secret Accessor は、アプリ用パスワードのシークレットに対して付与するのが推奨です。`roles/iam.serviceAccountUser` は、GitHub Actions のデプロイ用サービスアカウントに付与します。Cloud Run の実行用サービスアカウントに付与する権限ではありません。

### GitHub Actions の設定

リポジトリの **Settings > Secrets and variables > Actions** で設定します。

#### Variables

- `GCP_PROJECT_ID`: Google Cloud のプロジェクト ID
- `CLOUD_SQL_CONNECTION_NAME`: `PROJECT_ID:REGION:INSTANCE_ID` 形式の Cloud SQL 接続名
- `DB_DIALECT`: `postgres` または `mysql`
- `DB_USER`: Cloud SQL のアプリ用ユーザー名
- `DB_NAME`: Cloud SQL のデータベース名

#### Secrets

- `GCP_WORKLOAD_IDENTITY_PROVIDER`: `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL_ID/providers/PROVIDER_ID`
- `GCP_SERVICE_ACCOUNT_EMAIL`: GitHub Actions の認証と Cloud Run の実行に共用するサービスアカウントのメールアドレス

Cloud Run の DB パスワードは GitHub に登録せず、Google Cloud Secret Manager の `applearning-db-password` に保存してください。

Cloud Run のデプロイ時に `iam.serviceaccounts.actAs` エラーが出る場合は、`GCP_SERVICE_ACCOUNT_EMAIL` のサービスアカウント自身に Service Account User を付与します。たとえば PowerShell で次のように設定します。

```powershell
$PROJECT_ID = "あなたのプロジェクトID"
$SERVICE_ACCOUNT_EMAIL = "GCP_SERVICE_ACCOUNT_EMAILに設定したメールアドレス"

gcloud iam service-accounts add-iam-policy-binding $SERVICE_ACCOUNT_EMAIL `
  --project $PROJECT_ID `
  --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" `
  --role roles/iam.serviceAccountUser
```

認証に使うサービスアカウントと、Cloud Run の実行用サービスアカウントは同一にします。別々のアカウントに分ける場合は、デプロイ用アカウントに対し、実行用サービスアカウント上で `roles/iam.serviceAccountUser` を付与してください。エラーに表示される「認証されたアカウント」はデプロイ用、「service account」は実行用です。

#### 任意の Variables

- `GEMINI_MODEL`: Vertex AI のモデル ID (省略時 `gemini-3.1-flash-lite`)
- `VERTEX_AI_LOCATION`: Vertex AI のリージョン/エンドポイント (省略時 `global`)

Cloud Run のリージョンは `.github/workflows/deploy.yml` の `REGION` で設定します。Cloud SQL Connector はプライベートIPを使う設定です。Cloud Run の実行サービスアカウントには Cloud SQL Client (`roles/cloudsql.client`) と Vertex AI User (`roles/aiplatform.user`) を付与してください。初回デプロイ後、Cloud Run が発行する URL を開いて確認します。
