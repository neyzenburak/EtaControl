import copy

import pytest

from etacontrol.master_data import parse_paste, preview_paste, apply_paste
from etacontrol.storage import Store, now

P1,P2='ORNEK1','ORNEK2'


def seed(store):
    rows=[dict(plant=P1,gsdb='DEMO1',owner='Önceki',collection_enabled=False,source_refs=['Ornek']),
          dict(plant=P2,gsdb='DEMO1',owner='Diğer',collection_enabled=True,source_refs=['Ornek']),
          dict(plant=P1,gsdb='DEMO2',owner='Aynı',collection_enabled=True,source_refs=['Ornek'])]
    store.save_suppliers(rows)
    record=dict(id='record',plant=P1,supplier='DEMO1',asn='DEMO001',owner='Onceki',
                source_owner='Ham sorumlu',raw={'note':'kaynak'},issues=['OWNER_REPAIRED'])
    store.save_run(dict(id='run',kind='list',source_at=now(),imported_at=now(),label='Ornek',stats={}),[record])



@pytest.mark.parametrize('text',[
    'GSDB\tSorumlu\r\nDEMO1\tÖrnek Kişi\r\nDEMO2\tİkinci Kişi',
    '\ufeffGSDB - Sorumlu\n\n demo1 - Örnek Kişi\nDEMO2 — İkinci Kişi',
    'DEMO1;Örnek Kişi\nDEMO2 İkinci Kişi'])
def test_clipboard_formats_headers_unicode_and_empty_lines(text):
    result=parse_paste(text)
    assert not result['errors']
    assert [(r['gsdb'],r['owner']) for r in result['rows']]==[('DEMO1','Örnek Kişi'),('DEMO2','İkinci Kişi')]


def test_conflicting_duplicates_and_bad_rows_are_not_silently_ignored():
    result=parse_paste('DEMO1 - Bir\nDEMO1 - Bir\nDEMO1 - İki\nBAD - Üç\nDEMO2\tAd\tFazla sütun')
    assert result['duplicates']==1
    assert [e['line'] for e in result['errors']]==[3,4,5]
    assert parse_paste('')['errors']
    assert parse_paste('DEMO1 - '+('x'*101))['errors']


def test_scope_is_explicit_for_new_codes_and_previews_every_existing_plant(tmp_path):
    store=Store(tmp_path);seed(store)
    before=copy.deepcopy(store.suppliers())
    preview=preview_paste(store,'DEMO1 - Yeni')
    assert len(preview['changes'])==2 and preview['counts']['UPDATE']==2
    assert store.suppliers()==before
    assert preview_paste(store,'DEMO3 - Yeni')['errors']
    scoped=preview_paste(store,'DEMO1 - Yeni\nDEMO3 - Üç',P1)
    assert scoped['can_apply'] and scoped['counts']==dict(ADD=1,UPDATE=1,SAME=0)
    assert {c['plant'] for c in scoped['changes']}=={P1}


def test_atomic_apply_preserves_other_plants_flags_raw_records_and_omitted_rows(tmp_path):
    store=Store(tmp_path);seed(store)
    raw=copy.deepcopy(store.records('run')[0]['raw'])
    preview=preview_paste(store,'DEMO1 - Yeni\nDEMO3 - Üç',P1,False)
    assert apply_paste(store,preview)==dict(counts=dict(ADD=1,UPDATE=1,SAME=0),changed=2)
    rows={(r['plant'],r['gsdb']):r for r in store.suppliers()}
    assert rows[P1,'DEMO1']['owner']=='Yeni' and not rows[P1,'DEMO1']['collection_enabled']
    assert rows[P2,'DEMO1']['owner']=='Diğer'
    assert rows[P1,'DEMO2']['owner']=='Aynı'
    assert rows[P1,'DEMO3']['manual'] and not rows[P1,'DEMO3']['collection_enabled']
    record=store.records('run')[0]
    assert record['owner']=='Yeni' and record['raw']==raw and record['source_owner']=='Ham sorumlu'
    assert store.run('run')['mapping_revision']==store.get('supplier_revision')
    change=store.events(1)[0]['detail']['changes'][0]
    assert change['old_owner']=='Önceki' and change['owner']=='Yeni'
    before=copy.deepcopy(store.suppliers())
    with pytest.raises(ValueError):apply_paste(store,preview_paste(store,'DEMO1 - X\nBOZUK',P1))
    assert store.suppliers()==before


def test_failed_database_commit_rolls_back_entire_paste(tmp_path):
    store=Store(tmp_path);seed(store)
    before=copy.deepcopy(store.suppliers());records=copy.deepcopy(store.records('run'))
    with store.connect() as db:
        db.execute("CREATE TRIGGER prevent_rows BEFORE INSERT ON shipments BEGIN SELECT RAISE(ABORT,'test rollback'); END")
    preview=preview_paste(store,'DEMO1 - Yeni\nDEMO3 - Üç',P1)
    with pytest.raises(Exception,match='test rollback'):apply_paste(store,preview)
    assert store.suppliers()==before and store.records('run')==records


def test_first_import_requires_allowed_plant_and_supports_custom_flag_key(tmp_path):
    store=Store(tmp_path)
    with pytest.raises(ValueError):
        preview_paste(store,'DEMO1 - Ornek',P1)
    preview=preview_paste(store,'DEMO1 - Ornek',P1,False,plants=[P1],enabled_key='custom_flag')
    assert preview['can_apply'] and preview['counts']['ADD']==1
    apply_paste(store,preview,enabled_key='custom_flag')
    assert store.suppliers()[0]['custom_flag'] is False
    assert 'collection_enabled' not in store.suppliers()[0]


def test_preview_revision_binds_text_scope_flag_and_master_revision(tmp_path):
    store=Store(tmp_path);seed(store)
    baseline=preview_paste(store,'DEMO1 - Ornek',P1)['revision']
    assert baseline!=preview_paste(store,'DEMO1 - Baska',P1)['revision']
    assert baseline!=preview_paste(store,'DEMO1 - Ornek',P2)['revision']
    assert baseline!=preview_paste(store,'DEMO1 - Ornek',P1,False)['revision']
    store.set('supplier_revision','other')
    assert baseline!=preview_paste(store,'DEMO1 - Ornek',P1)['revision']
