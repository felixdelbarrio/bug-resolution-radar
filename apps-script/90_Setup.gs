const OBSOLETE_SHEETS = Object.freeze([
  'REPORT_JOBS',
  '_TRANSFER_STAGING',
  'HELIX_ITEMS',
  'INSIGHTS_LEARNING',
  'SOURCES',
  'ISSUES',
  'HELIX_LINKS',
  'NOTES',
  'INGEST_RUNS'
]);

const LEGACY_CONTRACT_HEADERS = Object.freeze({
  REPORT_AUDIT: Object.freeze([
    'report_id', 'report_type', 'filters_json', 'row_count',
    'created_at', 'created_by', 'file_id', 'file_url'
  ]),
  REPORT_SHARES: Object.freeze([
    'share_id', 'token_sha256', 'report_id', 'scope_key', 'scope_label',
    'filters_json', 'data_version', 'active', 'created_at', 'created_by'
  ])
});

const OBSOLETE_CONFIG_KEYS = Object.freeze([
  'DEFAULT_AUTH_MODE',
  'LAST_TRANSFER_METADATA'
]);
const OBSOLETE_SCRIPT_PROPERTIES = Object.freeze([
  'GEMINI_API_KEY',
  'GEMINI_MODEL'
]);

function _sheetHeaders_(sheet) {
  const lastColumn = sheet.getLastColumn();
  return lastColumn
    ? sheet.getRange(1, 1, 1, lastColumn).getDisplayValues()[0].map(_text_)
    : [];
}

function _sameHeaders_(actual, expected) {
  return actual.length === expected.length && actual.every(function (header, index) {
    return header === expected[index];
  });
}

function _resetLegacyContractCollisions_(ss) {
  Object.keys(LEGACY_CONTRACT_HEADERS).forEach(function (sheetName) {
    const sheet = ss.getSheetByName(sheetName);
    if (sheet && _sameHeaders_(_sheetHeaders_(sheet), LEGACY_CONTRACT_HEADERS[sheetName])) {
      ss.deleteSheet(sheet);
    }
  });
}

function _removeObsoleteStorage_(ss) {
  OBSOLETE_SHEETS.forEach(function (sheetName) {
    const sheet = ss.getSheetByName(sheetName);
    if (sheet) ss.deleteSheet(sheet);
  });
  OBSOLETE_CONFIG_KEYS.forEach(function (key) {
    _deleteRecord_(RADAR.sheets.config, key);
  });
  const properties = PropertiesService.getScriptProperties();
  OBSOLETE_SCRIPT_PROPERTIES.forEach(function (key) {
    properties.deleteProperty(key);
  });
  _readRecords_(RADAR.sheets.preferences).filter(function (row) {
    return _text_(row.preference_key) === 'report_drive_folder';
  }).forEach(function (row) {
    _deleteRecord_(RADAR.sheets.preferences, row.pref_uid);
  });
  _readRecords_(RADAR.sheets.newsletterRecipients).filter(function (row) {
    return !_text_(row.report_id) || !_text_(row.snapshot_id);
  }).forEach(function (row) {
    _deleteRecord_(RADAR.sheets.newsletterRecipients, row.recipient_uid);
  });
}

function _migrateSheetHeaders_(sheetName, sheet) {
  const expected = _headersFor_(sheetName);
  if (sheet.getMaxColumns() < expected.length) {
    sheet.insertColumnsAfter(sheet.getMaxColumns(), expected.length - sheet.getMaxColumns());
  }
  const actual = _sheetHeaders_(sheet);
  if (!actual.length) {
    sheet.getRange(1, 1, 1, expected.length).setValues([expected]);
    return;
  }
  if (_sameHeaders_(actual, expected)) return;
  const seen = new Set();
  const canRemap = actual.every(function (header) {
    if (!header || seen.has(header)) return false;
    seen.add(header);
    return true;
  });
  if (!canRemap) return;
  const sourceIndex = {};
  actual.forEach(function (header, index) { sourceIndex[header] = index; });
  const dataRowCount = Math.max(0, sheet.getLastRow() - 1);
  if (dataRowCount) {
    const sourceRange = sheet.getRange(2, 1, dataRowCount, actual.length);
    const values = sourceRange.getValues();
    const formulas = sourceRange.getFormulas();
    const remapped = values.map(function (row, rowIndex) {
      return expected.map(function (header) {
        if (!Object.prototype.hasOwnProperty.call(sourceIndex, header)) return '';
        const columnIndex = sourceIndex[header];
        return formulas[rowIndex][columnIndex] || row[columnIndex];
      });
    });
    sheet.getRange(2, 1, dataRowCount, expected.length).setValues(remapped);
  }
  sheet.getRange(1, 1, 1, expected.length).setValues([expected]);
}

