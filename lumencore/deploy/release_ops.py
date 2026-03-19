from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from gzip import GzipFile
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
LUMENCORE_ROOT = SCRIPT_DIR.parent
WORKSPACE_ROOT = LUMENCORE_ROOT.parent
DOCS_ROOT = WORKSPACE_ROOT / "docs"
DEFAULT_TARGET_ROOT = Path("/opt/lumencore")
ACTIVE_RELEASE_FILE = ".release_state/ACTIVE_RELEASE"
PREVIOUS_RELEASE_FILE = ".release_state/PREVIOUS_RELEASE"
NONE_RELEASE = "NONE"
DEPLOY_MODE = "target_build_from_staged_release_manifest_and_package"
ROLLBACK_MODE = "target_build_from_previously_staged_release_manifest_and_package"
DEFAULT_RELEASE_FILESET = [
    LUMENCORE_ROOT / "docker-compose.phase2.yml",
    LUMENCORE_ROOT / ".env.example",
    LUMENCORE_ROOT / "services" / "api" / "Dockerfile",
    LUMENCORE_ROOT / "services" / "api" / "requirements.txt",
    LUMENCORE_ROOT / "services" / "api" / "app",
    LUMENCORE_ROOT / "deploy" / "RELEASE_OPS.md",
    DOCS_ROOT / "RELEASE_MANIFEST.md",
    DOCS_ROOT / "CONTROLLED_LAUNCH_CHECKLIST.md",
    DOCS_ROOT / "DECISIONS.md",
    DOCS_ROOT / "IMPLEMENTATION_STATUS.md",
]


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_release_files() -> list[Path]:
    collected: list[Path] = []
    for item in DEFAULT_RELEASE_FILESET:
        if not item.exists():
            raise FileNotFoundError(f"missing release file: {item}")
        if item.is_dir():
            for child in sorted(path for path in item.rglob("*") if path.is_file()):
                collected.append(child)
        else:
            collected.append(item)
    return sorted(set(collected), key=lambda path: path.as_posix())


def _relative_manifest_path(path: Path) -> str:
    if path.is_relative_to(WORKSPACE_ROOT):
        return path.relative_to(WORKSPACE_ROOT).as_posix()
    raise ValueError(f"path outside workspace root: {path}")


