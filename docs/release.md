# Distribution and releases

The four launch modes of [SPEC §7.1](SPEC.md) and how each is produced.

| Mode | Built by | Output |
|---|---|---|
| `uv run` from a clone | nothing to build: the UI build is committed in `src/dsp408_multiui/web/` | — |
| Standalone executable | `packaging/exe.Dockerfile` (Linux, any arch) and `packaging/windows.Dockerfile` (Wine) | `dsp408-multiui-vX.Y.Z-linux-amd64`, `…-linux-arm64`, `…-windows-amd64.exe`, attached to the Gitea release |
| `docker run` / `docker compose` | `Dockerfile` (multi-arch with buildx) | `<gitea-host>/lord/dsp408-multiui:X.Y.Z` and `:latest` in the Gitea container registry |

## Keeping the committed UI up to date

After any change in `web/`, run `make web` and commit `src/dsp408_multiui/web/` together with the
sources. The `web` CI job rebuilds the UI and fails if the committed build differs.

## Making a release

1. Set `version = "X.Y.Z"` in `pyproject.toml`, run `uv lock`, update `docs/PROGRESS.md`, merge to
   `main`.
2. Tag and push: `git tag vX.Y.Z && git push origin vX.Y.Z`.
3. `.gitea/workflows/release.yaml`:
   1. checks that the tag matches the version;
   2. builds the three executables and attaches them to the release (it creates the release if
      needed);
   3. builds and pushes the multi-arch Docker image.

## Runner prerequisites

The release jobs run `docker buildx` from inside the job container. The Gitea Docker runner must
therefore:

- **give jobs access to a Docker daemon**: mount `/var/run/docker.sock` into job containers (in the
  `act_runner` config: `container.valid_volumes` and `container.options: -v
  /var/run/docker.sock:/var/run/docker.sock`), or use a runner label that runs on the host;
- **emulate arm64**: register QEMU once on the runner host with
  `docker run --privileged --rm tonistiigi/binfmt --install arm64`;
- provide a **`REGISTRY_TOKEN` secret** in the repository: a personal access token with package
  write access, used to push the image.

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

Without Docker, `packaging/build_exe.sh` builds the executable for the current platform; it needs
Python ≥ 3.12 and uv.

## Status of the artefacts

| Artefact | Built | Smoke-tested |
|---|---|---|
| Docker image (amd64) | yes, 236 MB | yes: `--simulator`, `/api/health`, Docker `HEALTHCHECK` reports healthy |
| Linux amd64 executable | yes, 34 MB | yes: `--version`, `--simulator`, UI served |
| Windows amd64 executable | yes, 14 MB | **no**: under Wine it fails to load `python312.dll` ("DLL initialization failed"). This is probably a Wine limitation with PyInstaller one-file executables; it must be checked on a real Windows machine |
| Linux arm64 executable, arm64 image | not yet (no QEMU on the development machine) | — |
