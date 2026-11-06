"""Yalnız aynı kurulum köküne ait yerel sunucuyu güvenle durdurur."""
import json
import os
import re
from pathlib import Path
import urllib.error
import urllib.request

import psutil

from .institution import ROOT, PackageError


def owned_server(argument, root):
    candidate=Path(argument)
    if not candidate.is_absolute() or candidate.name.lower()!='server.py':
        return False
    candidate=candidate.resolve()
    if candidate==root/'server.py':
        return True
    if not candidate.is_relative_to(root/'.yerel'):
        return False
    parts=candidate.relative_to(root/'.yerel').parts
    return len(parts)==3 and bool(re.fullmatch(r'[a-f0-9]{64}',parts[0])) and parts[1]=='runtime'


def recover(root=ROOT):
    """Başlatıcının kayıt yazamadan bıraktığı aynı kuruluma ait sunucuyu bulur."""
    root=Path(root).resolve()
    state=root/'data'/'server.json'
    if state.exists():
        return
    matches=[]
    for process in psutil.process_iter(['pid','ppid','cmdline','create_time']):
        try:
            args=process.info.get('cmdline') or []
            owned=any(owned_server(arg,root) for arg in args)
            if not owned or '--port' not in args:
                continue
            port=int(args[args.index('--port')+1])
            if not 8767<=port<8780:
                continue
            url=f'http://127.0.0.1:{port}'
            with urllib.request.urlopen(url+'/api/bootstrap',timeout=3) as response:
                if json.load(response).get('app_id')!='eta-control-local':
                    continue
            # Re-check process identity after HTTP: a PID may have exited/recycled.
            created=process.info.get('create_time')
            if not isinstance(created,(int,float)) or not process.is_running() or abs(process.create_time()-created)>=2:
                continue
            matches.append(dict(pid=process.pid,ppid=process.info.get('ppid'),created=process.create_time(),url=url))
        except (psutil.Error,OSError,ValueError,KeyError,IndexError):
            continue
    # Windows venv uses a redirector process and a real interpreter child with
    # the same arguments. They are one server, not two independent instances.
    matched_ids={meta['pid'] for meta in matches}
    matches=[meta for meta in matches if meta['ppid'] not in matched_ids]
    for meta in matches:
        meta.pop('ppid')
    if len(matches)>1:
        raise PackageError('Bu kuruluma ait birden fazla sunucu bulundu; yeni sunucu başlatılmadı. Uygulamaları kapatıp yeniden deneyin.')
    if matches:
        state.parent.mkdir(parents=True,exist_ok=True)
        temporary=state.with_suffix('.recovery.tmp')
        temporary.write_text(json.dumps(matches[0]),encoding='utf-8')
        os.replace(temporary,state)


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
                owned=owned_server(argument,root)
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
        children=[child for child in process.children(recursive=True)
                  if any(owned_server(arg,root) for arg in child.cmdline())]
        for child in reversed(children):
            try:child.terminate()
            except psutil.NoSuchProcess:pass
        try:process.terminate();process.wait(15)
        except psutil.NoSuchProcess:pass
        for child in children:
            try:child.wait(15)
            except psutil.NoSuchProcess:pass
    except psutil.NoSuchProcess:
        pass
    state.unlink(missing_ok=True)
