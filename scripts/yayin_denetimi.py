"""Git ile izlenen dosyaları yayın öncesi denetler; kurum sözcükleri yerel dosyadan okunabilir."""
from pathlib import Path
import argparse
import json
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
DENIED_SUFFIXES={'.zip','.db','.sqlite','.sqlite3','.xls','.xlsx','.xlsm','.csv','.mac','.png','.jpg','.jpeg','.pdf','.pyc'}
DENIED_DIRS={'data','.yerel','.venv','outputs','qa','node_modules','__pycache__','eta_app','web'}


def check(paths,terms=()):
    problems=[]
    for path in paths:
        relative=path.relative_to(ROOT)
        if path.suffix.lower() in DENIED_SUFFIXES or set(relative.parts)&DENIED_DIRS:
            problems.append(f'Yasaklı dosya: {relative}')
            continue
        if relative.parts[0]=='kurum' and relative.as_posix() not in {'kurum/README.md','kurum/.gitkeep'}:
            problems.append(f'Kurum dosyası izleniyor: {relative}')
        try:text=path.read_text(encoding='utf-8')
        except UnicodeError:
            problems.append(f'Metin olmayan dosya: {relative}');continue
        if re.search(r'[A-Z]:[\\/]+Users[\\/]+[A-Za-z0-9_]',text):
            problems.append(f'Kullanıcıya özel yol: {relative}')
        for term in terms:
            if re.search(r'(?<![A-Za-z0-9_])'+re.escape(term)+r'(?![A-Za-z0-9_])',text,re.I):
                problems.append(f'Özel sözcük bulundu: {relative}')
    return problems


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--private-terms',type=Path);args=parser.parse_args()
    terms=json.loads(args.private_terms.read_text(encoding='utf-8')) if args.private_terms else []
    output=subprocess.run(['git','ls-files','-z'],cwd=ROOT,check=True,capture_output=True).stdout
    paths=[ROOT/name.decode('utf-8') for name in output.split(b'\0') if name]
    problems=check(paths,terms)
    if problems:raise SystemExit('\n'.join(problems))
    print(f'Yayın denetimi geçti: {len(paths)} izlenen dosya.')
