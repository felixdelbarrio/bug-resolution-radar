/** One-time, idempotent setup. Run manually as spreadsheet owner. */
function setupApplication() {
  _resetRuntimeMemo_();
  const email = _activeEmail_() || RADAR.initialAdmin;
  _assert_(email === RADAR.initialAdmin, 'La inicialización debe ejecutarla el administrador inicial.', 'FORBIDDEN');
  return _withApplicationLock_(function () {
    const ss = _spreadsheet_(); Object.keys(CONTRACTS).forEach(function (name) {
      const headers = _headersFor_(name); let sheet = ss.getSheetByName(name); if (!sheet) sheet = ss.insertSheet(name);
      if (sheet.getMaxColumns() < headers.length) sheet.insertColumnsAfter(sheet.getMaxColumns(), headers.length - sheet.getMaxColumns());
      if (sheet.getLastRow() === 0 || sheet.getLastColumn() === 0) sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
      _validateSheetContract_(name); sheet.setFrozenRows(1); sheet.getRange(1, 1, 1, headers.length).setBackground(DESIGN_TOKENS.color.midnight).setFontColor(DESIGN_TOKENS.color.white).setFontWeight('bold');
    });
    _upsertRecord_(RADAR.sheets.users, { email: RADAR.initialAdmin, role: 'admin', active: true, display_name: 'Félix del Barrio', updated_at: _nowIso_(), updated_by: email });
    _setConfig_('CONTRACT_VERSION', RADAR.contractVersion, 'string', 'Versión estricta de contratos', email);
    const config = _getConfigMap_(); if (!config.DATA_VERSION) _setConfig_('DATA_VERSION', 'empty', 'string', 'Versión de datos activa', email);
    _seedDefaultNewsletterRecipients_();
    Object.keys(RADAR.sheets).forEach(function (key) {
      const sheet = ss.getSheetByName(RADAR.sheets[key]);
      if (sheet && !sheet.isSheetHidden()) sheet.hideSheet();
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
