"""Yerel master data için yapıştırma önizlemesi ve atomik sorumlu güncellemesi."""
import re
from collections import Counter

import hashlib
import json
from pathlib import Path
from .storage import uid

ASSETS = Path(__file__).resolve().parent / 'assets'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()


def parse_paste(text):
    if not isinstance(text, str) or len(text)>300_000:
        raise ValueError("Yapıştırılan metin en fazla 300.000 karakter olmalı.")
    lines=text.splitlines()
    if len(lines)>2000:
        raise ValueError("Tek seferde en fazla 2000 satır yapıştırın.")
    rows={};errors=[];duplicates=0
    for number,line in enumerate(lines,1):
        line=line.strip().lstrip('\ufeff')
        if not line:
            continue
        header=re.sub(r'[\t ;–—-]+',' ',line).casefold()
        if header in {'gsdb sorumlu','gsdb sorumlusu','gsdb sorumlu adı','gsdb sorumlu adi','gsdb llp person','gsdb owner'}:
            continue
        match=re.fullmatch(r'([A-Za-z0-9]{5})(?:[ \t]*[-–—;][ \t]*|\t+| +)(.+)',line)
        if not match:
            errors.append(dict(line=number,message="GSDB ve sorumluyu iki sütun veya GSDB - Sorumlu biçiminde girin."));continue
        code,owner=match[1].upper(),match[2].strip()
        if not owner or len(owner)>100 or any(ord(char)<32 or ord(char)==127 for char in owner):
            errors.append(dict(line=number,message="Sorumlu boş olamaz; en fazla 100 karakter ve tek sütun olmalı."));continue
        if code in rows:
            if rows[code]['owner']!=owner:
                errors.append(dict(line=number,message=f"{code}, {rows[code]['line']}. satırda farklı bir sorumluyla verilmiş."))
            else:
                duplicates+=1
            continue
        rows[code]=dict(gsdb=code,owner=owner,line=number)
    if not rows and not errors:
        errors.append(dict(line=0,message="Yapıştırılacak GSDB - Sorumlu satırı bulunamadı."))
    return dict(rows=list(rows.values()),errors=errors,duplicates=duplicates)


def preview_paste(store,text,plant='',new_enabled=True,*,plants=None,enabled_key='collection_enabled'):
    allowed_plants=set(plants) if plants is not None else {row['plant'] for row in store.suppliers()}
    if plant and plant not in allowed_plants:
        raise ValueError("Geçerli bir tesis seçin.")
    parsed=parse_paste(text)
    suppliers=store.suppliers()
    changes=[];errors=list(parsed['errors'])
    for row in parsed['rows']:
        matches=[s for s in suppliers if s['gsdb']==row['gsdb'] and (not plant or s['plant']==plant)]
        if not matches:
            if not plant:
                errors.append(dict(line=row['line'],message=f"{row['gsdb']} kayıtlı değil. Yeni kayıt eklemek için tesis seçin."));continue
            matches=[dict(plant=plant,gsdb=row['gsdb'],owner=None,**{enabled_key:new_enabled})]
        for target in matches:
            status='ADD' if target['owner'] is None else 'SAME' if target['owner']==row['owner'] else 'UPDATE'
            changes.append(dict(plant=target['plant'],gsdb=row['gsdb'],line=row['line'],old_owner=target['owner'],
                                owner=row['owner'],collection_enabled=target.get(enabled_key,True),status=status))
    counts=Counter(change['status'] for change in changes)
    return dict(changes=changes,errors=errors,duplicates=parsed['duplicates'],
                counts={status:counts[status] for status in ('ADD','UPDATE','SAME')},
                can_apply=not errors and bool(counts['ADD']+counts['UPDATE']),
                revision=digest(dict(suppliers=suppliers,revision=store.get('supplier_revision'),
                                     text=text,plant=plant,new_enabled=new_enabled)))


def commit_master(store,suppliers,changed_keys):
    revision=uid();prepared=[]
    owners={(s['plant'],s['gsdb']):s['owner'] for s in suppliers}
    for run in store.runs():
        records=store.records(run['id'])
        for record in records:
            key=(record['plant'],record['supplier'])
            if key not in changed_keys:
                continue
            record['owner']=owners[key]
            record['issues']=[i for i in record.get('issues',[]) if i not in {'MISSING_OWNER','OWNER_REPAIRED'}]
            if not record['owner']:
                record['issues'].append('MISSING_OWNER')
            elif record.get('source_owner','')!=record['owner']:
                record['issues'].append('OWNER_REPAIRED')
        stats=run.setdefault('stats',{})
        stats['owner_coverage']=sum(bool(r['owner']) for r in records)
        stats['owners_repaired']=sum('OWNER_REPAIRED' in r.get('issues',[]) for r in records)
        stats['issues']=dict(Counter(i for r in records for i in r.get('issues',[])))
        run['mapping_revision']=revision
        prepared.append((run,records))
    store.commit_import(suppliers,prepared,store.get('sources',[]),store.get('empty_snapshots',[]),revision)
    return revision


def apply_paste(store,preview,*,enabled_key='collection_enabled'):
    if preview['errors']:
        raise ValueError("Hatalı satırları düzeltin; hiçbir kayıt değiştirilmedi.")
    suppliers=store.suppliers();mapping={(s['plant'],s['gsdb']):s for s in suppliers};changed=set()
    for change in preview['changes']:
        if change['status']=='SAME':
            continue
        key=(change['plant'],change['gsdb'])
        if key not in mapping:
            target=dict(plant=change['plant'],gsdb=change['gsdb'],owner='',source_refs=['Master data · yapıştırma'],
                        **{enabled_key:change['collection_enabled']})
            suppliers.append(target);mapping[key]=target
        mapping[key].update(owner=change['owner'],manual=True)
        changed.add(key)
    if changed:
        commit_master(store,suppliers,changed)
        store.event("Yapıştırılan sorumlu listesi kaydedildi.",counts=preview['counts'],changed=len(changed),
                    changes=[{key:change[key] for key in ('plant','gsdb','old_owner','owner','status')}
                             for change in preview['changes'] if change['status']!='SAME'])
    return dict(counts=preview['counts'],changed=len(changed))
