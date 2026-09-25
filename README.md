# 数当てゲーム

## GitHub Actions で Cloud Run にデプロイする

このアプリは Dockerfile を使って Google Cloud Run にデプロイできます。
`main` ブランチへ push するたびに `.github/workflows/deploy.yml` が実行されます。

### 事前に必要なもの

1. Google Cloud プロジェクトを作成し、課金を有効にする。
2. 次の API を有効にする。
	- Cloud Run Admin API
	- Cloud Build API
	- Artifact Registry API
3. GitHub Actions 用の Workload Identity Federation とサービスアカウントを作成する。
4. サービスアカウントに、少なくとも次の権限を付与する。
	- Cloud Run Admin
	- Service Account User
	- Storage Admin（Cloud Build のソース保存用）

### Google Cloud 側の設定例

Google Cloud SDK でログインした後、PowerShell で実行します。`OWNER/REPO` は GitHub の所有者とリポジトリ名に置き換えてください。

```powershell
gcloud auth login
$PROJECT_ID = "あなたのプロジェクトID"
$GITHUB_REPO = "OWNER/REPO"
$POOL_ID = "github-actions"
$PROVIDER_ID = "github"
$SERVICE_ACCOUNT = "github-actions"

gcloud config set project $PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com iamcredentials.googleapis.com sts.googleapis.com

gcloud iam service-accounts create $SERVICE_ACCOUNT --project $PROJECT_ID
$SERVICE_ACCOUNT_EMAIL = "$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/run.admin
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/storage.admin
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/cloudbuild.builds.editor
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/artifactregistry.writer
gcloud projects add-iam-policy-binding $PROJECT_ID --member "serviceAccount:$SERVICE_ACCOUNT_EMAIL" --role roles/iam.serviceAccountUser

gcloud iam workload-identity-pools create $POOL_ID --project $PROJECT_ID --location global --display-name "GitHub Actions"
gcloud iam workload-identity-pools providers create-oidc $PROVIDER_ID --project $PROJECT_ID --location global --workload-identity-pool $POOL_ID --display-name "GitHub" --issuer-uri "https://token.actions.githubusercontent.com" --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.actor=assertion.actor" --attribute-condition "assertion.repository == '$GITHUB_REPO'"

$PROJECT_NUMBER = gcloud projects describe $PROJECT_ID --format="value(projectNumber)"
$PROVIDER = "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_ID/providers/$PROVIDER_ID"
$MEMBER = "principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/$POOL_ID/attribute.repository/$GITHUB_REPO"
gcloud iam service-accounts add-iam-policy-binding $SERVICE_ACCOUNT_EMAIL --project $PROJECT_ID --role roles/iam.workloadIdentityUser --member $MEMBER

Write-Output "GCP_WORKLOAD_IDENTITY_PROVIDER=$PROVIDER"
Write-Output "GCP_SERVICE_ACCOUNT=$SERVICE_ACCOUNT_EMAIL"
```

`roles/storage.admin` などの権限はプロジェクト単位で付与する簡易例です。本番運用では、専用バケットや Artifact Registry に対象を絞った権限へ縮小してください。

### GitHub の設定

リポジトリの **Settings > Secrets and variables > Actions** に、次を登録します。

#### Variables

- `GCP_PROJECT_ID`: Google Cloud のプロジェクト ID

#### Secrets

- `GCP_WORKLOAD_IDENTITY_PROVIDER`: `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL_ID/providers/PROVIDER_ID`
- `GCP_SERVICE_ACCOUNT`: GitHub Actions 用サービスアカウントのメールアドレス
- `FLASK_SECRET_KEY`: 長いランダム文字列。本番環境では必ず設定する

`FLASK_SECRET_KEY` は PowerShell で `python -c "import secrets; print(secrets.token_urlsafe(32))"` を実行して生成できます。

GitHub の **Settings > Secrets and variables > Actions > Variables** に `GCP_PROJECT_ID` を登録し、Secrets に上記 3 つを登録してください。

### デプロイ先

初回デプロイ後、Cloud Run が発行する URL を開いて確認します。リージョンを変更する場合は、ワークフローの `REGION` を変更してください。