import fs from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { FileBlob, SpreadsheetFile } from '@oai/artifact-tool';

const dir=path.dirname(fileURLToPath(import.meta.url));
const inventory=JSON.parse(await fs.readFile(path.join(dir,'inventory.json'),'utf8'));
const workbook=await SpreadsheetFile.importXlsx(await FileBlob.load(path.join(dir,'L9jWZnudmLmB93svQTbnEw.xlsx')));
const summary=await workbook.inspect({kind:'workbook,sheet,table',maxChars:6000,tableMaxRows:3,tableMaxCols:8,tableMaxCellChars:120});
await fs.writeFile(path.join(dir,'artifact_summary.ndjson'),summary.ndjson);
await fs.mkdir(path.join(dir,'previews'),{recursive:true});
const sheets=[];
for(let i=0;i<inventory.sheets.length;i++){
  const expected=inventory.sheets[i];
  const sheet=workbook.worksheets.getItem(expected.name);
  const values=sheet.getRange(expected.dimension).values;
  sheets.push({name:expected.name,range:expected.dimension,values});
  const preview=await workbook.render({sheetName:expected.name,range:expected.dimension,scale:1,format:'png'});
  await fs.writeFile(path.join(dir,'previews',`sheet${i+1}.png`),new Uint8Array(await preview.arrayBuffer()));
}
await fs.writeFile(path.join(dir,'artifact_all_values.json'),JSON.stringify(sheets,null,2)+'\n');
console.log(JSON.stringify({readOnly:true,exported:false,sheets:sheets.map(s=>({name:s.name,range:s.range,rows:s.values.length})),rendered:sheets.length}));
