from pathlib import Path
from html.parser import HTMLParser
from collections import Counter
from datetime import datetime, timezone
import json, hashlib, re
from pypdf import PdfReader
import pdfplumber

DIR=Path(__file__).resolve().parent
SRC=DIR/'extracted'

class Reader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags=Counter();self.stack=[];self.comments=[];self.resources=[];self.hidden=[]
        self.headings=[];self.blocks=[];self.inputs=[];self.tables=[];self.current_table=None
        self.row=None;self.cell=None;self.capture=None;self.capture_parts=[];self.text=[];self.style=[]
    def handle_starttag(self,tag,attrs):
        a=dict(attrs);self.tags[tag]+=1;self.stack.append(tag)
        if tag in ['img','script','iframe','object','embed','link','a','source','video','audio']:
            self.resources.append({'tag':tag,'attributes':a,'line':self.getpos()[0]})
        if 'hidden' in a or re.search(r'display\s*:\s*none|visibility\s*:\s*hidden',a.get('style',''),re.I):
            self.hidden.append({'tag':tag,'attributes':a,'line':self.getpos()[0]})
        if tag=='input':self.inputs.append({'attributes':a,'line':self.getpos()[0]})
        if tag in ['h1','h2','h3','p','li','blockquote','pre']:
            self.capture=tag;self.capture_parts=[]
        if tag=='table':
            self.current_table={'index':len(self.tables)+1,'line':self.getpos()[0],'preceding_heading':self.headings[-1]['text'] if self.headings else None,'rows':[]}
        if tag=='tr':self.row=[]
        if tag in ['th','td']:self.cell=[]
        if tag in ['h1','h2','h3','p','li','tr','section','div']:
            self.text.append('\n')
    def handle_endtag(self,tag):
        if tag in ['th','td'] and self.cell is not None:
            self.row.append(''.join(self.cell).strip());self.cell=None
        if tag=='tr' and self.row is not None:
            self.current_table['rows'].append(self.row);self.row=None
        if tag=='table' and self.current_table is not None:
            self.tables.append(self.current_table);self.current_table=None
        if tag==self.capture:
            rec={'tag':tag,'text':''.join(self.capture_parts).strip(),'line':self.getpos()[0]}
            if tag.startswith('h'):self.headings.append(rec)
            else:self.blocks.append(rec)
            self.capture=None;self.capture_parts=[]
        if self.stack and tag in self.stack:
            del self.stack[len(self.stack)-1-self.stack[::-1].index(tag):]
    def handle_data(self,data):
        if 'style' in self.stack:self.style.append(data);return
        if 'script' in self.stack:return
        self.text.append(data)
        if self.cell is not None:self.cell.append(data)
        if self.capture is not None:self.capture_parts.append(data)
    def handle_comment(self,data):self.comments.append({'line':self.getpos()[0],'text':data})

raw=(SRC/'프로모션원장.html').read_text();h=Reader();h.feed(raw)
html={'sha256':hashlib.sha256(raw.encode()).hexdigest(),'tags':h.tags,'headings':h.headings,'inputs':h.inputs,
      'tables':h.tables,'blocks':h.blocks,'resources_links':h.resources,'hidden_elements':h.hidden,
      'comments':h.comments,'css':''.join(h.style),'css_url_references':re.findall(r'url\(([^)]+)\)',raw,re.I),
      'scripts':h.tags['script'],'images':h.tags['img']}
(DIR/'html_inventory.json').write_text(json.dumps(html,ensure_ascii=False,indent=2)+'\n')
(DIR/'html_text.txt').write_text(re.sub(r'\n\s*\n+', '\n\n', ''.join(h.text)).strip()+'\n')
ledger=next(t for t in h.tables if t['preceding_heading']=='4. 원장')['rows']
codes=[dict(zip(ledger[0],row)) for row in ledger[1:]]
(DIR/'code_ledger.json').write_text(json.dumps(codes,ensure_ascii=False,indent=2)+'\n')

pdf=SRC/'할인중복_보상쿠폰_기준.pdf';reader=PdfReader(pdf);root=reader.trailer['/Root']
pages=[]
for i,p in enumerate(reader.pages,1):
    ann=[]
    for ref in p.get('/Annots',[]):
        obj=ref.get_object();ann.append({str(k):str(v) for k,v in obj.items()})
    pages.append({'page':i,'text':p.extract_text(),'images':[{'name':im.name,'bytes':len(im.data),'sha256':hashlib.sha256(im.data).hexdigest()} for im in p.images],
                  'annotations':ann,'page_actions':str(p.get('/AA')) if p.get('/AA') else None})
inv={'sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'pages':pages,'page_count':len(pages),
     'metadata':{str(k):str(v) for k,v in reader.metadata.items()},
     'root_keys':[str(k) for k in root],
     'open_action':str(root.get('/OpenAction')) if root.get('/OpenAction') else None,
     'additional_actions':str(root.get('/AA')) if root.get('/AA') else None,
     'acroform_present':'/AcroForm' in root,'optional_content_layers_present':'/OCProperties' in root,
     'attachments':list(reader.attachments.keys()),'encrypted':reader.is_encrypted,
     'name_tree_keys':[str(k) for k in root.get('/Names',{}).get_object()] if root.get('/Names') else []}
(DIR/'pdf_inventory.json').write_text(json.dumps(inv,ensure_ascii=False,indent=2)+'\n')
(DIR/'pypdf_text.txt').write_text('\n\f\n'.join(p['text'] for p in pages)+'\n')
with pdfplumber.open(pdf) as book:
    tables=[{'page':i+1,'tables':p.extract_tables()} for i,p in enumerate(book.pages)]
(DIR/'pdf_tables.json').write_text(json.dumps(tables,ensure_ascii=False,indent=2)+'\n')
poppler=(DIR/'pdf_text.txt').read_text()
key_terms=['REFER5000','CARE3000','CARE5000','CARE10000','90일','12개월','결제 완료','1인','부분환불']
texts='\n'.join(p['text'] for p in pages)
checks={'checked_at_utc':datetime.now(timezone.utc).isoformat(),'key_terms_both_extractors':{t:{'poppler':t in poppler,'pypdf':t in texts} for t in key_terms},
        'html_tables':len(h.tables),'html_table_rows':[len(t['rows']) for t in h.tables],'ledger_code_count':len(codes),'ledger_codes':[c['코드'] for c in codes],
        'pdf_pages_rendered_viewed':2,'pdf_page_image_count':sum(len(p['images']) for p in pages),'html_images':h.tags['img'],
        'html_scripts':h.tags['script'],'hidden_html_elements':len(h.hidden),'external_resources':len(h.resources),
        'pdf_annotations':sum(len(p['annotations']) for p in pages),'pdf_attachments':len(inv['attachments']),
        'zip_source_sha256':hashlib.sha256((DIR/'B-ulVcMRgNHbtfLjVugzvw.zip').read_bytes()).hexdigest()}
(DIR/'cross_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
assert all(v['poppler'] and v['pypdf'] for v in checks['key_terms_both_extractors'].values())
assert checks['ledger_code_count']==6
print(json.dumps(checks,ensure_ascii=False,indent=2))
