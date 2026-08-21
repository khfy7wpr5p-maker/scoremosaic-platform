"""Durable engine-local proof that one authenticated dispatch was accepted.

Stage 5-A2 uses this receipt as a prerequisite for source HTTP intake. It stores
only bounded identity evidence, never credentials, request signatures, nonces,
source bytes, execution state, or Gateway-owned state.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from hmac import compare_digest, new as hmac_new
import json, os, re, secrets, stat
from pathlib import Path
from typing import Any
from .receiver_authority import ENGINE_NAME

DISPATCH_ACCEPTANCE_STORE_VERSION = "scoremosaic-engine-dispatch-acceptance-v1"
_MAX_RECORD_BYTES = 16 * 1024
_MAC_DOMAIN = b"scoremosaic-engine-dispatch-acceptance-v1"
_JOB_ID_RE = re.compile(r"job_[A-Za-z0-9_-]{8,80}\Z")
_RUN_ID_RE = re.compile(r"run_[0-9a-f]{24}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")

class DispatchAcceptanceStoreError(ValueError):
    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(category)

def _canonical_json(value: dict[str, Any]) -> bytes:
    try:
        return json.dumps(value, ensure_ascii=True, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("ascii")
    except (TypeError, ValueError, OverflowError, UnicodeEncodeError):
        raise DispatchAcceptanceStoreError("dispatch_acceptance_state_invalid") from None

def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if type(key) is not str or key in value:
            raise DispatchAcceptanceStoreError("dispatch_acceptance_state_invalid")
        value[key] = item
    return value

@dataclass(frozen=True, slots=True)
class DispatchAcceptanceReceipt:
    engine: str
    job_id: str
    run_id: str
    dispatch_identity_sha256: str
    persistence_state: str
    def __post_init__(self) -> None:
        if (self.engine != ENGINE_NAME or type(self.job_id) is not str or _JOB_ID_RE.fullmatch(self.job_id) is None or type(self.run_id) is not str or _RUN_ID_RE.fullmatch(self.run_id) is None or type(self.dispatch_identity_sha256) is not str or _SHA256_RE.fullmatch(self.dispatch_identity_sha256) is None or self.persistence_state not in {"written", "replay", "loaded"}):
            raise DispatchAcceptanceStoreError("dispatch_acceptance_result_invalid")
    @property
    def source_delivery_authorized(self) -> bool: return True
    @property
    def engine_execution_allowed(self) -> bool: return False
    @property
    def retry_allowed(self) -> bool: return False
    def as_safe_dict(self) -> dict[str, object]:
        return {"version": DISPATCH_ACCEPTANCE_STORE_VERSION, "environment": "staging", "engine": self.engine, "jobId": self.job_id, "runId": self.run_id, "dispatchIdentitySha256": self.dispatch_identity_sha256, "persistenceState": self.persistence_state, "sourceDeliveryAuthorized": True, "engineExecutionAllowed": False, "retryAllowed": False}

class EngineDispatchAcceptanceStore:
    __slots__ = ("_root", "_integrity_key")
    def __init__(self, *, root: str | Path, integrity_key: bytes) -> None:
        try: checked = Path(root)
        except TypeError: raise DispatchAcceptanceStoreError("dispatch_acceptance_config_invalid") from None
        if not checked.is_absolute() or type(integrity_key) is not bytes or len(integrity_key) != 32:
            raise DispatchAcceptanceStoreError("dispatch_acceptance_config_invalid")
        self._root = checked; self._integrity_key = bytes(integrity_key)
        self._ensure_dir(self._root); self._ensure_dir(self._root / "accepted-dispatches")
    @staticmethod
    def _ensure_dir(path: Path) -> None:
        try: path.mkdir(mode=0o700, parents=True, exist_ok=True); observed = path.lstat()
        except OSError: raise DispatchAcceptanceStoreError("dispatch_acceptance_state_invalid") from None
        if stat.S_ISLNK(observed.st_mode) or not stat.S_ISDIR(observed.st_mode): raise DispatchAcceptanceStoreError("dispatch_acceptance_state_invalid")
    def _path(self, job_id: str, run_id: str) -> Path:
        if type(job_id) is not str or _JOB_ID_RE.fullmatch(job_id) is None or type(run_id) is not str or _RUN_ID_RE.fullmatch(run_id) is None: raise DispatchAcceptanceStoreError("dispatch_acceptance_input_invalid")
        return self._root / "accepted-dispatches" / f"{job_id}.{run_id}.json"
    def _mac(self, record: dict[str, Any]) -> str:
        if type(record) is not dict or "integrityMac" in record: raise DispatchAcceptanceStoreError("dispatch_acceptance_state_invalid")
        return hmac_new(self._integrity_key, b"\0".join((_MAC_DOMAIN, ENGINE_NAME.encode("ascii"), _canonical_json(record))), sha256).hexdigest()
    def _sealed(self, record: dict[str, Any]) -> bytes:
        sealed = dict(record); sealed["integrityMac"] = self._mac(record); payload = _canonical_json(sealed)
        if not payload or len(payload) > _MAX_RECORD_BYTES: raise DispatchAcceptanceStoreError("dispatch_acceptance_state_invalid")
        return payload
    @staticmethod
    def _read_flags() -> int:
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"): flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"): flags |= os.O_CLOEXEC
        return flags
    def _read(self, path: Path) -> dict[str, Any]:
        fd = None
        try:
            fd = os.open(path, self._read_flags()); observed = os.fstat(fd)
            if not stat.S_ISREG(observed.st_mode) or not 1 <= observed.st_size <= _MAX_RECORD_BYTES: raise DispatchAcceptanceStoreError("dispatch_acceptance_state_invalid")
            chunks=[]; total=0
            while True:
                chunk=os.read(fd, min(4096, _MAX_RECORD_BYTES + 1 - total))
                if not chunk: break
                total += len(chunk)
                if total > _MAX_RECORD_BYTES: raise DispatchAcceptanceStoreError("dispatch_acceptance_state_invalid")
                chunks.append(chunk)
            raw=b"".join(chunks)
        except FileNotFoundError: raise DispatchAcceptanceStoreError("dispatch_acceptance_not_found") from None
        except DispatchAcceptanceStoreError: raise
        except OSError: raise DispatchAcceptanceStoreError("dispatch_acceptance_state_invalid") from None
        finally:
            if fd is not None:
                try: os.close(fd)
                except OSError: raise DispatchAcceptanceStoreError("dispatch_acceptance_state_invalid") from None
        try: sealed=json.loads(raw.decode("ascii"), object_pairs_hook=_reject_duplicates, parse_constant=lambda _v: (_ for _ in ()).throw(ValueError()))
        except DispatchAcceptanceStoreError: raise
        except Exception: raise DispatchAcceptanceStoreError("dispatch_acceptance_state_invalid") from None
        if type(sealed) is not dict or _canonical_json(sealed) != raw or set(sealed) != {"version","engine","jobId","runId","dispatchIdentitySha256","integrityMac"}: raise DispatchAcceptanceStoreError("dispatch_acceptance_state_invalid")
        observed_mac=sealed.get("integrityMac"); record=dict(sealed); record.pop("integrityMac",None)
        if type(observed_mac) is not str or _SHA256_RE.fullmatch(observed_mac) is None or not compare_digest(observed_mac,self._mac(record)) or record.get("version") != DISPATCH_ACCEPTANCE_STORE_VERSION or record.get("engine") != ENGINE_NAME: raise DispatchAcceptanceStoreError("dispatch_acceptance_state_invalid")
        return record
    def _receipt(self, record: dict[str, Any], persistence_state: str) -> DispatchAcceptanceReceipt:
        return DispatchAcceptanceReceipt(engine=record.get("engine"), job_id=record.get("jobId"), run_id=record.get("runId"), dispatch_identity_sha256=record.get("dispatchIdentitySha256"), persistence_state=persistence_state)
    def publish(self, *, job_id: str, run_id: str, dispatch_identity_sha256: str) -> DispatchAcceptanceReceipt:
        if type(dispatch_identity_sha256) is not str or _SHA256_RE.fullmatch(dispatch_identity_sha256) is None: raise DispatchAcceptanceStoreError("dispatch_acceptance_input_invalid")
        path=self._path(job_id,run_id); record={"version":DISPATCH_ACCEPTANCE_STORE_VERSION,"engine":ENGINE_NAME,"jobId":job_id,"runId":run_id,"dispatchIdentitySha256":dispatch_identity_sha256}; payload=self._sealed(record)
        temp=path.parent / f".{path.name}.{secrets.token_hex(16)}.tmp"; flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
        if hasattr(os,"O_NOFOLLOW"): flags |= os.O_NOFOLLOW
        fd=None
        try:
            fd=os.open(temp,flags,0o600); offset=0
            while offset < len(payload):
                written=os.write(fd,payload[offset:])
                if written <= 0: raise OSError("write_failed")
                offset += written
            os.fchmod(fd,0o400); os.fsync(fd); os.close(fd); fd=None
            try: os.link(temp,path,follow_symlinks=False); created=True
            except FileExistsError: created=False
            dir_fd=os.open(path.parent,os.O_RDONLY)
            try: os.fsync(dir_fd)
            finally: os.close(dir_fd)
        except OSError: raise DispatchAcceptanceStoreError("dispatch_acceptance_state_invalid") from None
        finally:
            if fd is not None:
                try: os.close(fd)
                except OSError: pass
            try: temp.unlink(missing_ok=True)
            except OSError: pass
        stored=self._receipt(self._read(path), "written" if created else "replay")
        if stored.job_id != job_id or stored.run_id != run_id or not compare_digest(stored.dispatch_identity_sha256,dispatch_identity_sha256): raise DispatchAcceptanceStoreError("dispatch_acceptance_conflict")
        return stored
    def require(self, *, job_id: str, run_id: str, dispatch_identity_sha256: str) -> DispatchAcceptanceReceipt:
        if type(dispatch_identity_sha256) is not str or _SHA256_RE.fullmatch(dispatch_identity_sha256) is None: raise DispatchAcceptanceStoreError("dispatch_acceptance_input_invalid")
        stored=self._receipt(self._read(self._path(job_id,run_id)),"loaded")
        if not compare_digest(stored.dispatch_identity_sha256,dispatch_identity_sha256): raise DispatchAcceptanceStoreError("dispatch_acceptance_mismatch")
        return stored
