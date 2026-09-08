"""Offline checks against the actual configurable public Daily Digest runtime."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import unittest
import uuid


CATEGORIES = ["cs.CV", "cs.AI", "cs.LG", "cs.MM", "cs.RO", "cs.IT", "eess.IV"]
CONFIG_NAME = "daily-digest-config.json"
SKILL = Path("skills/global/literature-monitor")


# Synthetic checkpoint data enters through the same coverage, review, summary,
# finalization and rendering functions as an actual run. No fetch/send is mocked
# into reporting success; the network remains forbidden in the child process.
OFFLINE_PIPELINE = r'''
import copy
root = Path(data['root'])
runtime.initialize_runtime(root)
initial_success_bytes = (root / 'last-successful-run.json').read_bytes()
run_id = '2026-07-28-public-offline'
run_dir = root / 'runs' / run_id
categories = tuple(data['categories'])
assert tuple(runtime.TRACKED_CATEGORIES) == categories
assert 'cs.CV' not in categories
assert runtime.REPORT_CATEGORY == data['report_category']
if data.get('known_paper'):
    runtime.atomic_write_json(root / 'sent-papers.json', {
        'schema_version': runtime.SCHEMA_VERSION,
        'papers': {'2607.00003': {'latest_sent_version': 1,
            'latest_sent_announcement_date': '2026-07-27',
            'title': 'Synthetic previously delivered probability study'}},
    })
initial_sent_bytes = (root / 'sent-papers.json').read_bytes()
for category_index, category in enumerate(categories):
    papers = []
    count = 3 if data.get('known_paper') and category_index == 0 else 2
    for index in range(count):
        arxiv_id = f'2607.{category_index * 10 + index + 1:05d}'
        papers.append({
            'title': (f'Synthetic probability study {category_index}-{index}: cs.CV seven Seven'
                      if index == 0 else f'Synthetic background study {category_index}-{index}: cs.CV seven Seven'),
            'authors': ['Synthetic Author'], 'arxiv_id': arxiv_id, 'version': 1,
            'abstract': ('Synthetic probability methods mentioning cs.CV seven Seven in source text.'
                         if index == 0 else 'A synthetic background study mentioning cs.CV seven Seven.'),
            'categories': [category], 'query_sources': [category],
            'submitted_or_updated': '2026-07-28T01:00:00Z',
            'arxiv_url': f'https://arxiv.org/abs/{arxiv_id}',
            'pdf_url': f'https://arxiv.org/pdf/{arxiv_id}v1',
            'announcement_date': '2026-07-28', 'announcement_types': ['new'],
            'announcement_type': 'new', 'source': 'arxiv_announcement',
        })
    batch = {
        'schema_version': runtime.SCHEMA_VERSION, 'category': category,
        'announcement_date': '2026-07-28',
        'listing_url': runtime.announcement_listing_url(category),
        'source': 'arxiv_announcement',
        'counts': {'new_submissions': len(papers), 'cross_lists': 0,
                   'replacements': 0, 'total': len(papers)},
        'papers': papers, 'complete': True, 'inventory_validated': True,
        'requested_cursor_date': None, 'cursor_action': 'process_migration_batch',
    }
    batch['coverage'] = runtime.announcement_batch_coverage(batch)
    runtime.atomic_write_json(runtime.announcement_batch_output_path(root, run_id, category), batch)
if data.get('omit_category'):
    runtime.announcement_batch_output_path(root, run_id, data['omit_category']).unlink()
    try:
        runtime.prepare_review(root, run_id)
    except runtime.DigestValidationError:
        pass
    else:
        raise AssertionError('Review accepted a missing selected-category checkpoint')
    assert not (run_dir / 'digest-v4.json').exists()
    raise SystemExit(0)
prepared = runtime.prepare_review(root, run_id)
assert prepared['inventory'] == len(categories) * 2
assert prepared['report_records'] == len(categories) * 2 + int(bool(data.get('known_paper')))
manifest = runtime.read_json(run_dir / 'review-manifest-v3.json')
assert manifest['pages'], 'fixture must exercise model-review pages'
for page_record in manifest['pages']:
    page = runtime.read_json(Path(page_record['path']))
    decisions = []
    for paper in page['papers']:
        decisions.append({
            'arxiv_id': paper['arxiv_id'],
            'relevance_score': 90 if int(paper['arxiv_id'].split('.')[1]) % 2 else 50,
            'topic_group': 'direct_interest',
            'core_conclusion': '这是用于离线回归测试的合成概率研究结论。',
            'research_problem': '该合成研究用于检查概率方法的测试流程。',
            'method_overview': '通过合成概率数据检验摘要审核与报告生成。',
            'contributions': '该测试样例提供可重复的分类与筛选输入。',
            'research_relation': '该合成输入与已配置的概率研究主题相关。',
            'transferable_ideas': '可借鉴此测试的覆盖与完整性检查步骤。',
            'limitations': '合成数据不能用于推断真实论文的实验结果。',
            'worth_reading': '本条仅用于测试而不构成真实阅读建议。',
            'follow_up': '检查本地报告字段和分类覆盖是否一致。',
            'semantic_exclusion_reason': None,
        })
    path = run_dir / f"decision-input-{page['page']:03d}.json"
    runtime.atomic_write_json(path, {
        'schema_version': runtime.SCHEMA_VERSION, 'run_id': run_id,
        'page': page['page'], 'source_page_sha256': page_record['sha256'],
        'decisions': decisions,
    })
    runtime.record_review_page(root, run_id, page['page'], path)
runtime.prepare_cv_summary(root, run_id)
summary = runtime.read_json(run_dir / 'cv-summary-manifest-v4.json')
assert summary['pages'], 'fixture must exercise complete-report summary pages'
for page_record in summary['pages']:
    page = runtime.read_json(Path(page_record['path']))
    translations = []
    for arxiv_id, kind, _source_fields in page['items']:
        value = {'arxiv_id': arxiv_id, 'core_conclusion': '该合成样例检查概率摘要的中文报告字段。'}
        if kind == 'd':
            value.update({
                'research_problem': '该合成样例检查概率研究问题的报告表示。',
                'method_overview': '通过合成输入测试摘要审核后的报告内容。',
                'contributions': '该合成样例用于验证报告覆盖和字段完整性。',
            })
        translations.append(value)
    path = run_dir / f"summary-input-{page['page']:03d}.json"
    runtime.atomic_write_json(path, {
        'schema_version': runtime.SCHEMA_VERSION, 'run_id': run_id,
        'page': page['page'], 'source_page_sha256': page_record['sha256'],
        'translations': translations,
    })
    runtime.record_cv_summary_page(root, run_id, page['page'], path)
finalized = runtime.finalize_digest(root, run_id)
digest = runtime.read_json(Path(finalized['digest']))
runtime.validate_digest(digest)
assert all('cs.CV seven Seven' in paper['title'] for paper in digest['focus_papers'])
assert digest['report_category'] == data['report_category']
assert {row['category'] for row in digest['retrieval_coverage']} == set(categories)
assert len(digest['focus_papers']) == len(categories)
report = digest['cs_cv_report']
assert report['total'] == 1
assert digest['report_already_known_count'] == int(bool(data.get('known_paper')))
assert all(data['report_category'] in row['query_sources'] for row in report['detailed'] + report['compact'])
assert (root / 'last-successful-run.json').read_bytes() == initial_success_bytes, 'Rendering must not commit delivery'
assert (root / 'sent-papers.json').read_bytes() == initial_sent_bytes
'''


class DailyDigestPublicTests(unittest.TestCase):
    bundle_root = Path(__file__).resolve().parents[1]

    def setUp(self):
        scratch = self.bundle_root / ".test-tmp"
        scratch.mkdir(exist_ok=True)
        self.directory = scratch / ("daily-public-" + uuid.uuid4().hex)
        self.directory.mkdir()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        path = self.directory.resolve()
        expected_parent = (self.bundle_root / ".test-tmp").resolve()
        if path.parent != expected_parent or path.name != self.directory.name:
            raise AssertionError("refusing cleanup outside the exact test fixture")
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            raise AssertionError("refusing cleanup of a linked test fixture")
        shutil.rmtree(path)

    @property
    def scripts(self):
        return self.bundle_root / SKILL / "scripts"

    def state_root(self, name="state"):
        root = self.directory / name
        root.mkdir()
        return root

    def config(self, root, *, term="graph learning", categories=None, category_order=None,
               report_category=None):
        categories = list(CATEGORIES if categories is None else categories)
        return {
            "schema_version": 1,
            "configured": True,
            "digest_root": str(root.resolve()),
            "coordination_root": str((self.directory / "coordination").resolve()),
            "recipient": "me",
            "timezone": "UTC",
            "categories": categories,
            "category_order": categories if category_order is None else category_order,
            "report_category": report_category or categories[0],
            "topic_tiers": {"A": [term], "B": [], "C": []},
            "topic_labels": {
                "direct_interest": "Direct interest",
                "method_interest": "Method interest",
                "transfer_interest": "Transfer interest",
                "other_relevant": "Other relevant",
            },
            "architecture_terms": [],
            "context_terms": [],
            "exclusions": {"primary": [], "secondary": []},
        }

    def write_config(self, root, config=None):
        path = root / CONFIG_NAME
        path.write_text(json.dumps(config or self.config(root)), encoding="utf-8")
        return path

    def python(self, code, *, script_dir=None, **data):
        bootstrap = """
