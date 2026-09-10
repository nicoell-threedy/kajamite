"""Engine embedding remains independent of the optional MCP adapter."""
from pathlib import Path
import subprocess
import sys
import unittest


class EmbeddingTests(unittest.TestCase):
    def test_engine_restarts_with_a_standard_library_file_backed_backend(self):
        source = str(Path(__file__).parents[1] / 'src')
        program = r'''
import asyncio, json, os, sys, tempfile
from contextlib import asynccontextmanager
sys.path.insert(0, sys.argv[1])
from kajamite.engine import KnowledgeEngine
from kajamite.governance import RecordEngine
class Backend:
 def __init__(self, path): self.path=path
 def load(self):
  try:
   with open(self.path, encoding='utf-8') as f: return json.load(f)
  except FileNotFoundError: return {}
 def save(self, value):
  with open(self.path, 'w', encoding='utf-8') as f: json.dump(value, f)
 @asynccontextmanager
 async def mutation(self): yield
 async def call(self, name, args):
  notes=self.load()
  if name=='write_note':
   path=(args['directory'].strip('/') + '/' if args['directory'].strip('/') else '') + args['title'].lower()+'.md'
   notes[path]={'title':args['title'],'file_path':path,'permalink':path[:-3],'content':args['content'],'frontmatter':dict(args['metadata'])|{'type':args['note_type']}}
   self.save(notes); return {'file_path':path,'permalink':path[:-3]}
  if name=='read_note':
   key=args['identifier'].strip('/').removeprefix('memory://')
   for note in notes.values():
    if key in (note['file_path'], note['permalink']): return note
   raise RuntimeError('missing')
  if name=='list_directory': return {'nodes':[], 'page':args['page'], 'page_size':args['page_size'], 'total':0, 'has_more':False}
  raise RuntimeError(name)
async def run(path):
 stamp='2026-01-01T00:00:00.000000Z'
 record=RecordEngine().create_record('embedded','Synthetic embedded claim.',{'system':'example'},[{'observation_id':'o','statement':'Synthetic observation.','evidence_ids':['e']}],{'e':{'kind':'document','observed_at':stamp}},{'record_revision':1,'verified_at':stamp,'verifier':'reviewer','outcome':'supported','evidence_ids':['e']},timestamp=stamp,actor='reviewer',reason='Synthetic',event_id='created')
 created=await KnowledgeEngine(Backend(path)).record_create('facts',record)
 restored=await KnowledgeEngine(Backend(path)).read(created['identifier'],mode='inspect')
 assert restored['record']==record
with tempfile.TemporaryDirectory() as directory: asyncio.run(run(os.path.join(directory,'synthetic.json')))
assert not any(name.split('.')[0] in {'mcp','yaml'} for name in sys.modules)
'''
        subprocess.run([sys.executable, '-I', '-S', '-c', program, source], check=True)


if __name__ == '__main__':
    unittest.main()
