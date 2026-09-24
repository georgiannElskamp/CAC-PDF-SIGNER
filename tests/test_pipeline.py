import copy
import hashlib
import json
import re
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'automation/controller'))
import pipeline
import pipeline_policy as policy
import promote_release as release
import release_manifest
import repair_patch

SHA = 'a' * 40
MAIN = 'b' * 40
STAMP = '2026-01-01T00:00:00Z'


def pull():
    return {'number': 123, 'state': 'open', 'draft': False, 'user': {'login': policy.APP},
            'base': {'ref': 'research', 'sha': MAIN}, 'head': {'ref': 'change', 'sha': SHA, 'repo': {'full_name': policy.PUBLIC}}}


def run():
    return {'id': 42, 'path': '.github/workflows/build-candidate.yml', 'event': 'push',
            'head_branch': 'research', 'head_sha': SHA, 'status': 'completed', 'conclusion': 'success'}


class PipelinePolicyTests(unittest.TestCase):
    def test_only_trusted_research_prs_are_eligible(self):
        self.assertTrue(policy.eligible(pull()))
        for mutate in (lambda p: p['base'].update(ref='main'), lambda p: p.update(draft=True),
                       lambda p: p['user'].update(login='untrusted'), lambda p: p['head'].update(repo=None),
                       lambda p: p['head'].update(ref='main'), lambda p: p['head'].update(ref='research'),
                       lambda p: p['head'].update(ref='release-verification'), lambda p: p.update(state='closed')):
            value = pull(); mutate(value)
            self.assertFalse(policy.eligible(value))

    def test_version_increment_uses_impact_not_commit_count(self):
        self.assertEqual(policy.next_version('v0.7.0-rc.6', 'minor'), '0.8.0')
        self.assertEqual(policy.next_version('1.9.8', 'major'), '2.0.0')
        self.assertEqual(policy.next_version('1.9.8', 'patch'), '1.9.9')
        with self.assertRaises(ValueError): policy.next_version('main', 'minor')

    def test_release_notes_include_changes_merged_before_prior_publication(self):
        first, second = '1' * 40, '2' * 40
        merged = [
            {'number': 19, 'title': 'Sign ONLYOFFICE form boxes',
             'merged_at': '2026-09-23T19:00:51Z', 'merge_commit_sha': first,
             'labels': [{'name': 'release:minor'}]},
            {'number': 21, 'title': 'Sync accepted release',
             'merged_at': '2026-09-23T19:54:50Z', 'merge_commit_sha': second,
             'labels': []},
        ]
        comparison = {'status': 'ahead', 'ahead_by': 2, 'behind_by': 0}
        with patch.object(pipeline, 'api', return_value=comparison), \
             patch.object(pipeline, 'pages', return_value=[{'sha': first}, {'sha': second}]):
            relevant = pipeline.merged_since_snapshot(SHA, MAIN, merged)
        self.assertEqual([p['number'] for p in relevant], [19, 21])
        notes = pipeline.release_notes('0.9.0', MAIN, relevant)
        self.assertIn('form boxes (#19)', notes)
        self.assertNotIn('pending', notes)
        self.assertNotIn('approval', notes)
        with patch.object(pipeline, 'api', return_value={**comparison, 'behind_by': 1}), \
             patch.object(pipeline, 'pages') as commits:
            with self.assertRaisesRegex(RuntimeError, 'not an ancestor'):
                pipeline.merged_since_snapshot(SHA, MAIN, merged)
            commits.assert_not_called()
        with patch.object(pipeline, 'api', return_value=comparison), \
             patch.object(pipeline, 'pages', return_value=[{'sha': first}]):
            with self.assertRaisesRegex(RuntimeError, 'incomplete'):
                pipeline.merged_since_snapshot(SHA, MAIN, merged)

    def test_pinned_action_updates_cannot_smuggle_workflow_changes(self):
        old = 'uses: actions/checkout@' + 'a' * 40 + ' # v1\n'
        new = 'uses: actions/checkout@' + 'b' * 40 + ' # v2\n'
        self.assertTrue(policy.pin_only(old, new))
        self.assertFalse(policy.pin_only(old, new + 'run: malicious\n'))
        self.assertTrue(policy.sensitive([{'filename': 'safe.py', 'previous_filename': '.github/CODEOWNERS'}]))

    def test_candidate_requires_exact_source_branch_and_success(self):
        self.assertTrue(policy.candidate_run(run(), SHA, 'research'))
        for field, value in [('head_sha', MAIN), ('event', 'pull_request'), ('head_branch', 'main'),
                             ('status', 'in_progress'), ('conclusion', 'skipped'), ('path', '.github/workflows/checks.yml')]:
            record = run(); record[field] = value
            self.assertFalse(policy.candidate_run(record, SHA, 'research'))

    def test_completed_review_must_match_commit_and_request(self):
        request = {'created_at': STAMP}
        summary = {'user': {'login': policy.CODEX}, 'created_at': STAMP, 'updated_at': STAMP,
                   'body': '<!-- codex-pull-request-review-summary -->\nCode Review | Completed | `' + SHA[:7] + '` | Manual request <relative-time datetime="' + STAMP + '">'}
        reaction = {'user': {'login': policy.CODEX}, 'created_at': STAMP, 'content': '+1'}
        self.assertEqual(policy.review_result(SHA, request, [summary], [], [], [reaction]), 'clean')
        self.assertEqual(policy.review_result(MAIN, request, [summary], [], [], [reaction]), 'pending')
        self.assertEqual(policy.review_result(SHA, {'created_at': '2026-01-02T00:00:00Z'}, [summary], [], [], [reaction]), 'pending')
        reaction['content'] = 'eyes'
        self.assertEqual(policy.review_result(SHA, request, [summary], [], [], [reaction]), 'pending')
        finding = {'id': 1, 'user': {'login': policy.CODEX}, 'commit_id': SHA, 'submitted_at': STAMP, 'state': 'CHANGES_REQUESTED'}
        reaction['content'] = '+1'
        self.assertEqual(policy.review_result(SHA, request, [summary], [finding], [], [reaction]), 'findings')

    def test_missing_foreign_failed_and_newer_checks_cannot_pass(self):
        checks = [{'name': n, 'app': {'id': 15368}, 'check_suite': {'id':1}, 'started_at': STAMP, 'status': 'completed', 'conclusion': 'success'} for n in pipeline.REQUIRED]
        def responses(rows):
            return lambda path, **kwargs: ([dict(run(),check_suite_id=1,pull_requests=[{'number':123}])] if '/runs?' in path else rows)
        with patch.object(pipeline, 'pages', side_effect=responses(checks)):
            self.assertEqual(pipeline.ci_state(pull())[0], 'passed')
        for bad in (checks[:-1], [dict(c, app={'id': 7}) for c in checks],
                    checks + [dict(checks[0], started_at='2026-01-02', conclusion='failure')]):
            with patch.object(pipeline, 'pages', side_effect=responses(bad)):
                self.assertNotEqual(pipeline.ci_state(pull())[0], 'passed')

    def test_obsolete_workflow_pass_cannot_mask_running_replacement(self):
        old = dict(run(),check_suite_id=1,pull_requests=[{'number':123}])
        new = dict(old,id=43,status='in_progress',conclusion=None)
        with patch.object(pipeline,'pages',return_value=[old,new]):
            self.assertEqual(pipeline.ci_state(pull())[0],'pending')

    def test_newer_failed_build_does_not_fall_back_to_older_pass(self):
        with patch.object(pipeline, 'pages', return_value=[run(), dict(run(), id=43, conclusion='failure')]):
            self.assertIsNone(pipeline.successful_build(SHA, 'research'))

    def test_saved_request_intent_does_not_duplicate_a_cloud_task(self):
        state = Mock(); record = {'review': {'state': 'requesting'}}
        with patch.object(pipeline, 'pages', return_value=[]), patch.object(pipeline, 'api') as api:
            self.assertIsNone(pipeline.request_once(state, record, pull(), 'review'))
            api.assert_not_called()

    def test_repair_budget_stops_requests(self):
        with patch.object(pipeline, 'request_once') as request, patch.object(pipeline, 'status') as status:
            pipeline.repair(Mock(), {'repairs': 2}, {}, pull(), 'failure')
            request.assert_not_called()
            self.assertEqual(status.call_args.args[1], 'failure')

    def test_policy_change_requires_owner_approval_on_current_commit(self):
        good = {'user':{'login':policy.OWNER},'state':'APPROVED','commit_id':SHA,'submitted_at':STAMP}
        with patch.object(pipeline,'pages',return_value=[good]):
            self.assertTrue(pipeline.owner_approved(pull()))
        for reviews in ([], [dict(good,commit_id=MAIN)], [dict(good,user={'login':policy.CODEX})],
                        [good,dict(good,state='DISMISSED',submitted_at='2026-01-02')]):
            with patch.object(pipeline,'pages',return_value=reviews):
                self.assertFalse(pipeline.owner_approved(pull()))

    def test_main_pr_never_reaches_merge_code(self):
        value = pull(); value['base']['ref'] = 'main'
        with patch.object(pipeline, 'api') as api:
            pipeline.process_pull(Mock(), value)
            api.assert_not_called()

    def test_invalid_repair_isolated_to_its_pr_and_not_reparsed(self):
        state = Mock(data={'pulls':{}})
        other = pull(); other['number']=124
        with patch.object(pipeline,'process_pull',side_effect=[ValueError('Invalid repair hash'),None]) as process,patch.object(pipeline,'status') as status:
            pipeline.reconcile_pull(state,pull())
            pipeline.reconcile_pull(state,other)
            pipeline.reconcile_pull(state,pull())
            self.assertEqual(process.call_count,2)
            self.assertEqual(status.call_args.args[1],'failure')
        self.assertEqual(state.data['pulls']['123']['heads'][SHA]['attention'],'Invalid repair hash')

    def test_retarget_events_remain_enabled_for_all_required_pr_workflows(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('checks.yml','dependency-review.yml','pr-build.yml'):
            workflow=(root/'.github/workflows'/name).read_text(encoding='utf-8')
            declared=re.search(r'(?m)^    types: \[([^\]]+)\]',workflow)
            self.assertIsNotNone(declared)
            self.assertIn('edited',{event.strip() for event in declared.group(1).split(',')})

    def test_changed_head_after_review_cannot_merge(self):
        state = Mock(data={'pulls': {}})
        changed = pull(); changed['head']['sha'] = MAIN
        with patch.object(pipeline, 'policy_changes', return_value=[]), patch.object(pipeline, 'ci_state', return_value=('passed', [])), patch.object(pipeline, 'review', return_value='clean'), patch.object(pipeline, 'api', return_value=changed) as api, patch.object(pipeline, 'status'):
            pipeline.process_pull(state, pull())
            self.assertFalse(any(len(c.args) > 1 and c.args[1] != 'GET' for c in api.call_args_list))


class ApprovedPublicationTests(unittest.TestCase):
    def approved(self):
        value = pull()
        value.update(merged=True, merged_by={'login': policy.OWNER}, merge_commit_sha=MAIN)
        value['base']['ref'] = 'main'; value['head']['ref'] = 'release-verification'
        reviews = [{'user': {'login': policy.OWNER}, 'state': 'APPROVED', 'submitted_at': STAMP, 'commit_id': SHA}]
        return value, reviews

    def test_human_approval_and_manual_merge_are_both_required(self):
        value, reviews = self.approved()
        release.approved_pull(value, reviews, MAIN)
        for mutate in (lambda p: p.update(merged=False), lambda p: p['merged_by'].update(login=policy.APP),
                       lambda p: p['user'].update(login=policy.OWNER), lambda p: p['head'].update(ref='research')):
            altered = copy.deepcopy(value); mutate(altered)
            with self.assertRaises(ValueError): release.approved_pull(altered, reviews, MAIN)
        for invalid in ([], [dict(reviews[0], commit_id=MAIN)], [dict(reviews[0], state='DISMISSED')],
                        reviews + [dict(reviews[0], state='CHANGES_REQUESTED', submitted_at='2026-01-02')]):
            with self.assertRaises(ValueError): release.approved_pull(value, invalid, MAIN)

    def test_release_inspection_requires_complete_current_run_and_later_approval(self):
        value, reviews = self.approved()
        value.update(merged_at='2026-01-03T00:00:00Z')
        reviews[0]['submitted_at'] = '2026-01-02T00:00:00Z'
        build = dict(run(), head_branch='release-verification', updated_at=STAMP)
        gate = {'name':'Candidate qualification','conclusion':'success'}
        artifact = {'id':99,'name':'candidate','expired':False}
        def api(path):
            if path.endswith('/heads/main'): return {'object':{'sha':MAIN}}
            if path.endswith('/pulls/123'): return value
            if '/git/commits/' in path: return {'tree':{'sha':'c'*40}}
            self.fail(path)
        def pages(path, **kwargs):
            if '/commits/' in path and path.endswith('/pulls'): return [value]
            if path.endswith('/reviews'): return reviews
            if '/runs?' in path: return [build]
            if '/jobs?' in path: return [gate]
            if path.endswith('/artifacts'): return [artifact]
            self.fail(path)
        with patch.object(release,'api',side_effect=api), patch.object(release,'pages',side_effect=pages):
            self.assertEqual(release.inspect(MAIN)['artifact'],99)
            for status in ('failure','skipped',None):
                gate['conclusion']=status
                with self.assertRaises(ValueError): release.inspect(MAIN)
            gate['conclusion']='success'
            artifact['expired']=True
            with self.assertRaises(ValueError): release.inspect(MAIN)
            artifact['expired']=False
            build['updated_at']='2026-01-03T00:00:00Z'
            with self.assertRaisesRegex(ValueError,'after its latest build'): release.inspect(MAIN)

    def test_existing_release_tag_cannot_be_repointed(self):
        proof = {'main': MAIN}
        with tempfile.TemporaryDirectory() as folder, patch.object(release, 'inspect', return_value=proof), patch.object(release, 'validate_package', return_value={'tag': 'v1.0.0'}), patch.object(release, 'optional', return_value={'object': {'type': 'commit', 'sha': SHA}}), patch.object(release, 'api') as api:
            with self.assertRaises(ValueError): release.publish(Path(folder), proof)
            api.assert_not_called()

    def test_draft_lookup_uses_id_and_rejects_duplicate_tags(self):
        rows = [{'id': 7, 'tag_name': 'v1.0.0', 'draft': True, 'assets': []}]
        with patch.object(release, 'pages', return_value=rows), patch.object(release, 'api', return_value={'id': 7}) as api:
            self.assertEqual(release.find_release('v1.0.0'), {'id': 7})
            api.assert_called_once_with(release.REPO + '/releases/7')
            rows.append(dict(rows[0], id=8))
            with self.assertRaisesRegex(ValueError, 'Multiple releases'):
                release.find_release('v1.0.0')
            self.assertEqual(api.call_count, 1)

    def test_publication_creates_or_resumes_draft_before_publishing(self):
        proof = {'main': MAIN}
        for state in ('new', 'partial', 'complete', 'published', 'mismatch', 'renamed'):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); (root / 'docs').mkdir()
                (root / 'docs/RELEASE_NOTES.md').write_text('Release 1.0.0', encoding='utf-8')
                for name in release.ASSETS:
                    (root / name).write_bytes(('synthetic ' + name).encode())
                assets = [{'name': name, 'digest': 'sha256:' + release.sha256(root / name)} for name in release.ASSETS]
                draft = {'id': 7, 'tag_name': 'v1.0.0', 'draft': state != 'published', 'assets': copy.deepcopy(assets)}
                if state in ('new', 'partial'): draft['assets'] = assets[:0 if state == 'new' else 2]
                if state == 'mismatch': draft['assets'][0]['digest'] = 'sha256:' + '0' * 64
                rows = [] if state == 'new' else [{'id': 7, 'tag_name': 'v1.0.0', 'assets': []}]
                uploaded = {**draft, 'assets': assets}
                if state == 'renamed': uploaded['tag_name'] = 'v2.0.0'
                reads = 0
                def api(path, method='GET', body=None):
                    nonlocal reads
                    if path == release.REPO + '/releases' and method == 'POST':
                        self.assertTrue(body['draft'])
                        return draft
                    if path == release.REPO + '/releases/7':
                        if method == 'PATCH':
                            self.assertEqual(body, {'draft': False, 'prerelease': False, 'make_latest': 'true'})
                            return {**uploaded, 'draft': False}
                        reads += 1
                        return draft if reads == 1 and state != 'new' else uploaded
                    self.fail('Unexpected release endpoint: ' + path)
                with patch.object(release, 'ROOT', root), patch.object(release, 'inspect', return_value=proof), patch.object(release, 'validate_package', return_value={'tag': 'v1.0.0'}), patch.object(release, 'optional', return_value={'object': {'type': 'commit', 'sha': MAIN}}), patch.object(release, 'pages', return_value=rows), patch.object(release, 'api', side_effect=api) as requests, patch.object(release.subprocess, 'run') as upload:
                    if state in ('mismatch', 'renamed'):
                        with self.assertRaises(ValueError): release.publish(root, proof)
                    else:
                        release.publish(root, proof)
                    mutations = [(c.args[0], c.args[1]) for c in requests.call_args_list if len(c.args) > 1]
                    self.assertEqual(sum(method == 'POST' for _, method in mutations), int(state == 'new'))
                    self.assertEqual(sum(method == 'PATCH' for _, method in mutations), int(state in ('new', 'partial', 'complete')))
                    if state in ('new', 'partial'):
                        expected = [str(root / name) for name in release.ASSETS[0 if state == 'new' else 2:]]
                        upload.assert_called_once_with(['gh', 'release', 'upload', 'v1.0.0', '--repo', policy.PUBLIC, *expected], check=True)
                    else:
                        upload.assert_not_called()

    def test_substituted_metadata_fails_before_package_audit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); (root / 'plugin').mkdir(); (root / '.github').mkdir()
            (root / 'plugin/config.json').write_text('{"version":"1.0.0"}')
            (root / '.github/release-candidate.json').write_text('{"version":"1.0.0"}')
            (root / 'CAC-PDF-Signer.plugin').write_bytes(b'synthetic package')
            (root / 'metadata.json').write_text(json.dumps({'candidate':True, 'harness':SHA, 'plugin':{'tag':'v1.0.0','commit':SHA,'sha256':'0'*64}}))
            with patch.object(release, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'metadata differ'):
                    release.validate_package(root, {'candidate':SHA})

    def test_legacy_release_pin_still_requires_actual_tag_and_hash(self):
        approved = {'tag':'v0.7.0-rc.6','file':'CAC-PDF-Signer.plugin','sha256':'c'*64,'commit':SHA}
        metadata = {'tag_name':approved['tag'],'draft':False,'prerelease':False,'assets':[{'name':approved['file'], 'digest':'sha256:'+approved['sha256'], 'browser_download_url':f"https://github.com/{policy.PUBLIC}/releases/download/{approved['tag']}/{approved['file']}"}]}
        responses = [metadata, {'object':{'type':'commit','sha':SHA}}, {'status':'ahead'}]
        self.assertEqual(release_manifest.resolve(Mock(side_effect=responses), approved), approved)
        responses[1] = {'object':{'type':'commit','sha':MAIN}}
        with self.assertRaises(ValueError): release_manifest.resolve(Mock(side_effect=responses), approved)


