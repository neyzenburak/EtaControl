"""Yalnız aynı kurulum köküne ait yerel sunucuyu güvenle durdurur."""
import json
from pathlib import Path
import urllib.error
import urllib.request

import psutil

from .institution import ROOT, PackageError


def stop(root=ROOT):
    root=Path(root).resolve()
    state=root/'data'/'server.json'
    if not state.is_file():return
    meta=json.loads(state.read_text(encoding='utf-8'))
    try:
        process=psutil.Process(meta['pid'])
        args=process.cmdline()
        owned=False
        for argument in args:
            if argument.lower().endswith('server.py'):
                candidate=Path(argument).resolve()
                owned=candidate==root/'server.py' or (candidate.name=='server.py' and candidate.is_relative_to(root/'.yerel'))
                if owned:break
        if not owned or abs(process.create_time()-meta['created'])>=2:
            raise PackageError('Kayıtlı süreç bu kurulumun sunucusu değil; süreç durdurulmadı.')
        url=meta.get('url','')
        if not url.startswith('http://127.0.0.1:'):
            raise PackageError('Sunucu adresi yerel değil; işlem durduruldu.')
        try:
            with urllib.request.urlopen(url+'/api/jobs',timeout=5) as response:jobs=json.load(response)
        except urllib.error.URLError as exc:
            raise PackageError('Sunucunun çalışma durumu doğrulanamadı; uygulamayı kapatıp yeniden deneyin.') from exc
        if jobs.get('active'):
            raise PackageError('Terminal işlemi sürüyor; sunucu durdurulmadı.')
        process.terminate();process.wait(15)
    except psutil.NoSuchProcess:
        pass
    state.unlink(missing_ok=True)
