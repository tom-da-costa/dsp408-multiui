# Distribution and releases

The four launch modes of [SPEC §7.1](SPEC.md) and how each is produced.

| Mode | Built by | Output |
|---|---|---|
| `uv run` from a clone | nothing to build: the UI build is committed in `src/dsp408_multiui/web/` | — |
| Standalone executable | `packaging/exe.Dockerfile` (Linux, any arch) and `packaging/windows.Dockerfile` (Wine) | `dsp408-multiui-vX.Y.Z-linux-amd64`, `…-linux-arm64`, `…-windows-amd64.exe`, plus the simulator `dsp408-sim-vX.Y.Z-…` for each, attached to the Gitea release |
| `docker run` / `docker compose` | `Dockerfile` (multi-arch with buildx) | `<gitea-host>/lord/dsp408-multiui:X.Y.Z` and `:latest` in the Gitea container registry (`:main` for the rolling build) |

## The rolling "main" release

Every push to `main` publishes the pre-release **main** (git tag `main-latest`: a tag cannot share
the branch's name). It is rebuilt from scratch on each push. The release and its tag are recreated
on the new commit, so it only ever holds the latest build. Its files keep fixed names, so links stay valid:

```
<gitea>/lord/dsp408-multiui/releases/download/main-latest/dsp408-multiui-main-linux-amd64
<gitea>/lord/dsp408-multiui/releases/download/main-latest/dsp408-sim-main-windows-amd64.exe
```

Nothing is published unless the unit and end-to-end tests pass on that commit. The Docker image is
tagged `:main`. Being a pre-release, it never shows as the "latest release".

## Keeping the committed UI up to date

After any change in `web/`, run `make web` and commit `src/dsp408_multiui/web/` together with the
sources. The `web` CI job rebuilds the UI and fails if the committed build differs.

## Making a release

1. Set `version = "X.Y.Z"` in `pyproject.toml`, run `uv lock`, update `docs/PROGRESS.md`, merge to
   `main`.
2. Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. `.gitea/workflows/release.yaml` (the same workflow builds the rolling "main" release):
   1. checks that the tag matches the version and runs the tests;
   2. creates the release (`packaging/release.sh prepare`);
   3. builds the executables (app and `dsp408-sim`, per platform) and attaches them;
   4. builds and pushes the Docker image.

## Runner prerequisites

The release jobs run `docker buildx` from inside the job container. The Gitea Docker runner must
therefore:

- **give jobs access to a Docker daemon**: mount `/var/run/docker.sock` into job containers (in the
  `act_runner` config: `container.valid_volumes` and `container.options: -v
  /var/run/docker.sock:/var/run/docker.sock`), or use a runner label that runs on the host;
- **emulate arm64** (optional): register QEMU on the runner host with
  `docker run --privileged --rm tonistiigi/binfmt --install arm64` (again after each reboot of the
  host, unless the binfmt service of the host's distribution does it). Without it, the arm64
  executables and the arm64 image are skipped with a warning;
- provide a **`REGISTRY_TOKEN` secret** (optional) in the repository: a personal access token with
  the `write:package` scope. The automatic Actions token cannot push packages
  (`reqPackageAccess`). Without it, the Docker image is skipped with a warning;
- set the **`REGISTRY` variable** to the registry host as the runner's Docker daemon reaches it
  (here `cas.lan.leou.ovh:8443`). By default the host comes from the server URL, which inside
  the runner is the internal `cas:3000`, and the Docker daemon cannot reach that.

Checked on the current runner (2026-11-09): Docker socket and buildx available; no QEMU binfmt;
the Actions token can manage releases but not push packages.

The executables are built through `docker buildx build -o dist`, which sends the build context,
so they work even though the job container's `$PWD` does not exist on the host. A plain
`docker run -v "$PWD":…` would not.

## Building locally

```bash
# Linux executable for this machine's architecture
docker buildx build --build-arg NAME=dsp408-multiui-linux-amd64 -f packaging/exe.Dockerfile -o dist .
# Linux arm64 (needs QEMU binfmt, see above)
docker buildx build --platform linux/arm64 --build-arg NAME=dsp408-multiui-linux-arm64 \
  -f packaging/exe.Dockerfile -o dist .
# Windows (cross-built with Wine)
docker buildx build --build-arg NAME=dsp408-multiui-windows-amd64 -f packaging/windows.Dockerfile -o dist .
# Docker image
docker build -t dsp408-multiui .
```

Without Docker, `packaging/build_exe.sh` builds the executables (app and simulator) for the
current platform; it needs Python ≥ 3.12 and uv.

## Status of the artefacts

| Artefact | Built | Smoke-tested |
|---|---|---|
| Docker image (amd64) | yes, 236 MB | yes: demo mode, `/api/health`, Docker `HEALTHCHECK` reports healthy; `compose.sim.yaml` (app + `dsp408-sim`) online |
| Linux amd64 executable | yes, 34 MB | yes: `--version`, demo mode, UI served |
| Linux amd64 `dsp408-sim` executable | yes, 10 MB | `--version` |
| Windows amd64 executable | yes, 14 MB | **no**: under Wine it fails to load `python312.dll` ("DLL initialization failed"). This is probably a Wine limitation with PyInstaller one-file executables; it must be checked on a real Windows machine |
| Linux arm64 executable, arm64 image | not yet (no QEMU on the development machine) | — |
