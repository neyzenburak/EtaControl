from datetime import datetime
from io import BytesIO

from openpyxl import Workbook, load_workbook

from etacontrol.reports import capture_value, save, sheet_table
from etacontrol.storage import Store


def test_generic_table_preserves_text_and_does_not_execute_formulas(tmp_path):
    workbook=Workbook();workbook.remove(workbook.active)
    sheet=sheet_table(workbook,'Ornek','Örnek tablo',['Kimlik','Açıklama'],[['0001','=1+1']],table_name='OrnekTablo',text=['A','B'])
    path=save(workbook,tmp_path/'ornek.xlsx')
    book=load_workbook(BytesIO(path.read_bytes()))
    assert book['Ornek']['A6'].value=='0001'
    assert book['Ornek']['B6'].data_type=='s'
    assert book['Ornek'].freeze_panes=='A6'
    book.close()


def test_capture_time_is_converted_explicitly():
    assert capture_value('2026-01-01T09:00:00+00:00')==datetime(2026,1,1,12)


def test_store_and_import_do_not_mix_runs(tmp_path):
    store=Store(tmp_path)
    run=dict(id='ornek-calisma',imported_at='2026-01-01T09:00:00',source_at='2026-01-01T09:00:00',label='Örnek',kind='ornek')
    row=dict(id='ornek-kayit',plant='ORNEK',asn='0001',supplier='ORNEK',owner='Örnek sorumlu')
    store.save_run(run,[row])
    assert store.records('ornek-calisma')==[row]
    assert store.records('baska-calisma')==[]
    store.event('Örnek işlem')
    assert store.events(1)[0]['message']=='Örnek işlem'
