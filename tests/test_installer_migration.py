"""Run the actual installer against local Git repositories to verify the source migration."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_updater import app_files, commit, git

ROOT=Path(__file__).resolve().parents[1]


class TestInstallerMigration(unittest.TestCase):
    def test_old_source_changes_and_commits_survive_move_to_new_main(self):
        with tempfile.TemporaryDirectory() as folder:
            base=Path(folder)
            release=base/'release'
            release.mkdir()
            git(release,'init','-q','-b','BNTS_PiPath')
            app_files(release,'original')
            (release/'install.sh').write_text('#!/bin/sh\nexit 0\n')
            commit(release,'original app')
            installed=base/'pipath'
            subprocess.run(['git','clone','-q',str(release),str(installed)],check=True)
            git(installed,'remote','set-url','origin','https://github.com/jackallen28/jackallen.git')
            (installed/'local-commit.txt').write_text('Keep this local commit')
            commit(installed,'local teacher commit')
            local_head=git(installed,'rev-parse','HEAD')
            (installed/'main.py').write_text('print("unsaved teacher edit")\n')
            (installed/'teacher-notes.txt').write_text('Keep these untracked notes')
            git(release,'checkout','-qb','main')
            app_files(release,'new release')
            commit(release,'new repository release')
            # Only transport is redirected; the installer sees and migrates the real legacy origin.
            git(installed,'config',f'url.file://{release}.insteadOf','https://github.com/jackallen28/BNTS_PIPath.git')
            env=dict(os.environ,PIPATH_DIR=str(installed),PIPATH_NO_LAUNCH='1',
                     PIPATH_REPO='jackallen28/BNTS_PIPath',PIPATH_BRANCH='main')
            env['PATH']='/usr/bin:'+env['PATH']  # the system interpreter includes Tk, as on Pi OS Desktop
            result=subprocess.run(['bash',str(ROOT/'tools/install_pipath.sh')],env=env,
                                  capture_output=True,text=True,timeout=20)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(git(installed,'branch','--show-current'),'main')
            self.assertEqual(git(installed,'config','--get','remote.origin.url'),'https://github.com/jackallen28/BNTS_PIPath.git')
            self.assertEqual(git(installed,'rev-parse','HEAD'),git(release,'rev-parse','HEAD'))
            backups=git(installed,'for-each-ref','--format=%(objectname)','refs/heads/pipath-backup-*').splitlines()
            self.assertIn(local_head,backups)
            stash=git(installed,'stash','show','--include-untracked','-p','stash@{0}')
            self.assertIn('unsaved teacher edit',stash)
            self.assertIn('Keep these untracked notes',stash)
            self.assertTrue(any(r.startswith('pipath-previous-source-') for r in git(installed,'remote').splitlines()))
