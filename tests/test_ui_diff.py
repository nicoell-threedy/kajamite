"""Development checks for exact, bounded comparison of supplied text."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ESBUILD = ROOT / 'web/node_modules/.bin/esbuild'


@unittest.skipUnless(ESBUILD.is_file() and shutil.which('node'), 'frontend development dependencies required')
class ComparisonTests(unittest.TestCase):
    def test_source_and_token_reconstruction(self):
        cases = [
            ('', ''), ('', '# Added\n\n💡 café\n'), ('removed\n', ''),
            ('a\nb\nc\n', 'a\nchanged\nc\n'),
            ('Allow two hours.\nKeep the guide.', 'Allow three hours.\nKeep the guide.'),
            ('Keep 💡 café e\u0301. Retry 10 times.', '# Heading\n\n- Keep 💡 café e\u0301.\n- Retry 20 times.'),
            ('x ' * 1200 + '10', 'x ' * 1200 + '20'),
            ('\n'.join('old ' + str(i) for i in range(700)), '\n'.join('new ' + str(i) for i in range(700))),
            ('one\n\nthree', 'one\n\nthree\n'),
            ('<script>bad()</script>', '<img src=x onerror=bad()>'),
        ]
        script = r'''
const {lineDiff}=require(process.argv[1]);
const cases=JSON.parse(process.argv[2]);
for(const [before,after] of cases){
 const rows=lineDiff(before,after);
 for(const [side,source] of [['remove',before],['add',after]]){
  const selected=rows.filter(r=>r.type!==(side==='remove'?'add':'remove'));
  const rebuilt=selected.map(r=>r.parts.map(p=>p.text).join('')).join('\n');
  if(rebuilt!==source)throw Error('source reconstruction '+side);
  for(const row of selected)if(row.parts.map(p=>p.text).join('')!==row.text)throw Error('token reconstruction');
 }
}
const rows=lineDiff('Keep café 💡. Allow two hours.', 'Keep café 💡. Allow three hours.');
const changed=rows.flatMap(r=>r.parts.filter(p=>p.changed).map(p=>p.text)).join('');
if(!changed.includes('two')||!changed.includes('three')||changed.includes('café'))throw Error('word change isolation');
'''
        with tempfile.TemporaryDirectory(prefix='kajamite-diff-') as directory:
            bundle = Path(directory) / 'comparison.cjs'
            built = subprocess.run([str(ESBUILD), 'src/comparison.tsx', '--bundle', '--platform=node',
                                    '--format=cjs', '--outfile=' + str(bundle)], cwd=ROOT / 'web',
                                   capture_output=True, text=True, timeout=30)
            self.assertEqual(0, built.returncode, built.stderr)
            checked = subprocess.run(['node', '-e', script, str(bundle), json.dumps(cases)],
                                     capture_output=True, text=True, timeout=15)
            self.assertEqual(0, checked.returncode, checked.stderr)
