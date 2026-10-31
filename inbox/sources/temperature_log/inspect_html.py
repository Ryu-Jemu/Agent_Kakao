from pathlib import Path
from html.parser import HTMLParser
from collections import Counter
import json,re
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


raw=(SRC/'온도기록계_조회.html').read_text();h=Reader();h.feed(raw)
inv={'tags':h.tags,'headings':h.headings,'inputs':h.inputs,'tables':h.tables,'blocks':h.blocks,'resources_links':h.resources,'hidden_elements':h.hidden,'comments':h.comments,'css':''.join(h.style),'css_url_references':re.findall(r'url\(([^)]+)\)',raw,re.I),'scripts':h.tags['script'],'images':h.tags['img'],'svg_count':h.tags['svg']}
(DIR/'html_inventory.json').write_text(json.dumps(inv,ensure_ascii=False,indent=2)+'\n')
(DIR/'html_text.txt').write_text(re.sub(r'\n\s*\n+', '\n\n', ''.join(h.text)).strip()+'\n')
print(json.dumps({'tables':len(h.tables),'table_rows':[len(t['rows']) for t in h.tables],'svg':h.tags['svg'],'images':h.tags['img'],'scripts':h.tags['script'],'resources':h.resources,'hidden':h.hidden},ensure_ascii=False))