import json, pathlib, socket, sys, urllib.request
def denied_network(*args, **kwargs):
    raise AssertionError('Live network is forbidden in public Daily Digest tests')
socket.create_connection = denied_network
urllib.request.urlopen = denied_network
sys.path.insert(0, sys.argv[1])
data = json.loads(sys.argv[2])
from pathlib import Path
import daily_digest_runtime as runtime
import daily_digest_config as config
"""
        result = subprocess.run(
            [sys.executable, "-I", "-B", "-X", "utf8", "-c",
             textwrap.dedent(bootstrap) + "\n" + textwrap.dedent(code),
             str(script_dir or self.scripts), json.dumps(data)],
            cwd=self.directory, capture_output=True, text=True, timeout=45,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return result.stdout

    def cli(self, filename, *arguments):
        launcher = (
            "import runpy,sys; directory=sys.argv.pop(1); filename=sys.argv.pop(1); "
            "sys.path.insert(0,directory); runpy.run_path(directory+'/'+filename,run_name='__main__')"
        )
        return subprocess.run(
            [sys.executable, "-I", "-B", "-X", "utf8", "-c", launcher,
             str(self.scripts), filename, *arguments],
            cwd=self.directory, capture_output=True, text=True, timeout=45,
        )

    def test_packaged_runtime_uses_its_own_shared_client(self):
        self.python("""
