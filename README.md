# 豆電球をつけたり消したりするだけ

豆電球の点灯・消灯を切り替えるだけの Flask アプリです。状態とボタンを押した回数を Cloud SQL に保存します。Cloud SQL は PostgreSQL / MySQL に対応しています。

## ローカルで実行

Python 3.12 と Node.js 24 を使い、依存関係とブラウザー用 JavaScript を準備して起動します。Node.js はビルドにだけ使用し、アプリのサーバーは引き続き Flask / Gunicorn です。

```powershell
python -m pip install -r requirements.txt
npm ci
npm run build
python app.py
```

Cloud SQL の接続情報を設定しない場合は、ローカルの `bulb.db` (SQLite) に保存します。

自作ブラウザーコードは `src/bulb.ts`、`src/chat.ts`、`src/three-bulb.ts` を編集し、変更後に `npm run build` を実行してください。生成先は従来と同じ `static/*.js` の3ファイルで、Git 管理・手編集の対象にはしません。`bulb.js` と `chat.js` は従来どおり `defer` 付きの通常の script、`three-bulb.js` はブラウザー向け ESM です。CSS・画像・`static/vendor/` は生成物ではありません。

TypeScript は `strict` を有効にし、同梱 Three.js r180 の型を `@types/three` で補います。ブラウザーが読み込む Three.js 本体・相対 import・ライセンスは `static/vendor/` のままです。

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

## reCAPTCHA Enterprise

サイトを開く前に reCAPTCHA Enterprise の確認を1回行います。確認に成功するとブラウザーセッション中はチャットと電球を利用でき、チャット送信や電球の切り替え時に再度 CAPTCHA を求められることはありません。サーバーもセッションを確認し、確認を通過していない API 操作を拒否します。

Google Cloud プロジェクトで reCAPTCHA Enterprise API (`recaptchaenterprise.googleapis.com`) を有効にし、HTML に設定したサイトキーにアプリのホスト名を登録してください。`RECAPTCHA_SITE_KEY` 環境変数でサイトキーを変更できます。評価に使うプロジェクトIDは `RECAPTCHA_PROJECT_ID`、省略時は `GOOGLE_CLOUD_PROJECT` です。サーバーは ADC を使うため、ローカル実行時は `gcloud auth application-default login` を行い、実行サービスアカウントには reCAPTCHA Enterprise Agent (`roles/recaptchaenterprise.agent`) を付与してください。

セッション署名用のキーは、`FLASK_SECRET_KEY` が指定されていればそれを使います。省略した場合、Cloud Run では既存の `DB_PASSWORD` から用途を分けて安定した署名キーを導出するため、追加の Secret Manager シークレットは不要です。ローカルで両方を省略した場合はプロセス起動ごとに一時キーを生成するため、サーバー再起動後は再確認が必要です。

## 3D電球

電球は Three.js でブラウザー上に描画します。ライブラリは `static/vendor/` に同梱しているため、実行時に外部CDNへの接続は不要です。WebGLを利用できない環境では、ページ内のSVG電球を表示します。Three.js は MIT License で、ライセンス文を `static/vendor/THREE-LICENSE.txt` に含めています。

## SQL

データベース操作は `app.py` 内に SQL 文として記述しています。`bulb_state` テーブルに現在の点灯状態 (`is_on`) と累計押下回数 (`press_count`) を保存します。テーブル作成、初期行登録、状態取得、切り替え更新に使う SQL は `BulbDatabase` クラス内で確認できます。初期行の重複防止構文だけは PostgreSQL / SQLite と MySQL で異なります。

テスト:

```powershell
python -m unittest discover -s tests
```

## GitHub Actions から Cloud Run にデプロイ

`main` ブランチへの push で `.github/workflows/deploy.yml` が実行され、Cloud Run にデプロイされます。

### Google Cloud の準備

1. Google Cloud プロジェクトで課金を有効にし、次の API を有効にします。
   - Cloud Run Admin API
   - Cloud Build API
   - Artifact Registry API
   - Cloud SQL Admin API
   - Secret Manager API
   - Vertex AI API
   - reCAPTCHA Enterprise API
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
   - reCAPTCHA Enterprise Agent (`roles/recaptchaenterprise.agent`) — Cloud Run の実行サービスアカウントに付与

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
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com iamcredentials.googleapis.com sts.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com aiplatform.googleapis.com recaptchaenterprise.googleapis.com

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
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/recaptchaenterprise.agent

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

Cloud Run のリージョンは `.github/workflows/deploy.yml` の `REGION` で設定します。Cloud SQL Connector はプライベートIPを使う設定です。Cloud Run の実行サービスアカウントには Cloud SQL Client (`roles/cloudsql.client`)、Vertex AI User (`roles/aiplatform.user`)、reCAPTCHA Enterprise Agent (`roles/recaptchaenterprise.agent`) を付与してください。初回デプロイ後、Cloud Run が発行する URL を開いて確認します。
