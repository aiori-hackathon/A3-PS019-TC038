"""Automatic decisions require opt-in, validated AI output and fresh untouched findings."""
import json
import sqlite3

import pytest

from conftest import Client
from privacytwin import llm
from privacytwin.store import Store

DATA = b'email,mobile,notes\nalice.secret@example.in,9876543210,misc\nbob.secret@example.in,9123456789,misc\n'


@pytest.fixture
def ai(monkeypatch):
    prompts = []
    monkeypatch.setattr(llm, 'config', lambda: {'provider': 'Groq', 'model': 'test-model', 'url': 'unused', 'key': 'unused'})

    def chat(prompt, **kwargs):
        prompts.append(prompt)
        rows = json.loads(prompt.split('\n', 1)[1])
        return json.dumps({'decisions': [{'pt_id': r['pt_id'], 'decision': 'approve',
                                         'reason': 'Header and value evidence support the detected class.'} for r in rows]})
    monkeypatch.setattr(llm, 'chat', chat)
    return prompts


def configure(client, enabled=True, threshold=.95):
    response = client.post('/api/auto-triage/settings', json={'enabled': enabled, 'threshold': threshold})
    assert response.status_code == 200, response.text
    return response.json()


def rows(client):
    return client.get('/api/inventory').json()['rows']


def test_default_off_and_disabled_run_never_calls_model(client, ai):
    assert client.get('/api/auto-triage').json()['enabled'] is False
    events = client.scan_csv('people.csv', DATA)
    assert events[-1]['auto_triage'] is None
    assert client.post('/api/auto-triage/run').json()['status'] == 'disabled'
    assert not ai
    assert all(r['status'] == 'candidate' for r in rows(client))


def test_scan_auto_approval_provenance_privacy_and_undo(client, ai):
    configure(client)
    events = client.scan_csv('people.csv', DATA)
    result = events[-1]['auto_triage']
    assert result['approved'] == 2 and result['batch_id']
    assert any(e['type'] == 'triage' for e in events)
    approved = [r for r in rows(client) if r['decision_source'] == 'ai']
    assert len(approved) == 2
    assert all(r['status'] == 'confirmed' and r['reviewed_by'] == 'AI auto-triage' for r in approved)
    assert all(r['review_note'].startswith('AI auto-approved:') for r in approved)
    assert all(r['status'] == 'candidate' for r in rows(client) if r['detected_class'] == 'NOT_PERSONAL')
    for prompt in ai:
        assert 'alice.secret@example.in' not in prompt and '9876543210' not in prompt
        assert 'masked_examples' not in prompt
        for r in approved:
            for example in r['masked_examples']:
                assert example not in prompt
    audit = client.get('/api/audit').json()['entries']
    decisions = [e for e in audit if e['action'] == 'review.auto_approved']
    assert len(decisions) == 2
    assert all(e['payload']['model'] == 'test-model' and e['payload']['scan_id'] and e['payload']['reason'] for e in decisions)
    assert client.get('/api/evaluation').json()['human']['reviewed'] == 0
    assert client.get('/api/audit/verify').json()['ok'] is True
    assert client.get('/api/auto-triage').json()['undoable'] == 2
    assert client.post('/api/auto-triage/undo', json={'batch_id': result['batch_id']}).json()['restored'] == 2
    assert client.post('/api/auto-triage/undo', json={'batch_id': result['batch_id']}).json()['restored'] == 0
    assert client.post('/api/auto-triage/run').json()['approved'] == 0
    assert all(r['status'] == 'candidate' for r in rows(client))


def test_run_existing_never_overwrites_human_and_undo_preserves_later_review(client, ai):
    client.scan_csv('people.csv', DATA)
    email = next(r for r in rows(client) if r['column'] == 'email')
    client.post('/api/reviews', json={'keys': [email['key']], 'status': 'rejected', 'note': 'Test mailbox'})
    configure(client)
    result = client.post('/api/auto-triage/run').json()
    assert result['approved'] == 1
    assert next(r for r in rows(client) if r['column'] == 'email')['status'] == 'rejected'
    mobile = next(r for r in rows(client) if r['column'] == 'mobile')
    review = client.post('/api/reviews', json={'keys': [mobile['key']], 'status': 'confirmed'}).json()
    assert client.post('/api/auto-triage/undo', json={'batch_id': result['batch_id']}).json()['restored'] == 0
    assert client.get('/api/evaluation').json()['human']['reviewed'] == 2
    client.post('/api/reviews/undo', json={'previous': review['previous']})
    assert next(r for r in rows(client) if r['column'] == 'mobile')['decision_source'] == 'ai'
    assert client.get('/api/evaluation').json()['human']['reviewed'] == 1


@pytest.mark.parametrize('output', [None, 'not json', '{"decisions":{}}',
    '{"decisions":[{"pt_id":"PT-99999","decision":"approve","reason":"yes"}]}',
    '{"decisions":[{"pt_id":"PT-00001","decision":"reject","reason":"reason"}]}',
    '{"decisions":[{"pt_id":"PT-00001","decision":"approve","reason":""}]}'])
def test_invalid_or_failed_ai_leaves_candidates(client, ai, monkeypatch, output):
    client.scan_csv('people.csv', DATA)
    configure(client)
    monkeypatch.setattr(llm, 'chat', lambda *a, **kw: output)
    result = client.post('/api/auto-triage/run').json()
    assert result['status'] == 'unavailable' and result['approved'] == 0
    assert all(r['status'] == 'candidate' for r in rows(client))


