from pathlib import Path, PurePosixPath
import zipfile, json, hashlib, xml.etree.ElementTree as ET

root=Path(__file__).resolve().parent
src=root.parent/'hlI1ZFiRXl4sgzAw6HF52Q.zip'
root.mkdir(parents=True, exist_ok=True)
inventory=[]
with zipfile.ZipFile(src) as z:
    for i in z.infolist():
        p=PurePosixPath(i.filename)
        assert not p.is_absolute() and '..' not in p.parts
        assert i.file_size < 20_000_000
        assert (i.external_attr >> 16) & 0o170000 != 0o120000
        dest=root/i.filename
        if i.is_dir(): dest.mkdir(parents=True,exist_ok=True);continue
        dest.parent.mkdir(parents=True,exist_ok=True)
        data=z.read(i);dest.write_bytes(data)
        inventory.append({'name':i.filename,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
(root/'inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2))
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
relsns='{http://schemas.openxmlformats.org/package/2006/relationships}'
result={'files':inventory,'sheets':[]}
book=root/'결항집하기록.xlsx'
with zipfile.ZipFile(book) as z:
    wb=ET.fromstring(z.read('xl/workbook.xml'))
    rels={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
    shared=[]
    if 'xl/sharedStrings.xml' in z.namelist():
        for si in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('m:si',ns):shared.append(''.join(si.itertext()))
    result['defined_names']=[{'attr':n.attrib,'text':n.text} for n in wb.findall('m:definedNames/m:definedName',ns)]
    result['external_links']=[n for n in z.namelist() if 'externalLink' in n]
    result['comment_parts']=[n for n in z.namelist() if 'comment' in n.lower()]
    for s in wb.findall('m:sheets/m:sheet',ns):
        target=rels[s.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
        part=target.lstrip('/') if target.startswith('/') else 'xl/'+target
        st=ET.fromstring(z.read(part))
        sh={'name':s.attrib['name'],'state':s.attrib.get('state','visible'),'dimension':st.find('m:dimension',ns).attrib,'rows':[], 'formulas':[], 'hidden_rows':[], 'hidden_cols':[], 'hyperlinks':[], 'merges':[]}
        for row in st.findall('m:sheetData/m:row',ns):
            if row.attrib.get('hidden')=='1':sh['hidden_rows'].append(row.attrib['r'])
            cells=[]
            for c in row.findall('m:c',ns):
                val=c.find('m:v',ns); t=c.attrib.get('t'); inline=c.find('m:is',ns)
                value=val.text if val is not None else ''
                if t=='s':value=shared[int(value)]
                elif t=='inlineStr':value=''.join(inline.itertext()) if inline is not None else ''
                f=c.find('m:f',ns)
                item={'cell':c.attrib['r'],'value':value,'type':t,'style':c.attrib.get('s')}
                if f is not None:item['formula']=f.text;sh['formulas'].append(item)
                if value!='' or f is not None:cells.append(item)
            if cells:sh['rows'].append(cells)
        sh['hidden_cols']=[c.attrib for c in st.findall('m:cols/m:col',ns) if c.attrib.get('hidden')=='1']
        sh['hyperlinks']=[c.attrib for c in st.findall('m:hyperlinks/m:hyperlink',ns)]
        sh['merges']=[c.attrib for c in st.findall('m:mergeCells/m:mergeCell',ns)]
        result['sheets'].append(sh)
    result['comments']={n:z.read(n).decode('utf8') for n in result['comment_parts'] if n.endswith('.xml')}
(root/'workbook_inventory.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
for s in result['sheets']:
    print('\nSHEET',s['name'],s['state'],s['dimension'],'formulas',len(s['formulas']),'hidden',s['hidden_rows'],s['hidden_cols'])
    for row in s['rows']:print(' | '.join(c['cell']+'='+c['value'] for c in row))
print('COMMENT_PARTS',result['comment_parts'])