expected = Path(data['bundle']) / 'skills/_shared/arxiv_client.py'
assert Path(runtime._CENTRAL_ARXIV.__file__).resolve() == expected.resolve()
""", bundle=str(self.bundle_root))

    def test_plugin_runtime_uses_the_plugin_shared_client(self):
        plugin = self.bundle_root / "plugins/research-skills"
        scripts = plugin / "skills/literature-monitor/scripts"
        self.assertTrue((scripts / "daily_digest_runtime.py").is_file())
        self.python("""
expected = Path(data['plugin']) / 'skills/_shared/arxiv_client.py'
assert Path(runtime._CENTRAL_ARXIV.__file__).resolve() == expected.resolve()
""", plugin=str(plugin), script_dir=scripts)

    def test_configuration_template_is_not_an_authorized_configuration(self):
        root = self.state_root()
        template = self.bundle_root / SKILL / "templates/daily-digest-config.example.json"
        self.assertTrue(template.is_file(), str(template))
        self.python("""
value = json.loads(Path(data['template']).read_text(encoding='utf-8'))
assert value['configured'] is False
try:
    config.validate_config(value, Path(data['root']))
except config.PublicDigestConfigError:
    pass
else:
    raise AssertionError('Unconfigured example must fail closed')
""", root=str(root), template=str(template))

    def test_missing_configuration_prevents_state_initialization(self):
        root = self.state_root()
        self.python("""
try:
    runtime.initialize_runtime(Path(data['root']))
except ValueError:
    pass
else:
    raise AssertionError('Missing configuration initialized a transaction')
assert not list(Path(data['root']).iterdir())
""", root=str(root))

    def test_missing_configuration_prevents_network_retrieval(self):
        root = self.state_root()
        self.python("""
try:
    runtime.fetch_announcement_batch(Path(data['root']), 'cs.CV')
except ValueError:
    pass
else:
    raise AssertionError('Missing configuration allowed retrieval')
assert not list(Path(data['root']).iterdir())
""", root=str(root))

    def test_unconfigured_cli_fails_but_help_remains_available(self):
        root = self.state_root()
        help_result = self.cli("daily_digest_runtime.py", "--help")
        self.assertEqual(0, help_result.returncode, help_result.stderr)
        denied = self.cli("daily_digest_runtime.py", "init", "--root", str(root))
        self.assertNotEqual(0, denied.returncode)
        self.assertEqual([], list(root.iterdir()))

    def test_configured_cli_initializes_a_bound_profile_without_authorizing_send(self):
        root = self.state_root()
        settings = self.config(root)
        self.write_config(root, settings)
        checked = self.cli("daily_digest_config.py", "--root", str(root), "--check")
        self.assertEqual(0, checked.returncode, checked.stdout + checked.stderr)
        self.assertFalse(json.loads(checked.stdout)["send_authorized"])
        initialized = self.cli("daily_digest_runtime.py", "init", "--root", str(root))
        self.assertEqual(0, initialized.returncode, initialized.stdout + initialized.stderr)
        self.assertIn("public_profile_sha256:", (root / "config.md").read_text(encoding="utf-8"))
        self.assertFalse((root / "pending-run.json").exists())

    def test_rootless_delivery_preflight_requires_explicit_configuration(self):
        root = self.state_root()
        denied = self.cli("daily_digest_delivery.py", "preflight")
        self.assertNotEqual(0, denied.returncode)
        self.assertIn("public_digest_not_configured", denied.stdout + denied.stderr)
        self.assertEqual([], list(root.iterdir()))
        config_path = self.write_config(root)
        checked = self.cli("daily_digest_delivery.py", "--public-config", str(config_path), "preflight")
        # Missing rendering dependencies are a reported preflight result,
        # never an excuse to bypass the explicit configuration gate.
        self.assertIn(checked.returncode, {0, 3}, checked.stdout + checked.stderr)
        self.assertIsInstance(json.loads(checked.stdout)["ready"], bool)
        self.assertEqual({CONFIG_NAME}, {path.name for path in root.iterdir()})

    def test_configuration_alone_cannot_mint_a_send_proof(self):
        root = self.state_root()
        self.write_config(root)
        self.python("""
import daily_digest_delivery as delivery
root = Path(data['root'])
try:
    delivery.prepare_send_proof(root, root / 'missing-manifest.json', {})
except delivery.DeliveryValidationError:
    pass
