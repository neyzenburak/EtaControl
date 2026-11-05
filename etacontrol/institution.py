"""Yerel kurum paketinin doğrulanması ve atomik olarak hazırlanması."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = Path('kurum') / 'EtaControl_KurumPaketi.zip'


class PackageError(ValueError):
    """Kullanıcıya açıklanabilir kurum paketi hatası."""


def environment(root=ROOT):
    root = Path(root).resolve()
    return {**os.environ, 'ETA_CONTROL_DATA': str(root/'data'), 'PYTHONPATH': str(root), 'PYTHONIOENCODING': 'utf-8'}


def prepare(root=ROOT):
    root = Path(root).resolve()
    package = root/PACKAGE
    if not package.is_file():
        raise PackageError(f'Kurum paketi eksik. Yetkiliden aldığınız {PACKAGE.as_posix()} dosyasını bu klasöre koyup kurulumu yeniden çalıştırın.')
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    local = root/'.yerel'
    release = local/digest
    if (release/'HAZIR.json').is_file():
        saved = json.loads((release/'HAZIR.json').read_text(encoding='utf-8'))
        if all((release/path).is_file() and hashlib.sha256((release/path).read_bytes()).hexdigest()==sha for path,sha in saved['files'].items()):
            return release/'runtime'
    with zipfile.ZipFile(package) as archive:
        if len(archive.infolist())>500:
            raise PackageError('Kurum paketi dosya sınırını aşıyor.')
        if sum(i.file_size for i in archive.infolist())>25_000_000:
            raise PackageError('Kurum paketi boyut sınırını aşıyor.')
        try:
            manifest = json.loads(archive.read('manifest.json'))
        except (KeyError,ValueError) as exc:
            raise PackageError('Kurum paketinin manifest dosyası geçersiz.') from exc
        if manifest.get('format_version')!=1 or not isinstance(manifest.get('files'),dict):
            raise PackageError('Kurum paketi biçimi desteklenmiyor.')
        listed = manifest['files']
        names = [i.filename for i in archive.infolist()]
        if len(names)!=len(set(names)) or set(names)!=set(listed)|{'manifest.json'}:
            raise PackageError('Kurum paketinin dosya listesi doğrulanamadı.')
        content = {}
        for name, expected in listed.items():
            part = PurePosixPath(name)
            if '\\' in name or part.is_absolute() or '..' in part.parts or not part.parts or part.parts[0]!='runtime' or ':' in name:
                raise PackageError('Kurum paketinde geçersiz dosya yolu var.')
            info = archive.getinfo(name)
            if (info.external_attr>>16)&0o170000 == 0o120000:
                raise PackageError('Kurum paketi sembolik bağlantı içeremez.')
            value = archive.read(name)
            if hashlib.sha256(value).hexdigest()!=expected:
                raise PackageError(f'Kurum paketi bozuk: {name}')
            content[name]=value
        if not {'runtime/launcher.py','runtime/server.py'}<=set(content):
            raise PackageError('Kurum paketinin başlangıç dosyaları eksik.')
    local.mkdir(exist_ok=True)
    stage = local/('hazirlik-'+uuid.uuid4().hex)
    stage.mkdir()
    # Bütün yollar ve içerikler, ilk dosya yazılmadan önce doğrulandı.
    for name,value in content.items():
        destination = stage/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(value)
    (stage/'HAZIR.json').write_text(json.dumps({'sha256':digest,'files':listed},ensure_ascii=False),encoding='utf-8')
    if release.exists():
        release.rename(local/('onceki-'+uuid.uuid4().hex))
    stage.rename(release)
    return release/'runtime'
