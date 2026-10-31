from pathlib import Path, PurePosixPath
from zipfile import ZipFile
from xml.etree import ElementTree as E
from datetime import datetime, timezone
import hashlib, json, posixpath, re

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'extracted' / '온도기록계_관측기록.xlsx'
NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
      'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'p': 'http://schemas.openxmlformats.org/package/2006/relationships'}

def tag(n):
    return n.split('}', 1)[-1]

def text(n):
    return ''.join(n.itertext()) if n is not None else ''

def attrs(n):
    return {tag(k): v for k, v in n.attrib.items()}

def relpath(part, target):
    return posixpath.normpath(target.lstrip('/') if target.startswith('/') else
                             posixpath.join(posixpath.dirname(part), target))

def childxml(n):
    return E.tostring(n, encoding='unicode')

with ZipFile(SOURCE) as z:
    names = z.namelist()
    members = [{'part': x.filename, 'bytes': x.file_size,
                'compressed_bytes': x.compress_size, 'crc32': f'{x.CRC:08x}',
                'sha256': hashlib.sha256(z.read(x.filename)).hexdigest()}
               for x in z.infolist()]
    shared = []
    if 'xl/sharedStrings.xml' in names:
        shared = [text(x) for x in E.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si', NS)]
    rels = []
    for part in names:
        if part.endswith('.rels'):
            for r in E.fromstring(z.read(part)):
                rels.append({'part': part, **attrs(r)})
    wb = E.fromstring(z.read('xl/workbook.xml'))
    wr = {x['Id']: x for x in rels if x['part'] == 'xl/_rels/workbook.xml.rels'}
    sheets = []
    all_cells = []
    for sh in wb.findall('m:sheets/m:sheet', NS):
        rid = sh.attrib['{' + NS['r'] + '}id']
        part = relpath('xl/workbook.xml', wr[rid]['Target'])
        tree = E.fromstring(z.read(part))
        cells = []
        for c in tree.findall('m:sheetData/m:row/m:c', NS):
            typ = c.get('t', 'n')
            raw = c.find('m:v', NS)
            v = raw.text if raw is not None else None
            if typ == 's':
                value = shared[int(v)]
            elif typ == 'inlineStr':
                value = text(c.find('m:is', NS))
            elif typ == 'b':
                value = v == '1'
            else:
                value = v
            f = c.find('m:f', NS)
            entry = {'address': c.get('r'), 'type': typ, 'style': c.get('s'),
                     'value': value, 'raw_value': v,
                     'formula': text(f) if f is not None else None,
                     'formula_attributes': attrs(f) if f is not None else None}
            cells.append(entry)
            all_cells.append({'sheet': sh.get('name'), **entry})
        dim = tree.find('m:dimension', NS)
        sheet_data = {
            'name': sh.get('name'), 'sheet_id': sh.get('sheetId'),
            'state': sh.get('state', 'visible'), 'part': part,
            'dimension': dim.get('ref') if dim is not None else None,
            'cell_count': len(cells),
            'nonempty_cells': len([c for c in cells if c['value'] not in (None, '') or c['formula']]),
            'cells': cells,
            'rows': [attrs(n) for n in tree.findall('m:sheetData/m:row', NS)],
            'columns': [attrs(n) for n in tree.findall('m:cols/m:col', NS)],
            'hidden_rows': [attrs(n) for n in tree.findall('m:sheetData/m:row', NS) if n.get('hidden') in ('1','true')],
            'hidden_columns': [attrs(n) for n in tree.findall('m:cols/m:col', NS) if n.get('hidden') in ('1','true')],
            'merged_cells': [attrs(n) for n in tree.findall('m:mergeCells/m:mergeCell', NS)],
            'hyperlinks': [attrs(n) for n in tree.findall('m:hyperlinks/m:hyperlink', NS)],
            'drawing_references': [attrs(n) for n in tree if tag(n.tag) in ('drawing','legacyDrawing','legacyDrawingHF','picture')],
            'header_footer': [childxml(n) for n in tree.findall('m:headerFooter', NS)],
            'auto_filters': [attrs(n) for n in tree.findall('m:autoFilter', NS)],
            'sheet_protection': [attrs(n) for n in tree.findall('m:sheetProtection', NS)],
            'validations': [childxml(n) for n in tree.findall('m:dataValidations', NS)],
            'conditional_formatting': [childxml(n) for n in tree.findall('m:conditionalFormatting', NS)],
            'top_level_elements': [tag(n.tag) for n in tree],
        }
        sheets.append(sheet_data)
    media = [n for n in names if n.startswith('xl/media/')]
    special_parts = {k: [n for n in names if re.search(pattern, n, re.I)] for k, pattern in {
        'comments': r'comments|threadedComment|persons',
        'drawings': r'/drawings/|vmlDrawing',
        'charts': r'/charts/', 'media': r'/media/',
        'external_links': r'externalLink|connections|queryTable',
        'macros_active_content': r'vbaProject|activeX|embeddings|customUI',
        'tables_pivots': r'/tables/|pivotTable|pivotCache',
    }.items()}
    comments = []
    for p in special_parts['comments']:
        if p.endswith('.xml'):
            comments.append({'part': p, 'xml': z.read(p).decode('utf-8')})
    inventory = {
        'source_url': 'https://t1.kakaocdn.net/aitop100/aitop100/dist/tHHClVffN4f8jvA_vuOtuQ.zip#온도기록계_관측기록.xlsx',
        'captured_at_utc': datetime.now(timezone.utc).isoformat(),
        'bytes': SOURCE.stat().st_size,
        'sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'zip_crc_error': z.testzip(), 'members': members,
        'workbook_properties': [childxml(n) for n in wb if tag(n.tag) not in ('sheets',)],
        'defined_names': [attrs(n) | {'text': text(n)} for n in wb.findall('m:definedNames/m:definedName', NS)],
        'relationships': rels,
        'external_relationships': [r for r in rels if r.get('TargetMode') == 'External'],
        'styles_xml': z.read('xl/styles.xml').decode('utf-8'),
        'special_parts': special_parts, 'comments': comments,
        'sheets': sheets,
    }

(ROOT / 'inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2)+'\n')
(ROOT / 'all_cells.json').write_text(json.dumps(all_cells, ensure_ascii=False, indent=2)+'\n')
(ROOT / 'workbook_SHA256SUMS').write_text(inventory['sha256']+'  '+SOURCE.name+'\n')
lines = []
for s in sheets:
    lines += ['# '+s['name']+' — '+str(s['dimension'])+' — '+s['state'], '']
    for c in s['cells']:
        if c['value'] not in (None, '') or c['formula']:
            lines.append(c['address']+'\t'+str(c['value'])+(' [FORMULA: '+c['formula']+']' if c['formula'] else ''))
    lines.append('')
(ROOT / 'all_cells.txt').write_text('\n'.join(lines)+'\n')
print(json.dumps({'sha256': inventory['sha256'], 'bytes': inventory['bytes'],
    'sheets': [{'name':s['name'], 'state':s['state'], 'dimension':s['dimension'], 'cells':s['cell_count'], 'hidden_rows':len(s['hidden_rows']), 'hidden_cols':len(s['hidden_columns'])} for s in sheets],
    'total_cells':len(all_cells),'formulas':sum(c['formula'] is not None for c in all_cells),
    'special_parts':special_parts,'external_relationships':inventory['external_relationships'],
    'zip_crc_error':inventory['zip_crc_error']},ensure_ascii=False,indent=2))
