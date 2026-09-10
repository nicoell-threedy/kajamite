"""Replay native capabilities with isolated synthetic notes and no embedding model."""
import argparse
import asyncio
import json
from pathlib import Path
import tempfile

from commission import prepare, cleanup, wait_for_indexed_path
from kajamite.backend import connect
from kajamite.config import Settings


async def audit(config):
    async with connect(Settings.load(config)) as backend:
        catalog = await backend.session.list_tools()
        schemas = {tool.name: tool.input_schema for tool in catalog.tools}
        assert 'categories' in schemas['search_notes']['properties']
        assert 'build_context' in schemas and 'delete_note' in schemas
        for title, body in [('Manual', '## Observations\n- [fact] The synthetic quasarport is 8080.\n'),
                            ('Deployment', '## Observations\n- [decision] Use the documented quasarport.\n## Relations\n- depends_on [[Manual]]\n')]:
            result = await backend.call('write_note', {'title': title, 'content': body, 'directory': 'Example',
                                                       'overwrite': False, 'metadata': {'audit': {'version': 1}}})
            await wait_for_indexed_path(backend, 'quasarport', result['file_path'])
        results = await backend.call('search_notes', {'query': 'quasarport', 'search_type': 'text',
                                                     'entity_types': ['observation'], 'categories': ['fact'],
                                                     'page': 1, 'page_size': 10})
        assert any(row['file_path'] == 'Example/Manual.md' for row in results['results']), results
        note = await backend.call('read_note', {'identifier': 'Example/Manual.md', 'include_frontmatter': False})
        assert note['frontmatter']['audit'] == {'version': 1}
        graph = await backend.call('build_context', {'url': 'Example/Deployment.md', 'timeframe': None,
                                                    'depth': 1, 'page_size': 1, 'max_related': 10})
        related = [item for row in graph['results'] for item in row['related_results']]
        assert any(item.get('relation_type') == 'depends_on' for item in related)
        assert any(item.get('file_path') == 'Example/Manual.md' and item['type'] == 'entity' for item in related)
        deleted = await backend.call('delete_note', {'identifier': 'Example/Manual.md', 'is_directory': False})
        return {'status': 'passed', 'checks': ['observation category search', 'nested frontmatter readback',
                                              'typed relation', 'graph neighbor physical path', 'native deletion'],
                'delete_result': deleted,
                'capabilities': {'native_path_filter': 'directory' in schemas['search_notes']['properties'],
                                 'atomic_revision_compare': 'expected_revision' in schemas['edit_note']['properties'],
                                 'semantic_search': 'not enabled in isolated acceptance'}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--basic-memory', required=True)
    args = parser.parse_args()
    temporary = tempfile.TemporaryDirectory(prefix='kajamite-capabilities-')
    try:
        config, _ = prepare(Path(temporary.name), args.basic_memory)
        print(json.dumps(asyncio.run(audit(config))))
    finally:
        cleanup(temporary)


if __name__ == '__main__':
    main()