class RepairPatchTests(unittest.TestCase):
    def payload(self):
        return {'schema':1,'base':SHA,'request':'test-marker','files':[{'path':'tests/probe.py',
            'beforeSha256':hashlib.sha256(b'old\n').hexdigest(),'content':'new\n'}]}

    def parse(self, value):
        return repair_patch.parse('<cac-repair-patch>'+json.dumps(value)+'</cac-repair-patch>',SHA,'test-marker')

    def test_matching_existing_text_replacement_is_bounded(self):
        files=self.parse(self.payload())
        self.assertEqual(repair_patch.replacement(files[0],'old\n','100644')['content'],'new\n')
        for mode in ('120000','160000',None):
            with self.assertRaises(ValueError): repair_patch.replacement(files[0],'old\n',mode)
        with self.assertRaises(ValueError): repair_patch.replacement(files[0],'changed\n','100644')

    def test_wrong_request_policy_paths_and_binary_text_are_rejected(self):
        changes=[lambda p:p.update(base=MAIN),lambda p:p.update(request='other'),lambda p:p.update(files=[]),
            lambda p:p.update(files=p['files']*6),lambda p:p['files'][0].update(content='a'*50001),
            lambda p:p['files'][0].update(content='bad'+chr(0))]
        for path in ('../escape.py','/absolute.py','.github/workflows/run.yml','automation/controller/pipeline.py',
                     'tools/promote_release.py','tests/test_pipeline.py','image.png','a//b.py'):
            changes.append(lambda p,path=path:p['files'][0].update(path=path))
        for change in changes:
            value=self.payload();change(value)
            with self.assertRaises(ValueError):self.parse(value)

    def test_duplicate_json_properties_and_ambiguous_blocks_are_rejected(self):
        value=json.dumps(self.payload())
        with self.assertRaises(ValueError):
            repair_patch.parse('<cac-repair-patch>'+value.replace('"schema": 1','"schema": 1, "schema": 1')+'</cac-repair-patch>',SHA,'test-marker')
        block='<cac-repair-patch>'+value+'</cac-repair-patch>'
        with self.assertRaises(ValueError):repair_patch.parse(block+block,SHA,'test-marker')
        self.assertIsNone(repair_patch.parse('A cloud task summary without a patch',SHA,'test-marker'))

    def test_controller_applies_only_the_pinned_text_to_a_live_temporary_branch(self):
        reply={'id':7,'user':{'login':policy.CODEX},'created_at':STAMP,
            'body':'<cac-repair-patch>'+json.dumps(self.payload())+'</cac-repair-patch>'}
        record={'repair':{'created_at':STAMP,'marker':'test-marker'}}
        state=Mock()
        def api(path,method='GET',body=None):
            if path.endswith('/git/commits/'+SHA):return {'tree':{'sha':'original-tree'}}
            if path.endswith('/git/trees/original-tree?recursive=1'):return {'truncated':False,'tree':[{'path':'tests/probe.py','mode':'100644','type':'blob'}]}
            if path.endswith('/pulls/123'):return pull()
            if method=='POST' and path.endswith('/git/trees'):
                self.assertEqual(body['tree'],[{'path':'tests/probe.py','mode':'100644','type':'blob','content':'new\n'}])
                return {'sha':'updated-tree'}
            if method=='POST' and path.endswith('/git/commits'):
                self.assertEqual(body['parents'],[SHA]);return {'sha':MAIN}
            if method=='PATCH' and path.endswith('/git/refs/heads/change'):
                self.assertEqual(body,{'sha':MAIN,'force':False});return {}
            self.fail(path)
        with patch.object(pipeline,'pages',return_value=[reply]),patch.object(pipeline,'text_file',return_value='old\n'),patch.object(pipeline,'api',side_effect=api):
            self.assertTrue(pipeline.apply_repair(state,record,pull()))
        self.assertEqual(record['patch']['state'],'applied')
        self.assertEqual(state.save.call_count,2)
        with patch.object(pipeline,'api') as request:
            with self.assertRaises(RuntimeError):pipeline.apply_repair(state,record,pull())
            request.assert_not_called()
