#!/usr/bin/env sh
# Gitea release helper for .gitea/workflows/release.yaml.
#
#   packaging/release.sh env          print the release settings for this push, as shell exports
#                                     (eval "$(packaging/release.sh env)")
#   packaging/release.sh prepare      create the release (rolling "main" release: recreate it on
#                                     the pushed commit, dropping the previous build's files)
#   packaging/release.sh upload FILE… attach files to the release (replacing same-name files)
#
# Env: GITEA_URL (e.g. https://gitea.example), GITEA_REPO (owner/name), GITEA_TOKEN, plus
# GITHUB_REF / GITHUB_REF_NAME / GITHUB_SHA from the runner.
#
# A push of tag vX.Y.Z publishes release vX.Y.Z. A push to main publishes the pre-release "main"
# (tag main-latest; a tag cannot be named like the branch): it always holds the latest build of
# main, with fixed file names such as dsp408-multiui-main-linux-amd64.
set -eu

ROLLING_TAG="main-latest"
API="${GITEA_URL%/}/api/v1/repos/${GITEA_REPO}"

settings() {
  case "${GITHUB_REF:-}" in
    refs/tags/v*)
      echo "RELEASE_TAG=${GITHUB_REF_NAME}"
      echo "RELEASE_TITLE=${GITHUB_REF_NAME}"
      echo "ASSET_VERSION=${GITHUB_REF_NAME}"
      echo "ROLLING=false"
      echo "IMAGE_TAGS=${GITHUB_REF_NAME#v} latest"
      ;;
    refs/heads/main)
      echo "RELEASE_TAG=${ROLLING_TAG}"
      echo "RELEASE_TITLE=main"
      echo "ASSET_VERSION=main"
      echo "ROLLING=true"
      echo "IMAGE_TAGS=main"
      ;;
    *)
      echo "unsupported ref ${GITHUB_REF:-<none>}: push a vX.Y.Z tag or to main" >&2
      exit 1
      ;;
  esac
}

SETTINGS="$(settings | sed 's/^/export /; s/=\(.*\)$/="\1"/')"
eval "$SETTINGS"

call() {  # call METHOD PATH [curl args…]: prints the body, fails on HTTP >= 400
  method="$1"; path="$2"; shift 2
  curl -fsS -X "$method" -H "Authorization: token ${GITEA_TOKEN}" "$@" "$API$path"
}

release_id() {
  call GET "/releases/tags/$RELEASE_TAG" 2>/dev/null \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' 2>/dev/null || true
}

create_release() {
  body="$1"
  python3 - "$RELEASE_TAG" "$RELEASE_TITLE" "$GITHUB_SHA" "$ROLLING" "$body" > /tmp/release.json <<'EOF'
import json, sys
tag, title, sha, rolling, body = sys.argv[1:]
print(json.dumps({"tag_name": tag, "name": title, "target_commitish": sha, "body": body,
                  "prerelease": rolling == "true"}))
EOF
  call POST "/releases" -H "Content-Type: application/json" -d @/tmp/release.json >/dev/null
}

case "${1:-}" in
  env)
    echo "$SETTINGS"
    ;;
  prepare)
    if [ "$ROLLING" = "true" ]; then
      # Recreate the rolling release on the new commit: drop the release and its tag first.
      call DELETE "/releases/tags/$RELEASE_TAG" >/dev/null 2>&1 || true
      call DELETE "/tags/$RELEASE_TAG" >/dev/null 2>&1 || true
      # A bare SHA: Gitea links it (GITEA_URL is the runner's internal address).
      create_release "Latest build of the \`main\` branch, updated on every push: commit \
$GITHUB_SHA, $(date -u '+%Y-%m-%d %H:%M UTC').

Not a versioned release: use it to try the current state. The files keep the same names from one \
build to the next, so download links stay valid."
    elif [ -z "$(release_id)" ]; then
      create_release "See docs/PROGRESS.md for what changed." \
        || [ -n "$(release_id)" ]  # another job may have created it meanwhile
    fi
    echo "release $RELEASE_TAG ($(release_id)) ready for $GITHUB_SHA"
    ;;
  upload)
    shift
    ID="$(release_id)"
    [ -n "$ID" ] || { echo "cannot find release $RELEASE_TAG" >&2; exit 1; }
    for FILE in "$@"; do
      NAME="$(basename "$FILE")"
      OLD="$(call GET "/releases/$ID/assets" | python3 -c '
import json, sys
print(" ".join(str(a["id"]) for a in json.load(sys.stdin) if a["name"] == sys.argv[1]))' "$NAME")"
      for A in $OLD; do call DELETE "/releases/$ID/assets/$A" >/dev/null; done
      echo "uploading $NAME to release $RELEASE_TAG ($ID)"
      call POST "/releases/$ID/assets?name=$NAME" -F "attachment=@$FILE" >/dev/null
    done
    ;;
  *)
    echo "usage: $0 env | prepare | upload FILE..." >&2
    exit 2
    ;;
esac
