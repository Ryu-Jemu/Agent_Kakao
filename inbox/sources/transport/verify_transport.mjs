import fs from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import {FileBlob, SpreadsheetFile} from '@oai/artifact-tool';
const input=await FileBlob.load(fileURLToPath(new URL('./결항집하기록.xlsx',import.meta.url)));
const wb=await SpreadsheetFile.importXlsx(input);
const summary=await wb.inspect({kind:'workbook,sheet,table', maxChars:8000,tableMaxRows:2,tableMaxCols:3});
await fs.writeFile(new URL('./artifact_summary.ndjson',import.meta.url),summary.ndjson);
const xml=JSON.parse(await fs.readFile(new URL('./workbook_inventory.json',import.meta.url),'utf8'));
const checks=[];
for(const sh of xml.sheets){
  const sheet=wb.worksheets.getItem(sh.name);
  let count=0;const diffs=[];
  for(const row of sh.rows)for(const c of row){
    const observed=sheet.getRange(c.cell).values[0][0];count++;
    if(String(observed??'')!==c.value)diffs.push({cell:c.cell,xml:c.value,artifact:observed});
  }
  checks.push({sheet:sh.name,cells:count,diffs});
}
await fs.writeFile(new URL('./cross_checks.json',import.meta.url),JSON.stringify(checks,null,2));
console.log(JSON.stringify(checks));
