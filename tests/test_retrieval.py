"""Native retrieval mappings retain explicit scope and bounded context."""
import unittest
from kajamite.service import NoteOperations
from test_service import FakeBackend


class GraphBackend(FakeBackend):
    async def call(self, name, arguments):
        if name == 'build_context':
            self.calls.append((name, arguments))
            return {'results': [{'primary_result': {'type': 'entity', 'file_path': 'Notes/start.md'},
                                 'related_results': [
                                     {'type': 'entity', 'file_path': 'Notes/target.md'},
                                     {'type': 'entity', 'file_path': 'Outside/secret.md'},
                                     {'type': 'entity', 'file_path': 'Notes/start.md'},
                                     {'type': 'relation', 'relation_type': 'depends_on', 'content': 'not public'},
                                 ]}], 'metadata': {'related_count': 4}, 'has_more': False}
        return await super().call(name, arguments)


class RetrievalTests(unittest.IsolatedAsyncioTestCase):
    async def test_graph_uses_native_paths_then_rereads_only_in_scope(self):
        backend = GraphBackend()
        service = NoteOperations(backend)
        for title, namespace, content in [('Start', 'Notes', 'start'), ('Target', 'Notes', 'current value'), ('Secret', 'Outside', 'private value')]:
            await service.create(title, content, namespace)
        result = await service.related('Notes/start.md', ['Notes'])
        self.assertEqual([note['identifier'] for note in result['notes']], ['Notes/start.md', 'Notes/target.md'])
        self.assertNotIn('private value', str(result))
        self.assertTrue(result['partial'])
        arguments = next(args for name, args in backend.calls if name == 'build_context')
        self.assertIsNone(arguments['timeframe'])
        self.assertEqual(result['graph']['excluded_outside_scope'], 1)

    async def test_search_binds_category_and_item_type_to_cursor(self):
        backend = FakeBackend()
        service = NoteOperations(backend)
        await service.create('First', 'marker', 'Notes')
        await service.create('Second', 'marker', 'Notes')
        page = await service.search(['Notes'], query='marker', item_types=['observation'], categories=['fact'], page_size=1)
        native = next(args for name, args in reversed(backend.calls) if name == 'search_notes')
        self.assertEqual(native['categories'], ['fact'])
        self.assertEqual(native['entity_types'], ['observation'])
        with self.assertRaises(ValueError):
            await service.search(['Notes'], query='marker', item_types=['observation'], categories=['decision'], cursor=page['next_cursor'])

    async def test_search_deduplicates_native_entities_but_preserves_distinct_observations(self):
        backend = FakeBackend()
        service = NoteOperations(backend)
        repeated = FakeBackend._note("Notes/first.md", "First", "marker")
        other = FakeBackend._note("Notes/second.md", "Second", "marker")
        backend.search_rows = [repeated] * 51 + [other]
        result = await service.search(["Notes"], query="marker")
        self.assertEqual(["Notes/first.md", "Notes/second.md"], [row["identifier"] for row in result["results"]])
        self.assertEqual(52, result["scanned_results"])
        self.assertTrue(result["exhausted"])
        first = dict(repeated, type="observation", observation_id="one")
        second = dict(repeated, type="observation", observation_id="two")
        backend.search_rows = [first, first, second]
        result = await service.search(["Notes"], query="marker", item_types=["observation"])
        self.assertEqual(["one", "two"], [row["item_id"] for row in result["results"]])
