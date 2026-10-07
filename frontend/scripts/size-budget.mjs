// Reports the gzip size of every built asset and fails when the total exceeds the budget in package.json ("sizeBudgetKB").
import { createRequire } from 'node:module';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';
import { gzipSync } from 'node:zlib';

const require = createRequire(import.meta.url);
const pkg = require('../package.json');
const budgetKB = pkg.sizeBudgetKB ?? 900;
const dir = join(import.meta.dirname, '..', '..', 'matter', 'static', 'assets');
let total = 0;
const rows = [];
for (const name of readdirSync(dir)) {
  const p = join(dir, name);
  if (!statSync(p).isFile() || !/\.(js|css)$/.test(name)) continue;
  const gz = gzipSync(readFileSync(p)).length;
  total += gz;
  rows.push([name, gz]);
}
rows.sort((a, b) => b[1] - a[1]);
for (const [name, gz] of rows) console.log(`${(gz / 1024).toFixed(1).padStart(8)} KB  ${name}`);
console.log(`${(total / 1024).toFixed(1).padStart(8)} KB  total (gzip), budget ${budgetKB} KB`);
if (total / 1024 > budgetKB) {
  console.error(`the built assets exceed the size budget by ${(total / 1024 - budgetKB).toFixed(1)} KB`);
  process.exit(1);
}
