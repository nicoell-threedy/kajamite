"""Installed engine acceptance against an isolated native backend."""
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from commission import prepare, cleanup
from kajamite.backend import connect, unpack
from kajamite.config import Settings
from kajamite.engine import KnowledgeEngine
from kajamite.governance import RecordEngine
from mcp import ClientSession, StdioServerParameters
import kajamite
from mcp.client.stdio import stdio_client

STAMP = '2026-01-01T00:00:00.000000Z'
SCOPE = {'system': 'example', 'version': '1'}


def make_record(identifier="service-port", depends_on=None):
    return RecordEngine().create_record(
        identifier, 'The service uses port 8080.\n', SCOPE,
        [{'observation_id': 'manual', 'statement': 'The manual specifies port 8080.', 'evidence_ids': ['manual']}],
        {'manual': {'kind': 'document', 'reference': 'example:manual@1', 'observed_at': STAMP}},
        {'record_revision': 1, 'verified_at': STAMP, 'verifier': 'reviewer', 'outcome': 'supported', 'evidence_ids': ['manual']},
        depends_on=depends_on, timestamp=STAMP, actor='reviewer', reason='Manual reviewed', event_id='created')


async def protocol_call(config, name, arguments):
    host = Path(__file__).with_name('engine_protocol_host.py')
    params = StdioServerParameters(command=sys.executable, args=[str(host), '--config', str(config)],
                                  env={"PYTHONPATH": str(Path(kajamite.__file__).resolve().parents[1])})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=90) as session:
            await session.initialize()
            tools = await session.list_tools()
            schema = next(tool.input_schema for tool in tools.tools if tool.name == 'knowledge_search')
            assert 'namespaces' in schema.get('properties', {})
            assert schema['properties']['retrieval_mode']['enum'] == ['text', 'semantic', 'hybrid']
            assert 'args' not in schema.get('properties', {}) and 'kwargs' not in schema.get('properties', {})
            return unpack(await session.call_tool(name, arguments))


