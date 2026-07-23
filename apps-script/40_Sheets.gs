/** Contractual persistence adapter. Domain code must never call this module. */
var RADAR_RUNTIME_MEMO = null;
function _runtimeMemo_() {
  if (!RADAR_RUNTIME_MEMO) RADAR_RUNTIME_MEMO = { sheets: {}, contracts: {}, records: {}, values: {} };
  return RADAR_RUNTIME_MEMO;
}
function _resetRuntimeMemo_() { RADAR_RUNTIME_MEMO = { sheets: {}, contracts: {}, records: {}, values: {} }; }
function _forgetSheet_(sheetName) {
  const memo = _runtimeMemo_();
  delete memo.records[sheetName];
  if (sheetName === RADAR.sheets.config) {
    delete memo.values.config;
    delete memo.values.dataVersion;
  }
}
function _spreadsheet_() {
  const memo = _runtimeMemo_();
  if (!memo.values.spreadsheet) memo.values.spreadsheet = SpreadsheetApp.openById(RADAR.spreadsheetId);
  return memo.values.spreadsheet;
}
function _contractFor_(sheetName) {
  const contract = CONTRACTS[sheetName];
  _assert_(contract, 'No existe contrato para la hoja ' + sheetName + '.', 'CONTRACT_ERROR');
  return contract;
}
function _headersFor_(sheetName) { return _contractFor_(sheetName).columns.map(function (c) { return c[0]; }); }
function _sheet_(sheetName) {
  const memo = _runtimeMemo_();
  const sheet = memo.sheets[sheetName] || _spreadsheet_().getSheetByName(sheetName);
  _assert_(sheet, 'Falta la hoja contractual ' + sheetName + '. Ejecuta setupApplication().', 'CONTRACT_ERROR');
  memo.sheets[sheetName] = sheet;
  return sheet;
}
function _validateSheetContract_(sheetName) {
  const memo = _runtimeMemo_();
  if (memo.contracts[sheetName]) return true;
  const sheet = _sheet_(sheetName); const expected = _headersFor_(sheetName);
  const actual = sheet.getLastColumn() ? sheet.getRange(1, 1, 1, sheet.getLastColumn()).getDisplayValues()[0].map(_text_) : [];
  _assert_(actual.length === expected.length && actual.every(function (h, i) { return h === expected[i]; }), 'Cabeceras incompatibles en ' + sheetName + '. Esperado: ' + expected.join(', ') + '.', 'CONTRACT_ERROR');
  memo.contracts[sheetName] = true;
  return true;
}
function _validateAllContracts_() { Object.keys(CONTRACTS).forEach(_validateSheetContract_); return true; }
function _rowToRecord_(headers, row) { const out = {}; headers.forEach(function (h, i) { out[h] = row[i]; }); return out; }
function _readRecords_(sheetName) {
  const memo = _runtimeMemo_();
  if (Object.prototype.hasOwnProperty.call(memo.records, sheetName)) return memo.records[sheetName];
  _validateSheetContract_(sheetName); const sheet = _sheet_(sheetName); const lastRow = sheet.getLastRow();
  if (lastRow < 2) { memo.records[sheetName] = []; return memo.records[sheetName]; }
  const headers = _headersFor_(sheetName); const values = sheet.getRange(2, 1, lastRow - 1, headers.length).getValues();
  memo.records[sheetName] = values.map(function (row) { return _rowToRecord_(headers, row); });
  return memo.records[sheetName];
}
function _recordToRow_(sheetName, record) {
  const contract = _contractFor_(sheetName); const allowed = new Set(contract.columns.map(function (c) { return c[0]; }));
  Object.keys(record || {}).forEach(function (key) { _assert_(allowed.has(key), 'Columna desconocida "' + key + '" para ' + sheetName + '.', 'CONTRACT_ERROR'); });
  return contract.columns.map(function (spec) {
    const name = spec[0]; const type = spec[1]; const required = spec[2]; const allowedValues = spec[3]; let value = record[name];
    if (value == null) value = '';
    if (required) _assert_(value !== '', 'Falta ' + sheetName + '.' + name + '.', 'VALIDATION_ERROR');
    if (value === '') return '';
    if (type === 'string') {
      const longText = ['content_json'].indexOf(name) >= 0;
      value = _sanitizeText_(value, longText ? 45000 : 10000);
      value = _sheetSafeText_(value);
    }
    else if (type === 'email') { value = _canonicalEmail_(value); _assert_(/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value), name + ' no es un email válido.', 'VALIDATION_ERROR'); }
    else if (type === 'url') value = _sanitizeUrl_(value);
    else if (type === 'datetime') { value = _date_(value); _assert_(value, name + ' no es una fecha válida.', 'VALIDATION_ERROR'); }
    else if (type === 'boolean') value = value === true || _fold_(value) === 'true' || String(value) === '1';
    else if (type === 'number') { value = Number(value); _assert_(isFinite(value), name + ' no es numérico.', 'VALIDATION_ERROR'); }
    else if (type === 'json') { const parsed = typeof value === 'string' ? _safeJsonParse_(value, undefined) : value; _assert_(parsed !== undefined, name + ' no contiene JSON válido.', 'VALIDATION_ERROR'); value = _safeJsonStringify_(parsed); _assert_(value.length <= 48000, name + ' supera el tamaño máximo de una celda.', 'TRANSFER_INVALID'); }
    else if (type === 'enum') { value = _text_(value); _assert_(allowedValues.indexOf(value) >= 0, name + ' contiene un valor no permitido.', 'VALIDATION_ERROR'); }
    return value;
  });
}
function _appendRecords_(sheetName, records) {
  if (!records || !records.length) return 0;
  _validateSheetContract_(sheetName); _assertUniqueRecords_(sheetName, records); const sheet = _sheet_(sheetName); const rows = records.map(function (r) { return _recordToRow_(sheetName, r); });
  sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows); _forgetSheet_(sheetName); return rows.length;
}
function _assertUniqueRecords_(sheetName, records) {
  const unique = _contractFor_(sheetName).unique || [];
  if (!unique.length) return true;
  const seen = new Set();
  (records || []).forEach(function (record) {
    const identity = unique.map(function (key) { return _text_(record[key]); }).join('\u001f');
    _assert_(!seen.has(identity), 'Clave duplicada en ' + sheetName + ': ' + identity + '.', 'CONTRACT_ERROR');
    seen.add(identity);
  });
  return true;
}
function _upsertRecord_(sheetName, record) {
  _validateSheetContract_(sheetName); const contract = _contractFor_(sheetName); const key = contract.key; const keyValue = _text_(record[key]);
  _assert_(keyValue, 'Falta la clave de ' + sheetName + '.', 'VALIDATION_ERROR'); const sheet = _sheet_(sheetName); const headers = _headersFor_(sheetName); const keyIndex = headers.indexOf(key);
  const lastRow = sheet.getLastRow(); let target = lastRow + 1;
  if (lastRow > 1) { const values = sheet.getRange(2, keyIndex + 1, lastRow - 1, 1).getDisplayValues(); for (let i = 0; i < values.length; i += 1) if (_text_(values[i][0]) === keyValue) { target = i + 2; break; } }
  sheet.getRange(target, 1, 1, headers.length).setValues([_recordToRow_(sheetName, record)]); _forgetSheet_(sheetName); return record;
}
function _deleteRecord_(sheetName, keyValue) {
  _validateSheetContract_(sheetName); const contract = _contractFor_(sheetName); const headers = _headersFor_(sheetName); const keyIndex = headers.indexOf(contract.key); const sheet = _sheet_(sheetName); const lastRow = sheet.getLastRow();
  if (lastRow < 2) return false; const values = sheet.getRange(2, keyIndex + 1, lastRow - 1, 1).getDisplayValues();
  for (let i = values.length - 1; i >= 0; i -= 1) if (_text_(values[i][0]) === _text_(keyValue)) { sheet.deleteRow(i + 2); _forgetSheet_(sheetName); return true; }
  return false;
}
function _getConfigMap_() {
  const memo = _runtimeMemo_();
  if (memo.values.config) return memo.values.config;
  const out = {}; _readRecords_(RADAR.sheets.config).forEach(function (r) { out[_text_(r.key)] = _safeJsonParse_(r.value, r.value); });
  memo.values.config = out; return out;
}
function _setConfig_(key, value, kind, description, userEmail) {
  const saved = _upsertRecord_(RADAR.sheets.config, { key: _text_(key), value: kind === 'string' ? _text_(value) : _safeJsonStringify_(value), kind: kind || 'string', description: _text_(description), updated_at: _nowIso_(), updated_by: userEmail });
  if (_text_(key) === 'DATA_VERSION') PropertiesService.getScriptProperties().setProperty('RADAR_DATA_VERSION', _text_(value) || 'empty');
  return saved;
}
function _dataVersion_() {
  const memo = _runtimeMemo_();
  if (!memo.values.dataVersion) {
    const properties = PropertiesService.getScriptProperties(); const stored = _text_(properties.getProperty('RADAR_DATA_VERSION'));
    memo.values.dataVersion = stored || _text_(_getConfigMap_().DATA_VERSION) || 'empty';
    if (!stored) properties.setProperty('RADAR_DATA_VERSION', memo.values.dataVersion);
  }
  return memo.values.dataVersion;
}
function _cacheEpoch_() {
  const memo = _runtimeMemo_();
  if (!memo.values.cacheEpoch) memo.values.cacheEpoch = PropertiesService.getScriptProperties().getProperty('RADAR_CACHE_EPOCH') || 'initial';
  return memo.values.cacheEpoch;
}
function _invalidateCaches_() {
  const epoch = _uuid_();
  PropertiesService.getScriptProperties().setProperty('RADAR_CACHE_EPOCH', epoch);
  _resetRuntimeMemo_();
  _runtimeMemo_().values.cacheEpoch = epoch;
  return epoch;
}