def build_manifest(*, release_id: str, rollback_release_id: str | None = None) -> dict[str, Any]:
    files = _iter_release_files()
    release_files: list[dict[str, Any]] = []
    for path in files:
        release_files.append(
            {
                "path": _relative_manifest_path(path),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )

    manifest: dict[str, Any] = {
        "release_id": release_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "system_phase": "27",
        "deploy_mode": DEPLOY_MODE,
        "rollback_mode": ROLLBACK_MODE,
        "workspace_root": str(WORKSPACE_ROOT),
        "lumencore_root": str(LUMENCORE_ROOT),
        "deploy_target": {
            "root": "/opt/lumencore",
            "compose_file": "/opt/lumencore/docker-compose.phase2.yml",
            "env_file": "/opt/lumencore/.env",
            "api_source_root": "/opt/lumencore/services/api",
            "api_app_root": "/opt/lumencore/services/api/app",
            "active_release_file": f"/opt/lumencore/{ACTIVE_RELEASE_FILE}",
            "previous_release_file": f"/opt/lumencore/{PREVIOUS_RELEASE_FILE}",
        },
        "services": [
            {
                "name": "lumencore-api",
                "build_context": "/opt/lumencore/services/api",
                "dockerfile": "/opt/lumencore/services/api/Dockerfile",
                "runtime_entrypoint": "uvicorn app.main:app --host 0.0.0.0 --port 8000",
            },
            {
                "name": "lumencore-worker",
                "build_context": "/opt/lumencore/services/api",
                "dockerfile": "/opt/lumencore/services/api/Dockerfile",
                "runtime_entrypoint": "celery -A app.worker_tasks worker",
            },
            {
                "name": "lumencore-scheduler",
                "build_context": "/opt/lumencore/services/api",
                "dockerfile": "/opt/lumencore/services/api/Dockerfile",
                "runtime_entrypoint": "celery -A app.worker_tasks beat",
            },
        ],
        "health_contract": {
            "public_liveness": ["/health"],
            "canonical_release_truth": ["/api/system/health", "/api/system/execution-summary", "/api/operator/summary"],
            "required_status": {
                "/api/system/health": "ok",
            },
        },
        "scope": {
            "enabled_connector_paths": ["search.web_search"],
            "disabled_connectors": ["git"],
            "deferred": ["OpenClaw integration", "remote dispatch", "node execution authority"],
        },
        "rollback": {
            "strategy": "re-deploy previous staged release manifest and package using target rebuild",
            "previous_release_id": rollback_release_id,
        },
        "release_files": release_files,
    }

    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    manifest["manifest_sha256"] = _sha256_bytes(manifest_bytes)
    return manifest


def write_manifest(*, manifest: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output_path


def package_release(*, manifest: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
    with output_path.open("wb") as raw_file:
        with GzipFile(filename="", mode="wb", fileobj=raw_file, mtime=0) as gz_file:
            with tarfile.open(fileobj=gz_file, mode="w") as tar:
                manifest_info = tarfile.TarInfo(name=f"{manifest['release_id']}/release-manifest.json")
                manifest_info.size = len(manifest_bytes)
                manifest_info.mtime = 0
                manifest_info.uid = 0
                manifest_info.gid = 0
                manifest_info.uname = "root"
                manifest_info.gname = "root"
                tar.addfile(manifest_info, io.BytesIO(manifest_bytes))

                for entry in manifest["release_files"]:
                    source_path = WORKSPACE_ROOT / Path(entry["path"])
                    data = source_path.read_bytes()
                    info = tarfile.TarInfo(name=f"{manifest['release_id']}/{entry['path']}")
                    info.size = len(data)
                    info.mtime = 0
                    info.uid = 0
                    info.gid = 0
                    info.uname = "root"
                    info.gname = "root"
                    tar.addfile(info, io.BytesIO(data))
    return output_path


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _write_env_value(*, env_path: Path, release_id: str, manifest_sha256: str, system_phase: str) -> None:
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    filtered: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if stripped.startswith("LUMENCORE_SYSTEM_PHASE=") or stripped.startswith("LUMENCORE_RELEASE_ID=") or stripped.startswith("LUMENCORE_RELEASE_MANIFEST_SHA256="):
            continue
        filtered.append(raw)
    filtered.extend(
        [
            f"LUMENCORE_SYSTEM_PHASE={system_phase}",
            f"LUMENCORE_RELEASE_ID={release_id}",
            f"LUMENCORE_RELEASE_MANIFEST_SHA256={manifest_sha256}",
        ]
    )
    env_path.write_text("\n".join(filtered) + "\n", encoding="utf-8")


def _state_file(target_root: Path, relative_path: str) -> Path:
    return target_root / relative_path


def _read_release_state(target_root: Path, relative_path: str) -> str:
    path = _state_file(target_root, relative_path)
    if not path.exists():
        return NONE_RELEASE
    value = path.read_text(encoding="utf-8").strip()
    return value or NONE_RELEASE


def _write_release_state(target_root: Path, relative_path: str, release_id: str) -> Path:
    path = _state_file(target_root, relative_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text((release_id or NONE_RELEASE) + "\n", encoding="utf-8")
    return path


def _load_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    required = ["release_id", "manifest_sha256", "system_phase", "deploy_target"]
    missing = [key for key in required if key not in manifest]
    if missing:
        raise RuntimeError(f"manifest missing keys: {', '.join(missing)}")
    return manifest


def _verify_package(package_path: Path, release_id: str) -> None:
    if not package_path.exists():
        raise FileNotFoundError(f"missing release package: {package_path}")
    with tarfile.open(package_path, mode="r:gz") as tar:
        names = tar.getnames()
    expected_manifest_entry = f"{release_id}/release-manifest.json"
    if expected_manifest_entry not in names:
        raise RuntimeError(f"package missing manifest entry: {expected_manifest_entry}")


def verify_target(*, target_root: Path, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    expected = {
        "target_root": target_root,
        "compose_file": target_root / "docker-compose.phase2.yml",
        "env_file": target_root / ".env",
        "api_root": target_root / "services" / "api",
        "api_app_root": target_root / "services" / "api" / "app",
        "api_main": target_root / "services" / "api" / "app" / "main.py",
        "dockerfile": target_root / "services" / "api" / "Dockerfile",
        "active_release_file": _state_file(target_root, ACTIVE_RELEASE_FILE),
        "previous_release_file": _state_file(target_root, PREVIOUS_RELEASE_FILE),
    }
    for name, path in expected.items():
        ok = path.exists() or name in {"active_release_file", "previous_release_file"}
        checks.append({"name": name, "path": str(path), "ok": ok})

    duplicate_root = target_root / "lumencore" / "services" / "api"
    duplicate_exists = duplicate_root.exists()
    checks.append(
        {
            "name": "unexpected_nested_release_root",
            "path": str(duplicate_root),
            "ok": not duplicate_exists,
            "detail": "nested lumencore/services/api tree must not exist under deploy root",
        }
    )

    env_values = _parse_env_file(expected["env_file"])
    if manifest is not None:
        checks.append(
            {
                "name": "release_id_match",
                "path": str(expected["env_file"]),
                "ok": env_values.get("LUMENCORE_RELEASE_ID") == manifest.get("release_id"),
                "expected": manifest.get("release_id"),
                "actual": env_values.get("LUMENCORE_RELEASE_ID"),
            }
        )
        checks.append(
            {
                "name": "manifest_sha_match",
                "path": str(expected["env_file"]),
                "ok": env_values.get("LUMENCORE_RELEASE_MANIFEST_SHA256") == manifest.get("manifest_sha256"),
                "expected": manifest.get("manifest_sha256"),
                "actual": env_values.get("LUMENCORE_RELEASE_MANIFEST_SHA256"),
            }
        )

    return {
        "target_root": str(target_root),
        "ok": all(item["ok"] for item in checks),
        "checks": checks,
    }


def _run_checked(command: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(command, cwd=str(cwd) if cwd else None, check=True)


def _verify_runtime_health(base_url: str, *, retries: int = 12, delay_seconds: float = 2.0) -> dict[str, Any]:
    system_health_url = f"{base_url.rstrip('/')}/api/system/health"
    operator_summary_url = f"{base_url.rstrip('/')}/api/operator/summary"
    last_error: str | None = None

    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(system_health_url, timeout=5) as response:
                system_health = json.loads(response.read().decode("utf-8"))
            if system_health.get("status") != "ok":
                last_error = f"system health not ok: {system_health}"
            else:
                with urllib.request.urlopen(operator_summary_url, timeout=5) as response:
                    operator_summary = json.loads(response.read().decode("utf-8"))
                return {
                    "system_health": system_health,
                    "operator_summary": {
                        "counts": operator_summary.get("counts"),
                        "system_health": operator_summary.get("system_health"),
                    },
                    "health_attempts": attempt,
                }
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
            last_error = str(exc)

        if attempt < retries:
            time.sleep(delay_seconds)

    raise RuntimeError(f"runtime health verification failed after {retries} attempts: {last_error}")


def _manifest_path_for_release(target_root: Path, release_id: str) -> Path:
    return target_root / "docs" / "releases" / f"{release_id}.release-manifest.json"


def _package_path_for_release(target_root: Path, release_id: str) -> Path:
    return target_root / "releases" / f"{release_id}.tar.gz"


def deploy_release(*, target_root: Path, manifest_path: Path, package_path: Path, health_base_url: str) -> dict[str, Any]:
    manifest = _load_manifest(manifest_path)
    release_id = str(manifest["release_id"])
    structural_verify = verify_target(target_root=target_root, manifest=None)
    if not structural_verify["ok"]:
        raise RuntimeError(json.dumps(structural_verify, indent=2))
    _verify_package(package_path, release_id)
    current_active = _read_release_state(target_root, ACTIVE_RELEASE_FILE)
    current_active = _read_release_state(target_root, ACTIVE_RELEASE_FILE)
    current_previous = _read_release_state(target_root, PREVIOUS_RELEASE_FILE)
    fallback_previous = str(manifest.get("rollback", {}).get("previous_release_id") or NONE_RELEASE)
    if current_active == release_id:
        previous_release = current_previous if current_previous not in {NONE_RELEASE, release_id} else fallback_previous
    else:
        previous_release = current_active if current_active != NONE_RELEASE else fallback_previous

    env_path = target_root / ".env"
    _write_env_value(
        env_path=env_path,
        release_id=release_id,
        manifest_sha256=str(manifest["manifest_sha256"]),
        system_phase=str(manifest.get("system_phase", "27")),
    )

    compose_file = target_root / "docker-compose.phase2.yml"
    _run_checked(["docker", "compose", "--env-file", str(env_path), "-f", str(compose_file), "build", "lumencore-api"])
    _run_checked(
        [
            "docker", "compose", "--env-file", str(env_path), "-f", str(compose_file), "up", "-d", "--no-deps", "--force-recreate",
            "lumencore-api", "lumencore-worker", "lumencore-scheduler",
        ]
    )

    health = _verify_runtime_health(health_base_url)
    _write_release_state(target_root, ACTIVE_RELEASE_FILE, release_id)
    _write_release_state(target_root, PREVIOUS_RELEASE_FILE, previous_release)

    return {
        "deploy_mode": DEPLOY_MODE,
        "active_release": release_id,
        "previous_release": previous_release,
        "manifest_path": str(manifest_path),
        "package_path": str(package_path),
        "health": health,
    }


def rollback_release(*, target_root: Path, health_base_url: str) -> dict[str, Any]:
    current_active = _read_release_state(target_root, ACTIVE_RELEASE_FILE)
    previous_release = _read_release_state(target_root, PREVIOUS_RELEASE_FILE)
    if previous_release == NONE_RELEASE:
        raise RuntimeError("rollback blocked: PREVIOUS_RELEASE is NONE")

    manifest_path = _manifest_path_for_release(target_root, previous_release)
    package_path = _package_path_for_release(target_root, previous_release)
    if not manifest_path.exists() or not package_path.exists():
        raise FileNotFoundError(
            "rollback blocked: missing previous release artifacts "
            f"manifest={manifest_path.exists()} package={package_path.exists()} "
            f"manifest_path={manifest_path} package_path={package_path}"
        )

    manifest = _load_manifest(manifest_path)
    structural_verify = verify_target(target_root=target_root, manifest=None)
    if not structural_verify["ok"]:
        raise RuntimeError(json.dumps(structural_verify, indent=2))
    _verify_package(package_path, previous_release)

    env_path = target_root / ".env"
    _write_env_value(
        env_path=env_path,
        release_id=previous_release,
        manifest_sha256=str(manifest["manifest_sha256"]),
        system_phase=str(manifest.get("system_phase", "27")),
    )

    compose_file = target_root / "docker-compose.phase2.yml"
    _run_checked(["docker", "compose", "--env-file", str(env_path), "-f", str(compose_file), "build", "lumencore-api"])
    _run_checked(
        [
            "docker", "compose", "--env-file", str(env_path), "-f", str(compose_file), "up", "-d", "--no-deps", "--force-recreate",
            "lumencore-api", "lumencore-worker", "lumencore-scheduler",
        ]
    )

    health = _verify_runtime_health(health_base_url)
    _write_release_state(target_root, ACTIVE_RELEASE_FILE, previous_release)
    _write_release_state(target_root, PREVIOUS_RELEASE_FILE, current_active)

    return {
        "rollback_mode": ROLLBACK_MODE,
        "active_release": previous_release,
        "previous_release": current_active,
        "manifest_path": str(manifest_path),
        "package_path": str(package_path),
        "health": health,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Release-ops tooling for Lumencore Phase 27")
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest_parser = subparsers.add_parser("manifest", help="Generate a release manifest")
    manifest_parser.add_argument("--release-id", required=True)
    manifest_parser.add_argument("--rollback-release-id", default=None)
    manifest_parser.add_argument("--output", required=True)

    package_parser = subparsers.add_parser("package", help="Generate a release manifest and deterministic tar.gz package")
    package_parser.add_argument("--release-id", required=True)
    package_parser.add_argument("--rollback-release-id", default=None)
    package_parser.add_argument("--manifest-output", required=True)
    package_parser.add_argument("--package-output", required=True)

    verify_parser = subparsers.add_parser("verify-target", help="Verify a deploy target against the canonical layout")
    verify_parser.add_argument("--target-root", required=True)
    verify_parser.add_argument("--manifest", default=None)

    deploy_parser = subparsers.add_parser("deploy", help="Canonical deploy entrypoint for a staged release")
    deploy_parser.add_argument("--target-root", required=True)
    deploy_parser.add_argument("--manifest", required=True)
    deploy_parser.add_argument("--package", required=True)
    deploy_parser.add_argument("--health-base-url", default="http://127.0.0.1")

    rollback_parser = subparsers.add_parser("rollback", help="Canonical rollback entrypoint for the staged previous release")
    rollback_parser.add_argument("--target-root", required=True)
    rollback_parser.add_argument("--health-base-url", default="http://127.0.0.1")

    args = parser.parse_args()

    if args.command == "manifest":
        manifest = build_manifest(release_id=args.release_id, rollback_release_id=args.rollback_release_id)
        path = write_manifest(manifest=manifest, output_path=Path(args.output))
        print(json.dumps({"manifest_path": str(path), "release_id": manifest["release_id"], "manifest_sha256": manifest["manifest_sha256"]}, indent=2))
        return

    if args.command == "package":
        manifest = build_manifest(release_id=args.release_id, rollback_release_id=args.rollback_release_id)
        manifest_path = write_manifest(manifest=manifest, output_path=Path(args.manifest_output))
        package_path = package_release(manifest=manifest, output_path=Path(args.package_output))
        print(json.dumps({"manifest_path": str(manifest_path), "package_path": str(package_path), "release_id": manifest["release_id"], "manifest_sha256": manifest["manifest_sha256"]}, indent=2))
        return

    if args.command == "verify-target":
        manifest = None
        if args.manifest:
            manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        print(json.dumps(verify_target(target_root=Path(args.target_root), manifest=manifest), indent=2))
        return

    if args.command == "deploy":
        result = deploy_release(
            target_root=Path(args.target_root),
            manifest_path=Path(args.manifest),
            package_path=Path(args.package),
            health_base_url=args.health_base_url,
        )
        print(json.dumps(result, indent=2))
        return

    if args.command == "rollback":
        result = rollback_release(target_root=Path(args.target_root), health_base_url=args.health_base_url)
        print(json.dumps(result, indent=2))
        return


if __name__ == "__main__":
    main()


