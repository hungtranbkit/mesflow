"""Bounded private JSON; atomic replacement, single writer, no pickle."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile
from .domain import DataError

MAX_BYTES = 2*1024*1024


class Store:
    def __init__(self, root, create=False):
        self.root=Path(root)
        if create:
            self.root.mkdir(mode=0o700,parents=True,exist_ok=True)
        st=self.root.lstat()
        if not stat.S_ISDIR(st.st_mode) or st.st_mode & 0o077 or st.st_uid!=os.getuid():
            raise DataError('private_state_directory_required')

    def read(self, name, default=None):
        try:
            path=self.root/name
            st=path.lstat()
            if not stat.S_ISREG(st.st_mode) or st.st_mode & 0o077 or st.st_size>MAX_BYTES:
                raise DataError('invalid_state_file')
            value=json.loads(path.read_text())
            if not isinstance(value,dict) or value.get('schema_version')!=1:
                raise DataError('invalid_state_schema')
            return value
        except FileNotFoundError:
            if default is not None:return default
            raise DataError('snapshot_unavailable') from None
        except (ValueError,UnicodeError):
            raise DataError('invalid_state_json') from None

    def write(self,name,value):
        raw=json.dumps(value,allow_nan=False,separators=(',',':')).encode()
        if len(raw)>MAX_BYTES:raise DataError('state_size_exceeded')
        fd,tmp=tempfile.mkstemp(prefix='.'+name,dir=self.root)
        try:
            with os.fdopen(fd,'wb') as f:
                f.write(raw);f.flush();os.fsync(f.fileno())
            os.replace(tmp,self.root/name)
            directory=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY)
            try:os.fsync(directory)
            finally:os.close(directory)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)

    @contextmanager
    def lock(self):
        fd=os.open(self.root/'worker.lock',os.O_CREAT|os.O_WRONLY|os.O_NOFOLLOW,0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise DataError('worker_busy') from None
            for name in ('.control.json*','.snapshot.json*'):
                for orphan in self.root.glob(name):orphan.unlink()
            yield
        finally:os.close(fd)
