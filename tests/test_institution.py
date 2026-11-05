import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from etacontrol.institution import PackageError, environment, prepare


def package(root,files=None):
    directory=root/'kurum';directory.mkdir(exist_ok=True)
    files=files or {'runtime/launcher.py':b'print("ornek")','runtime/server.py':b'pass'}
    manifest={'format_version':1,'files':{name:hashlib.sha256(value).hexdigest() for name,value in files.items()}}
    with zipfile.ZipFile(directory/'EtaControl_KurumPaketi.zip','w') as archive:
        archive.writestr('manifest.json',json.dumps(manifest))
        for name,value in files.items():archive.writestr(name,value)


def test_missing_package_explains_where_to_copy_it(tmp_path):
    with pytest.raises(PackageError,match='kurum'):
        prepare(tmp_path)


def test_install_is_repeatable_and_preserves_local_data(tmp_path):
    (tmp_path/'data').mkdir();db=tmp_path/'data'/'ornek.db';db.write_bytes(b'korunacak')
    package(tmp_path)
    runtime=prepare(tmp_path)
    assert runtime.parent.parent==tmp_path/'.yerel'
    assert prepare(tmp_path)==runtime
    assert db.read_bytes()==b'korunacak'
    assert environment(tmp_path)['ETA_CONTROL_DATA']==str(tmp_path/'data')


def test_changed_installed_file_is_repaired_without_deleting_old_copy(tmp_path):
    package(tmp_path);runtime=prepare(tmp_path)
    (runtime/'server.py').write_text('degisti')
    assert prepare(tmp_path)==runtime and (runtime/'server.py').read_text()=='pass'
    assert list((tmp_path/'.yerel').glob('onceki-*'))


@pytest.mark.parametrize('bad',['../disari.py','runtime/../../disari.py','/runtime/yanlis.py','runtime/C:yanlis.py','runtime\\yanlis.py'])
def test_paths_are_checked_before_writing_files(tmp_path,bad):
    package(tmp_path,{bad:b'pass','runtime/launcher.py':b'pass','runtime/server.py':b'pass'})
    with pytest.raises(PackageError):prepare(tmp_path)
    assert not (tmp_path/'.yerel').exists()


def test_bad_checksum_is_rejected(tmp_path):
    package(tmp_path)
    path=tmp_path/'kurum'/'EtaControl_KurumPaketi.zip'
    with zipfile.ZipFile(path) as archive:entries={i.filename:archive.read(i) for i in archive.infolist()}
    entries['runtime/server.py']=b'changed'
    with zipfile.ZipFile(path,'w') as archive:
        for name,value in entries.items():archive.writestr(name,value)
    with pytest.raises(PackageError,match='bozuk'):prepare(tmp_path)
