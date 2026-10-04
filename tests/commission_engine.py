"""Installed engine acceptance against an isolated native backend."""
import argparse
import asyncio
import hashlib
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
from kajamite.service import KnowledgeError
from mcp import ClientSession, StdioServerParameters
import kajamite
from mcp.client.stdio import stdio_client

STAMP = '2026-01-01T00:00:00.000000Z'
SCOPE = {'system': 'example', 'version': '1'}


def make_record(identifier="service-port", depends_on=None, *, mirror_claim=False):
    return RecordEngine().create_record(
        identifier, 'The service uses port 8080.\n', SCOPE,
        [{'observation_id': 'manual', 'statement': 'The service uses port 8080.\n' if mirror_claim else 'The manual specifies port 8080.', 'evidence_ids': ['manual']}],
        {'manual': {'kind': 'document', 'reference': 'example:manual@1', 'observed_at': STAMP}},
        {'record_revision': 1, 'verified_at': STAMP, 'verifier': 'reviewer', 'outcome': 'supported', 'evidence_ids': ['manual']},
        depends_on=depends_on, timestamp=STAMP, actor='reviewer', reason='Manual reviewed', event_id='created')


async def protocol_call(config, name, arguments, *, expect_error=False):
    host = Path(__file__).with_name('engine_protocol_host.py')
    params = StdioServerParameters(command=sys.executable, args=[str(host), '--config', str(config)],
                                  env={"PYTHONPATH": str(Path(kajamite.__file__).resolve().parents[1])})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write, read_timeout_seconds=90) as session:
            await session.initialize()
            tools = await session.list_tools()
            schema = next(tool.input_schema for tool in tools.tools if tool.name == 'knowledge_search')
            assert 'namespaces' in schema.get('properties', {})
            for tool_name in ('knowledge_record_create', 'knowledge_record_transition'):
                compact_schema = next(tool.input_schema for tool in tools.tools if tool.name == tool_name)
                assert compact_schema['properties']['include_history']['type'] == 'boolean'
                assert compact_schema['properties']['include_history']['default'] is True
            assert schema['properties']['retrieval_mode']['enum'] == ['text', 'semantic', 'hybrid']
            assert 'args' not in schema.get('properties', {}) and 'kwargs' not in schema.get('properties', {})
            response = await session.call_tool(name, arguments)
            if expect_error:
                assert response.is_error
                return response.structured_content
            return unpack(response)


