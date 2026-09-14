"""Strict local history readback and immutable staging; no remote shell or uploads."""
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def safe_relative(value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value or '\0' in value:
        raise ValueError('UNSAFE_PATH')
    p = PurePosixPath(value)
    if p.is_absolute() or '..' in p.parts or any(x in ('', '.', '..') for x in value.split('/')):
        raise ValueError('UNSAFE_PATH')
    return p


def contained(root, relative):
    root = Path(root).resolve()
    p = root.joinpath(*safe_relative(str(relative)).parts)
    if not p.resolve().is_relative_to(root):
        raise ValueError('PATH_ESCAPES_ROOT')
    return p


def history_file(outputs, node, extension, comfy_root):
    entries = [item for values in outputs.get(node, {}).values() if isinstance(values, list)
               for item in values if isinstance(item, dict) and isinstance(item.get('filename'), str)
               and item['filename'].endswith(extension)]
    if len(entries) != 1:
        raise ValueError('HISTORY_OUTPUT_COUNT')
    item = entries[0]
    filename = item['filename']
    if len(safe_relative(filename).parts) != 1 or item.get('type') != 'output':
        raise ValueError('UNSAFE_HISTORY_OUTPUT')
    subfolder = item.get('subfolder', '')
    if not isinstance(subfolder, str):
        raise ValueError('UNSAFE_SUBFOLDER')
    if subfolder:
        safe_relative(subfolder)
    path = contained(Path(comfy_root) / 'output', (subfolder + '/' if subfolder else '') + filename)
    if not path.is_file() or path.stat().st_size == 0:
        raise ValueError('HISTORY_FILE_NOT_PRESENT_LOCALLY')
    return path


def copy_verified(source, target):
    source, target = Path(source), Path(target)
    expected = digest(source)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if digest(target) != expected:
            raise ValueError('EXISTING_FILE_HASH_MISMATCH')
        return expected
    # Temporary file + atomic exclusive hard link prevents clobbering concurrent writes.
    fd, tmp = tempfile.mkstemp(prefix=target.name + '.', suffix='.part', dir=target.parent)
    try:
        with os.fdopen(fd, 'wb') as destination, source.open('rb') as origin:
            shutil.copyfileobj(origin, destination)
            destination.flush()
            os.fsync(destination.fileno())
        if digest(tmp) != expected or digest(source) != expected:
            raise ValueError('COPY_HASH_MISMATCH')
        try:
            os.link(tmp, target)
        except FileExistsError:
            if digest(target) != expected:
                raise ValueError('CONCURRENT_FILE_HASH_MISMATCH') from None
        if digest(target) != expected:
            raise ValueError('STAGED_HASH_MISMATCH')
    finally:
        Path(tmp).unlink(missing_ok=True)
    return expected


def stop_gate(directory):
    directory = Path(directory).resolve()
    if any((parent / 'STOP').exists() for parent in (directory, *directory.parents)):
        raise ValueError('STOP_PRESENT_NO_SUBMISSION')
