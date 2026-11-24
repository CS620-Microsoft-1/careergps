#!/usr/bin/env bash
# Build both images, push them to GitHub Container Registry, and deploy them to App Service.
# Safe to re-run: the first run creates everything, later runs only redeploy new images.
#
#   az login                                         # once
#   docker login ghcr.io -u <github-username>        # once; password = classic token with write:packages
#   ./deploy/azure.sh                                # from the repo root, with Docker running
#
# The packages must be public so App Service can pull them without credentials: after the first
# push, set each package to Public in GitHub (package -> Package settings -> Change visibility).
#
# Reads backend/.env (becomes the API's app settings) and frontend/.env (Supabase public values).
# Override any name below by setting it in the environment, e.g. LOCATION=westus2 ./deploy/azure.sh
set -euo pipefail
cd "$(dirname "$0")/.."

RG=${RG:-rg-careergps}
LOCATION=${LOCATION:-northcentralus}       # nearest allowed region to Supabase (us-east-2); Azure for Students
                                           # only allows some: az policy assignment list --query "[].parameters"
PLAN=${PLAN:-plan-careergps}
# Defaults to the repo's GitHub owner; set GHCR_OWNER=<your-username> if the org blocks packages.
GHCR_OWNER=${GHCR_OWNER:-$(git remote get-url origin | sed -E 's#.*github\.com[:/]([^/]+)/.*#\1#')}
API_APP=${API_APP:-careergps-api}          # globally unique, becomes <name>.azurewebsites.net
WEB_APP=${WEB_APP:-careergps-web}          # globally unique
API_URL=${API_URL:-https://$API_APP.azurewebsites.net}
WEB_URL=${WEB_URL:-https://$WEB_APP.azurewebsites.net}
TAG=$(git rev-parse --short HEAD)$(git diff --quiet HEAD || echo -dirty)

REGISTRY=ghcr.io/$(echo "$GHCR_OWNER" | tr '[:upper:]' '[:lower:]')   # ghcr names must be lowercase
API_IMAGE=$REGISTRY/careergps-api:$TAG
WEB_IMAGE=$REGISTRY/careergps-web:$TAG

for f in backend/.env frontend/.env; do [[ -f $f ]] || { echo "Missing $f" >&2; exit 1; }; done

echo "==> Build and push images ($TAG)"
docker build --platform linux/amd64 -t "$API_IMAGE" backend
# NEXT_PUBLIC_ values are compiled in, so the API URL is fixed per frontend image.
(set -a; . frontend/.env; set +a
 docker build --platform linux/amd64 -t "$WEB_IMAGE" \
   --build-arg NEXT_PUBLIC_API_URL="$API_URL" \
   --build-arg NEXT_PUBLIC_SUPABASE_URL \
   --build-arg NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY frontend)
docker push "$API_IMAGE"
docker push "$WEB_IMAGE"

# App Service pulls anonymously, so stop here (before creating anything) if a package is still private.
public() {
  local repo=${1#ghcr.io/}; repo=${repo%:*}
  local token
  token=$(curl -fsS "https://ghcr.io/token?scope=repository:$repo:pull" | python3 -c 'import json,sys; print(json.load(sys.stdin)["token"])') &&
    curl -fsS -o /dev/null -H "Authorization: Bearer $token" \
      -H "Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.v2+json" \
      "https://ghcr.io/v2/$repo/manifests/$TAG"
}
for image in "$API_IMAGE" "$WEB_IMAGE"; do
  public "$image" 2>/dev/null || {
    echo "$image is not public yet. On GitHub open the package -> Package settings -> Change visibility"
    echo "-> Public, then re-run this script." >&2
    exit 1
  }
done

echo "==> Resource group and plan"
az group show -n "$RG" -o none 2>/dev/null || az group create -n "$RG" -l "$LOCATION" -o none
az appservice plan show -n "$PLAN" -g "$RG" -o none 2>/dev/null ||
  az appservice plan create -n "$PLAN" -g "$RG" -l "$LOCATION" --is-linux --sku B1 -o none

# Creates the app on first run, otherwise swaps the image. The system identity is for Foundry.
deploy_app() {
  local app=$1 image=$2
  if az webapp show -n "$app" -g "$RG" -o none 2>/dev/null; then
    az webapp config container set -n "$app" -g "$RG" --container-image-name "$image" -o none
  else
    az webapp create -n "$app" -g "$RG" -p "$PLAN" --container-image-name "$image" \
      --assign-identity '[system]' -o none
  fi
  az webapp update -n "$app" -g "$RG" --https-only true -o none
  # Always On keeps background threads (resume analysis) from being stopped when idle.
  az webapp config set -n "$app" -g "$RG" --always-on true -o none
  az webapp log config -n "$app" -g "$RG" --docker-container-logging filesystem -o none
}

echo "==> API app"
deploy_app "$API_APP" "$API_IMAGE"
# backend/.env -> app settings, via a temp file so secrets stay off the command line.
# MIGRATION_DATABASE_URL is left out: migrations are run by the database owner, not the app.
SETTINGS=$(mktemp)
trap 'rm -f "$SETTINGS"' EXIT
python3 - "$SETTINGS" "$WEB_URL" <<'PY'
import json, sys
out, web_url = sys.argv[1], sys.argv[2]
settings = {}
for line in open("backend/.env"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    settings[key.strip()] = value.strip().strip("'\"")
settings.pop("MIGRATION_DATABASE_URL", None)
settings.update(CORS_ORIGINS=web_url, WEBSITES_PORT="8000")
json.dump(settings, open(out, "w"))
PY
az webapp config appsettings set -n "$API_APP" -g "$RG" --settings "@$SETTINGS" -o none
rm -f "$SETTINGS"

echo "==> Web app"
deploy_app "$WEB_APP" "$WEB_IMAGE"
az webapp config appsettings set -n "$WEB_APP" -g "$RG" --settings WEBSITES_PORT=3000 -o none

echo "==> Waiting for the API"
for _ in $(seq 30); do
  curl -fsS "$API_URL/health/db" && break
  sleep 10
done
echo

PRINCIPAL_ID=$(az webapp identity show -n "$API_APP" -g "$RG" --query principalId -o tsv)
cat <<EOF

Deployed $TAG
  Frontend: $WEB_URL
  API:      $API_URL

First deploy only:
  1. Send the Foundry project owner the API's identity and ask them to run:
       az role assignment create --assignee $PRINCIPAL_ID --role "Azure AI User" --scope <Foundry resource ID>
  2. Supabase -> Authentication -> URL Configuration: Site URL $WEB_URL, add redirect URL $WEB_URL/**
Logs: az webapp log tail -n $API_APP -g $RG
EOF