else:
    raise AssertionError('Configuration without verified Draft minted a send proof')
assert {p.name for p in root.iterdir()} == {data['config_name']}
""", root=str(root), config_name=CONFIG_NAME)

    def test_daily_routing_keeps_external_write_and_tool_requirements(self):
        self.python("""
sys.path.insert(0, str(Path(data['bundle']) / 'scripts/skills'))
import router
entries = json.loads((Path(data['bundle']) / 'skills/registry.yaml').read_text(encoding='utf-8'))['skills']
daily = router.route('$literature-monitor daily_arxiv_email', entries)
assert daily.primary_skill == 'literature-monitor' and daily.mode == 'daily_arxiv_email'
assert daily.side_effect_class == 'authorized_external_write'
assert set(daily.required_tools) == {'arxiv-daily', 'gmail'}
assert daily.mcp_calls == []
weekly = router.route('$literature-monitor weekly', entries)
assert weekly.mode == 'weekly' and weekly.side_effect_class == 'read_only'
""", bundle=str(self.bundle_root))

    def test_invalid_configuration_cannot_weaken_delivery_or_coverage_constraints(self):
        root = self.state_root()
        invalid = []
        for key, value in (
            ("configured", False), ("recipient", "reader@example.org"),
            ("send_authorized", True),
            ("timezone", "Invalid/ExampleZone"), ("digest_root", str(self.directory / "other")),
            ("categories", []), ("categories", ["cs.CV", "cs.CV"]),
            ("categories", ["math"]), ("categories", ["physics"]),
            ("categories", ["cs.*"]), ("categories", ["../math.PR"]),
            ("categories", ["made.up"]), ("categories", ["Math.PR"]),
            ("category_order", CATEGORIES[:-1]),
            ("category_order", [CATEGORIES[0]] * len(CATEGORIES)),
            ("report_category", "quant-ph"), ("report_category", None),
            ("topic_tiers", {"A": [], "B": [], "C": []}),
            ("topic_tiers", {"A": ["REPLACE_WITH_YOUR_TOPIC"], "B": [], "C": []}),
        ):
            value_config = self.config(root)
            value_config[key] = value
            invalid.append(value_config)
        self.python("""
for index, value in enumerate(data['invalid']):
    try:
        config.validate_config(value, Path(data['root']))
    except config.PublicDigestConfigError:
        continue
    raise AssertionError('Invalid configuration accepted: ' + str(index))
""", root=str(root), invalid=invalid)

    def test_user_interests_change_actual_prefilter_and_topic_classification(self):
        graph_root, systems_root = self.state_root("graph"), self.state_root("systems")
        self.write_config(graph_root, self.config(graph_root, term="graph learning"))
        self.write_config(systems_root, self.config(systems_root, term="distributed systems"))
        self.python("""
graph = {'title': 'Graph learning with verified structure', 'abstract': ''}
systems = {'title': 'Reliable distributed systems', 'abstract': ''}
runtime.configure_public_runtime(Path(data['graph']))
assert runtime.local_prefilter(graph)['prefilter_score'] > runtime.local_prefilter(systems)['prefilter_score']
assert runtime.assign_topic_group(graph) == 'direct_interest'
assert runtime.assign_topic_group(systems) == 'other_relevant'
runtime.configure_public_runtime(Path(data['systems']))
assert runtime.local_prefilter(systems)['prefilter_score'] > runtime.local_prefilter(graph)['prefilter_score']
assert runtime.assign_topic_group(systems) == 'direct_interest'
assert runtime.assign_topic_group(graph) == 'other_relevant'
assert runtime.ARCHITECTURE_TERMS == ()
assert runtime.VISION_CONTEXT_TERMS == ()
""", graph=str(graph_root), systems=str(systems_root))

    def test_user_category_order_changes_actual_review_order(self):
        first, second = self.state_root("first"), self.state_root("second")
        self.write_config(first, self.config(first, category_order=CATEGORIES))
        self.write_config(second, self.config(second, category_order=list(reversed(CATEGORIES))))
        self.python("""
papers = [
 {'title': 'Graph learning', 'abstract': '', 'arxiv_id': '2601.00001', 'query_sources': ['cs.CV']},
 {'title': 'Graph learning', 'abstract': '', 'arxiv_id': '2601.00002', 'query_sources': ['eess.IV']},
]
def order(root):
    runtime.configure_public_runtime(Path(root))
    items = [{'paper': paper, **runtime.local_prefilter(paper)} for paper in papers]
    return [item['paper']['arxiv_id'] for item in sorted(items, key=runtime._review_rank_key)]
assert order(data['first']) == ['2601.00001', '2601.00002']
assert order(data['second']) == ['2601.00002', '2601.00001']
""", first=str(first), second=str(second))

    def test_user_exclusions_change_actual_filtering(self):
        root = self.state_root()
        settings = self.config(root)
        settings["exclusions"] = {"primary": ["excluded sample topic"], "secondary": ["out of scope sample"]}
        self.write_config(root, settings)
        self.python("""
