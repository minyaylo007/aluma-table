"""Агент деплою ALUMA: pull з GitHub без облікових даних.

Контракти: specs/001-release-pipeline/contracts/agent-cli.md, production-ref.md, release-artifact.md;
переходи — data-model.md «Переходи агента».

    pullagent.py --config <json> --once      один цикл (так кличе таймер)
    pullagent.py --config <json> --dry-run   прочитати посилання, скачати й звірити, надрукувати «було → стане»
    pullagent.py --config <json> --status    state.json і останні 5 рядків журналу

Лише stdlib, системний python3. Агент не слухає портів, не піднімає прав, не звертається до REST API GitHub і
не надсилає жодних заголовків автентифікації; git — з ізольованою конфігурацією; перезапускає тільки
restart_unit і тільки через systemctl --user. Живих даних і файлу з секретами не відкриває.

Коди виходу: 0 — нічого не змінилось / установка вдалася / dry-run зійшовся; 1 — установка не вдалася,
попередню повернуто; 2 — не вдалося й повернення, потрібна людина; 3 — відмова до установки (ручні правки,
немає тегу, суми не зійшлися, погана конфігурація); 4 — GitHub недоступний; 5 — триває інша установка.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
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
import time
import urllib.error
import urllib.parse
import urllib.request

# Територія агента (FR-018). Тести підміняють ці кортежі на тимчасову теку.
ALLOWED_BASE_DIRS = ("/opt/ihor/",)
ALLOWED_STATIC_DIRS = ("/srv/aluma",)
# Посилання скачування релізу GitHub переадресовує на свої сховища; більше нікуди.
REDIRECT_HOSTS = ("github.com", "objects.githubusercontent.com", "release-assets.githubusercontent.com")

TAG_RX = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
UNIT_RX = re.compile(r"^ihor-aluma-[a-z0-9-]+\.service$")
USER_AGENT = {"User-Agent": "aluma-pullagent/1"}
HEALTH_POLL_S = 2
BACKOFF_FIRST_S = 60
BACKOFF_MAX_S = 600
VENV_DONE = ".complete"


class ConfigError(ValueError):
    """Конфігурація виходить за територію агента — старт заборонено."""


class FetchError(OSError):
    """Скачати не вдалося (мережа, 404, заборонена переадресація)."""


class _Refused(Exception):
    def __init__(self, reason, paths=None):
        super().__init__(reason)
        self.reason = reason
        self.paths = paths or []


# ── перевірки конфігурації ────────────────────────────────────────────────────────────────────────────────


def _inside(path: str, roots) -> bool:
    if ".." in path.split("/") or not path.startswith("/"):
        return False
    norm = os.path.normpath(path)
    return any(norm == r.rstrip("/") or norm.startswith(r.rstrip("/") + "/") for r in roots)


def _relative(value: str) -> bool:
    return bool(value) and not value.startswith("/") and ".." not in value.split("/")


def redirect_allowed(url: str) -> bool:
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return (parts.scheme == "https" and parts.hostname in REDIRECT_HOSTS and parts.username is None
            and parts.password is None and parts.port is None)


def validate(cfg: dict) -> None:
    need = ("repo_url", "ref", "tag_glob", "asset_name", "base_dir", "keep_releases", "requirements", "units_dir",
            "restart_unit", "health_url", "health_timeout_s", "static_src", "static_dst", "rsync_flags")
    missing = [k for k in need if k not in cfg]
    if missing:
        raise ConfigError("missing keys: " + ", ".join(missing))
    repo = urllib.parse.urlsplit(cfg["repo_url"])
    if (repo.scheme != "https" or repo.hostname != "github.com" or repo.username or repo.password or repo.port
            or repo.query or len([p for p in repo.path.split("/") if p]) != 2):
        raise ConfigError("repo_url must be https://github.com/<owner>/<repo>")
    health = urllib.parse.urlsplit(cfg["health_url"])
    if health.scheme != "http" or health.hostname != "127.0.0.1" or health.username or not health.port:
        raise ConfigError("health_url must be http://127.0.0.1:<port>/…")
    if not _inside(cfg["base_dir"], ALLOWED_BASE_DIRS):
        raise ConfigError("base_dir outside the allowed territory")
    if not _inside(cfg["static_dst"], ALLOWED_STATIC_DIRS):
        raise ConfigError("static_dst outside the allowed territory")
    for key in ("requirements", "units_dir", "static_src"):
        if not _relative(cfg[key]):
            raise ConfigError(f"{key} must be a relative path inside the release")
    if not UNIT_RX.match(cfg["restart_unit"]):
        raise ConfigError("restart_unit must be one of the ALUMA user units")
    if not isinstance(cfg["keep_releases"], int) or cfg["keep_releases"] < 2:
        raise ConfigError("keep_releases must be an integer >= 2")
    flags = cfg["rsync_flags"]
    if not isinstance(flags, list) or not all(isinstance(f, str) and f.startswith("-") for f in flags):
        raise ConfigError("rsync_flags must be a list of options")
    if cfg["ref"] != "refs/heads/production" or not cfg["tag_glob"].startswith("refs/tags/"):
        raise ConfigError("ref / tag_glob are not the production ref and release tags")
    if "{tag}" not in cfg["asset_name"] or "/" in cfg["asset_name"]:
        raise ConfigError("asset_name must be a file name with {tag}")


# ── реальні підключення (тести їх підміняють) ─────────────────────────────────────────────────────────────


def _run(argv, env=None, cwd=None):
    return subprocess.run(argv, env=env, cwd=cwd, capture_output=True, text=True, timeout=900)


class _Redirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not redirect_allowed(newurl):
            raise FetchError("redirect to a host outside the allow-list")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _fetch(url, headers=None, timeout=30):
    opener = urllib.request.build_opener(_Redirects)
    request = urllib.request.Request(url, headers=dict(headers or {}))
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.read()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise FetchError(type(exc).__name__) from None


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _semver(tag: str):
    m = TAG_RX.match(tag)
    return tuple(int(x) for x in m.groups()) if m else None


# ── агент ─────────────────────────────────────────────────────────────────────────────────────────────────


class Agent:
    def __init__(self, config, *, runner=None, fetch=None, sleep=time.sleep, now=time.time, units_home=None,
                 out=None):
        validate(config)
        self.cfg = config
        self.run = runner or _run
        self.fetch = fetch or _fetch
        self.sleep = sleep
        self.now = now
        self.out = out or sys.stdout
        self.base = pathlib.Path(config["base_dir"])
        self.releases = self.base / "releases"
        self.venvs = self.base / "venvs"
        self.state_dir = self.base / "state"
        self.current = self.base / "current"
        self.static_dst = config["static_dst"].rstrip("/") + "/"
        self.units_home = pathlib.Path(units_home) if units_home else pathlib.Path.home() / ".config/systemd/user"

    # ── журнал і стан ──
    def _iso(self) -> str:
        return dt.datetime.fromtimestamp(self.now(), dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def log(self, event, **fields):
        rec = {"event": event, "at": self._iso()}
        rec.update({k: v for k, v in fields.items() if v is not None})
        if "reason" in rec:
            rec["reason"] = str(rec["reason"])[:200]
        line = json.dumps(rec, ensure_ascii=False)
        print(line, file=self.out)
        if self.state_dir.is_dir():
            with open(self.state_dir / "deploy.log", "a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def _say(self, text):
        print(text, file=self.out)

    def _load(self, name, default):
        path = self.state_dir / name
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return default

    def _save(self, name, obj):
        path = self.state_dir / name
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)

    def _state(self):
        st = self._load("state.json", {})
        return {"current": st.get("current"), "previous": st.get("previous")}

    @staticmethod
    def _ref(item):
        return {"tag": item["tag"], "sha": item["git_sha"][:7]} if item else None

    def _ensure_dirs(self):
        for d in (self.releases, self.venvs):
            d.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.state_dir, 0o700)

    # ── точки входу ──
    def status(self) -> int:
        self._say(json.dumps(self._load("state.json", {}), ensure_ascii=False, indent=1))
        log = self.state_dir / "deploy.log"
        if log.exists():
            for line in log.read_text(encoding="utf-8").splitlines()[-5:]:
                self._say(line)
        return 0

    def once(self, dry_run=False) -> int:
        self._ensure_dirs()
        lock = open(self.state_dir / "agent.lock", "a+")
        try:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self.log("lock_busy")
                return 5
            return self._cycle(dry_run)
        finally:
            lock.close()

    # ── цикл ──
    def _cycle(self, dry_run) -> int:
        state = self._state()
        cur = state["current"]
        linked = self._linked_tag()
        if not dry_run and linked and (cur is None or linked != cur["tag"]):
            return self._resume(state, linked)

        backoff = self._load("backoff.json", {})
        if self.now() < backoff.get("next_at", 0):
            self.log("source_unavailable", reason="backoff")
            return 4
        refs = self._ls_remote()
        if refs is None:
            failures = backoff.get("failures", 0) + 1
            delay = min(BACKOFF_FIRST_S * 2 ** (failures - 1), BACKOFF_MAX_S)
            self._save("backoff.json", {"failures": failures, "next_at": self.now() + delay})
            self.log("source_unavailable", reason="ls_remote")
            return 4
        if backoff:
            (self.state_dir / "backoff.json").unlink(missing_ok=True)

        desired = refs.get(self.cfg["ref"])
        if not desired:
            self.log("unchanged", reason="no_production_ref")
            return 0
        failed = self._load("failed.json", {})
        if any(sha != desired for sha in failed):
            failed = {sha: v for sha, v in failed.items() if sha == desired}
            self._save("failed.json", failed)
        if cur and cur["git_sha"] == desired:
            self.log("unchanged")
            return 0
        if desired in failed:
            self.log("unchanged", reason="failed_before")
            return 0
        tag = self._tag_for(refs, desired)
        if not tag:
            self.log("refused", reason="no_release_tag", to={"tag": None, "sha": desired[:7]})
            return 3
        if cur:
            dirty = self._verify_tree(self.releases / cur["tag"], cur["tag"], cur["git_sha"], strict=False)
            if dirty:
                self.log("refused", reason="dirty_current", paths=dirty[:5])
                return 3

        t0 = self.now()
        tmp_holder = []
        try:
            rel = self._obtain(tag, desired, dry_run, tmp_holder)
        except _Refused as exc:
            self.log("refused", reason=exc.reason, to={"tag": tag, "sha": desired[:7]})
            return 3
        except FetchError:
            self.log("source_unavailable", reason="download", to={"tag": tag, "sha": desired[:7]})
            return 4
        if dry_run:
            try:
                changed = self._units_diff(rel)
                self._say(f"{cur['tag'] if cur else '—'} → {tag} ({desired[:7]}): архів і суми зійшлися; "
                          f"venv {self._req_hash(rel)}; юніти змінено: {len(changed)}")
                self.log("dry_run", **{"from": self._ref(cur), "to": {"tag": tag, "sha": desired[:7]}})
            finally:
                for tmp in tmp_holder:
                    shutil.rmtree(tmp, ignore_errors=True)
            return 0
        return self._install(state, tag, desired, rel, "production_ref", t0)

    # ── git ──
    def _git_env(self):
        return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": os.environ.get("HOME", "/nonexistent"),
                "LANG": "C.UTF-8", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/bin/false"}

    def _ls_remote(self):
        argv = ["git", "-c", "credential.helper=", "-c", "protocol.version=2", "ls-remote", self.cfg["repo_url"],
                self.cfg["ref"], self.cfg["tag_glob"]]
        try:
            res = self.run(argv, env=self._git_env())
        except (OSError, subprocess.SubprocessError):
            return None
        if res.returncode != 0:
            return None
        refs = {}
        for line in res.stdout.splitlines():
            sha, _, name = line.partition("\t")
            if re.fullmatch(r"[0-9a-f]{40}", sha) and name:
                refs[name] = sha
        return refs

    @staticmethod
    def _tag_for(refs, sha):
        tags = {}
        for name, value in refs.items():
            if not name.startswith("refs/tags/"):
                continue
            short = name[len("refs/tags/"):]
            if short.endswith("^{}"):
                tags[short[:-3]] = value              # очищений sha анотованого тегу
            else:
                tags.setdefault(short, value)
        hits = [t for t, s in tags.items() if s == sha and _semver(t)]
        return max(hits, key=_semver) if hits else None

    # ── каталоги версій ──
    def _linked_tag(self):
        if self.current.is_symlink():
            return os.readlink(self.current).rstrip("/").rsplit("/", 1)[-1]
        return None

    @staticmethod
    def _files(root: pathlib.Path):
        out = set()
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d != "__pycache__" and not (dirpath == str(root) and d == ".venv")]
            for name in filenames:
                rel = os.path.relpath(os.path.join(dirpath, name), root).replace(os.sep, "/")
                if rel != ".venv":
                    out.add(rel)
            for d in list(dirnames):
                p = os.path.join(dirpath, d)
                if os.path.islink(p):
                    out.add(os.path.relpath(p, root).replace(os.sep, "/"))
        return out

    def _verify_tree(self, root: pathlib.Path, tag, sha, strict):
        """Порожній список — дерево збігається з MANIFEST.sha256 і RELEASE.json; інакше — шляхи з відхиленнями."""
        manifest = root / "MANIFEST.sha256"
        if not manifest.is_file():
            return ["MANIFEST.sha256"]
        listed = {}
        for line in manifest.read_text(encoding="utf-8").splitlines():
            digest, sep, rel = line.partition("  ")
            if sep and re.fullmatch(r"[0-9a-f]{64}", digest):
                listed[rel] = digest
        problems = []
        for rel, digest in sorted(listed.items()):
            path = root / rel
            if path.is_symlink():
                data = os.readlink(path).encode()
            elif path.is_file():
                data = path.read_bytes()
            else:
                problems.append(rel)
                continue
            if _sha256(data) != digest:
                problems.append(rel)
        if strict:
            problems += sorted(self._files(root) - set(listed) - {"MANIFEST.sha256"})
        try:
            info = json.loads((root / "RELEASE.json").read_text(encoding="utf-8"))
            if info.get("version") != tag or info.get("git_sha") != sha:
                problems.append("RELEASE.json")
        except (OSError, ValueError):
            problems.append("RELEASE.json")
        return problems

    def _obtain(self, tag, sha, dry_run, tmp_holder):
        """Каталог версії, звірений з архівом релізу. Уже розпакована й ціла версія — без мережі (відкат)."""
        dest = self.releases / tag
        if dest.is_dir():
            if not self._verify_tree(dest, tag, sha, strict=False):
                return dest
            if dry_run:
                raise _Refused("checksum")
            shutil.rmtree(dest)
        downloads = self.state_dir / "downloads" / tag
        downloads.mkdir(parents=True, exist_ok=True)
        try:
            url = f"{self.cfg['repo_url']}/releases/download/{tag}/"
            name = self.cfg["asset_name"].format(tag=tag)
            sums = self.fetch(url + "SHA256SUMS", headers=USER_AGENT, timeout=30)
            archive = self.fetch(url + name, headers=USER_AGENT, timeout=300)
            (downloads / "SHA256SUMS").write_bytes(sums)
            (downloads / name).write_bytes(archive)
            expected = None
            for line in sums.decode("utf-8", "replace").splitlines():
                digest, sep, fname = line.partition("  ")
                if sep and fname == name:
                    expected = digest
            if expected is None or _sha256(archive) != expected:
                raise _Refused("checksum")
            tmp = self.releases / f".tmp-{tag}-{os.getpid()}"
            shutil.rmtree(tmp, ignore_errors=True)
            tmp_holder.append(tmp)
            prefix = f"aluma-{tag}/"
            try:
                with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
                    if not all(m.name.startswith(prefix) for m in tar.getmembers()):
                        raise _Refused("checksum")
                    tar.extractall(tmp, filter="data")
            except tarfile.TarError:
                raise _Refused("checksum") from None
            root = tmp / prefix.rstrip("/")
            if self._verify_tree(root, tag, sha, strict=True):
                raise _Refused("checksum")
            if dry_run:
                return root
            os.replace(root, dest)
            shutil.rmtree(tmp, ignore_errors=True)
            tmp_holder.remove(tmp)
            return dest
        except _Refused:
            for tmp in tmp_holder:
                shutil.rmtree(tmp, ignore_errors=True)
            raise
        finally:
            shutil.rmtree(downloads, ignore_errors=True)

    # ── venv і юніти ──
    def _req_hash(self, rel) -> str:
        return _sha256((rel / self.cfg["requirements"]).read_bytes())[:12]

    def _prepare_venv(self, rel):
        digest = self._req_hash(rel)
        venv = self.venvs / digest
        if not (venv / VENV_DONE).exists():
            shutil.rmtree(venv, ignore_errors=True)
            # venv створюється одразу на місці: шляхи всередині venv абсолютні, перейменування їх ламає.
            steps = ([sys.executable, "-m", "venv", str(venv)],
                     [str(venv / "bin" / "pip"), "install", "--disable-pip-version-check", "-q", "-r",
                      str(rel / self.cfg["requirements"])])
            for argv in steps:
                if self.run(argv).returncode != 0:
                    shutil.rmtree(venv, ignore_errors=True)
                    raise _Refused("venv")
            (venv / VENV_DONE).write_text("ok\n")
        link = rel / ".venv"
        if link.is_symlink() or link.exists():
            link.unlink()
        os.symlink(f"../../venvs/{digest}", link)

    def _unit_files(self, rel):
        src = rel / self.cfg["units_dir"]
        if not src.is_dir():
            return []
        return sorted(p for p in src.iterdir() if p.is_file() and p.name.startswith("ihor-aluma-"))

    def _units_diff(self, rel):
        changed = []
        for f in self._unit_files(rel):
            dst = self.units_home / f.name
            if not dst.exists() or dst.read_bytes() != f.read_bytes():
                changed.append(f.name)
        return changed

    def _write_unit(self, name, data):
        self.units_home.mkdir(parents=True, exist_ok=True)
        dst = self.units_home / name
        tmp = dst.with_name(dst.name + ".tmp")
        tmp.write_bytes(data)
        os.chmod(tmp, 0o644)
        os.replace(tmp, dst)

    def _sync_units(self, rel):
        backup = {}
        for f in self._unit_files(rel):
            dst = self.units_home / f.name
            new = f.read_bytes()
            old = dst.read_bytes() if dst.exists() else None
            if old != new:
                backup[f.name] = old
                self._write_unit(f.name, new)
        if backup:
            self._systemctl("daemon-reload")
        return backup

    def _restore_units(self, backup):
        for name, old in backup.items():
            if old is None:
                (self.units_home / name).unlink(missing_ok=True)
            else:
                self._write_unit(name, old)
        if backup:
            self._systemctl("daemon-reload")

    def _systemctl(self, action, unit=None) -> int:
        argv = ["systemctl", "--user", action] + ([unit] if unit else [])
        try:
            return self.run(argv).returncode
        except (OSError, subprocess.SubprocessError):
            return 1

    # ── установка ──
    def _switch(self, tag):
        tmp = self.base / "current.new"
        if tmp.is_symlink() or tmp.exists():
            tmp.unlink()
        os.symlink(f"releases/{tag}", tmp)
        os.replace(tmp, self.current)

    def _local_health(self, tag, sha) -> bool:
        deadline = self.now() + self.cfg["health_timeout_s"]
        while True:
            try:
                body = json.loads(self.fetch(self.cfg["health_url"], headers=USER_AGENT, timeout=5))
                if body.get("ok") is True and (tag is None or (body.get("version") == tag and
                                                               body.get("git_sha") == sha)):
                    return True
            except (FetchError, ValueError, AttributeError):
                pass
            if self.now() >= deadline:
                return False
            self.sleep(HEALTH_POLL_S)

    def _static_entries(self, rel):
        prefix = self.cfg["static_src"].rstrip("/") + "/"
        entries = {}
        for line in (rel / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines():
            digest, sep, path = line.partition("  ")
            if sep and path.startswith(prefix):
                entries[path[len(prefix):]] = digest
        return entries

    def _publish_static(self, rel) -> bool:
        src = str(rel / self.cfg["static_src"]).rstrip("/") + "/"
        try:
            return self.run(["rsync", *self.cfg["rsync_flags"], src, self.static_dst]).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _verify_static(self, rel) -> bool:
        dst = pathlib.Path(self.static_dst)
        for path, digest in self._static_entries(rel).items():
            target = dst / path
            try:
                if _sha256(target.read_bytes()) != digest or not target.stat().st_mode & 0o004:
                    return False
            except OSError:
                return False
        return True

    def _bring_up(self, rel, tag, sha):
        if self._systemctl("restart", self.cfg["restart_unit"]) != 0:
            return False, "restart_failed"
        if not self._local_health(tag, sha):
            return False, "local_health_timeout"
        if not self._publish_static(rel):
            return False, "static_publish"
        if not self._verify_static(rel):
            return False, "static_verify"
        return True, ""

    def _install(self, state, tag, sha, rel, trigger, t0) -> int:
        cur = state["current"]
        moves = {"from": self._ref(cur), "to": {"tag": tag, "sha": sha[:7]}}
        self.log("deploy_start", trigger=trigger, **moves)
        try:
            self._prepare_venv(rel)
        except _Refused as exc:
            self.log("refused", trigger=trigger, reason=exc.reason, **moves)
            return 3
        backup = self._sync_units(rel)
        self._switch(tag)
        ok, reason = self._bring_up(rel, tag, sha)
        if ok:
            return self._done(state, tag, sha, trigger, t0)
        return self._revert(state, tag, sha, backup, reason, trigger, t0)

    def _done(self, state, tag, sha, trigger, t0) -> int:
        cur = state["current"]
        previous = cur if cur and cur["tag"] != tag else state["previous"]
        new = {"current": {"tag": tag, "git_sha": sha}, "previous": previous, "updated_at": self._iso()}
        self._save("state.json", new)
        self._prune(new)
        secs = int(self.now() - t0)
        self.log("deploy_done", trigger=trigger, result="ok", secs=secs,
                 **{"from": self._ref(cur), "to": {"tag": tag, "sha": sha[:7]}})
        self._say(f"{cur['tag'] if cur else '—'} → {tag}: ok ({secs} s)")
        return 0

    def _revert(self, state, tag, sha, backup, reason, trigger, t0) -> int:
        cur = state["current"]
        failed = self._load("failed.json", {})
        failed[sha] = {"tag": tag, "at": self._iso(), "reason": reason}
        self._save("failed.json", failed)
        self._restore_units(backup)
        if cur is None:
            # Перший перехід: попередня версія — не з каталогів версій; повертаємо юніти й прибираємо current.
            self.current.unlink(missing_ok=True)
            ok = reason not in ("static_publish", "static_verify") and \
                self._systemctl("restart", self.cfg["restart_unit"]) == 0 and self._local_health(None, None)
        else:
            self._switch(cur["tag"])
            ok, _ = self._bring_up(self.releases / cur["tag"], cur["tag"], cur["git_sha"])
        moves = {"from": {"tag": tag, "sha": sha[:7]}, "to": self._ref(cur)}
        secs = int(self.now() - t0)
        if ok:
            self.log("revert_done", trigger=trigger, result="reverted", reason=reason, secs=secs, **moves)
            self._say(f"{tag} → {cur['tag'] if cur else 'попередня'}: reverted ({reason}, {secs} s)")
            return 1
        self.log("revert_failed", trigger=trigger, result="failed", reason=reason, secs=secs, **moves)
        self._say(f"{tag}: revert failed ({reason}) — потрібна людина (docs/DELIVERY.md)")
        return 2

    def _resume(self, state, linked) -> int:
        """Перервано між перемиканням і DONE: довести до узгодженого — нова з перевіркою або попередня."""
        rel = self.releases / linked
        t0 = self.now()
        try:
            sha = json.loads((rel / "RELEASE.json").read_text(encoding="utf-8"))["git_sha"]
        except (OSError, ValueError, KeyError, TypeError):
            sha = ""
        moves = {"from": self._ref(state["current"]), "to": {"tag": linked, "sha": sha[:7]}}
        self.log("deploy_start", trigger="resume", **moves)
        if sha and not self._verify_tree(rel, linked, sha, strict=False):
            ok, reason = self._bring_up(rel, linked, sha)
            if ok:
                return self._done(state, linked, sha, "resume", t0)
        else:
            reason = "resume_invalid"
        return self._revert(state, linked, sha or "0" * 40, {}, reason, "resume", t0)

    def _prune(self, state):
        protected = {x["tag"] for x in (state["current"], state["previous"]) if x}
        versions = sorted((d.name for d in self.releases.iterdir() if d.is_dir() and _semver(d.name)),
                          key=_semver, reverse=True)
        keep = set(protected)
        for name in versions:
            if len(keep) >= self.cfg["keep_releases"]:
                break
            keep.add(name)
        for name in versions:
            if name not in keep:
                shutil.rmtree(self.releases / name, ignore_errors=True)
        for d in self.releases.iterdir():
            if d.name.startswith(".tmp-"):
                shutil.rmtree(d, ignore_errors=True)
        used = set()
        for name in keep:
            link = self.releases / name / ".venv"
            if link.is_symlink():
                used.add(os.readlink(link).rstrip("/").rsplit("/", 1)[-1])
        for d in self.venvs.iterdir():
            if d.is_dir() and d.name not in used:
                shutil.rmtree(d, ignore_errors=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="ALUMA deploy agent (pull, no credentials).")
    ap.add_argument("--config", required=True)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--status", action="store_true")
    args = ap.parse_args(argv)
    try:
        with open(args.config, encoding="utf-8") as fh:
            config = json.load(fh)
        agent = Agent(config)
    except (OSError, ValueError) as exc:
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        print(json.dumps({"event": "refused", "at": stamp, "reason": "bad_config: " + str(exc)[:150]}))
        return 3
    if args.status:
        return agent.status()
    return agent.once(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
