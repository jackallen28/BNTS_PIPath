"""Bounded, opt-out launch updates. Student data never belongs in the installation.

Git installs only fast-forward a clean copy of the configured release branch.
Managed ZIP installs validate the candidate and preserve a recoverable old copy.
No application modules are imported until this check is finished.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile

REPOSITORY = 'jackallen28/BNTS_PIPath'
BRANCH = 'main'
MANIFEST = '.pipath-install.json'
MAX_DOWNLOAD = 64 * 1024 * 1024


@dataclass(frozen=True)
class UpdateResult:
    status: str
    message: str


def _git(root, *args, timeout=15):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    return subprocess.run(['git','-C',str(root),*args], capture_output=True, text=True,
                          timeout=timeout, check=True, env=env).stdout.strip()


def _file_hashes(root: Path):
    result = {}
    for path in root.rglob('*'):
        rel = path.relative_to(root)
        if '__pycache__' in rel.parts or path.suffix == '.pyc' or rel.as_posix() == MANIFEST:
            continue
        if path.is_symlink():
            raise ValueError('Symbolic links require a manual update.')
        if path.is_file():
            result[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def write_archive_manifest(root: Path, repository=REPOSITORY, branch=BRANCH):
    root = Path(root)
    metadata = {'repository':repository,'branch':branch,'files':_file_hashes(root)}
    (root/MANIFEST).write_text(json.dumps(metadata,sort_keys=True)+'\n')


def _validate(root):
    for rel in ('main.py','pipath/app.py','data/catalog.toml'):
        if not (root/rel).is_file():
            raise ValueError('The update is missing application files.')
    import tomllib
    with (root/'data/catalog.toml').open('rb') as f:
        tomllib.load(f)
    for path in root.rglob('*.py'):
        if '__pycache__' not in path.parts:
            compile(path.read_bytes(), str(path), 'exec')


def _safe_member(name):
    path = PurePosixPath(name)
    return name and not path.is_absolute() and '..' not in path.parts and '\\' not in name


def _validate_git_candidate(root, ref):
    with tempfile.TemporaryDirectory(prefix='pipath-candidate-') as folder:
        archive = Path(folder)/'source.tar'
        with archive.open('wb') as out:
            subprocess.run(['git','-C',str(root),'archive',ref], stdout=out, stderr=subprocess.PIPE,
                           check=True, timeout=15)
        candidate = Path(folder)/'source'
        candidate.mkdir()
        with tarfile.open(archive) as source:
            members = source.getmembers()
            if any(not _safe_member(m.name) or not (m.isfile() or m.isdir()) for m in members):
                raise ValueError('Unsupported archive entry.')
            for member in members:
                target = candidate/member.name
                if member.isdir():
                    target.mkdir(parents=True,exist_ok=True)
                else:
                    target.parent.mkdir(parents=True,exist_ok=True)
                    with source.extractfile(member) as incoming, target.open('wb') as outgoing:
                        shutil.copyfileobj(incoming,outgoing)
                    target.chmod(member.mode & 0o777)
        _validate(candidate)


def _git_update(root, repository, branch):
    if _git(root, 'symbolic-ref','--quiet','--short','HEAD') != branch:
        return UpdateResult('skipped','Development branch: keeping this version of PiPath.')
    if _git(root,'status','--porcelain','--untracked-files=normal'):
        return UpdateResult('skipped','Local app changes found. Keeping them; use a manual update when ready.')
    origin = _git(root,'config','--get','remote.origin.url')
    allowed = {f'https://github.com/{repository}.git',f'https://github.com/{repository}',
               f'git@github.com:{repository}.git',f'ssh://git@github.com/{repository}.git'}
    if origin not in allowed:
        return UpdateResult('skipped','This installation uses a different source. Keeping the installed app.')
    before = _git(root,'rev-parse','HEAD')
    try:
        _git(root,'fetch','--no-tags','origin',branch)
    except (subprocess.SubprocessError,OSError):
        return UpdateResult('offline','Could not check for updates. Opening the installed version.')
    candidate = _git(root,'rev-parse','FETCH_HEAD')
    if candidate == before:
        return UpdateResult('current','PiPath is up to date.')
    try:
        _git(root,'merge-base','--is-ancestor',before,candidate)
    except subprocess.CalledProcessError:
        return UpdateResult('skipped','Local history differs from the release. A manual update is needed.')
    _validate_git_candidate(root,candidate)
    if (_git(root,'status','--porcelain','--untracked-files=normal') or
            _git(root,'rev-parse','HEAD') != before):
        return UpdateResult('skipped','App files changed during the check. Keeping your version.')
    _git(root,'merge','--ff-only',candidate)
    return UpdateResult('updated','PiPath updated. Opening the new version…')


def _download_zip(url, destination):
    start = time.monotonic()
    with urllib.request.urlopen(url,timeout=8) as response, destination.open('wb') as out:
        total = 0
        while chunk := response.read(64 * 1024):
            total += len(chunk)
            if total > MAX_DOWNLOAD or time.monotonic()-start > 20:
                raise ValueError('Update download exceeded its limits.')
            out.write(chunk)


def _unpack_zip(archive, destination):
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        if len(members) > 5000 or sum(m.file_size for m in members) > MAX_DOWNLOAD:
            raise ValueError('Update archive is too large.')
        seen = set()
        for member in members:
            if (not _safe_member(member.filename) or member.filename in seen
                    or (member.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('Unsupported archive entry.')
            seen.add(member.filename)
        source.extractall(destination)
    children = list(destination.iterdir())
    if len(children) != 1 or not children[0].is_dir():
        raise ValueError('Unexpected update layout.')
    return children[0]


def _archive_update(root,repository,branch):
    try:
        metadata = json.loads((root/MANIFEST).read_text())
    except (OSError,ValueError):
        return UpdateResult('skipped','Run Update PiPath once to enable launch updates for this ZIP installation.')
    if metadata.get('repository') != repository or metadata.get('branch') != branch:
        return UpdateResult('skipped','This installation uses a different release. Keeping the installed app.')
    if metadata.get('files') != _file_hashes(root):
        return UpdateResult('skipped','Local app changes found. Keeping them; use a manual update when ready.')
    with tempfile.TemporaryDirectory(prefix='.pipath-update-',dir=root.parent) as folder:
        folder = Path(folder)
        archive = folder/'update.zip'
        try:
            _download_zip(f'https://codeload.github.com/{repository}/zip/refs/heads/{branch}',archive)
        except (OSError,ValueError,urllib.error.URLError):
            return UpdateResult('offline','Could not check for updates. Opening the installed version.')
        unpack = folder/'unpack'
        unpack.mkdir()
        candidate = _unpack_zip(archive,unpack)
        _validate(candidate)
        if _file_hashes(candidate) == metadata['files']:
            return UpdateResult('current','PiPath is up to date.')
        write_archive_manifest(candidate,repository,branch)
        if _file_hashes(root) != metadata['files']:
            return UpdateResult('skipped','App files changed during the check. Keeping your version.')
        backup = root.with_name(root.name+'.before-update-'+uuid.uuid4().hex[:10])
        root.rename(backup)
        try:
            candidate.rename(root)
        except BaseException:
            backup.rename(root)
            raise
        # Retain a recoverable backup; never delete the previous installation automatically.
    return UpdateResult('updated','PiPath updated. Opening the new version…')


def check_and_update(root: Path, repository=REPOSITORY, branch=BRANCH):
    root = Path(root).resolve()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository) or not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_./-]*',branch):
        return UpdateResult('skipped','Invalid update settings. Opening the installed version.')
    data = Path(os.environ.get('PIPATH_HOME',str(Path.home()/'PiPath'))).expanduser().resolve()
    if data.is_relative_to(root) or root.is_relative_to(data):
        return UpdateResult('skipped','Student data overlaps the app folder. A manual update is needed.')
    try:
        with (root.parent/('.'+root.name+'-update.lock')).open('a') as lock:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                return UpdateResult('busy','Another PiPath update is running. Please reopen PiPath shortly.')
            if (root/'.git').exists():
                return _git_update(root,repository,branch)
            return _archive_update(root,repository,branch)
    except (OSError,ValueError,SyntaxError,subprocess.SubprocessError,zipfile.BadZipFile,tarfile.TarError):
        return UpdateResult('failed','The update could not be installed. Opening the installed version.')


def launch_update_check(root: Path, enabled=True):
    """Show progress before importing the app; restart once if files changed.

    Returns False if the user closed the launch window or another update is active.
    Only Raspberry Pis check automatically; development machines remain unchanged.
    """
    if os.environ.pop('PIPATH_UPDATE_RESTARTED',None) == '1':
        return True
    from .gpio import on_real_pi
    if not enabled or os.environ.get('PIPATH_AUTO_UPDATE','1') == '0' or not on_real_pi():
        return True
    import queue
    import threading
    import tkinter as tk
    import sys
    result_queue = queue.Queue()
    splash = tk.Tk(className='PiPath')
    splash.title('PiPath — checking for updates')
    splash.configure(bg='#C0C0C0')
    splash.geometry('520x140')
    splash.resizable(False,False)
    message = tk.Label(splash,text='Checking for PiPath updates…\nYour saved work stays on this Pi.',
                       bg='#C0C0C0',font=('DejaVu Sans',11),wraplength=480,padx=20,pady=25)
    message.pack(fill='both',expand=True)
    closing = False
    result = None
    def close():
        nonlocal closing
        closing = True
        message.configure(text='Finishing the update check before closing…')
    splash.protocol('WM_DELETE_WINDOW',close)
    def worker():
        try:
            outcome = check_and_update(root,os.environ.get('PIPATH_REPO',REPOSITORY),os.environ.get('PIPATH_BRANCH',BRANCH))
        except Exception:
            outcome = UpdateResult('failed','Could not check for updates. Opening the installed version.')
        result_queue.put(outcome)
    def poll():
        nonlocal result
        try:
            result = result_queue.get_nowait()
        except queue.Empty:
            splash.after(50,poll)
            return
        message.configure(text=result.message)
        splash.after(700,lambda: (splash.quit(),splash.destroy()))
    threading.Thread(target=worker,daemon=True).start()
    splash.after(50,poll)
    splash.mainloop()
    if closing or result.status == 'busy':
        return False
    if result.status == 'updated':
        os.environ['PIPATH_UPDATE_RESTARTED'] = '1'
        os.execv(sys.executable,[sys.executable,str(Path(root)/'main.py'),*sys.argv[1:]])
    return True
