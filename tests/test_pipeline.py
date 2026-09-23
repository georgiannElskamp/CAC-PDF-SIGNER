import copy
import hashlib
import json
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
