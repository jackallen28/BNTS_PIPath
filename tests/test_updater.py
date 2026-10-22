"""Exercise updates with real local Git history and ZIPs; no network or student data writes."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from pipath import updater


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],text=True,stderr=subprocess.DEVNULL).strip()


def app_files(root,version):
    (root/'pipath').mkdir(parents=True,exist_ok=True)
    (root/'data').mkdir(exist_ok=True)
    (root/'main.py').write_text(f'print({version!r})\n')
    (root/'pipath/app.py').write_text(f'VERSION = {version!r}\n')
    (root/'data/catalog.toml').write_text('project = []\n')


def commit(root,message):
    git(root,'add','.')
    git(root,'-c','user.name=PiPath Test','-c','user.email=test@example.invalid','commit','-qm',message)


class TestGitUpdates(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.source=self.base/'source'
        self.source.mkdir()
        git(self.source,'init','-q','-b',updater.BRANCH)
        app_files(self.source,'one')
        commit(self.source,'initial')
        self.root=self.base/'pipath'
        subprocess.run(['git','clone','-q',str(self.source),str(self.root)],check=True)
        git(self.root,'remote','set-url','origin',f'https://github.com/{updater.REPOSITORY}.git')
        self.data=self.base/'students'
        self.data.mkdir()
        (self.data/'work.py').write_text('my student work')
        self.env=patch.dict(os.environ,{'PIPATH_HOME':str(self.data)})
        self.env.start()
        original=updater._git
        def local_fetch(root,*args,**kw):
            if args[:3] == ('fetch','--no-tags','origin'):
                return original(root,'fetch','--no-tags',str(self.source),*args[3:],**kw)
            return original(root,*args,**kw)
        self.fetch=patch.object(updater,'_git',side_effect=local_fetch)
        self.fetch.start()

    def tearDown(self):
        self.fetch.stop()
        self.env.stop()
        self.tmp.cleanup()

    def release(self,version='two'):
        app_files(self.source,version)
        commit(self.source,'release')

    def test_fast_forward_then_repeat_is_current_student_work_survives(self):
        self.release()
        self.assertEqual(updater.check_and_update(self.root).status,'updated')
        self.assertEqual(git(self.root,'rev-parse','HEAD'),git(self.source,'rev-parse','HEAD'))
        self.assertEqual(updater.check_and_update(self.root).status,'current')
        self.assertEqual((self.data/'work.py').read_text(),'my student work')

    def test_local_edits_and_local_commits_are_not_overwritten(self):
        self.release()
        (self.root/'main.py').write_text('teacher edits')
        self.assertEqual(updater.check_and_update(self.root).status,'skipped')
        self.assertEqual((self.root/'main.py').read_text(),'teacher edits')
        (self.root/'main.py').write_text('print("teacher version")\n')
        commit(self.root,'local work')
        before=git(self.root,'rev-parse','HEAD')
        self.assertEqual(updater.check_and_update(self.root).status,'skipped')
        self.assertEqual(git(self.root,'rev-parse','HEAD'),before)

    def test_development_branch_is_not_switched(self):
        git(self.root,'checkout','-qb','my-feature')
        self.release()
        self.assertEqual(updater.check_and_update(self.root).status,'skipped')
        self.assertEqual(git(self.root,'branch','--show-current'),'my-feature')

    def test_offline_keeps_installed_version(self):
        self.release()
        self.fetch.stop()
        original=updater._git
        def offline(root,*args,**kw):
            if args[0]=='fetch': raise subprocess.TimeoutExpired('git fetch',15)
            return original(root,*args,**kw)
        with patch.object(updater,'_git',side_effect=offline):
            result=updater.check_and_update(self.root)
        self.assertEqual(result.status,'offline')
        self.assertIn('one',(self.root/'main.py').read_text())

    def test_broken_release_is_rejected_before_install(self):
        (self.source/'main.py').write_text('this is not python!\n')
        commit(self.source,'invalid candidate')
        before=git(self.root,'rev-parse','HEAD')
        self.assertEqual(updater.check_and_update(self.root).status,'failed')
        self.assertEqual(git(self.root,'rev-parse','HEAD'),before)
        self.assertIn('one',(self.root/'main.py').read_text())


class TestArchiveUpdates(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        self.root=self.base/'pipath'
        self.root.mkdir()
        app_files(self.root,'one')
        updater.write_archive_manifest(self.root)
        self.env=patch.dict(os.environ,{'PIPATH_HOME':str(self.base/'students')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def download(self,url,destination):
        candidate=self.base/'release'
        app_files(candidate,'two')
        with zipfile.ZipFile(destination,'w') as archive:
            for path in candidate.rglob('*'):
                if path.is_file(): archive.write(path,'pipath-release/'+path.relative_to(candidate).as_posix())

    def test_managed_zip_update_keeps_backup_and_repeats_cleanly(self):
        with patch.object(updater,'_download_zip',side_effect=self.download):
            self.assertEqual(updater.check_and_update(self.root).status,'updated')
            self.assertEqual(updater.check_and_update(self.root).status,'current')
        self.assertIn('two',(self.root/'main.py').read_text())
        backups=list(self.base.glob('pipath.before-update-*'))
        self.assertEqual(len(backups),1)
        self.assertIn('one',(backups[0]/'main.py').read_text())

    def test_extra_teacher_files_block_automatic_replacement(self):
        (self.root/'teacher-notes.txt').write_text('keep this')
        with patch.object(updater,'_download_zip') as download:
            self.assertEqual(updater.check_and_update(self.root).status,'skipped')
            download.assert_not_called()
        self.assertEqual((self.root/'teacher-notes.txt').read_text(),'keep this')

    def test_malicious_archive_cannot_write_outside_candidate(self):
        def download(url,destination):
            with zipfile.ZipFile(destination,'w') as archive:
                archive.writestr('../escaped.txt','bad')
        with patch.object(updater,'_download_zip',side_effect=download):
            self.assertEqual(updater.check_and_update(self.root).status,'failed')
        self.assertFalse((self.base/'escaped.txt').exists())
        self.assertIn('one',(self.root/'main.py').read_text())

    def test_student_data_inside_installation_blocks_updates(self):
        with patch.dict(os.environ,{'PIPATH_HOME':str(self.root/'students')}):
            self.assertEqual(updater.check_and_update(self.root).status,'skipped')