/** Idempotent setup and compatible contract migration. Run manually as spreadsheet owner. */
function setupApplication() {
  _resetRuntimeMemo_();
  const email = _activeEmail_() || RADAR.initialAdmin;
  _assert_(email === RADAR.initialAdmin, 'La inicialización debe ejecutarla el administrador inicial.', 'FORBIDDEN');
  return _withApplicationLock_(function () {
    const ss = _spreadsheet_();
    _resetLegacyContractCollisions_(ss);
    Object.keys(CONTRACTS).forEach(function (name) {
      const headers = _headersFor_(name); let sheet = ss.getSheetByName(name); if (!sheet) sheet = ss.insertSheet(name);
      _migrateSheetHeaders_(name, sheet);
      _validateSheetContract_(name); sheet.setFrozenRows(1); sheet.getRange(1, 1, 1, headers.length).setBackground(DESIGN_TOKENS.color.midnight).setFontColor(DESIGN_TOKENS.color.white).setFontWeight('bold');
    });
    _upsertRecord_(RADAR.sheets.users, { email: RADAR.initialAdmin, role: 'admin', active: true, display_name: 'Félix del Barrio', updated_at: _nowIso_(), updated_by: email });
    _setConfig_('APP_VERSION', RADAR.appVersion, 'string', 'Versión de código de la WebApp desplegada', email);
    _setConfig_('CONTRACT_VERSION', RADAR.contractVersion, 'string', 'Versión estricta de contratos', email);
    const config = _getConfigMap_();
    if (!config.SUMMARY_CHART_IDS) {
      _setConfig_('SUMMARY_CHART_IDS', ['timeseries', 'open_priority_pie', 'resolution_hist'], 'json', 'Tres gráficos visibles en Resumen', email);
    }
    if (!config.DATA_VERSION) _setConfig_('DATA_VERSION', 'empty', 'string', 'Versión de datos activa', email);
    _removeObsoleteStorage_(ss);
    const controlSheet = ss.getSheetByName(RADAR.sheets.config);
    if (controlSheet && controlSheet.isSheetHidden()) controlSheet.showSheet();
    Object.keys(RADAR.sheets).forEach(function (key) {
      const sheet = ss.getSheetByName(RADAR.sheets[key]);
      if (sheet && sheet.getName() !== RADAR.sheets.config && !sheet.isSheetHidden()) sheet.hideSheet();
    });
    _invalidateCaches_();
    return { ok: true, spreadsheetId: ss.getId(), contractVersion: RADAR.contractVersion, admin: RADAR.initialAdmin };
  });
}
function _cleanupExpiredTransfers_() {
  return _withApplicationLock_(function () {
    const props = PropertiesService.getScriptProperties(); const all = props.getProperties(); const runIds = new Set(); let removed = 0;
    Object.keys(all).filter(function (key) { return key.indexOf('transfer:') === 0; }).forEach(function (key) {
      const meta = _safeJsonParse_(all[key], null);
      const createdAt = meta ? Number(meta.createdAt) : NaN;
      if (!meta || !isFinite(createdAt) || Date.now() - createdAt > RADAR.transferTtlSeconds * 1000) {
        if (meta && meta.runId) runIds.add(_text_(meta.runId));
        _discardTransfer_(key.slice('transfer:'.length), meta); removed += 1;
      }
    });
    if (runIds.size) {
      _readRecords_(RADAR.sheets.importRuns).forEach(function (run) {
        if (runIds.has(_text_(run.run_id)) && _text_(run.status) === 'validated') {
          _upsertRecord_(RADAR.sheets.importRuns, Object.assign({}, run, { status: 'cancelled', finished_at: _nowIso_(), details: 'Importación caducada y eliminada sin modificar datos.' }));
        }
      });
    }
    return removed;
  });
}
function cleanupExpiredTransfers() { _resetRuntimeMemo_(); _requireAdmin_(); return _cleanupExpiredTransfers_(); }
