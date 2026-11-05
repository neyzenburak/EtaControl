"""Kurumdan ba??ms?z XLSX tablo, bi?im ve atomik dosya ?retimi."""
from __future__ import annotations
from datetime import datetime, timezone, timedelta
from pathlib import Path
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
INK = '193247'
ISTANBUL = timezone(timedelta(hours=3))

def date_value(value):
    return datetime.fromisoformat(value).replace(tzinfo=None) if value else None

def capture_value(value):
    return datetime.fromisoformat(value).astimezone(ISTANBUL).replace(tzinfo=None) if value else None

def put(sheet, row, col, value):
    cell = sheet.cell(row, col, value)
    if isinstance(value, str):
        cell.data_type = 's'  # Identifiers and terminal text are never Excel formulas.
    return cell

def sheet_table(wb, name, title, headers, rows, *, metadata='', raw=False, start=None,
                table_name=None, text=(), dates=(), days=(), times=()):
    sheet = wb.create_sheet(name)
    sheet.sheet_view.showGridLines = False
    start = start or (1 if raw else 5)
    if not raw:
        put(sheet, 2, 1, title).font = Font(name='Arial', size=16, bold=True, color=INK)
        put(sheet, 3, 1, metadata).font = Font(name='Arial', size=10, color='657380')
    for row_number, values in enumerate([headers, *rows], start):
        sheet.row_dimensions[row_number].height = 21
        for column, value in enumerate(values, 1):
            cell = put(sheet, row_number, column, value)
            cell.font = Font(name='Arial', size=10, color='253746')
            cell.alignment = Alignment(vertical='center')
            letter = get_column_letter(column)
            if row_number == start:
                cell.fill = PatternFill('solid', fgColor=INK)
                cell.font = Font(name='Arial', size=10, bold=True, color='FFFFFF')
            elif letter in text:
                cell.number_format = '@'
            elif letter in dates:
                cell.number_format = 'yyyy-mm-dd hh:mm'
            elif letter in days:
                cell.number_format = 'yyyy-mm-dd'
            elif letter in times:
                cell.number_format = 'hh:mm:ss'
    for column in range(1, len(headers) + 1):
        sheet.column_dimensions[get_column_letter(column)].width = 18
    sheet.freeze_panes = f'A{start + 1}'
    if rows:
        table = Table(displayName=table_name, ref=f'A{start}:{get_column_letter(len(headers))}{start + len(rows)}')
        table.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
        sheet.add_table(table)
    return sheet

def save(wb, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    try:
        wb.save(temporary)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return path
