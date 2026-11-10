# Distribution and releases

The launch modes of the [README](../README.md#usage) and how each is produced.

| Mode | Built by | Output |
|---|---|---|
| `uv run` from a clone | nothing to build: the UI build is committed in `src/tracks_dsp_controller/web/` | — |
| Standalone executable | `packaging/exe.Dockerfile` (Linux, any arch) and `packaging/build_exe.sh` (Windows runner) | `tracks-dsp-controller-vX.Y.Z-linux-amd64`, `…-linux-arm64`, `…-windows-amd64.exe`, plus the simulator `tracks-dsp-sim-vX.Y.Z-…` for each, attached to the GitHub release |
| `docker run` / `docker compose` | `Dockerfile` (multi-arch with buildx) | `ghcr.io/tom-da-costa/tracks-dsp-controller:X.Y.Z` and `:latest` (`:main` for the rolling build) |

## The rolling "main" release

Every push to `main` publishes the pre-release **main** (git tag `main-latest`: a tag cannot share
the branch's name). It is rebuilt from scratch on each push. The release and its tag are recreated
on the new commit, so it only ever holds the latest build. Its files keep fixed names, so links stay valid:

```
https://github.com/tom-da-costa/tracks-dsp-controller/releases/download/main-latest/tracks-dsp-controller-main-linux-amd64
https://github.com/tom-da-costa/tracks-dsp-controller/releases/download/main-latest/tracks-dsp-sim-main-windows-amd64.exe
```

Nothing is published unless the unit and end-to-end tests pass on that commit. The Docker image is
tagged `:main`. Being a pre-release, it never shows as the "latest release".

## Keeping the committed UI up to date

After any change in `web/`, run `make web` and commit `src/tracks_dsp_controller/web/` together with the
sources. The `web` CI job rebuilds the UI and fails if the committed build differs.

## Making a release

1. Set `version = "X.Y.Z"` in `pyproject.toml`, run `uv lock`, commit
   `chore: release X.Y.Z` directly on `main` (no pull request) and push.
2. Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. `.github/workflows/release.yml` (the same workflow builds the rolling "main" release):
   1. checks that the tag matches the version and runs the tests;
   2. creates the release (`packaging/release.sh prepare`, with the `gh` CLI);
   3. builds the executables (app and `tracks-dsp-sim`, per platform), runs `--version` on each and
      attaches them;
   4. builds and pushes the multi-arch Docker image to `ghcr.io`.

## How the release jobs build

Everything runs on GitHub-hosted runners with the automatic Actions token: no secret to set up.

| Job | Runner | How |
|---|---|---|
| `exe-linux` amd64 | `ubuntu-24.04` | `packaging/exe.Dockerfile` (Debian bookworm, so the executable runs on glibc ≥ 2.36: Debian 12, Raspberry Pi OS bookworm, Ubuntu 24.04) |
| `exe-linux` arm64 | `ubuntu-24.04-arm` | same Dockerfile, built natively on the arm64 runner (no emulation) |
| `exe-windows` | `windows-latest` | `packaging/build_exe.sh` under Git Bash, Python 3.12 from `actions/setup-python` |
| `docker` | `ubuntu-latest` | `docker/build-push-action`, amd64 + arm64 (arm64 through QEMU), layer cache in the Actions cache |

The first push creates the `tracks-dsp-controller` package on `ghcr.io`. GitHub makes a new package
private: set it to **public** once, in the package settings (Package settings › Change
visibility), so that `docker pull` works without logging in.

## Building locally

```bash
# Linux executable for this machine's architecture
docker buildx build --build-arg NAME=tracks-dsp-controller-linux-amd64 -f packaging/exe.Dockerfile -o dist .
# Linux arm64 on an amd64 machine (needs QEMU binfmt:
#   docker run --privileged --rm tonistiigi/binfmt --install arm64)
docker buildx build --platform linux/arm64 --build-arg NAME=tracks-dsp-controller-linux-arm64 \
  -f packaging/exe.Dockerfile -o dist .
# Windows, cross-built with Wine (the release uses a real Windows runner instead)
docker buildx build --build-arg NAME=tracks-dsp-controller-windows-amd64 -f packaging/windows.Dockerfile -o dist .
# Docker image
docker build -t tracks-dsp-controller .
```

Without Docker, `packaging/build_exe.sh` builds the executables (app and simulator) for the
current platform; it needs Python ≥ 3.12 and uv.

## Status of the artefacts

| Artefact | Built | Smoke-tested |
|---|---|---|
| Docker image (amd64) | yes, 236 MB | yes: demo mode, `/api/health`, Docker `HEALTHCHECK` reports healthy; `compose.sim.yaml` (app + `tracks-dsp-sim`) online |
| Linux amd64 executable | yes, 34 MB | yes: `--version`, demo mode, UI served |
| Linux amd64 `tracks-dsp-sim` executable | yes, 10 MB | `--version` |
| Windows amd64 executable | in CI, on a Windows runner | `--version` in CI. The earlier Wine cross-build failed to load `python312.dll` under Wine; still to be checked by hand on a real Windows machine |
| Linux arm64 executable, arm64 image | in CI (native arm64 runner; image through QEMU) | `--version` in CI for the executable |
