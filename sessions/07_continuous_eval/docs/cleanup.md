# Cleanup (Challenge 7)

Delete in this order. Cloud SQL comes first: it is billed for every hour it exists, even when idle or stopped
(a stopped instance still pays for storage and its IP address). Cloud Run, Artifact Registry and Secret Manager stay
within their free tiers for this lab, but delete them too.

```bash
set -a && source deploy/cloudrun.env && set +a
gcloud sql instances delete agent-pg
gcloud run services delete agent-api --region=us-central1
gcloud artifacts repositories delete agentops --location=us-central1
for s in openai-api-key tavily-api-key db-password agent-users; do gcloud secrets delete $s --quiet; done
gcloud projects remove-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:$SA_EMAIL --role=roles/cloudsql.client
gcloud iam service-accounts delete $SA_EMAIL
rm -rf secrets/
```

Check (both lists must be empty):
```bash
gcloud sql instances list
gcloud run services list
gcloud secrets list
```

Keep the project and its budget alert: Session 05 deploys again from GitHub Actions.
"The deleted instance name can be reused immediately to create a new instance"
(https://cloud.google.com/sql/docs/postgres/delete-instance). If the delete is refused because deletion protection is
on, run `gcloud sql instances patch agent-pg --no-deletion-protection` and delete again.

Charges appear in Billing → Reports with a delay (up to a day). Check them the next day.