runtime.configure_public_runtime(Path(data['root']))
assert runtime.exclusion_reason({'title': 'Excluded sample topic'}) == 'configured_primary_exclusion'
assert runtime.exclusion_reason({'title': 'Out of scope sample'}) == 'configured_secondary_exclusion'
assert runtime.exclusion_reason({'title': 'Graph learning'}) is None
""", root=str(root))

    def test_initialized_run_rejects_reinterpreting_a_changed_profile(self):
        root = self.state_root()
        self.write_config(root)
        self.python("""
root = Path(data['root'])
runtime.initialize_runtime(root)
path = root / data['config_name']
settings = json.loads(path.read_text(encoding='utf-8'))
settings['topic_tiers']['A'] = ['distributed systems']
path.write_text(json.dumps(settings), encoding='utf-8')
try:
    runtime.configure_public_runtime(root)
except ValueError:
    pass
else:
    raise AssertionError('An initialized run was reinterpreted with a changed profile')
""", root=str(root), config_name=CONFIG_NAME)

    def test_unbound_existing_transaction_is_not_silently_adopted(self):
        root = self.state_root()
        self.write_config(root)
        pending = root / "pending-run.json"
        pending.write_text('{"run_id":"existing-unbound-run"}', encoding="utf-8")
        before = pending.read_bytes()
        self.python("""
try:
    runtime.configure_public_runtime(Path(data['root']))
except ValueError:
    pass
else:
    raise AssertionError('Existing transaction without profile binding was adopted')
""", root=str(root))
        self.assertEqual(before, pending.read_bytes())

    def test_public_schema_matches_generic_topic_groups(self):
        schema = json.loads((self.bundle_root / SKILL / "references/daily-arxiv-digest.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(
            {"direct_interest", "method_interest", "transfer_interest", "other_relevant"},
            set(schema["$defs"]["paper"]["properties"]["topic_group"]["enum"]),
        )

    def test_specific_non_cs_categories_and_single_category_are_supported(self):
        root = self.state_root()
        configurations = [self.config(root, categories=categories, report_category=categories[-1])
                          for categories in (["quant-ph"], ["math.PR", "quant-ph"],
                                             ["hep-th", "stat.ML", "q-bio.NC"])]
        self.python("""
assert runtime.TRACKED_CATEGORIES == (), 'No retrieval defaults before configuration'
for value in data['configurations']:
    validated = config.validate_config(value, Path(data['root']))
    assert list(validated['categories']) == value['categories']
    assert validated['report_category'] == value['report_category']
""", root=str(root), configurations=configurations)

    def test_selected_categories_are_replaced_when_switching_independent_roots(self):
        first, second = self.state_root("probability"), self.state_root("quantum")
        self.write_config(first, self.config(first, categories=["math.PR", "math.ST"], report_category="math.PR"))
        self.write_config(second, self.config(second, categories=["quant-ph"]))
        self.python("""
runtime.configure_public_runtime(Path(data['first']))
assert runtime.TRACKED_CATEGORIES == ('math.PR', 'math.ST')
runtime.configure_public_runtime(Path(data['second']))
assert runtime.TRACKED_CATEGORIES == ('quant-ph',)
assert runtime.CATEGORY_ORDER == ('quant-ph',)
assert runtime.REPORT_CATEGORY == 'quant-ph'
""", first=str(first), second=str(second))

    def test_mcp_schema_and_real_handler_read_live_configured_categories(self):
        first, second = self.state_root("probability"), self.state_root("quantum")
        self.write_config(first, self.config(first, categories=["math.PR", "quant-ph"], report_category="math.PR"))
        self.write_config(second, self.config(second, categories=["quant-ph"]))
        self.python(r'''
import ast, asyncio, re, types
source = Path(data['wrapper']).read_text(encoding='utf-8')
tree = ast.parse(source)
runtime_imports = [node for node in tree.body if
    isinstance(node, ast.Import) and any(alias.name == 'daily_digest_runtime' for alias in node.names)
    or isinstance(node, ast.ImportFrom) and node.module == 'daily_digest_runtime']
assert runtime_imports
assert not any(isinstance(node, ast.ImportFrom) and
               any(alias.name == 'TRACKED_CATEGORIES' for alias in node.names)
               for node in runtime_imports), 'MCP froze configuration before startup'
namespace = {'__builtins__': __builtins__, 'asyncio': asyncio, 're': re,
             'types': types.SimpleNamespace(Tool=lambda **kwargs: types.SimpleNamespace(**kwargs))}
exec(compile(ast.Module(body=runtime_imports, type_ignores=[]), '<actual-wrapper-imports>', 'exec'), namespace)
class GateBoundary(Exception):
    pass
class BoundaryGate:
    calls = 0
    def require_digest_session(self, token):
        self.calls += 1
        assert token == 'synthetic-offline-session'
        raise GateBoundary('Stop before retrieval; token binding is still mandatory')
gate = BoundaryGate()
namespace.update(gate=gate, PriorityGateError=ValueError)
handler = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
               and node.name == 'handle_call_tool')
handler.decorator_list = []
future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
module = ast.fix_missing_locations(ast.Module(body=[future, handler], type_ignores=[]))
exec(compile(module, '<actual-wrapper-handler>', 'exec'), namespace)
assignment_names = {'DIGEST_SESSION_TOKEN_ARGUMENT', 'DIGEST_SESSION_TOKEN_SCHEMA', 'FETCH_ANNOUNCEMENT_BATCH_TOOL'}
assignments = [node for node in tree.body if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id in assignment_names for target in node.targets)]
for root_name, expected in ((data['first'], ['math.PR', 'quant-ph']), (data['second'], ['quant-ph'])):
    runtime.configure_public_runtime(Path(root_name))
    namespace['ARGS'] = types.SimpleNamespace(role='digest', digest_root=Path(root_name))
    exec(compile(ast.Module(body=assignments, type_ignores=[]), '<actual-wrapper-tool-schema>', 'exec'), namespace)
    actual = namespace['FETCH_ANNOUNCEMENT_BATCH_TOOL'].inputSchema['properties']['category']['enum']
    assert actual == expected, (actual, expected)
    arguments = {'category': expected[0], 'digest_session_token': 'synthetic-offline-session'}
    calls = gate.calls
    try:
        asyncio.run(namespace['handle_call_tool']('fetch_announcement_batch', arguments))
    except GateBoundary:
        pass
    else:
        raise AssertionError('Configured category did not reach the session guard')
    assert gate.calls == calls + 1
    for category in ({'cs.CV', 'math.PR'} - set(expected)):
        arguments['category'] = category
        try:
            asyncio.run(namespace['handle_call_tool']('fetch_announcement_batch', arguments))
        except ValueError:
            pass
        else:
            raise AssertionError('Unconfigured category reached retrieval')
        assert gate.calls == calls + 1
''', first=str(first), second=str(second), wrapper=str(self.scripts / 'arxiv_priority_mcp_server.py'))

    def test_initialized_root_rejects_changing_categories_or_report_category(self):
        for change in ("categories", "report_category"):
            root = self.state_root(change)
            self.write_config(root, self.config(root, categories=["math.PR", "quant-ph"], report_category="math.PR"))
            self.python("""