async def run(config):
    settings = Settings.load(config)
    async with connect(settings) as backend:
        engine = KnowledgeEngine(backend, evidence_checker=lambda record, scope: True)
        created = await engine.record_create('Records', make_record())
        identifier = created['identifier']
        assert created['committed_revision'] == 1
        assert (await engine.read(identifier, request_scope=SCOPE))['content'] == make_record()['claim']
        assert (await engine.read(identifier.removesuffix('.md'), request_scope=SCOPE))['content'] == make_record()['claim']
        assert (await engine.read(identifier, request_scope={'system': 'other'}))['withheld']
        note = await engine.create('Preference', 'Prefer the morning session.', 'Notes', kind='preference')
        assert (await engine.read(note['note']['identifier']))['review_status'] == 'unreviewed'
        assert note['knowledge_change']['after']['title'] == 'Preference'
        body_record = await engine.record_create('BodyEdits', make_record('body-change'))
        revised = await engine.record_transition(body_record['identifier'], 'revise', 1, 'body-edit',
            '2026-01-01T00:00:01.000000Z', 'reviewer', 'Correct claim text',
            {'claim': '# Connection policy\n\nThe service\nuses port 9090.\n'})
        assert revised['committed_revision'] == 2
        assert revised['record']['claim'] == '# Connection policy\n\nThe service\nuses port 9090.\n'
        assert revised['record']['events'][0] == body_record['record']['events'][0]
        pair = revised['knowledge_change']['body_change']['replacements'][0]
        marked = [''.join(pair[side]['preview'][a:b] for a, b in pair[side]['changed_ranges']) for side in ('before', 'after')]
        assert ''.join(marked[0].split()) == '8080' and '9090' in marked[1]
        assert revised['knowledge_change']['after']['title'] == 'Connection policy'
        assert (await engine.read(body_record['identifier'], mode='inspect'))['title'] == 'Connection policy'
        assert body_record['identifier'] == revised['identifier']
        fields = {field['key']: field for field in revised['knowledge_change']['record_changes']}
        assert fields['status']['after'] == 'needs_revalidation'
        assert 'events' not in fields and 'claim' not in fields
        older = await engine.record_create('Successions', make_record('older'))
        successor = await engine.record_create('Successions', make_record('successor'))
    supersession = {
        'identifier': older['identifier'], 'action': 'supersede', 'expected_revision': 1,
        'operation_id': 'compact-supersession', 'timestamp': '2026-01-01T00:00:01.000000Z',
        'actor': 'reviewer', 'reason': 'Use the canonical explanation',
        'changes': {'successor_identifier': successor['identifier'], 'successor_revision': 1}}
    superseded = await protocol_call(config, 'knowledge_record_transition', supersession)
    assert superseded['record']['status'] == 'superseded'
    assert superseded['record']['superseded_by'] == 'successor'
    assert (await protocol_call(config, 'knowledge_record_transition', supersession))['replayed']
    # A new backend session reads the durable record, rather than process-local state.
    async with connect(settings) as backend:
        engine = KnowledgeEngine(backend, evidence_checker=lambda record, scope: True)
        persisted = await engine.read(older['identifier'], mode='inspect')
        assert persisted['record'] == superseded['record']
        assert persisted['record']['events'][0] == older['record']['events'][0]
        original = await engine.read(identifier, mode='inspect')
        assert original['record'] == make_record()
        changed = await engine.record_transition(identifier, 'evidence_health', 1, 'source-event',
            '2026-01-01T00:00:01.000000Z', 'source-checker', 'Manual changed',
            {'outcome': 'changed', 'condition_id': 'manual-revision-2'})
        assert changed['committed_revision'] == 2
        assert (await engine.read(identifier, request_scope=SCOPE))['withheld']
        verified = {**changed['record']['verification'], 'record_revision': 3,
                    'verified_at': '2026-01-01T00:00:02.000000Z', 'outcome': 'supported'}
        restored = await engine.record_transition(identifier, 'revalidate', 2, 'review-event',
            '2026-01-01T00:00:02.000000Z', 'reviewer', 'Source reviewed; claim remains supported',
            {'verification': verified})
        assert restored['committed_revision'] == 3
        assert restored['knowledge_change']['readback_verified']
        assert any(field['key'] == 'status' and field['after'] == 'supported'
                   for field in restored['knowledge_change']['record_changes'])
        assert (await engine.read(identifier, request_scope=SCOPE))['content'] == make_record()['claim']
        replayed = await engine.record_transition(identifier, 'revalidate', 2, 'review-event',
            '2026-01-01T00:00:02.000000Z', 'reviewer', 'Source reviewed; claim remains supported',
            {'verification': verified})
        assert replayed['replayed']
        preference = await engine.read(note['note']['identifier'])
        body_budget = len(make_record()['claim']) + len(preference['content'])
        inspected = await engine.context(identifiers=[identifier, preference['identifier']],
                                         mode='inspect', max_chars=body_budget)
        assert not inspected['partial'] and len(inspected['notes']) == 2
        assert inspected['used_chars'] == body_budget
        assert inspected['notes'][0]['content'] == make_record()['claim']
        assert all(item['reuse_checked'] is False for item in inspected['notes'])
    protocol_read = await protocol_call(config, 'knowledge_read', {'identifier': identifier, 'request_scope': SCOPE})
    assert protocol_read['content'] == make_record()['claim'] and protocol_read['record_revision'] == 3
    protocol_changed = await protocol_call(config, 'knowledge_record_transition', {
        'identifier': identifier, 'action': 'dispute', 'expected_revision': 3, 'operation_id': 'protocol-dispute',
        'timestamp': '2026-01-01T00:00:03.000000Z', 'actor': 'protocol-reviewer', 'reason': 'Synthetic protocol dispute'})
    assert protocol_changed['committed_revision'] == 4
    async with connect(settings) as backend:
        assert (await KnowledgeEngine(backend, evidence_checker=lambda record, scope: True).read(identifier, mode='inspect'))['record']['record_revision'] == 4
    with tempfile.NamedTemporaryFile('w', suffix='.json', encoding='utf-8', delete=False) as handle:
        json.dump({'identifier': identifier, 'mode': 'inspect'}, handle)
        arguments_path = handle.name
    try:
        cli = subprocess.run([sys.executable, '-m', 'kajamite', '--config', str(config), 'call', 'knowledge_read', '--arguments', arguments_path], capture_output=True, text=True)
        assert cli.returncode == 0, cli.stderr
        assert json.loads(cli.stdout)['record']['record_revision'] == 4
    finally:
        Path(arguments_path).unlink(missing_ok=True)
    async with connect(settings) as backend:
        engine = KnowledgeEngine(backend, evidence_checker=lambda record, scope: True)
        target = await engine.record_create('Dependencies', make_record('target'))
        dependent = await engine.record_create('Dependencies', make_record('dependent', ['target']))
        assert (await engine.read(dependent['identifier'], request_scope=SCOPE))['record_revision'] == 1
        await engine.record_transition(target['identifier'], 'retract', 1, 'retract-target',
            '2026-01-01T00:00:04.000000Z', 'reviewer', 'Withdraw target')
        assert (await engine.read(dependent['identifier'], request_scope=SCOPE))['withheld']
        maintenance = await engine.record_maintain('Dependencies', 'target-withdrawn',
            '2026-01-01T00:00:05.000000Z', 'reviewer', 'Dependency withdrawn')
        assert not maintenance['partial'] and len(maintenance['completed']) == 1
        removed = await engine.record_remove(dependent['identifier'], 2)
        assert removed['mutation']['deleted'] and removed['knowledge_change']['verification'] == 'backend_confirmed'
        assert removed['projection'] in {'absent', 'pending', 'unknown'}
    return {'status': 'passed', 'checks': ['native governed codec', 'request scope', 'plain preference',
        'restart continuity', 'source change withholding', 'revalidation', 'revision receipt', 'operation replay',
        'MCP engine host', 'MCP lifecycle routing', 'CLI inspect without source checker',
        'native dependency maintenance', 'native removal evidence', 'compact supersession references',
        'mixed inspection prose budget', 'word-level reflow receipts', 'stored receipt titles', 'governed heading title without rename']}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--basic-memory', required=True)
    args = parser.parse_args()
    temporary = tempfile.TemporaryDirectory(prefix='kajamite-engine-acceptance-')
    try:
        config, _ = prepare(Path(temporary.name), args.basic_memory)
        print(json.dumps(asyncio.run(run(config))))
    finally:
        cleanup(temporary)


if __name__ == '__main__':
    main()
