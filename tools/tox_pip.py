# The following comment should be removed at some point in the future.
# mypy: disallow-untyped-defs=False

import os
import shutil
import subprocess
import sys
from glob import glob

VIRTUAL_ENV = os.environ['VIRTUAL_ENV']
TOX_PIP_DIR = os.path.join(VIRTUAL_ENV, 'pip')


def pip(args):
    # First things first, get a recent (stable) version of pip.
    # Capped at the era's pip: the GitHub legs add live PyPI as an
    # extra index (the release-date index carries no cryptography wheel for
    # darwin-arm64 or for CPython 3.9 on Windows), which otherwise resolves a
    # present-day pip here -- and a present-day pip rejects the
    # `--use-feature=2020-resolver` flag that tools/requirements/tests.txt
    # opens with, so no test env can be built. `<21` is what the release-date
    # index would have served anyway, so the Travis legs (which use that index
    # alone) resolve exactly what they already did. Capping it HERE rather than via
    # PIP_CONSTRAINT is deliberate: a constraint on `pip` also applies to the
    # sdist that tox installs from a path, which pip refuses with
    # "installation from path or url cannot be constrained to a version".
    if not os.path.exists(TOX_PIP_DIR):
        subprocess.check_call([sys.executable, '-m', 'pip',
                               '--disable-pip-version-check',
                               'install', '-t', TOX_PIP_DIR,
                               'pip<21'])
        shutil.rmtree(glob(os.path.join(TOX_PIP_DIR, 'pip-*.dist-info'))[0])
    # And use that version.
    pypath = os.environ.get('PYTHONPATH')
    pypath = pypath.split(os.pathsep) if pypath is not None else []
    pypath.insert(0, TOX_PIP_DIR)
    os.environ['PYTHONPATH'] = os.pathsep.join(pypath)
    subprocess.check_call([sys.executable, '-m', 'pip'] + args)


if __name__ == '__main__':
    pip(sys.argv[1:])
