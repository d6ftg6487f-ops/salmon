# 豆電球をつけたり消したりするだけ

豆電球の点灯・消灯を切り替えるだけの Flask アプリです。状態とボタンを押した回数を Cloud SQL に保存します。Cloud SQL は PostgreSQL / MySQL に対応しています。

## ローカルで実行

Python 3.12 以降を使い、依存関係をインストールして起動します。

```powershell
python -m pip install -r requirements.txt
python app.py
```

Cloud SQL の接続情報を設定しない場合は、ローカルの `bulb.db` (SQLite) に保存します。

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
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com iamcredentials.googleapis.com sts.googleapis.com sqladmin.googleapis.com secretmanager.googleapis.com

gcloud iam service-accounts create $SERVICE_ACCOUNT --project $PROJECT_ID
$SERVICE_ACCOUNT_EMAIL = "$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/run.admin
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/storage.admin
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/cloudbuild.builds.editor
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/artifactregistry.writer
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/iam.serviceAccountUser
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/cloudsql.client
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/secretmanager.secretAccessor

gcloud iam workload-identity-pools create $POOL_ID --project $PROJECT_ID --location global --display-name "GitHub Actions"
gcloud iam workload-identity-pools providers create-oidc $PROVIDER_ID --project $PROJECT_ID --location global --workload-identity-pool $POOL_ID --display-name "GitHub" --issuer-uri "https://token.actions.githubusercontent.com" --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.actor=assertion.actor" --attribute-condition "assertion.repository == '$GITHUB_REPO'"

$PROJECT_NUMBER = gcloud projects describe $PROJECT_ID --format="value(projectNumber)"
$PROVIDER = "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_ID/providers/$PROVIDER_ID"
$MEMBER = "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_ID/attribute.repository/$GITHUB_REPO"
gcloud iam service-accounts add-iam-policy-binding $SERVICE_ACCOUNT_EMAIL --project $PROJECT_ID --role roles/iam.workloadIdentityUser --member $MEMBER

Write-Output "GCP_WORKLOAD_IDENTITY_PROVIDER=$PROVIDER"
Write-Output "GCP_SERVICE_ACCOUNT=$SERVICE_ACCOUNT_EMAIL"
```

本番環境では、サービスアカウントのロールをプロジェクト全体に付与するのではなく、可能な限り対象リソースに絞ってください。特に Secret Manager Secret Accessor は、アプリ用パスワードのシークレットに対して付与するのが推奨です。

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
- `GCP_SERVICE_ACCOUNT`: GitHub Actions と Cloud Run が使用するサービスアカウントのメールアドレス

Cloud Run の DB パスワードは GitHub に登録せず、Google Cloud Secret Manager の `applearning-db-password` に保存してください。

Cloud Run のリージョンは `.github/workflows/deploy.yml` の `REGION` で設定します。Cloud SQL Connector はプライベートIPを使う設定です。Cloud Run の実行サービスアカウントには Cloud SQL Client (`roles/cloudsql.client`) を付与してください。初回デプロイ後、Cloud Run が発行する URL を開いて確認します。
