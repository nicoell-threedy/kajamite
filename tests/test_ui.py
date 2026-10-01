"""Optional browser acceptance. Set KAJAMITE_BROWSER to an existing Chromium."""
import html as html_module
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
 assert(el('counts').textContent === '1 note · 9 changes', 'notes and passages are distinct');
 for (const state of ['disputed','needs_revalidation','unverifiable','superseded','retracted']) {
  await result({knowledge_change:CHANGE,record:{status:state}});
  assert(!el('status').hidden && el('status').textContent.includes(state.replaceAll('_',' ').replace(/^./, c=>c.toUpperCase())), 'saved lifecycle state visible: '+state);
 }
 await result({knowledge_change:CHANGE,record:{status:'supported'}});
 assert(el('status').hidden, 'supported state does not require attention');
 el('toggle').click(); await wait();
 assert(requests[0] === 'fullscreen' && !el('review').hidden, 'advertised fullscreen');
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
 for (const clipped of [CLIPPED, CLIPPED_GROUP]) {
  await result({knowledge_change:clipped});
  assert(el('overview').textContent.includes('Text changed outside the receipt excerpts'), 'clipped edit disclosed in summary');
  assert(el('counts').textContent === '1 note · 1 change', 'clipped edit remains a change');
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
 await result({knowledge_change:CHANGE,record:{status:'needs_revalidation'},content:[{type:'text',text:'uncertain'}]},true);
 assert(el('status').textContent.includes('may have committed') && !el('status').textContent.includes('Saved record state'), 'failure takes precedence over record state');
 await result({}); assert(el('headline').textContent === 'No change receipt returned', 'missing receipt');
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
                  + json.dumps(clipped_group) + ';\n' + script)
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
        change = receipt.for_edit(before, before | {'metadata': {'status': 'confirmed', 'record_revision': 2}},
                                  find_text=None, replacement=None, metadata_keys={'status', 'record_revision'})
        long_text = 'Shared context ' * 65
        long_change = receipt.for_revise(before, before | {'content': 'Updated'}, [
            {'find_text': long_text + 'Arrive Monday.', 'replacement': long_text + 'Arrive Tuesday.'}])
        script = 'const CHANGES=' + json.dumps([change, long_change]) + ';const PAGE=' + json.dumps(html()) + ';' + r'''
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
 el('toggle').click();await wait();assert(el('changes').textContent.includes('Status'),'field labeled in details');
 assert(!el('evidence-toggle')&&!el('raw'),'diagnostics secondary');
 await result({knowledge_change:CHANGES[1]});
 assert(el('overview').textContent.includes('Monday')&&el('overview').textContent.includes('Tuesday'),'summary reaches changed words after long shared prefix');
 el('toggle').click();await wait();
 const full=Array.from(doc().querySelectorAll('button')).find(b=>b.textContent==='Show full excerpt');
 assert(full,'long excerpt bounded');full.click();await wait();assert(el('changes').textContent.includes('Tuesday'),'full excerpt reachable');
 await result({completed:[{knowledge_change:CHANGES[0]}],errors:[{identifier:'Plans/Other.md',error:'Revision conflict'}],partial:true});
 assert(doc().body.textContent.includes('Other: Revision conflict')&&el('review').hidden,'failure visible without opening');
 document.getElementById('outcome').textContent='BROWSER_ACCEPTANCE_OK';
})().catch(e=>document.getElementById('outcome').textContent='FAILED: '+e.message);
'''
        self.run_browser(script)
