"""Optional browser acceptance. Set KAJAMITE_BROWSER to an existing Chromium."""
import html as html_module
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from kajamite import receipt
from kajamite.ui import html


@unittest.skipUnless(os.environ.get('KAJAMITE_BROWSER'), 'set KAJAMITE_BROWSER for browser acceptance')
class UiTests(unittest.TestCase):
    def test_compact_summary_metadata_and_fallback(self):
        before = {'file_path': 'Example/retry.md', 'content': 'Retry after 60 seconds.', 'title': 'Retry policy'}
        after = before | {'content': 'Retry after 20 seconds.'}
        change = receipt.for_edit(before, after, find_text=before['content'], replacement=after['content'], metadata_keys=set())
        change['record_revision'] = 2
        full = {'ok': True, 'operation': 'record_revise', 'receipt_id': 'synthetic-receipt',
                'identifier': before['file_path'], 'committed_revision': 2, 'replayed': False,
                'record': {'record_revision': 2, 'status': 'needs_revalidation'}, 'knowledge_change': change}
        summary = {'response_format': 'kajamite-mutation-summary/1', 'ok': True, 'operation': 'record_revise',
                   'receipt_id': 'synthetic-receipt', 'identifier': before['file_path'], 'committed_revision': 2,
                   'record_status': 'needs_revalidation', 'replayed': False, 'readback_verified': True,
                   'change_summary': 'Retry delay changed from 60 to 20 seconds.', 'audit': {'available': True}}
        script = 'const FULL=' + json.dumps(full) + ';const SUMMARY=' + json.dumps(summary) + ';' + r'''
const frame=document.querySelector('iframe');
const send=data=>frame.contentWindow.postMessage({jsonrpc:'2.0',...data},'*');
const wait=()=>new Promise(resolve=>setTimeout(resolve,50));
const doc=()=>frame.contentDocument, el=id=>doc().getElementById(id);
const assert=(v,m)=>{if(!v)throw Error(m)};
const show=async(params)=>{send({method:'ui/notifications/tool-result',params});await wait();};
const hash=async(text)=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text))),v=>v.toString(16).padStart(2,'0')).join('');
const wire=async(snapshot=FULL,summary=SUMMARY)=>{
 const serialized=JSON.stringify(snapshot);
 return {structuredContent:{...summary,audit:{...summary.audit,sha256:await hash(serialized)}},_meta:{audit_snapshot:serialized}};
};
let initialized;const ready=new Promise(resolve=>initialized=resolve);
window.addEventListener('message',e=>{if(e.source!==frame.contentWindow)return;const m=e.data;
 if(m.method==='ui/initialize')send({id:m.id,result:{hostContext:{displayMode:'inline',availableDisplayModes:['inline']}}});
 if(m.method==='ui/notifications/initialized')initialized();
});
(async()=>{
 await ready;
 for(const available of [true,false]){
  await show(await wire(FULL,{...SUMMARY,audit:{available}}));
  assert(el('headline').textContent==='Note updated','matched metadata restores the actual receipt');
  assert(el('overview').textContent.includes('60')&&el('overview').textContent.includes('20'),'actual before and after remain prominent');
  assert(el('status').textContent.includes('Needs revalidation'),'saved state survives metadata adaptation');
  el('toggle').click();await wait();
  assert(el('changes').querySelector('.diff'),'complete diff remains available');
 }
 const mismatches=[null,{...FULL,receipt_id:'other'}, {...FULL,operation:'other'},
  {...FULL,identifier:'Other/note.md'}, {...FULL,committed_revision:3}, {...FULL,replayed:true},
  {...FULL,record:{...FULL.record,status:'supported'}},
  {...FULL,knowledge_change:{...FULL.knowledge_change,record_revision:3}},
  {...FULL,knowledge_change:{...FULL.knowledge_change,readback_verified:false}}, {...FULL,partial:true}];
 for(const snapshot of mismatches){
  await show(await wire(snapshot));
  assert(el('headline').textContent==='Operation completed','missing details do not erase completion');
  assert(el('status').textContent.includes('Complete diff unavailable'),'missing or mismatched diff is explicit');
  assert(el('toggle').textContent==='View summary','summary action is honest');
  el('toggle').click();await wait();assert(!el('changes').querySelector('.diff'),'mismatched snapshot never becomes a diff');
 }
 await show({structuredContent:{...SUMMARY,audit:{available:false}}});
 assert(el('overview').textContent.includes('Do not repeat the write'),'capacity failure does not invite another write');
 const altered=await wire();altered._meta.audit_snapshot=altered._meta.audit_snapshot.replace('Retry after 20','Retry after 90');
 await show(altered);
 assert(el('headline').textContent==='Operation completed'&&el('status').textContent.includes('Complete diff unavailable'),'altered snapshot fails its digest');
 await show({...await wire(),isError:true});
 assert(el('headline').textContent==='Operation failed','wire errors override successful metadata');
 const delayed=await wire();const subtle=frame.contentWindow.crypto.subtle, originalDigest=subtle.digest.bind(subtle);
 subtle.digest=async(...args)=>{await new Promise(resolve=>setTimeout(resolve,100));return originalDigest(...args);};
 send({method:'ui/notifications/tool-result',params:delayed});
 send({method:'ui/notifications/tool-input',params:{}});await new Promise(resolve=>setTimeout(resolve,150));
 assert(el('headline').textContent==='Working','late digest cannot overwrite new input');
 send({method:'ui/notifications/tool-result',params:delayed});
 send({method:'ui/notifications/tool-cancelled',params:{reason:'Stopped'}});await new Promise(resolve=>setTimeout(resolve,150));
 assert(el('headline').textContent==='Operation cancelled','late digest cannot overwrite cancellation');
 subtle.digest=originalDigest;
 await show({structuredContent:FULL});
 assert(el('headline').textContent==='Note updated','ordinary structured receipt remains supported');
 frame.style.width='320px';await show({structuredContent:SUMMARY});
 assert(doc().documentElement.scrollWidth<=320,'summary fallback fits narrow view');
 document.getElementById('outcome').textContent='BROWSER_ACCEPTANCE_OK';
})().catch(error=>document.getElementById('outcome').textContent='FAILED: '+error.message);
'''
        script += '\nframe.srcdoc=' + json.dumps(html()) + ';'
        self.run_browser(script)

    def test_disclosure_and_host_states(self):
        before = {'file_path': 'Notes/Example.md', 'content': 'old', 'metadata': {}}
        change = receipt.for_revise(before, before | {'content': 'new'}, [
            {'find_text': f'old passage {i}', 'replacement': f'new passage {i}'} for i in range(9)])
        unchanged = receipt.for_revise(before, before, [{'find_text': 'old', 'replacement': 'old'}])
        prefix = 'Unchanged context. ' * 200
        late_before = before | {'content': prefix + 'Retry after 10 seconds.'}
        late_after = before | {'content': prefix + 'Retry after 30 seconds.'}
        clipped = receipt.for_edit(late_before, late_after, find_text=late_before['content'],
                                   replacement=late_after['content'], metadata_keys=set())
        clipped_group = receipt.for_revise(late_before, late_after, [
            {'find_text': late_before['content'], 'replacement': late_after['content']}])
        reflow_before = {'file_path': 'Notes/stable-id.md', 'title': 'Resource retry policy',
                         'content': 'Keep shared resource 💡 café. Retry after 10 seconds. Retain instance state.'}
        reflow_after = reflow_before | {'content': '# Retry policy\n\n- Keep shared resource 💡 café.\n- Retry after 20 seconds.\n- Retain instance state.'}
        reflow = receipt.for_edit(reflow_before, reflow_after, find_text=reflow_before['content'],
                                 replacement=reflow_after['content'], metadata_keys=set())
        created = receipt.for_create({'file_path': 'Notes/new-note.md', 'content': 'New reader-facing explanation.',
                                      'metadata': {'title': 'generated-id', 'permalink': 'notes/new-note'}})
        claim = '# Topic\n\n' + 'Complete synthetic explanation. ' * 100 + '\nFinal supported step: café 💡.'
        verified = {'identifier': 'Notes/topic.md', 'committed_revision': 1,
                    'record': {'record_revision': 1, 'claim': claim},
                    'knowledge_change': receipt.for_create({'file_path': 'Notes/topic.md', 'content': '\n' + claim})}
        verified['knowledge_change'].update(record_revision=1, record_claim_sha256=hashlib.sha256(claim.encode()).hexdigest())
        script = r'''
const frame = document.querySelector('iframe');
let requests = [], modeReply = 'fullscreen', sizes = 0, initialized;
const initialization = new Promise(resolve => initialized = resolve);
const reply = data => frame.contentWindow.postMessage({jsonrpc:'2.0', ...data}, '*');
window.addEventListener('message', e => {
 if (e.source !== frame.contentWindow) return;
 const m = e.data;
 if (m.method === 'ui/initialize') reply({id:m.id,result:{hostContext:{displayMode:'inline',availableDisplayModes:['inline','fullscreen']}}});
 if (m.method === 'ui/notifications/initialized') initialized();
 if (m.method === 'ui/request-display-mode') {
  requests.push(m.params.mode);
  if (modeReply === 'reject') reply({id:m.id,error:{code:-32000,message:'Unavailable'}});
  else if (modeReply !== 'timeout') reply({id:m.id,result:{mode:m.params.mode === 'inline' ? 'inline' : modeReply}});
 }
 if (m.method === 'ui/notifications/size-changed') sizes++;
});
const wait = (ms=40) => new Promise(resolve => setTimeout(resolve,ms));
const doc = () => frame.contentDocument, el = id => doc().getElementById(id);
const assert = (value, label) => { if (!value) throw Error(label); };
const result = async (value, error=false) => {reply({method:'ui/notifications/tool-result',params:{structuredContent:value,isError:error}}); await wait();};
(async () => {
 await initialization; await result({knowledge_change:CHANGE});
 assert(el('review').hidden && !el('evidence'), 'details start hidden');
 assert(doc().body.getBoundingClientRect().height < 240, 'compact initial height');
 assert(el('overview').textContent.includes('old passage 0') && el('overview').textContent.includes('new passage 0'), 'real edits visible without interaction');
 assert(el('counts').textContent === '1 note · 9 text edits', 'notes and passages are distinct');
 for (const state of ['disputed','needs_revalidation','unverifiable','superseded','retracted']) {
  await result({knowledge_change:CHANGE,record:{status:state}});
  assert(!el('status').hidden && el('status').textContent.includes(state.replaceAll('_',' ').replace(/^./, c=>c.toUpperCase())), 'saved lifecycle state visible: '+state);
 }
 await result({knowledge_change:CHANGE,record:{status:'supported'}});
 assert(el('status').hidden, 'supported state does not require attention');
 await result({replayed:true,identifier:'Notes/Example.md',operation_revision:2,committed_revision:3,record:{status:'needs_revalidation'}});
 assert(el('headline').textContent==='Previously completed' && el('subject').textContent.includes('Notes/Example.md'), 'replay identifies the returned note');
 assert(el('counts').textContent==='Operation revision 2 · Returned revision 3', 'replay distinguishes original operation from current readback');
 assert(el('status').textContent==='Returned record state: Needs revalidation.', 'replay labels the returned state');
 el('toggle').click();await wait();assert(!el('changes').querySelector('.diff'), 'replay without a receipt invents no diff');
 await result({replayed:true,identifier:'Notes/Example.md',committed_revision:3});
 assert(el('counts').textContent==='Returned revision 3', 'missing operation revision is not invented');
 await result({knowledge_change:CHANGE,record:{status:'supported'}});
 const changeRequest=requests.length;
 el('toggle').click(); await wait();
 assert(requests[changeRequest] === 'fullscreen' && !el('review').hidden, 'advertised fullscreen');
 assert(el('changes').children.length === 3, 'bounded first disclosure');
 el('more').click(); await wait(); assert(el('changes').children.length === 6, 'show more');
 reply({method:'ui/notifications/host-context-changed',params:{displayMode:'inline'}}); await wait();
 assert(el('review').hidden, 'host close restores summary');
 for (const mode of ['reject','inline','timeout']) {
  await result({knowledge_change:CHANGE}); modeReply = mode; el('toggle').click(); await wait(mode==='timeout'?1600:40);
  assert(!el('review').hidden, 'inline fallback: '+mode);
 }
 const count = requests.length;
 reply({method:'ui/notifications/host-context-changed',params:{availableDisplayModes:['inline']}}); await wait();
 await result({knowledge_change:CHANGE}); el('toggle').click(); await wait();
 assert(requests.length === count && sizes > 0, 'capability detection and sizing');
 await result({preview:true,identifier:'Notes/Example.md',proposed_content:'Preview text'});
 assert(el('headline').textContent === 'Preview · nothing saved', 'preview');
 await result({knowledge_change:UNCHANGED});
 assert(el('headline').textContent === 'No content changes' && el('counts').textContent.includes('0 changes'), 'no-op');
 await result({knowledge_change:CREATED});
 assert(el('overview').textContent.includes('New reader-facing explanation.') && !el('overview').textContent.includes('generated-id'), 'creation summary leads with prose');
 assert(el('counts').textContent==='1 note' && !el('overview').textContent.includes('field update'), 'creation does not describe initialization as edits');
 el('toggle').click(); await wait();
 assert(el('changes').children.length === 1 && el('note-fields').hidden && el('more').hidden, 'creation fields are secondary');
 assert(el('fields-toggle').textContent.includes('Initial note fields'), 'creation field disclosure identifies initialization');
 el('fields-toggle').click(); await wait();
 assert(el('note-fields').textContent.includes('generated-id') && el('note-fields').textContent.includes('notes/new-note'), 'all initialized fields remain inspectable');
 await result({knowledge_change:CREATED}); el('toggle').click(); await wait();
 assert(el('note-fields').hidden, 'new result resets field disclosure');
 await result(VERIFIED); el('toggle').click(); await wait();
 const fullNote = [...el('changes').querySelectorAll('button')].find(button => button.textContent === 'Show full note');
 assert(fullNote && !el('changes').textContent.includes('not the full note'), 'verified claim offers complete note');
 fullNote.click(); await wait();
 assert(el('changes').textContent.includes('Final supported step: café 💡.'), 'complete Unicode claim is readable beyond receipt limit');
 for (const invalid of ['hash', 'revision', 'readback', 'legacy']) {
  const value = structuredClone(VERIFIED);
  if (invalid === 'hash') value.record.claim += ' Altered.';
  if (invalid === 'revision') value.committed_revision = 2;
  if (invalid === 'readback') value.knowledge_change.readback_verified = false;
  if (invalid === 'legacy') delete value.knowledge_change.record_claim_sha256;
  await result(value); el('toggle').click(); await wait();
  assert(!el('changes').textContent.includes('Show full note') && el('changes').textContent.includes('not the full note'), 'unbound claim retains excerpt disclosure: '+invalid);
 }
 for (const clipped of [CLIPPED, CLIPPED_GROUP]) {
  await result({knowledge_change:clipped});
  assert(el('overview').textContent.includes('Text changed outside the receipt excerpts'), 'clipped edit disclosed in summary');
  assert(el('counts').textContent === '1 note · 1 text edit', 'clipped edit remains a change');
  el('toggle').click(); await wait();
  assert(el('changes').textContent.includes('The changed passage is unavailable.'), 'missing passage disclosed in details');
  assert(!el('changes').querySelector('mark') && !el('changes').querySelector('.diff'), 'identical previews are not a diff');
  assert(!el('changes').querySelector('button'), 'unavailable passage has no misleading excerpt expansion');
 }
 await result({replayed:true,knowledge_change:CHANGE,record:{status:'needs_revalidation'}});
 assert(el('headline').textContent === 'Previously completed', 'replay');
 assert(!el('status').textContent.includes('Saved record state'), 'replay does not imply a new saved state');
 await result({completed:[{knowledge_change:CHANGE},{knowledge_change:CHANGE,replayed:true}],errors:[{record_id:'Failed',error:'Uncertain'}],partial:true});
 assert(el('headline').textContent.includes('partially') && el('counts').textContent.startsWith('1 note changed'), 'partial maintenance excludes replay');
 await result({completed:[],errors:[],partial:false});
 assert(el('headline').textContent === 'No new changes', 'empty maintenance');
 await result({content:[{type:'text',text:'uncertain'}]},true);
 assert(el('headline').textContent === 'Operation failed' && el('status').textContent.includes('may have committed'), 'failure');
 const rejectedInput = {ok:false,error:{mutation_outcome:'not_started'},content:[{type:'text',text:'Required verification fields are missing.'}]};
 await result(rejectedInput,true);
 assert(el('headline').textContent === 'Operation failed' && el('status').textContent.includes('No write was attempted'), 'explicit pre-write rejection');
 assert(el('overview').textContent.includes('Required verification fields'), 'input error remains primary');
 for (const contradiction of [{ok:true},{knowledge_change:CHANGE},{completed:[{knowledge_change:CHANGE}]},{mutation:{}},{committed_revision:2},{replayed:true},{accepted_state:{records:['Example']}},{error:{mutation_outcome:'not_started',accepted_state:{records:['Example']}}}]) {
  await result({...rejectedInput,...contradiction},true);
  assert(el('status').textContent.includes('may have committed'), 'contradictory completion retains uncertainty');
 }
 await result({...rejectedInput,error:{mutation_outcome:'unknown'}},true);
 assert(el('status').textContent.includes('may have committed'), 'unknown rejection metadata retains uncertainty');
 await result({knowledge_change:CHANGE,record:{status:'needs_revalidation'},content:[{type:'text',text:'uncertain'}]},true);
 assert(el('status').textContent.includes('may have committed') && !el('status').textContent.includes('Saved record state'), 'failure takes precedence over record state');
 await result({}); assert(el('headline').textContent === 'No change receipt returned', 'missing receipt');
 await result({knowledge_change:REFLOW}); el('toggle').click(); await wait();
 assert(el('subject').querySelector('strong').textContent === 'Resource retry policy', 'stored readable title');
 const marks = [...doc().querySelectorAll('.diff mark')].map(node=>node.textContent).join('');
 assert(marks.includes('10') && marks.includes('20'), 'changed values highlighted');
 assert(!marks.includes('shared resource') && !marks.includes('café'), 'reflow retains unhighlighted phrases');
 assert(doc().querySelector('.diff-line p').textContent === REFLOW.body_change.before.preview, 'Unicode before text preserved');
 assert(doc().querySelector('.diff-after p').textContent === REFLOW.body_change.after.preview, 'Unicode after text preserved');
 await result({completed:[{knowledge_change:REFLOW}]}); await wait();
 assert(el('overview').textContent.includes('Resource retry policy'), 'batch readable title');
 el('toggle').click(); await wait();
 assert(doc().querySelector('#changes h2').textContent === 'Resource retry policy', 'expanded batch readable title');
 assert(el('changes').textContent.includes('Guides/stable-policy-id.md') || el('changes').textContent.includes('Notes/stable-id.md'), 'batch stable path');
 const invalidRanges = JSON.parse(JSON.stringify(REFLOW));
 invalidRanges.body_change.after.changed_ranges = [[-1, 999999]];
 await result({knowledge_change:invalidRanges}); el('toggle').click(); await wait();
 assert(el('headline').textContent === 'Note updated', 'invalid highlight ranges fall back');
 const malicious = JSON.parse(JSON.stringify(CHANGE));
 malicious.after.identifier = '<img src=x onerror="window.pwned=true">';
 malicious.body_change.replacements[0].after.preview = '<script>window.pwned=true<\/script>';
 await result({knowledge_change:malicious}); el('toggle').click(); await wait();
 assert(!doc().querySelector('img') && !frame.contentWindow.pwned, 'inert source text');
 frame.style.width = '320px'; await wait();
 assert(doc().documentElement.scrollWidth <= 320, 'narrow layout');
 reply({method:'ui/notifications/tool-input',params:{}}); await wait();
 assert(el('headline').textContent === 'Working' && el('review').hidden && el('actions').hidden, 'new input clears success');
 reply({method:'ui/notifications/tool-cancelled',params:{reason:'Stopped'}}); await wait();
 assert(el('headline').textContent === 'Operation cancelled', 'cancelled');
 await result({knowledge_change:CHANGE});
 document.getElementById('outcome').textContent = 'BROWSER_ACCEPTANCE_OK';
})().catch(error => document.getElementById('outcome').textContent = 'FAILED: '+error.message);
'''
        script = ('const CHANGE = ' + json.dumps(change) + '; const UNCHANGED = ' + json.dumps(unchanged)
                  + '; const CLIPPED = ' + json.dumps(clipped) + '; const CLIPPED_GROUP = '
                  + json.dumps(clipped_group) + '; const REFLOW = ' + json.dumps(reflow)
                  + '; const CREATED = ' + json.dumps(created) + '; const VERIFIED = ' + json.dumps(verified) + ';\n' + script)
        script += '\nframe.srcdoc = ' + json.dumps(html()) + ';'
        self.run_browser(script)

    def run_browser(self, script):
        with tempfile.TemporaryDirectory(prefix='kajamite-ui-') as directory:
            page = Path(directory) / 'host.html'
            page.write_text('<!doctype html><meta charset="utf-8"><iframe style="width:640px;height:800px"></iframe>'
                            '<pre id="outcome">RUNNING</pre><script>' + script.replace('</script', '<\\/script') + '</script>', encoding='utf-8')
            completed = subprocess.run([
                os.environ['KAJAMITE_BROWSER'], '--headless', '--no-sandbox', '--disable-gpu',
                '--disable-dev-shm-usage', '--no-proxy-server', '--no-first-run',
                '--user-data-dir=' + str(Path(directory) / 'profile'),
                '--virtual-time-budget=9000', '--dump-dom', page.as_uri(),
            ], capture_output=True, text=True, timeout=45)
            self.assertEqual(0, completed.returncode, completed.stderr[-1000:])
            outcome = completed.stdout.split('<pre id="outcome">', 1)[-1].split('</pre>', 1)[0]
            self.assertEqual('BROWSER_ACCEPTANCE_OK', html_module.unescape(outcome))

    def test_themes_apply_without_rebuilding_or_external_requests(self):
        first = html({'light': {'primary': '#123456', 'radius': '0.5rem'},
                      'dark': {'primary': '#abcdef'}})
        second = html({'light': {'primary': '#654321'}})
        script = 'const PAGES = ' + json.dumps([html(), first, second]) + ';' + r"""
const frame = document.querySelector('iframe');
let ready = false, requests = 0;
const send = data => frame.contentWindow.postMessage({jsonrpc:'2.0', ...data}, '*');
const wait = (ms=60) => new Promise(resolve => setTimeout(resolve,ms));
const assert = (value, label) => { if (!value) throw Error(label); };
const token = name => frame.contentDocument.documentElement.style.getPropertyValue('--'+name);
const host = context => send({method:'ui/notifications/host-context-changed',params:context});
window.addEventListener('message', event => {
 if (event.source !== frame.contentWindow) return;
 const m = event.data;
 if (m.method === 'ui/initialize') send({id:m.id,result:{hostContext:{theme:'light',displayMode:'inline',availableDisplayModes:['inline']}}});
 if (m.method === 'ui/notifications/initialized') {
   ready = true;
   send({method:'ui/notifications/tool-result',params:{structuredContent:{preview:true,identifier:'Demo/Note.md',proposed_content:'Synthetic preview'}}});
 }
});
const load = async index => {
 ready = false; frame.srcdoc = PAGES[index];
 for (let i=0;i<30 && !ready;i++) await wait();
 assert(ready, 'initialized '+index); await wait();
};
(async()=>{
 await load(0);
 const doc = () => frame.contentDocument;
 const style = node => frame.contentWindow.getComputedStyle(node);
 host({styles:{variables:{'--color-background-primary':'rgb(240, 241, 242)','--color-text-primary':'rgb(20, 21, 22)','--primary':'#ff0000','--font-sans':'Georgia, serif'}}}); await wait();
 assert(style(doc().querySelector('[data-slot="card"]')).backgroundColor==='rgb(240, 241, 242)', 'host palette maps to card');
 assert(token('primary')==='#ff0000', 'host shadcn token');
 host({styles:{variables:{'--primary':'url(https://example.invalid/track)','--background':'red; color: blue','--not-supported':'red'}}}); await wait();
 assert(!token('primary') && !token('background') && !token('not-supported'), 'replace clears stale and unsafe tokens');
 assert(style(doc().body).backgroundColor==='rgba(0, 0, 0, 0)' && style(doc().documentElement).backgroundColor==='rgba(0, 0, 0, 0)', 'transparent embedding');
 const light = style(doc().querySelector('[data-slot="card"]')).backgroundColor;
 host({theme:'dark'});await wait();assert(style(doc().querySelector('[data-slot="card"]')).backgroundColor!==light, 'host appearance changes default theme');
 await load(1);
 assert(token('primary')==='#123456','adopter light theme');
 host({styles:{variables:{'--primary':'#ff0000'}},theme:'dark'});await wait();
 assert(token('primary')==='#abcdef','adopter dark overrides host');
 assert(token('radius')==='0.5rem','shared geometry retained');
 host({theme:'light'});await wait();assert(token('primary')==='#123456','return to light');
 doc().getElementById('toggle').click();await wait();
 assert(!doc().getElementById('evidence-toggle'),'raw receipt behind secondary disclosure');
 doc().getElementById('about-toggle').click();await wait();
 const evidence=doc().getElementById('evidence-toggle');evidence.focus();evidence.click();await wait();
 assert(doc().getElementById('raw').textContent.includes('Synthetic preview'),'accessible evidence disclosure');
 send({method:'ui/notifications/tool-result',params:{structuredContent:{}}});await wait();
 doc().getElementById('toggle').click();await wait();
 assert(!doc().getElementById('raw'),'new result closes technical evidence');
 frame.style.width='320px';await wait();assert(doc().documentElement.scrollWidth<=320,'themed narrow layout');
 await load(2);assert(token('primary')==='#654321','second adopter same compiled bundle');
 assert(!doc().querySelector('script[src], link[href], img, iframe'),'no external assets');
 assert(frame.contentWindow.performance.getEntriesByType('resource').length===0,'no resource requests');
 document.getElementById('outcome').textContent='BROWSER_ACCEPTANCE_OK';
})().catch(error=>document.getElementById('outcome').textContent='FAILED: '+error.message);
"""
        self.run_browser(script)

    def test_semantic_summary_and_bounded_comparison(self):
        before = {'file_path': 'Plans/Conference.md', 'content': 'Agenda', 'metadata': {'status': 'draft', 'record_revision': 1}}
        operations = {'saved': {'fingerprint': 'synthetic-replay-marker', 'committed_revision': 2}}
        change = receipt.for_edit(before, before | {'metadata': {'status': 'confirmed', 'record_revision': 2,
                                                                'kajamite_operations': operations}},
                                  find_text=None, replacement=None, metadata_keys={'status', 'record_revision', 'kajamite_operations'})
        tracking = receipt.for_edit(before, before | {'metadata': before['metadata'] | {'kajamite_operations': operations}},
                                    find_text=None, replacement=None, metadata_keys={'kajamite_operations'})
        old_record = {'scope': {'product': 'Alpha'}, 'status': 'supported'}
        new_record = {'scope': {'product': 'Beta'}, 'status': 'needs_revalidation'}
        semantic = receipt.for_edit(before | {'metadata': {'kajamite_record': old_record}},
                                    before | {'metadata': {'kajamite_record': new_record}},
                                    find_text=None, replacement=None, metadata_keys={'kajamite_record'})
        legacy = dict(semantic)
        semantic = semantic | {'record_changes': receipt.record_changes(old_record, new_record)}
        long_text = 'Shared context ' * 65
        long_change = receipt.for_revise(before, before | {'content': 'Updated'}, [
            {'find_text': long_text + 'Arrive Monday.', 'replacement': long_text + 'Arrive Tuesday.'}])
        paragraph = 'Removing a local entry clears its cached details and registration, but keeps the shared collection available to the other entries that still refer to it.'
        passage = receipt.for_revise(before, before | {'content': paragraph}, [{'find_text': 'Removing a local entry deletes the shared collection.', 'replacement': paragraph}])
        passage['record_changes'] = [{'key': 'evidence', 'message': 'Support updated.'}, {'key': 'observations', 'message': 'Statements updated.'}]
        script = 'const CHANGES=' + json.dumps([change, long_change, tracking, semantic, legacy, passage]) + ';const PAGE=' + json.dumps(html()) + ';' + r'''
const frame=document.querySelector('iframe');
const send=data=>frame.contentWindow.postMessage({jsonrpc:'2.0',...data},'*');
const wait=()=>new Promise(r=>setTimeout(r,70));
const doc=()=>frame.contentDocument, el=id=>doc().getElementById(id);
const assert=(v,m)=>{if(!v)throw Error(m)};
let ready=false;
window.addEventListener('message',e=>{if(e.source!==frame.contentWindow)return;
 if(e.data.method==='ui/initialize')send({id:e.data.id,result:{hostContext:{theme:'light',availableDisplayModes:['inline']}}});
 if(e.data.method==='ui/notifications/initialized')ready=true;
});
(async()=>{
 frame.srcdoc=PAGE;for(let i=0;i<30&&!ready;i++)await wait();assert(ready,'initialized');
 const result=async value=>{send({method:'ui/notifications/tool-result',params:{structuredContent:value}});await wait();};
 await result({knowledge_change:CHANGES[0]});
 assert(el('subject').textContent.includes('Conference'),'named subject');
 assert(el('overview').textContent.includes('Status: draft → confirmed'),'field labeled in summary');
 assert(!el('overview').textContent.includes('revision'),'counter excluded');
 assert(el('counts').textContent==='1 note · 1 field update' && !el('overview').textContent.includes('synthetic-replay-marker'),'bookkeeping excluded from review count');
 el('toggle').click();await wait();assert(el('changes').textContent.includes('Status'),'field labeled in details');
 assert(!el('evidence-toggle')&&!el('raw'),'diagnostics secondary');
 assert(!el('changes').textContent.includes('Kajamite operations'),'bookkeeping excluded from primary details');
 el('about-toggle').click();await wait();el('evidence-toggle').click();await wait();
 assert(el('raw').textContent.includes('synthetic-replay-marker'),'bookkeeping preserved in raw receipt');
 await result({knowledge_change:CHANGES[2]});
 assert(el('overview').textContent.includes('Audit information updated') && !el('headline').textContent.includes('No content changes'),'tracking-only save remains explicit');
 await result({completed:[{knowledge_change:CHANGES[2]}],errors:[],partial:false});
 assert(el('overview').textContent.includes('Audit information updated') && !el('overview').textContent.includes('No notes changed'), 'batch audit-only save remains explicit');
 await result({knowledge_change:CHANGES[3]});
 assert(el('overview').textContent.includes('Scope · Product: Alpha → Beta') && el('overview').textContent.includes('Needs revalidation'),'semantic scope and readable status visible');
 assert(!el('overview').textContent.includes('Kajamite record'),'record JSON excluded only with projection');
 el('toggle').click();await wait();
 assert(el('changes').textContent.includes('Scope · Product') && !el('changes').textContent.includes('Kajamite record'),'semantic detail rows');
 el('about-toggle').click();await wait();el('evidence-toggle').click();await wait();
 assert(el('raw').textContent.includes('kajamite_record'),'raw record retained');
 await result({knowledge_change:CHANGES[4]});
 assert(el('overview').textContent.includes('Kajamite record'),'legacy record metadata remains reviewable');
 await result({completed:[{knowledge_change:CHANGES[3]}],errors:[],partial:false});
 assert(el('overview').textContent.includes('Scope · Product: Alpha → Beta') && !el('overview').textContent.includes('Kajamite record'),'maintenance uses semantic projection');
 assert(el('status').textContent==='1 saved note needs revalidation.' && !el('status').hidden,'maintenance state consequence remains prominent');
 const group=Array.from({length:5},(_,i)=>({knowledge_change:{...CHANGES[3],after:{...CHANGES[3].after,identifier:`Notes/dependent-${i}.md`}}}));
 await result({completed:[...group,group[0],{...group[1],replayed:true}],errors:[],partial:false});
 assert(el('status').textContent==='5 saved notes need revalidation.','unique fresh note states include items outside the summary');
 await result({completed:group.map(x=>({...x,replayed:true})),errors:[],partial:false});
 assert(el('status').hidden,'replayed states are not current saves');
 await result({completed:[{knowledge_change:{...CHANGES[3],readback_verified:false}}],errors:[],partial:false});
 assert(el('status').hidden,'unverified receipt does not assert saved state');
 await result({completed:group,errors:[{identifier:'Notes/failed.md',error:'Conflict'}],partial:true});
 assert(el('status').textContent==='Inspect failed items before retrying.','failure takes priority over lifecycle summary');
 await result({knowledge_change:CHANGES[1]});
 assert(el('overview').textContent.includes('Monday')&&el('overview').textContent.includes('Tuesday'),'summary reaches changed words after long shared prefix');
 el('toggle').click();await wait();
 const full=Array.from(doc().querySelectorAll('button')).find(b=>b.textContent==='Show full excerpt');
 assert(full,'long excerpt bounded');full.click();await wait();assert(el('changes').textContent.includes('Tuesday'),'full excerpt reachable');
 await result({knowledge_change:CHANGES[5]});
 assert(el('counts').textContent==='1 note · 1 text edit · 2 field updates','text edits separated from supporting fields');
 assert(el('overview').textContent.includes('other entries that still refer to it.'),'bounded paragraph retains final qualification');
 assert(el('overview').textContent.includes('1 field update in details'),'remaining fields are not extra passage edits');
 frame.style.width='320px';await wait();el('toggle').click();await wait();
 const row=doc().querySelector('.diff-line');
 assert(frame.contentWindow.getComputedStyle(row).gridTemplateColumns.split(' ').length===1,'narrow diff labels stack above text');
 const longId='source-'+'x'.repeat(115)+'-00';
 await result({knowledge_change:{...CHANGES[3],record_changes:[{key:'evidence',message:`12 added: ${longId} (+11 more). Exact values are in the raw receipt.`}]}});
 assert(doc().body.scrollWidth<=doc().documentElement.clientWidth,'collapsed long identifier summary stays inside narrow frame');
 el('toggle').click();await wait();
 assert(el('changes').textContent.includes('(+11 more)'),'expanded summary retains omitted-entry count');
 assert(doc().body.scrollWidth<=doc().documentElement.clientWidth,'expanded long identifier summary wraps');
 await result({knowledge_change:{...CHANGES[3],record_changes:[{key:'details',before:{reference:longId},after:{reference:longId+'-updated'},before_present:true,after_present:true}]}});
 el('toggle').click();await wait();
 assert(doc().body.scrollWidth<=doc().documentElement.clientWidth,'expanded JSON field values wrap');
 frame.style.width='760px';await wait();
 await result({completed:[{knowledge_change:CHANGES[0]}],errors:[{identifier:'Plans/Other.md',error:'Revision conflict'}],partial:true});
 assert(doc().body.textContent.includes('Other: Revision conflict')&&el('review').hidden,'failure visible without opening');
 document.getElementById('outcome').textContent='BROWSER_ACCEPTANCE_OK';
})().catch(e=>document.getElementById('outcome').textContent='FAILED: '+e.message);
'''
        self.run_browser(script)
