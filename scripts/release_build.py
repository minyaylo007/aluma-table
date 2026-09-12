"""Відтворюваний архів релізу і SHA256SUMS (contracts/release-artifact.md, research.md R6).

    python3 scripts/release_build.py --tag vX.Y.Z --sha <40 hex> --out <тека> [--repo <репозиторій>]

Дерево коміту (`git archive`) + `dist/` від `build.py` цього коміту (preview, без Pillow: python -S) +
RELEASE.json + RELEASE.env + MANIFEST.sha256 → `aluma-vX.Y.Z.tar.gz` (записи за іменем, mtime = час коміту,
власник 0:0, gzip без імені й часу) і `SHA256SUMS`. Той самий коміт → побайтно той самий архів.
Заборонені шляхи (живі дані, секрети, залежності) — відмова ДО збірки. Лише stdlib.

Код виходу: 0 — готово; 1 — відмова (заборонений шлях, збірка впала); 2 — погані аргументи.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
TAG_RX = re.compile(r"^v\d+\.\d+\.\d+$")
SHA_RX = re.compile(r"^[0-9a-f]{40}$")
BUILD_MODE = "preview"   # --production — одна явна правка, коли власник заповнить факти (spec, Edge Cases)
ALLOWED_ENV_EXAMPLE = "deploy/aluma.env.example"


def forbidden(rel: str) -> bool:
    """Шлях, якому не місце в архіві: живі дані, дампи, бази, .env, samconfig, залежності."""
    parts = rel.split("/")
    name = parts[-1]
    if parts[0] == "data" or parts[0].startswith("dump") or name.startswith("dump"):
        return True
    if any(p in ("node_modules", "ms-playwright", ".venv") for p in parts[:-1]):
        return True
    if name.endswith(".db"):
        return True
    if name.startswith(".env") and rel != ALLOWED_ENV_EXAMPLE:
        return True
    return rel == "infra/samconfig.toml"


def git(repo, *args, binary=False):
    out = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True).stdout
    return out if binary else out.decode("utf-8").strip()


def tree_entries(repo, sha):
    """{шлях: режим} для файлів коміту (регулярні й символьні посилання; підмодулів у проєкті немає)."""
    raw = git(repo, "ls-tree", "-r", "-z", "--full-tree", sha, binary=True)
    entries = {}
    for rec in raw.split(b"\0"):
        if not rec:
            continue
        meta, path = rec.split(b"\t", 1)
        mode, kind, _ = meta.split(b" ")
        if kind != b"blob":
            raise ValueError(f"непідтримуваний запис дерева: {path.decode('utf-8', 'replace')}")
        entries[path.decode("utf-8")] = mode.decode()
    return entries


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(src: pathlib.Path) -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    # -S: без site-packages (Pillow не підхопиться, як у системного python3 машини); -B: без __pycache__.
    subprocess.run([sys.executable, "-S", "-B", "build.py"], cwd=src, env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def finalize(tag, sha, committed_at, files) -> dict:
    """Додає RELEASE.json, RELEASE.env і MANIFEST.sha256 (сума кожного файлу, крім себе) до files."""
    info = {"version": tag, "git_sha": sha, "build_mode": BUILD_MODE, "committed_at": committed_at}
    files["RELEASE.json"] = ((json.dumps(info) + "\n").encode(), 0o644, None)
    files["RELEASE.env"] = (f"APP_VERSION={tag}\nGIT_SHA={sha}\n".encode(), 0o644, None)
    manifest = "".join(
        f"{sha256_hex(data if link is None else link.encode())}  {rel}\n"
        for rel, (data, _, link) in sorted(files.items()))
    files["MANIFEST.sha256"] = (manifest.encode(), 0o644, None)
    return files


def make_archive(tag, sha, committed_ts, files) -> bytes:
    """files: {шлях: (байти, режим, ціль_посилання|None)} → .tar.gz байтами, детерміновано."""
    prefix = f"aluma-{tag}/"
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tar:
        for rel in sorted(files):
            data, mode, link = files[rel]
            ti = tarfile.TarInfo(prefix + rel)
            ti.mtime = committed_ts
            ti.uid = ti.gid = 0
            ti.uname = ti.gname = ""
            if link is not None:
                ti.type = tarfile.SYMTYPE
                ti.linkname = link
                ti.mode = 0o777
                tar.addfile(ti)
            else:
                ti.mode = mode
                ti.size = len(data)
                tar.addfile(ti, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0, compresslevel=9) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def release(repo, tag, sha, out_dir) -> int:
    entries = tree_entries(repo, sha)
    bad = sorted(rel for rel in entries if forbidden(rel))
    if bad:
        print("відмова: заборонені шляхи в коміті " + sha[:12] + ":", file=sys.stderr)
        for rel in bad[:20]:
            print("  " + rel, file=sys.stderr)
        return 1

    committed_ts = int(git(repo, "show", "-s", "--format=%ct", sha))
    committed_at = dt.datetime.fromtimestamp(committed_ts, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    tmp = pathlib.Path(tempfile.mkdtemp(prefix="aluma-release-"))
    try:
        src = tmp / "src"
        src.mkdir()
        with tarfile.open(fileobj=io.BytesIO(git(repo, "archive", "--format=tar", sha, binary=True))) as tar:
            tar.extractall(src, filter="tar")
        try:
            build(src)
        except subprocess.CalledProcessError as exc:
            tail = (exc.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-5:]
            print("відмова: build.py завершився з кодом " + str(exc.returncode), file=sys.stderr)
            for line in tail:
                print("  " + line[:200], file=sys.stderr)
            return 1

        files = {}
        for rel, mode in entries.items():
            path = src / rel
            if mode == "120000":
                files[rel] = (b"", 0o777, os.readlink(path))
            else:
                files[rel] = (path.read_bytes(), 0o755 if mode == "100755" else 0o644, None)
        dist = src / "dist"
        for path in sorted(p for p in dist.rglob("*") if p.is_file()):
            files["dist/" + path.relative_to(dist).as_posix()] = (path.read_bytes(), 0o644, None)

        finalize(tag, sha, committed_at, files)
        archive = make_archive(tag, sha, committed_ts, files)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"aluma-{tag}.tar.gz"
    (out_dir / name).write_bytes(archive)
    digest = sha256_hex(archive)
    (out_dir / "SHA256SUMS").write_text(f"{digest}  {name}\n", encoding="utf-8", newline="\n")
    print(f"{tag} {sha[:12]}: {len(files)} файлів, {name} sha256={digest}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Архів релізу ALUMA і SHA256SUMS.")
    ap.add_argument("--tag", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--repo", default=str(ROOT))
    args = ap.parse_args(argv)

    if not TAG_RX.match(args.tag):
        print(f"помилка: тег має бути vX.Y.Z, а не {args.tag!r}", file=sys.stderr)
        return 2
    if not SHA_RX.match(args.sha):
        print("помилка: --sha має бути повним sha (40 hex)", file=sys.stderr)
        return 2
    repo = pathlib.Path(args.repo)
    probe = subprocess.run(["git", "-C", str(repo), "cat-file", "-e", args.sha + "^{commit}"],
                           capture_output=True)
    if probe.returncode != 0:
        print(f"помилка: коміту {args.sha[:12]} немає в {repo}", file=sys.stderr)
        return 2
    return release(repo, args.tag, args.sha, pathlib.Path(args.out))


if __name__ == "__main__":
    sys.exit(main())
