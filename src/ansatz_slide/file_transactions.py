"""Local source publication with retained displaced versions and no-clobber recovery."""
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid

from .project import atomic_write


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    mode = path.lstat().st_mode
    if not stat.S_ISREG(mode):
        raise ValueError(f'Expected regular file, not link or special file: {path}')


def restore_missing(backup, target):
    """Never replace a file created by another writer during recovery."""
    staged = backup.parent/('restore-' + uuid.uuid4().hex)
    atomic_write(staged, backup.read_bytes())
    staged.chmod(stat.S_IMODE(backup.stat().st_mode))
    try:
        os.link(staged, target)
    except FileExistsError:
        return False
    finally:
        staged.unlink(missing_ok=True)
    return True


class Publication:
    def __init__(self, target, backup, new_hash):
        self.target, self.backup, self.new_hash = target, backup, new_hash

    def rollback(self):
        # Capture, rather than discard, any version found at the destination.
        if not self.target.exists():
            restore_missing(self.backup, self.target)
            return
        if self.target.is_symlink():
            return
        displaced = self.backup.parent/'rollback-displaced'
        os.rename(self.target, displaced)
        original = self.backup if digest(displaced.read_bytes()) == self.new_hash else displaced
        restore_missing(original, self.target)


def preserving_replace(target, data, expected_hash):
    """Capture the exact displaced file before publishing without overwriting.

    The destination is briefly absent between rename and exclusive link. Ordinary
    writers that bypass the API lock may conflict; displaced versions stay in
    .ansatz-recovery for recovery, including on success. No global isolation from
    unrelated editors is claimed.
    """
    target = Path(target)
    regular(target)
    recovery_root = target.parent/'.ansatz-recovery'
    if recovery_root.is_symlink():
        raise ValueError('Recovery directory must not be a symlink')
    folder = recovery_root/uuid.uuid4().hex
    folder.mkdir(parents=True)
    atomic_write(folder/'recovery.json', json.dumps({'target':str(target), 'expectedHash':expected_hash}, indent=2).encode())
    staged, backup = folder/'candidate', folder/'previous'
    atomic_write(staged, data)
    # All fallible permission work precedes the first change to the live source.
    staged.chmod(stat.S_IMODE(target.stat().st_mode))
    regular(target)
    if digest(target.read_bytes()) != expected_hash:
        raise RuntimeError('Concurrent source edit before publication; retry page check')
    os.rename(target, backup)
    publication = Publication(target, backup, digest(data))
    try:
        regular(backup)
        if digest(backup.read_bytes()) != expected_hash:
            raise RuntimeError('Concurrent source edit at publication')
        os.link(staged, target)  # Fails rather than replacing a new external file.
    except Exception as exc:
        restore_missing(backup, target)
        raise RuntimeError(f'Publication conflict/failure; displaced source retained at {backup}: {exc}') from exc
    return publication


def retract_created(target, expected_hash):
    """Retain a failed new publication; restore a displaced external version."""
    target = Path(target)
    if not target.exists() or target.is_symlink(): return
    regular(target)
    recovery_root = target.parent/'.ansatz-recovery'
    if recovery_root.is_symlink(): raise ValueError('Recovery directory must not be a symlink')
    folder = recovery_root/uuid.uuid4().hex
    folder.mkdir(parents=True)
    displaced = folder/'failed-creation'
    try: os.rename(target, displaced)
    except FileNotFoundError: return
    if digest(displaced.read_bytes()) != expected_hash:
        restore_missing(displaced, target)
