"""Operator-owned scope; never accept client-supplied DB/URL/key overrides."""
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import stat

from .domain import CONTRACT, DataError


def secret(path):
    p = Path(path)
    st = p.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077 or st.st_uid != os.getuid():
        raise DataError('private_file_permissions_required')
    if st.st_size > 16384:
        raise DataError('private_file_too_large')
    return p.read_text().strip()


@dataclass(frozen=True)
class Config:
    enabled: bool
    operations: tuple
    source: str
    state_dir: Path
    read_key_file: Path
    engine_key_file: Path
    dsn_file: Path | None = None

    @property
    def scope(self):
        value = [CONTRACT, self.source, list(self.operations)]
        return hashlib.sha256(json.dumps(value).encode()).hexdigest()

    @classmethod
    def load(cls, path):
        obj = json.loads(secret(path))
        if set(obj) - {'schema_version','enabled','operations','source','state_dir','read_key_file','engine_key_file','dsn_file'}:
            raise DataError('unknown_configuration_field')
        if type(obj.get('schema_version')) is not int or obj['schema_version'] != 1 or type(obj.get('enabled')) is not bool:
            raise DataError('invalid_configuration_version')
        ops = obj.get('operations')
        if not isinstance(ops,list) or not 1 <= len(ops) <= 4 or any(type(x) is not int or not 1 <= x <= 2147483647 for x in ops) or len(set(ops)) != len(ops):
            raise DataError('explicit_operation_scope_required')
        if obj.get('source') not in ('synthetic','real'):
            raise DataError('explicit_provenance_required')
        paths = {k: Path(obj[k]) for k in ('state_dir','read_key_file','engine_key_file')}
        if obj.get('dsn_file'):
            paths['dsn_file'] = Path(obj['dsn_file'])
        if paths['read_key_file']==paths['engine_key_file']:
            raise DataError('separate_read_and_engine_keys_required')
        if any(not p.is_absolute() for p in paths.values()):
            raise DataError('absolute_private_paths_required')
        return cls(obj['enabled'],tuple(sorted(ops)),obj['source'],**paths)
