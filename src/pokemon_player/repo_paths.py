from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath


REPO_ROOT_ENV = "POKEMON_PLAYER_REPO_ROOT"
REPO_ANCHORS = frozenset({"apps", "research", "scripts", "src", "tests"})
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")


def find_repo_root(start: str | Path | None = None) -> Path:
    """Find the checkout root without depending on the process working directory."""

    configured = os.environ.get(REPO_ROOT_ENV)
    if configured:
        root = Path(configured).expanduser().resolve()
        if _looks_like_repo_root(root):
            return root
        raise ValueError(f"{REPO_ROOT_ENV} does not point to a Pokemon Player checkout: {root}")

    starts = [Path(start).expanduser() if start is not None else Path.cwd(), Path(__file__)]
    for candidate_start in starts:
        candidate = candidate_start.resolve()
        if candidate.is_file():
            candidate = candidate.parent
        for parent in (candidate, *candidate.parents):
            if _looks_like_repo_root(parent):
                return parent
    raise FileNotFoundError("Could not find the Pokemon Player repository root.")


def resolve_repo_path(
    value: str | Path,
    *,
    repo_root: str | Path | None = None,
    must_exist: bool = False,
) -> Path:
    """Resolve a stored artifact path, including paths from an older checkout location.

    New metadata stores POSIX-style paths relative to the repository root. Older records
    may contain an absolute Windows or POSIX path. When an old path contains a known
    repository anchor such as ``research/``, the matching path in the current checkout
    is preferred. If it is not present, an existing original absolute path remains usable.
    """

    root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
    raw = str(value).strip()
    if not raw:
        raise ValueError("Artifact path cannot be empty.")

    relative_suffix = _repo_relative_suffix(raw)
    original = _as_native_absolute_path(raw)

    if relative_suffix is not None:
        remapped = root.joinpath(*relative_suffix.parts)
        if remapped.exists() or original is None or not original.exists():
            result = remapped
        else:
            result = original
    elif original is not None:
        result = original
    else:
        normalized = raw.replace("\\", "/")
        result = root.joinpath(*PurePosixPath(normalized).parts)

    if must_exist and not result.exists():
        raise FileNotFoundError(result)
    return result


def portable_repo_path(value: str | Path, *, repo_root: str | Path | None = None) -> str:
    """Serialize an in-repository path as a stable POSIX-style artifact identifier."""

    root = Path(repo_root).resolve() if repo_root is not None else find_repo_root()
    raw = str(value).strip()
    if not raw:
        raise ValueError("Artifact path cannot be empty.")

    suffix = _repo_relative_suffix(raw)
    if suffix is not None:
        return suffix.as_posix()

    original = _as_native_absolute_path(raw)
    if original is None:
        normalized = PurePosixPath(raw.replace("\\", "/"))
        if ".." in normalized.parts:
            raise ValueError(f"Repository path cannot escape the checkout: {value}")
        return normalized.as_posix()

    try:
        return original.resolve().relative_to(root).as_posix()
    except ValueError:
        return str(original)


def _looks_like_repo_root(path: Path) -> bool:
    return (path / "pyproject.toml").is_file() and (path / "research").is_dir()


def _repo_relative_suffix(raw: str) -> PurePosixPath | None:
    normalized = raw.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    lowered = [part.casefold() for part in parts]
    for index, part in enumerate(lowered):
        if part in REPO_ANCHORS:
            suffix = PurePosixPath(*parts[index:])
            if ".." not in suffix.parts:
                return suffix
    return None


def _as_native_absolute_path(raw: str) -> Path | None:
    if WINDOWS_ABSOLUTE_RE.match(raw):
        if os.name != "nt":
            return None
        return Path(PureWindowsPath(raw))
    path = Path(raw).expanduser()
    return path if path.is_absolute() else None