def test_no_provider_and_abstention(client, monkeypatch):
    configure(client)
    events = client.scan_csv('people.csv', DATA)
    assert events[-1]['type'] == 'done' and events[-1]['auto_triage']['status'] == 'unavailable'
    monkeypatch.setattr(llm, 'config', lambda: {'provider': 'Groq', 'model': 'test-model', 'url': 'unused'})
    monkeypatch.setattr(llm, 'chat', lambda *a, **kw: '{"decisions":[]}')
    assert client.post('/api/auto-triage/run').json()['approved'] == 0
    assert all(r['status'] == 'candidate' for r in rows(client))


def test_disable_while_provider_is_running_discards_response(client, ai, monkeypatch):
    client.scan_csv('people.csv', DATA)
    configure(client)
    original = llm.chat

    def disable(prompt, **kw):
        configure(client, False)
        return original(prompt, **kw)
    monkeypatch.setattr(llm, 'chat', disable)
    assert client.post('/api/auto-triage/run').json()['approved'] == 0
    assert all(r['status'] == 'candidate' for r in rows(client))


def test_human_decision_during_provider_call_wins(client, ai, monkeypatch):
    client.scan_csv('people.csv', DATA)
    configure(client)
    original = llm.chat
    email = next(r for r in rows(client) if r['column'] == 'email')

    def decide(prompt, **kw):
        client.post('/api/reviews', json={'keys': [email['key']], 'status': 'needs_info'})
        return original(prompt, **kw)
    monkeypatch.setattr(llm, 'chat', decide)
    assert client.post('/api/auto-triage/run').json()['approved'] == 1
    assert next(r for r in rows(client) if r['column'] == 'email')['status'] == 'needs_info'


def test_threshold_and_workspace_isolation(client, app, ai):
    for threshold in (.89, 1.01):
        assert client.post('/api/auto-triage/settings', json={'enabled': True, 'threshold': threshold}).status_code == 422
    configure(client, threshold=1)
    client.scan_csv('people.csv', DATA)
    other = Client(app, 'b'*40)
    assert other.get('/api/auto-triage').json()['enabled'] is False
    batch = client.get('/api/auto-triage').json()['last_batch']
    assert other.post('/api/auto-triage/undo', json={'batch_id': batch}).json()['restored'] == 0
    assert other.get('/api/inventory').json()['rows'] == []


def test_export_import_preserves_provenance_but_disables_automation(client, app, ai):
    configure(client)
    client.scan_csv('people.csv', DATA)
    exported = client.get('/api/workspace/export')
    other = Client(app, 'c'*40)
    response = other.post('/api/workspace/import', files={'file': ('workspace.json', exported.content, 'application/json')})
    assert response.status_code == 200, response.text
    assert other.get('/api/auto-triage').json()['enabled'] is False
    assert len([r for r in rows(other) if r['decision_source'] == 'ai']) == 2
    assert other.get('/api/evaluation').json()['human']['reviewed'] == 0
    assert other.get('/api/audit/verify').json()['ok'] is True


def test_legacy_review_schema_upgrade(tmp_path):
    path = tmp_path/'legacy.sqlite3'
    with sqlite3.connect(path) as c:
        c.execute('CREATE TABLE reviews(id INTEGER PRIMARY KEY AUTOINCREMENT, ws TEXT NOT NULL, column_key TEXT NOT NULL, '
                  'status TEXT NOT NULL, class_override TEXT, note TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL)')
        c.execute("INSERT INTO reviews(ws,column_key,status,note,actor,created_at) VALUES('ws','key','confirmed','','person','now')")
    store = Store(path)
    with store.connect() as c:
        row = c.execute('SELECT * FROM reviews').fetchone()
    assert row['decision_source'] == 'human' and row['automation_batch'] is None


def test_minimum_confidence_controls_eligibility(client, ai):
    rs = client.get('/api/rules').json()['active']
    rs.pop('hash')
    for rule in rs['rules']:
        if rule['id'] == 'email':
            rule['weight'] = .9
    assert client.post('/api/rules', json={'ruleset': rs, 'note': 'Test confidence gate'}).status_code == 200
    configure(client, threshold=.95)
    client.scan_csv('people.csv', DATA)
    email = next(r for r in rows(client) if r['column'] == 'email')
    assert email['confidence'] == .9 and email['status'] == 'candidate'
    configure(client, threshold=.9)
    assert client.post('/api/auto-triage/run').json()['approved'] == 1


def test_rescan_requires_new_ai_approval_and_stale_response_is_skipped(client, ai, monkeypatch):
    configure(client)
    client.scan_csv('people.csv', DATA)
    configure(client, False)
    client.scan_csv('people.csv', DATA)
    assert all(r['status'] == 'candidate' for r in rows(client))
    configure(client)
    original = llm.chat

    def rescan(prompt, **kw):
        # A second scan arrives while the old scan's metadata is with the model.
        configure(client, False)
        client.scan_csv('people.csv', DATA)
        configure(client)
        return original(prompt, **kw)
    monkeypatch.setattr(llm, 'chat', rescan)
    assert client.post('/api/auto-triage/run').json()['approved'] == 0
    assert all(r['status'] == 'candidate' for r in rows(client))
    monkeypatch.setattr(llm, 'chat', original)
    assert client.post('/api/auto-triage/run').json()['approved'] == 2


def test_metadata_never_declared_and_decisions_exported(client, ai):
    import io
    import zipfile
    configure(client)
    client.scan_csv('people.csv', DATA)
    assert all(not r['meta']['legal_basis']['value'] for r in rows(client))
    response = client.post('/api/evidence')
    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as pack:
        inventory = pack.read('inventory.csv').decode()
    assert 'decision_source' in inventory and 'AI auto-triage' in inventory
    assert 'AI auto-approved:' in inventory
