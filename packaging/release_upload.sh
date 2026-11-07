#!/usr/bin/env sh
# Attach files to the Gitea release of a tag, creating the release if needed.
# Usage: packaging/release_upload.sh <tag> <file>...
# Env: GITEA_URL (e.g. https://gitea.example), GITEA_REPO (owner/name), GITEA_TOKEN.
set -eu
TAG="$1"; shift
API="${GITEA_URL%/}/api/v1/repos/${GITEA_REPO}"
AUTH="Authorization: token ${GITEA_TOKEN}"

release_id() {
  curl -fsS -H "$AUTH" "$API/releases/tags/$TAG" 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' 2>/dev/null || true
}

ID="$(release_id)"
if [ -z "$ID" ]; then
  curl -fsS -X POST -H "$AUTH" -H "Content-Type: application/json" \
    -d "{\"tag_name\": \"$TAG\", \"name\": \"$TAG\", \"body\": \"See docs/PROGRESS.md for what changed.\"}" \
    "$API/releases" >/dev/null || true   # another job may have created it meanwhile
  ID="$(release_id)"
fi
[ -n "$ID" ] || { echo "cannot find or create release $TAG" >&2; exit 1; }

for FILE in "$@"; do
  NAME="$(basename "$FILE")"
  echo "uploading $NAME to release $TAG ($ID)"
  curl -fsS -X POST -H "$AUTH" -F "attachment=@$FILE" "$API/releases/$ID/assets?name=$NAME" >/dev/null
done