async def run(config):
    settings = Settings.load(config)
    async with connect(settings) as backend:
        engine = KnowledgeEngine(backend, evidence_checker=lambda record, scope: True)
        try:
            await engine.record_create('Records', make_record('filename.md'))
        except KnowledgeError as error:
            assert str(error) == 'record_id is an identifier, not a Markdown filename; omit the .md suffix'
        else:
            raise AssertionError('Filename-shaped record IDs must fail before creation')
        created = await engine.record_create('Records', make_record())
        identifier = created['identifier']
        creation_fields = {item['key']: item for item in created['knowledge_change']['record_changes']}
        assert '1 added: manual' in creation_fields['evidence']['message']
        assert '1 added: manual' in creation_fields['observations']['message']
        assert '1 added: manual' in created['knowledge_change_text']
        try:
            await engine.record_create('Records', make_record())
        except KnowledgeError as error:
            assert error.mutation_outcome == 'not_started'
        else:
            raise AssertionError('Duplicate creation must be rejected before writing')
        assert (await engine.read(identifier, mode='inspect'))['record'] == created['record']
        duplicate = await protocol_call(config, 'knowledge_record_create',
            {'namespace': 'Records', 'record': make_record()}, expect_error=True)
        assert duplicate['error']['mutation_outcome'] == 'not_started'
        assert created['committed_revision'] == 1
        assert created['knowledge_change']['record_claim_sha256'] == hashlib.sha256(created['record']['claim'].encode('utf-8')).hexdigest()
        assert (await engine.read(identifier, request_scope=SCOPE))['content'] == make_record()['claim']
        assert (await engine.read(identifier.removesuffix('.md'), request_scope=SCOPE))['content'] == make_record()['claim']
        assert (await engine.read(identifier, request_scope={'system': 'other'}))['withheld']
        before = await engine.read(identifier, mode='inspect')
        anchor = make_record()['evidence']['manual']
        for evidence, message in [
            ([anchor], 'changes.evidence must be an object keyed by evidence ID'),
            ({'replacement': anchor}, 'observations reference unknown evidence IDs; preserve referenced IDs or update observations with the evidence mapping'),
        ]:
            try:
                await engine.record_transition(identifier, 'revise', 1, 'invalid-evidence',
                    '2026-01-01T00:00:01.000000Z', 'reviewer', 'Update support', {'evidence': evidence})
            except KnowledgeError as error:
                assert str(error) == message
            else:
                raise AssertionError('Invalid evidence must fail before mutation')
            assert (await engine.read(identifier, mode='inspect')) == before
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
        audited = await engine.record_create('Audit', make_record('source-recheck', mirror_claim=True))
        current = audited['record']
        evidence = {key: value | {'observed_at': '2026-01-01T00:00:01.000000Z'} for key, value in current['evidence'].items()}
        verification = current['verification'] | {'record_revision': 2, 'verified_at': '2026-01-01T00:00:01.000000Z'}
        original_audit = await engine.read(audited['identifier'], mode='inspect')
        for changes, message in [
            ({'status': 'supported', 'superseded_by': None}, 'revision changes accept only'),
            ({'evidence': evidence, 'verification': {key: value for key, value in verification.items()
                if key not in {'record_revision', 'verified_at'}}},
                'verification is missing fields: record_revision, verified_at'),
            ({'observations': [{'statement': 'Updated synthetic observation.', 'evidence_ids': ['manual']}]},
                'observations[0] is missing fields: observation_id'),
        ]:
            try:
                await engine.record_transition(audited['identifier'], 'revise', 1, 'recheck',
                    verification['verified_at'], 'reviewer', 'Recheck unchanged evidence', changes)
            except KnowledgeError as error:
                assert str(error).startswith(message)
            else:
                raise AssertionError('Invalid revision input must be rejected')
            assert await engine.read(audited['identifier'], mode='inspect') == original_audit
        refreshed = await engine.record_transition(audited['identifier'], 'revise', 1, 'recheck',
            verification['verified_at'], 'reviewer', 'Recheck unchanged evidence',
            {'evidence': evidence, 'verification': verification})
        assert refreshed['knowledge_change']['record_changes'] == []
        assert 'Audit information updated; note text unchanged.' in refreshed['knowledge_change_text']
        assert 'kajamite_record' not in refreshed['knowledge_change_text']
        assert 'Saved record state: supported' in refreshed['knowledge_change_text']
        assert refreshed['knowledge_change']['metadata_changes']
        assert refreshed['record']['evidence'] == evidence and refreshed['record']['verification'] == verification
        assert refreshed['record']['events'][0] == current['events'][0]
        corrected_replay = await engine.record_transition(audited['identifier'], 'revise', 1, 'recheck',
            verification['verified_at'], 'reviewer', 'Recheck unchanged evidence',
            {'evidence': evidence, 'verification': verification})
        assert corrected_replay['replayed'] and corrected_replay['record'] == refreshed['record']
        mirrored = await engine.record_create('Audit', make_record('explicit-mirror', mirror_claim=True))
        mirror_args = {'identifier': mirrored['identifier'], 'action': 'revise', 'expected_revision': 1,
            'operation_id': 'mirror-correction', 'timestamp': '2026-01-01T00:00:01.000000Z',
            'actor': 'reviewer', 'reason': 'Correct explicitly selected support', 'changes': {
                'replacements': [{'find_text': '8080', 'replacement': '9090'}], 'mirror_observations': ['manual'],
                'verification': mirrored['record']['verification'] | {
                    'record_revision': 2, 'verified_at': '2026-01-01T00:00:01.000000Z'}}}
        mirror_result = await protocol_call(config, 'knowledge_record_transition', mirror_args)
        mirror_current = (await engine.read(mirrored['identifier'], mode='inspect'))['record']
        assert mirror_current == mirror_result['record']
        assert mirror_current['claim'] == mirror_current['observations'][0]['statement'] == 'The service uses port 9090.\n'
        assert mirror_current['evidence'] == mirrored['record']['evidence']
        assert mirror_current['events'][:-1] == mirrored['record']['events']
        mirror_replay = await protocol_call(config, 'knowledge_record_transition', mirror_args)
        assert mirror_replay['replayed'] and mirror_replay['record'] == mirror_current
        stale = await protocol_call(config, 'knowledge_record_transition',
            mirror_args | {'operation_id': 'stale-mirror-correction'}, expect_error=True)
        assert stale['error']['mutation_outcome'] == 'not_started'
        assert 'expected 1, found 2' in stale['content'][0]['text']
        assert (await engine.read(mirrored['identifier'], mode='inspect'))['record'] == mirror_current
        passage = 'Retry after 60 seconds.'
        statement = 'Retry after 20 seconds.'
        observations = [{'observation_id': 'purpose', 'statement': 'Purpose remains.', 'evidence_ids': ['manual']},
                        {'observation_id': 'retry', 'statement': passage, 'evidence_ids': ['manual']}]
        base = make_record('passage-support')
        record = RecordEngine().create_record('passage-support', 'Purpose remains.\n\n' + passage,
            SCOPE, observations, base['evidence'], base['verification'],
            timestamp=STAMP, actor='reviewer', reason='Synthetic passages', event_id='created')
        section = await engine.record_create('Passages', record)
        section_update = await engine.record_transition(section['identifier'], 'revise', 1, 'passage-edit',
            '2026-01-01T00:00:01.000000Z', 'reviewer', 'Correct one passage',
            {'replacements': [{'find_text': passage, 'replacement': statement}],
             'observations': [observations[0], observations[1] | {'statement': statement}],
             'verification': base['verification'] | {'record_revision': 2, 'verified_at': '2026-01-01T00:00:01.000000Z'}})
        assert section_update['knowledge_change']['record_changes'] == []
        assert section_update['knowledge_change']['metadata_changes']
        assert section_update['record']['observations'][1]['statement'] == statement
        assert section_update['record']['events'][0] == record['events'][0]
        assert (await engine.read(audited['identifier'], request_scope=SCOPE))['content'] == current['claim']
        leaf = await engine.record_create('Details', make_record('linked-leaf'))
        overview_record = make_record('linked-overview')
        overview_record['claim'] = 'The overview links to [[Details/linked-leaf.md]].\n'
        overview_record['events'][0]['snapshot']['claim'] = overview_record['claim']
        linked_overview = await engine.record_create('Overviews', overview_record)
        older = await engine.record_create('Successions', make_record('older'))
        successor = await engine.record_create('Successions', make_record('successor'))
    compact = await protocol_call(config, 'knowledge_record_create', {
        'namespace': 'Compact', 'record': make_record('compact-result'), 'include_history': False})
    assert compact['history_included'] is False and 'events' not in compact['record']
    compact_args = {'identifier': compact['identifier'], 'action': 'dispute', 'expected_revision': 1,
        'operation_id': 'compact-dispute', 'timestamp': '2026-01-01T00:00:01.000000Z',
        'actor': 'reviewer', 'reason': 'Conflicting evidence'}
    compact_change = await protocol_call(config, 'knowledge_record_transition', compact_args | {'include_history': False})
    assert compact_change['record']['status'] == 'disputed' and 'events' not in compact_change['record']
    assert any(row['key'] == 'kajamite_record' for row in compact_change['knowledge_change']['metadata_changes'])
    compact_replay = await protocol_call(config, 'knowledge_record_transition', compact_args)
    assert compact_replay['replayed'] and compact_replay['operation_revision'] == 2
    compact_full = await protocol_call(config, 'knowledge_read', {'identifier': compact['identifier'], 'mode': 'inspect'})
    assert len(compact_full['record']['events']) == 2 and compact_full['record'] == compact_replay['record']
    assert {k: v for k, v in compact_full['record'].items() if k != 'events'} == compact_change['record']
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
        native_contexts = []
        native_call = backend.call

        async def traced_context(name, arguments):
            result = await native_call(name, arguments)
            if name == 'build_context':
                native_contexts.append({'arguments': arguments, 'result': result})
            return result

        backend.call = traced_context
        engine = KnowledgeEngine(backend, evidence_checker=lambda record, scope: True)
        linked = await engine.related(leaf['identifier'], namespaces=['Details', 'Overviews'],
            depth=1, max_chars=len(leaf['record']['claim']) + len(overview_record['claim']), mode='inspect')
        graph_evidence = {'bundle': linked, 'native_contexts': native_contexts}
        assert {note['identifier'] for note in linked['notes']} == {leaf['identifier'], linked_overview['identifier']}, graph_evidence
        assert not linked['partial'] and not linked['graph']['limited'], graph_evidence
        assert all(note['mode'] == 'inspect' and note['reuse_checked'] is False for note in linked['notes'])
        assert linked['used_chars'] == len(leaf['record']['claim']) + len(overview_record['claim']), graph_evidence
        narrow = await engine.related(leaf['identifier'], namespaces=['Details'], depth=1, mode='inspect')
        assert [note['identifier'] for note in narrow['notes']] == [leaf['identifier']]
        assert narrow['partial'] and narrow['graph']['excluded_outside_scope'] == 1
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
    return {'status': 'passed', 'checks': ['native governed codec', 'duplicate creation without write', 'request scope', 'plain preference',
        'restart continuity', 'source change withholding', 'revalidation', 'revision receipt', 'operation replay', 'revision input rejection and corrected replay', 'mirrored passage support projection',
        'MCP engine host', 'MCP lifecycle routing', 'CLI inspect without source checker',
        'native dependency maintenance', 'native removal evidence', 'compact supersession references',
        'mixed inspection prose budget', 'word-level reflow receipts', 'stored receipt titles', 'governed heading title without rename', 'unchanged-evidence recheck audit retention', 'compact plain receipt with full structured audit', 'compact mutation projection and full audit readback', 'incoming governed links within a prose budget']}


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
