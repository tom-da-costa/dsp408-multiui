#!/usr/bin/env sh
# GitHub release helper for .github/workflows/release.yml (needs the gh CLI).
#
#   packaging/release.sh env          print the release settings for this push, as shell exports
#                                     (eval "$(packaging/release.sh env)")
#   packaging/release.sh prepare      create the release (rolling "main" release: recreate it on
#                                     the pushed commit, dropping the previous build's files)
#   packaging/release.sh upload FILE… attach files to the release (replacing same-name files)
#
# Env: GH_TOKEN and GH_REPO (owner/name) for gh, plus GITHUB_REF / GITHUB_REF_NAME / GITHUB_SHA
# from the runner.
#
# A push of tag vX.Y.Z publishes release vX.Y.Z. A push to main publishes the pre-release "main"
# (tag main-latest; a tag cannot be named like the branch): it always holds the latest build of
# main, with fixed file names such as dsp408-multiui-main-linux-amd64.
set -eu

ROLLING_TAG="main-latest"

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

case "${1:-}" in
  env)
    echo "$SETTINGS"
    ;;
  prepare)
    if [ "$ROLLING" = "true" ]; then
      # Recreate the rolling release on the new commit: drop the release and its tag first.
      gh release delete "$RELEASE_TAG" --cleanup-tag --yes >/dev/null 2>&1 || true
      gh release create "$RELEASE_TAG" --prerelease --latest=false --target "$GITHUB_SHA" \
        --title "$RELEASE_TITLE" --notes "Latest build of the \`main\` branch, updated on every \
push: commit $GITHUB_SHA, $(date -u '+%Y-%m-%d %H:%M UTC').

Not a versioned release: use it to try the current state. The files keep the same names from one \
build to the next, so download links stay valid."
    elif ! gh release view "$RELEASE_TAG" >/dev/null 2>&1; then
      gh release create "$RELEASE_TAG" --verify-tag --title "$RELEASE_TITLE" --generate-notes \
        || gh release view "$RELEASE_TAG" >/dev/null  # another job may have created it meanwhile
    fi
    echo "release $RELEASE_TAG ready for $GITHUB_SHA"
    ;;
  upload)
    shift
    [ "$#" -gt 0 ] || { echo "nothing to upload" >&2; exit 1; }
    gh release upload "$RELEASE_TAG" "$@" --clobber
    ;;
  *)
    echo "usage: $0 env | prepare | upload FILE..." >&2
    exit 2
    ;;
esac
