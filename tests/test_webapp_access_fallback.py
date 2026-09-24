"""Executable regressions for the Apps Script WebApp permission boundary."""
import subprocess
from pathlib import Path

from test_apps_script_cloud_contract import _function_body

ROOT = Path(__file__).resolve().parents[1]
APPS = ROOT / 'apps-script'


def run_node(script: str) -> None:
    result = subprocess.run(['node', '-'], input=script, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_identity_fallback_never_grants_administration_and_rejects_outside_domain():
    sources = '\n'.join(p.read_text() for p in sorted(APPS.glob('*.gs')))
    run_node(sources + r"""
const assert = require('node:assert/strict');
let email = '', identityFails = false, rolesFail = false, reads = 0;
let rows = [];
const Session = { getActiveUser: () => {
  if (identityFails) throw Error('permission denied');
  return { getEmail: () => email };
} };
function _readRecords_() { reads++; if (rolesFail) throw Error('denied'); return rows; }
const adminCalls = [
  () => registerAppVersion(), () => saveSummaryChartIds([]),
  () => getAdminConsole('scope'), () => getAnalyticsReport({}),
  () => getNewsletterSettings(), () => revalidateNewsletterSender(),
  () => saveNewsletterRecipient({}), () => sendPeriodNewsletter('report', 'test'),
  () => sendPeriodNewsletter('report', 'send'), () => saveReportDriveFolder('folder'),
  () => getPeriodReportStatus('scope'), () => validateTransferImport({}),
  () => cancelTransferImport('token'), () => commitTransferImport('token'),
  () => listImportRuns()
];
function denied() {
  for (const call of adminCalls) assert.equal(call().error.code, 'FORBIDDEN');
  assert.throws(() => cleanupExpiredTransfers(), { code: 'FORBIDDEN' });
  assert.throws(() => setupApplication(), { code: 'FORBIDDEN' });
}
assert.equal(_requireUser_().role, 'viewer');
assert.equal(reads, 0);
assert.equal(_requireDomainViewer_().role, 'shared');
denied();
identityFails = true;
assert.equal(_requireUser_().email, '');
denied();
identityFails = false; email = 'reader@' + RADAR.allowedDomain;
assert.equal(_requireUser_().role, 'viewer');
denied();
rows = [{ email, active: true, role: 'admin' }];
assert.equal(_requireAdmin_().email, email);
rolesFail = true;
assert.equal(_requireUser_().role, 'viewer');
denied();
rolesFail = false; rows[0].active = false;
assert.equal(_requireUser_().role, 'viewer');
email = 'attacker@outside.invalid';
assert.throws(() => _requireUser_(), { code: 'FORBIDDEN' });
assert.throws(() => _requireDomainViewer_(), { code: 'FORBIDDEN' });
assert.equal(getBootstrap().error.code, 'FORBIDDEN');
""")


def test_bootstrap_survives_missing_identity_roles_storage_and_initial_view():
    sources = '\n'.join((APPS / name).read_text() for name in
                        ['00_Config.gs', '10_Main.gs', '40_Sheets.gs', '99_Core.gs'])
    run_node(sources + r"""
const assert = require('node:assert/strict');
const Session = { getActiveUser: () => ({ getEmail: () => '' }) };
let storageFails = false, viewFails = false;
function _workspaceManifest_() {
  if (storageFails) throw Error('document access denied');
  return { scopes: [{ scopeKey: 'es::*', country: 'España', dataVersion: 'v', sourceIds: [] }], sources: [] };
}
function _dataVersion_() { return 'v'; }
function _cacheEpoch_() { return 'e'; }
function _dashboardPayload_(request) {
  if (viewFails) throw Error('snapshot denied');
  return { view: request.view };
}
let response = getBootstrap();
assert.equal(response.ok, true);
assert.equal(response.data.user.role, 'viewer');
assert.equal(response.data.administration, null);
assert.equal(response.data.dashboard.view, 'overview');
viewFails = true;
response = getBootstrap();
assert.equal(response.ok, true);
assert.equal(response.data.scopes.length, 1);
assert.equal(response.data.dashboard, null);
assert.equal(response.data.dataError.code, 'INTERNAL_ERROR');
viewFails = false;
for (const view of ['overview', 'insights', 'trends', 'issues']) {
  assert.equal(queryDashboard({ scopeKey: 'es::*', view }).data.view, view);
}
assert.equal(queryDashboard({ scopeKey: 'unpublished', view: 'issues' }).error.code, 'FORBIDDEN');
storageFails = true;
response = getBootstrap();
assert.equal(response.ok, true);
assert.deepEqual(response.data.scopes, []);
assert.equal(response.data.dataError.code, 'INTERNAL_ERROR');
""")


def test_stale_dashboard_error_cannot_replace_current_route_and_failure_is_retryable():
    app = (APPS / 'App.html').read_text()
    run_node('async function refreshDashboard(expectedEpoch = state.navigationEpoch) {' +
             _function_body(app, 'refreshDashboard') + r"""}
const assert = require('node:assert/strict');
const state = { scopeKey: 'es::*', route: 'dashboard', navigationEpoch: 1, dashboard: null };
let reject, messages = [], busy = 0, retry;
const fetchDashboard = () => new Promise((resolve, failure) => { reject = failure; });
const requestFor = () => ({});
const setBusy = active => { busy += active ? 1 : -1; };
const renderDataUnavailable = (message, action) => { messages.push(message); retry = action; };
(async () => {
  const first = refreshDashboard();
  state.navigationEpoch++; state.route = 'settings';
  reject(Error('old failure')); await first;
  assert.deepEqual(messages, []); assert.equal(busy, 0);
  state.route = 'dashboard';
  const second = refreshDashboard();
  reject(Error('temporary failure')); await second;
  assert.deepEqual(messages, ['temporary failure']);
  assert.equal(typeof retry, 'function'); assert.equal(busy, 0);
})().catch(error => { console.error(error); process.exitCode = 1; });
""")


def test_owner_scopes_are_explicit_and_do_not_include_unused_trigger_management():
    import json
    manifest = json.loads((APPS / 'appsscript.json').read_text())
    assert manifest['webapp'] == {'access': 'DOMAIN', 'executeAs': 'USER_DEPLOYING'}
    assert set(manifest['oauthScopes']) == {
        'https://www.googleapis.com/auth/' + scope for scope in
        ['spreadsheets', 'userinfo.email', 'presentations', 'drive',
         'gmail.send', 'gmail.settings.basic']
    }


def test_bootstrap_never_relabels_another_scope_and_does_not_wait_for_telemetry():
    app = (APPS / 'App.html').read_text()
    script = 'async function boot() {' + _function_body(app, 'boot') + '}\n'
    for name in ['requestKey']:
        script += f'function {name}(request) {{' + _function_body(app, name) + '}\n'
    run_node(script + r"""
const assert = require('node:assert/strict');
const bootstrap = {
  user: { role: 'admin' }, app: { name: 'Radar', contractVersion: '8', cacheEpoch: 'e', dataVersion: 'v' },
  initialState: { scopeKey: 'es::*', panel: 'overview' },
  scopes: [{ scopeKey: 'es::*', dataVersion: 'es' }, { scopeKey: 'mx::*', dataVersion: 'mx' }],
  dashboard: { country: 'España' }
};
const state = { memory: new Map(), dashboard: null };
const node = { classList: { add() {}, remove() {} } };
const $ = () => node;
const view = () => node;
const document = { body: {}, documentElement: { dataset: {} } };
const window = { setTimeout() {} };
const RPC = { call: async () => bootstrap };
const deadline = promise => promise;
const isShared = () => false;
const isAdmin = () => true;
let savedScope = 'mx::*', refreshed = 0, rendered = 0, unavailable = 0;
const readLocalPreferences = () => ({ scopeKey: savedScope });
const requestFor = () => ({ scopeKey: state.scopeKey, view: state.panel, pageSize: state.pageSize, sortId: 'default' });
const syncScope = () => {};
const syncNavigation = () => {};
const renderCurrent = () => { rendered++; };
const refreshDashboard = async () => { refreshed++; };
const trackEvent = () => {};
const flushAnalytics = () => new Promise(() => {});
const runIdleMaintenance = () => {};
const PersistentCache = { prune: async () => {} };
const renderDataUnavailable = () => { unavailable++; };
const showAccessError = error => { throw error; };
const watchdog = setTimeout(() => { console.error('boot blocked on telemetry'); process.exitCode = 1; }, 500);
(async () => {
  await boot();
  assert.equal(refreshed, 1); assert.equal(rendered, 0);
  assert.equal(state.memory.size, 0);
  savedScope = 'es::*';
  await boot();
  assert.equal(refreshed, 1); assert.equal(rendered, 1);
  bootstrap.dashboard = null; bootstrap.dataError = { code: 'INTERNAL_ERROR' };
  await boot();
  assert.equal(unavailable, 1); assert.equal(refreshed, 1);
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(() => clearTimeout(watchdog));
""")
