"""Native retrieval mappings retain explicit scope and bounded context."""
import unittest
from kajamite.errors import BackendError
from kajamite.engine import KnowledgeEngine
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



class PagedGraphBackend(FakeBackend):
    def __init__(self, pages):
        super().__init__()
        self.pages = pages

    async def call(self, name, arguments):
        if name == 'build_context':
            self.calls.append((name, dict(arguments)))
            return self.pages[min(arguments['page'] - 1, len(self.pages) - 1)]
        return await super().call(name, arguments)


def graph_page(paths, more=False, related_count=0):
    return {'results': [{'primary_result': {'type': 'entity', 'file_path': 'Notes/start.md'},
                         'related_results': [{'type': 'entity', 'file_path': path} for path in paths]}],
            'has_more': more, 'metadata': {'related_count': related_count}}

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

    async def test_graph_reads_continuation_before_claiming_completeness(self):
        for service_type in (NoteOperations, KnowledgeEngine):
            with self.subTest(service=service_type.__name__):
                backend = PagedGraphBackend([graph_page(['Notes/first.md'], True),
                                             graph_page(['Notes/first.md', 'Notes/last.md'])])
                service = service_type(backend)
                for title in ('Start', 'First', 'Last'):
                    await service.create(title, title, 'Notes')
                kwargs = {'mode': 'inspect'} if service_type is KnowledgeEngine else {}
                result = await service.related('Notes/start.md', ['Notes'], **kwargs)
                self.assertEqual(['Notes/start.md', 'Notes/first.md', 'Notes/last.md'],
                                 [note['identifier'] for note in result['notes']])
                self.assertFalse(result['partial'])
                self.assertFalse(result['graph']['limited'])
                self.assertEqual([1, 2], [args['page'] for name, args in backend.calls if name == 'build_context'])

    async def test_graph_preserves_limits_and_unique_scope_exclusions_across_pages(self):
        scenarios = [
            ([graph_page([], True)], 10, True, 5, 0),
            ([graph_page(['Notes/first.md'], True, 100), graph_page([])], 10, True, 2, 0),
            ([graph_page(['Notes/first.md', 'Notes/last.md'], True)], 2, True, 1, 0),
            ([graph_page(['Outside/secret.md'], True), graph_page(['Outside/secret.md'])], 10, False, 2, 1),
        ]
        for pages, max_notes, limited, count, excluded in scenarios:
            with self.subTest(pages=count, limited=limited, excluded=excluded):
                backend = PagedGraphBackend(pages)
                service = KnowledgeEngine(backend)
                for title in ('Start', 'First', 'Last'):
                    await service.create(title, title, 'Notes')
                await service.create('Secret', 'hidden body', 'Outside')
                result = await service.related('Notes/start.md', ['Notes'], max_notes=max_notes, mode='inspect')
                self.assertEqual(limited, result['graph']['limited'])
                self.assertEqual(excluded, result['graph']['excluded_outside_scope'])
                self.assertTrue(result['partial'])
                self.assertNotIn('hidden body', str(result))
                self.assertLessEqual(len(result['notes']), max_notes)
                self.assertEqual(count, len([args for name, args in backend.calls if name == 'build_context']))

    async def test_graph_continuation_failure_is_not_reported_as_complete(self):
        backend = PagedGraphBackend([graph_page([], True)])
        service = KnowledgeEngine(backend)
        await service.create('Start', 'start', 'Notes')
        original = backend.call

        async def unavailable_page(name, arguments):
            if name == 'build_context' and arguments['page'] == 2:
                raise BackendError('continuation unavailable')
            return await original(name, arguments)

        backend.call = unavailable_page
        with self.assertRaisesRegex(BackendError, 'continuation unavailable'):
            await service.related('Notes/start.md', ['Notes'], mode='inspect')

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