root = Path(data['root'])
runtime.initialize_runtime(root)
path = root / data['config_name']
original = path.read_bytes()
settings = json.loads(original)
if data['change'] == 'categories':
    settings['categories'] = ['math.PR']
    settings['category_order'] = ['math.PR']
else:
    settings['report_category'] = 'quant-ph'
path.write_text(json.dumps(settings), encoding='utf-8')
try:
    runtime.configure_public_runtime(root)
except runtime.DigestValidationError as exc:
    assert 'configuration_changed' in str(exc)
else:
    raise AssertionError('Initialized category profile drift was accepted')
path.write_bytes(original)
runtime.configure_public_runtime(root)
assert runtime.TRACKED_CATEGORIES == ('math.PR', 'quant-ph')
""", root=str(root), config_name=CONFIG_NAME, change=change)

    def run_non_cs_pipeline(self, categories, report_category, code="", **extra):
        root = self.state_root()
        self.write_config(root, self.config(root, term="probability", categories=categories,
                                          report_category=report_category))
        return self.python(OFFLINE_PIPELINE + "\n" + textwrap.dedent(code),
                           root=str(root), categories=categories, report_category=report_category,
                           schema=str(self.bundle_root / SKILL / "references/daily-arxiv-digest.schema.json"),
                           **extra)

    def test_single_non_cs_category_runs_review_summary_and_digest_validation(self):
        self.run_non_cs_pipeline(["quant-ph"], "quant-ph")

    def test_known_paper_from_previous_date_is_counted_without_redelivery(self):
        self.run_non_cs_pipeline(["quant-ph"], "quant-ph", r'''
assert digest['report_already_known_count'] == 1
displayed = [*digest['focus_papers'], *digest['watch_papers'],
             *digest['cs_cv_report']['detailed'], *digest['cs_cv_report']['compact']]
assert '2607.00003' not in {paper['arxiv_id'] for paper in displayed}
assert '2607.00003' not in runtime.render_html(digest)
''', known_paper=True)

    def test_forged_known_count_cannot_hide_an_unreported_paper(self):
        self.run_non_cs_pipeline(["math.PR", "quant-ph"], "math.PR", r'''
changed = copy.deepcopy(digest)
assert changed['report_already_known_count'] == 0
assert changed['cs_cv_report']['total'] == 1
changed['cs_cv_report']['detailed'] = []
changed['cs_cv_report']['compact'] = []
changed['cs_cv_report']['total'] = 0
changed['stats']['cv_remainder'] = 0
changed['report_already_known_count'] = 1
for operation in (runtime.validate_digest, runtime.render_html):
    try:
        operation(changed)
    except runtime.DigestValidationError:
        pass
    else:
        raise AssertionError('Forged known count bypassed the frozen inventory evidence')
''')

    def test_missing_selected_category_prevents_review_and_digest(self):
        self.run_non_cs_pipeline(["math.PR", "quant-ph"], "math.PR", omit_category="quant-ph")

    def test_non_cs_digest_schema_html_and_portable_pdf_are_complete(self):
        self.run_non_cs_pipeline(["math.PR", "quant-ph"], "math.PR", r'''
import daily_digest_delivery as delivery
import jsonschema
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from pypdf import PdfReader
schema = json.loads(Path(data['schema']).read_text(encoding='utf-8'))
jsonschema.Draft202012Validator(schema).validate(digest)
html_text = runtime.render_html(digest)
assert 'math.PR Top 50' in html_text
assert 'cs.CV Top 50' not in html_text
assert 'cs.CV seven Seven' in html_text, 'Source title was rewritten as product text'
source_phrase = '用户原文保留 cs.CV seven Seven 文本。'
source_digest = copy.deepcopy(digest)
source_digest['overview'] = source_phrase
assert source_phrase in runtime.render_html(source_digest)
assert source_phrase in runtime.render_markdown(source_digest)
html_path = run_dir / 'portable-report.html'
html_path.write_text(html_text, encoding='utf-8')
delivery._validate_html(digest, html_path)
# The bundled CID font makes this a portable structural/text PDF test. Production
# CJK fonts, Poppler rasterization and the external mail bridge remain separate
# deployment prerequisites; the actual layout and content code is exercised.
pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
pdfmetrics.registerFontFamily('STSong-Light', normal='STSong-Light', bold='STSong-Light',
                              italic='STSong-Light', boldItalic='STSong-Light')
delivery._register_pdf_fonts = lambda: ('STSong-Light', 'STSong-Light')
pdf_path = run_dir / 'portable-report.pdf'
delivery._build_pdf(digest, pdf_path)
record = delivery._validate_pdf(digest, pdf_path, smoke_render=False)
assert record['pdf_pages'] >= 3
assert record['pdf_rendered_pages'] == []
extracted = '\n'.join(page.extract_text() or '' for page in PdfReader(str(pdf_path)).pages)
assert 'math.PR Top 50' in extracted and 'cs.CV Top 50' not in extracted
for category in data['categories']:
    assert category in extracted
assert (root / 'last-successful-run.json').read_bytes() == initial_success_bytes
''')

    def test_non_cs_digest_rejects_missing_coverage_and_wrong_report_membership(self):
        self.run_non_cs_pipeline(["math.PR", "quant-ph"], "math.PR", r'''
changed = copy.deepcopy(digest)
changed['retrieval_coverage'].pop()
try:
    runtime.validate_digest(changed)
except runtime.DigestValidationError:
    pass
else:
    raise AssertionError('Digest accepted missing configured coverage')
changed = copy.deepcopy(digest)
changed['cs_cv_report']['detailed'][0]['query_sources'] = ['quant-ph']
try:
    runtime.validate_digest(changed)
except runtime.DigestValidationError:
    pass
else:
    raise AssertionError('Complete report accepted a paper outside report_category')
changed = copy.deepcopy(digest)
changed['report_category'] = 'quant-ph'
try:
    runtime.validate_digest(changed)
except runtime.DigestValidationError:
    pass
else:
    raise AssertionError('Digest report identity differs from configured category')
''')

    def node(self, script):
        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required for the offline Gmail bridge boundary tests")
        result = subprocess.run([node, "-e", textwrap.dedent(script),
                                 str(self.scripts / "daily_digest_gmail_bridge.js")],
                                cwd=self.directory, capture_output=True, text=True, timeout=30)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_mime_bridge_passes_configuration_to_real_public_chunk_reader(self):
        root = self.state_root("state's $config")
        config_path = self.write_config(root, self.config(root, categories=["math.PR"]))
        initialized = self.cli("daily_digest_runtime.py", "init", "--root", str(root))
        self.assertEqual(0, initialized.returncode, initialized.stdout + initialized.stderr)
        html = "<html>合成离线附件测试</html>".encode("utf-8")
        pdf = b"%PDF-1.4\n% Synthetic MIME fixture\n" + bytes(range(251)) * 195
        html_path, pdf_path = root / "body.html", root / "arxiv-daily-fixture.pdf"
        html_path.write_bytes(html)
        pdf_path.write_bytes(pdf)
        manifest = {
            "validated": True, "delivery_format": "html_pdf_single",
            "message_count": 1, "attachment_count": 1, "mime_chunk_bytes": 24000,
            "html_path": str(html_path), "html_bytes": len(html),
            "html_sha256": hashlib.sha256(html).hexdigest(),
            "pdf_path": str(pdf_path), "pdf_bytes": len(pdf),
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(), "pdf_filename": pdf_path.name,
        }
        fixture = {
            "pythonExe": sys.executable,
            "scriptPath": str(self.scripts / "daily_digest_delivery.py"),
            "workdir": str(self.directory), "publicConfigPath": str(config_path),
            "manifest": manifest,
        }
        (self.directory / "mime-input.json").write_text(json.dumps(fixture), encoding="utf-8")
        self.node(r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {spawnSync} = require('node:child_process');
const fixture = JSON.parse(fs.readFileSync('mime-input.json', 'utf8'));
const launcher = [
  'import pathlib,runpy,socket,sys,urllib.request',
  "def denied(*args, **kwargs): raise AssertionError('Live network is forbidden in MIME preparation tests')",
  'socket.create_connection = denied',
  'urllib.request.urlopen = denied',
  'script = sys.argv.pop(1)',
  'sys.path.insert(0, str(pathlib.Path(script).parent))',
  "runpy.run_path(script, run_name='__main__')",
].join('\n');
let reads = 0;
global.tools = {
  async exec_command(input) {
    // Decode only the checked helper's quoted command shape; CI needs no PowerShell.
    const suffix = '; exit $LASTEXITCODE';
    assert.ok(input.cmd.startsWith('& ') && input.cmd.endsWith(suffix));
    const command = input.cmd.slice(2, -suffix.length);
    const tokens = command.match(/'(?:[^']|'')*'|[^\s]+/g).map(value =>
      value.startsWith("'") ? value.slice(1, -1).replaceAll("''", "'") : value);
    assert.equal(tokens[0], fixture.pythonExe);
    assert.equal(tokens[1], '-B');
    assert.equal(tokens[2], fixture.scriptPath);
    assert.deepEqual(tokens.slice(3, 6), ['--public-config', fixture.publicConfigPath, 'mime-chunk']);
    assert.equal(input.workdir, fixture.workdir);
    assert.ok(input.max_output_tokens >= 12000);
    const run = args => spawnSync(tokens[0], ['-I', '-B', '-X', 'utf8', '-c', launcher, ...args], {
      cwd: input.workdir, encoding: 'utf8', timeout: 10000, maxBuffer: 1024 * 1024,
    });
    if (reads === 0) {
      const denied = run([tokens[2], ...tokens.slice(5)]);
      assert.ifError(denied.error);
      assert.notEqual(denied.status, 0, 'Rootless public reader accepted missing configuration');
      assert.match(denied.stdout + denied.stderr, /public_digest_not_configured/);
    }
    reads++;
    const result = run(tokens.slice(2));
    assert.ifError(result.error);
    assert.equal(result.status, 0, result.stdout + result.stderr);
    return {exit_code: result.status, output: result.stdout};
  },
};
const readChunk = global.tools.exec_command;
global.tools.exec_command = async input => {
  try { return await readChunk(input); }
  catch (error) { console.error(error); throw error; }
};
// No Gmail tools exist in this process: MIME preparation must use only local reads.
const bridge = eval(fs.readFileSync(process.argv[1], 'utf8'));
(async () => {
  const payload = await bridge.prepareMimePayload(fixture);
  assert.equal(payload.mime_type, 'multipart/mixed');
  assert.equal(payload.parts.length, 2);
  for (const [index, kind] of ['html', 'pdf'].entries()) {
    assert.deepEqual(Buffer.from(payload.parts[index].body.base64_url_content, 'base64url'),
                     fs.readFileSync(fixture.manifest[kind + '_path']));
  }
  assert.equal(reads, 4, 'Fixture must exercise a complete multi-chunk attachment');
})().catch(error => { console.error(error); process.exitCode = 1; });
""")

    def test_direct_send_is_inert_without_the_verified_transaction_path(self):
        self.node("""
const fs = require('fs');
let sends = 0;
global.tools = {mcp__codex_apps__gmail_send_draft: async () => { sends++; return {}; }};
const bridge = eval(fs.readFileSync(process.argv[1], 'utf8'));
(async () => {
  if (bridge.sendVerifiedDraft !== undefined || bridge.attemptVerifiedDraftOnce !== undefined) throw Error('Private send primitive exposed');
  let failure;
  try { await bridge.callGmail('send_draft', {draft_id: 'synthetic-draft'}, () => {}); }
  catch (error) { failure = error; }
  if (failure?.failureCode !== 'gmail_connector_validation_failed' || sends !== 0) throw Error('Unverified send crossed the boundary');
})().catch(error => { console.error(error); process.exitCode = 1; });
""")

    def test_gmail_read_retry_does_not_turn_into_write_retry(self):
        self.node("""
const fs = require('fs');
let reads = 0, writes = 0, sends = 0;
global.setTimeout = callback => { callback(); return 0; };
global.tools = {
 mcp__codex_apps__gmail_get_profile: async () => {
   reads++; if (reads < 3) throw Error('synthetic transient read failure');
   return {content: [], structuredContent: {result: {email: 'reader@example.org'}}};
 },
 mcp__codex_apps__gmail_create_draft: async () => { writes++; throw Error('synthetic write failure'); },
 mcp__codex_apps__gmail_send_draft: async () => { sends++; throw Error('must not send'); },
};
const bridge = eval(fs.readFileSync(process.argv[1], 'utf8'));
(async () => {
 await bridge.getProfile();
 try { await bridge.createDraft({subject: 'Synthetic offline fixture'}); } catch (_) {}
 if (reads !== 3 || writes !== 1 || sends !== 0) throw Error('Read/write retry boundary changed');
})().catch(error => { console.error(error); process.exitCode = 1; });
""")


if __name__ == "__main__":
    unittest.main()
