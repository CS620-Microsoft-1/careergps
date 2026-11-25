#!/usr/bin/env bash
# Build both images, push them to GitHub Container Registry, and deploy them to Azure Container Apps.
# Safe to re-run: the first run creates everything, later runs only redeploy new images.
#
#   az login                                         # once
#   docker login ghcr.io -u <github-username>        # once; password = classic token with write:packages
#   ./deploy/azure.sh                                # from the repo root, with Docker running
#
# The packages must be public so Container Apps can pull them without credentials: after the first
# push, set each package to Public in GitHub (package -> Package settings -> Change visibility).
#
# Reads backend/.env (stored as Container Apps secrets for the API) and frontend/.env (Supabase
# public values). Override any name below in the environment, e.g. LOCATION=canadacentral ./deploy/azure.sh
set -euo pipefail
cd "$(dirname "$0")/.."

RG=${RG:-rg-careergps}
LOCATION=${LOCATION:-northcentralus}       # nearest allowed region to Supabase (us-east-2); Azure for Students
                                           # only allows some: az policy assignment list --query "[].parameters"
ENV_NAME=${ENV_NAME:-cae-careergps}
# Defaults to the repo's GitHub owner; set GHCR_OWNER=<your-username> if the org blocks packages.
GHCR_OWNER=${GHCR_OWNER:-$(git remote get-url origin | sed -E 's#.*github\.com[:/]([^/]+)/.*#\1#')}
API_APP=${API_APP:-careergps-api}
WEB_APP=${WEB_APP:-careergps-web}
TAG=$(git rev-parse --short HEAD)$(git diff --quiet HEAD || echo -dirty)

REGISTRY=ghcr.io/$(echo "$GHCR_OWNER" | tr '[:upper:]' '[:lower:]')   # ghcr names must be lowercase
API_IMAGE=$REGISTRY/careergps-api:$TAG
WEB_IMAGE=$REGISTRY/careergps-web:$TAG

for f in backend/.env frontend/.env; do [[ -f $f ]] || { echo "Missing $f" >&2; exit 1; }; done

echo "==> Resource group and Container Apps environment"
az provider register -n Microsoft.App --wait -o none
az group show -n "$RG" -o none 2>/dev/null || az group create -n "$RG" -l "$LOCATION" -o none
# No Log Analytics workspace (it bills per GB); live logs still work with `az containerapp logs show`.
az containerapp env show -n "$ENV_NAME" -g "$RG" -o none 2>/dev/null ||
  az containerapp env create -n "$ENV_NAME" -g "$RG" -l "$LOCATION" --logs-destination none -o none
# App URLs are https://<app>.<environment domain>, known only once the environment exists.
DOMAIN=$(az containerapp env show -n "$ENV_NAME" -g "$RG" --query properties.defaultDomain -o tsv)
API_URL=${API_URL:-https://$API_APP.$DOMAIN}
WEB_URL=${WEB_URL:-https://$WEB_APP.$DOMAIN}

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

# Container Apps pulls anonymously, so stop here (before creating apps) if a package is still private.
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

# backend/.env -> one secret per key (lowercase, dashes) and an env var that references it.
# MIGRATION_DATABASE_URL is left out: migrations are run by the database owner, not the app.
# shortcut: secret values pass as CLI arguments on this machine; use `--yaml` if that ever matters.
SECRETS=() ENV_VARS=()
while IFS= read -r -d '' pair; do
  key=${pair%%=*} name=$(echo "${pair%%=*}" | tr '[:upper:]_' '[:lower:]-')
  SECRETS+=("$name=${pair#*=}") ENV_VARS+=("$key=secretref:$name")
done < <(python3 - "$WEB_URL" <<'PY'
import sys
settings = {}
for line in open("backend/.env"):
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    settings[key.strip()] = value.strip().strip("'\"")
settings.pop("MIGRATION_DATABASE_URL", None)
settings["CORS_ORIGINS"] = sys.argv[1]
sys.stdout.write("".join(f"{k}={v}\0" for k, v in settings.items()))
PY
)

echo "==> API identity"
# Express environments (Azure picks that mode itself) reject system-assigned identities, so the API
# uses a user-assigned one. It outlives the app, so the Foundry role is granted only once.
IDENTITY=${IDENTITY:-id-careergps-api}
az identity show -n "$IDENTITY" -g "$RG" -o none 2>/dev/null || az identity create -n "$IDENTITY" -g "$RG" -l "$LOCATION" -o none
IDENTITY_ID=$(az identity show -n "$IDENTITY" -g "$RG" --query id -o tsv)
PRINCIPAL_ID=$(az identity show -n "$IDENTITY" -g "$RG" --query principalId -o tsv)
# DefaultAzureCredential picks the user-assigned identity by this client ID.
ENV_VARS+=("AZURE_CLIENT_ID=$(az identity show -n "$IDENTITY" -g "$RG" --query clientId -o tsv)")

echo "==> API app"
# An API app from before the switch still carries a system identity, which blocks every update.
# Recreating it keeps its URL; it holds no data beyond local files that a restart loses anyway.
if [[ $(az containerapp show -n "$API_APP" -g "$RG" --query identity.type -o tsv 2>/dev/null) == *SystemAssigned* ]]; then
  echo "Recreating $API_APP with the user-assigned identity"
  az containerapp delete -n "$API_APP" -g "$RG" --yes -o none
fi
if az containerapp show -n "$API_APP" -g "$RG" -o none 2>/dev/null; then
  az containerapp secret set -n "$API_APP" -g "$RG" --secrets "${SECRETS[@]}" -o none
  az containerapp update -n "$API_APP" -g "$RG" --image "$API_IMAGE" --set-env-vars "${ENV_VARS[@]}" -o none
else
  # Exactly one replica: résumé analysis runs on a background thread, and plan/run stores use
  # in-process locks and local files, so scaling to zero or out would lose work.
  az containerapp create -n "$API_APP" -g "$RG" --environment "$ENV_NAME" --image "$API_IMAGE" \
    --ingress external --target-port 8000 --cpu 0.5 --memory 1.0Gi --min-replicas 1 --max-replicas 1 \
    --user-assigned "$IDENTITY_ID" --secrets "${SECRETS[@]}" --env-vars "${ENV_VARS[@]}" -o none
fi

echo "==> Web app"
if az containerapp show -n "$WEB_APP" -g "$RG" -o none 2>/dev/null; then
  az containerapp update -n "$WEB_APP" -g "$RG" --image "$WEB_IMAGE" -o none
else
  # Scales to zero when idle: the first visit after a quiet spell waits a few seconds.
  az containerapp create -n "$WEB_APP" -g "$RG" --environment "$ENV_NAME" --image "$WEB_IMAGE" \
    --ingress external --target-port 3000 --cpu 0.25 --memory 0.5Gi --min-replicas 0 --max-replicas 1 -o none
fi

echo "==> Waiting for the API"
for _ in $(seq 30); do
  curl -fsS "$API_URL/health/db" && break
  sleep 10
done
echo

cat <<EOF

Deployed $TAG
  Frontend: $WEB_URL
  API:      $API_URL

First deploy only:
  1. Send the Foundry project owner the API's identity ($IDENTITY) and ask them to run:
       az role assignment create --assignee $PRINCIPAL_ID --role "Foundry User" --scope <Foundry resource ID>
  2. Supabase -> Authentication -> URL Configuration: Site URL $WEB_URL, add redirect URL $WEB_URL/**
Logs: az containerapp logs show -n $API_APP -g $RG --follow
EOF
