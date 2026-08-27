/** Shared utilities. Functions ending in _ are intentionally private RPC-wise. */
function _nowIso_() { return new Date().toISOString(); }
function _text_(value) { return value == null ? '' : String(value).trim(); }
function _uuid_() { return Utilities.getUuid(); }
function _canonicalEmail_(value) { return _text_(value).toLowerCase(); }
function _fold_(value) {
  return _text_(value).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}
function _compact_(value) { return _fold_(value).replace(/[^a-z0-9]+/g, ''); }
function _date_(value) {
  if (value instanceof Date && !isNaN(value.getTime())) return value;
  if (!_text_(value)) return null;
  const d = new Date(value);
  return isNaN(d.getTime()) ? null : d;
}
function _dayKey_(value) {
  const d = _date_(value);
  return d ? Utilities.formatDate(d, 'UTC', 'yyyy-MM-dd') : '';
}
function _safeJsonParse_(value, fallback) {
  if (value == null || value === '') return fallback;
  if (typeof value !== 'string') return value;
  try { return JSON.parse(value); } catch (err) { return fallback; }
}
function _safeJsonStringify_(value) {
  return JSON.stringify(value == null ? null : value).replace(/[\u2028\u2029]/g, '');
}
function _assert_(condition, message, code) {
  if (!condition) {
    const error = new Error(message || 'Operación no válida.');
    error.code = code || 'VALIDATION_ERROR';
    throw error;
  }
}
function _sanitizeText_(value, maxLength) {
  const clean = _text_(value).replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '');
  return clean.slice(0, Math.max(0, Number(maxLength || 5000)));
}
function _sheetSafeText_(value) {
  const text = _text_(value);
  return /^[=+@-]/.test(text) ? "'" + text : text;
}
function _sanitizeUrl_(value) {
  const raw = _text_(value);
  if (!raw) return '';
  _assert_(/^https:\/\//i.test(raw), 'Solo se permiten URLs HTTPS.', 'INVALID_URL');
  _assert_(!/[\r\n]/.test(raw), 'URL no válida.', 'INVALID_URL');
  _assert_(!/^https:\/\/[^/?#]*@/i.test(raw), 'La URL no puede contener credenciales.', 'SECRET_FIELD_REJECTED');
  _assert_(!/[?&#](access_token|refresh_token|api_key|apikey|token|authorization|password|passwd|secret)=/i.test(raw), 'La URL contiene un parámetro sensible no permitido.', 'SECRET_FIELD_REJECTED');
  return raw.slice(0, 2048);
}
function _sanitizeKey_(value) {
  const key = _text_(value).toUpperCase();
  _assert_(/^[A-Z0-9][A-Z0-9._:-]{0,127}$/.test(key), 'Identificador no válido.', 'INVALID_KEY');
  return key;
}
function _sanitizeSourceId_(value) {
  const sourceId = _text_(value).toLowerCase();
  _assert_(/^[a-z0-9][a-z0-9._:-]{0,127}$/.test(sourceId), 'source_id no válido.', 'INVALID_KEY');
  return sourceId;
}
function _validateNoSecrets_(record) {
  const forbidden = /(^|_)(cookie|secret|password|passwd|authorization|access_token|refresh_token|api_key)($|_)/i;
  Object.keys(record || {}).forEach(function (key) {
    _assert_(!forbidden.test(key), 'El payload contiene un campo secreto no permitido.', 'SECRET_FIELD_REJECTED');
  });
}
function _hash_(value) {
  const bytes = Utilities.computeDigest(Utilities.DigestAlgorithm.SHA_256, String(value), Utilities.Charset.UTF_8);
  return bytes.map(function (b) { const n = (b + 256) % 256; return ('0' + n.toString(16)).slice(-2); }).join('');
}
function _cacheKey_(prefix, payload) {
  return ['radar', RADAR.contractVersion, prefix, _hash_(_safeJsonStringify_(payload)).slice(0, 24)].join(':');
}
function _cacheGetJson_(cache, key) {
  const manifest = _safeJsonParse_(cache.get(key + ':manifest'), null);
  if (!manifest || !manifest.parts || manifest.parts > 40) return null;
  const keys = []; for (let i = 0; i < manifest.parts; i += 1) keys.push(key + ':part:' + i);
  const values = cache.getAll(keys); let encoded = '';
  for (let i = 0; i < keys.length; i += 1) {
    if (!Object.prototype.hasOwnProperty.call(values, keys[i])) return null;
    encoded += values[keys[i]];
  }
  return _safeJsonParse_(encoded, null);
}
function _cachePutJson_(cache, key, value, ttlSeconds) {
  const encoded = _safeJsonStringify_(_webSafe_(value)); const chunkSize = 20000; const entries = {};
  const parts = Math.max(1, Math.ceil(encoded.length / chunkSize));
  if (parts > 40) return false;
  entries[key + ':manifest'] = _safeJsonStringify_({ parts: parts });
  for (let i = 0; i < parts; i += 1) entries[key + ':part:' + i] = encoded.slice(i * chunkSize, (i + 1) * chunkSize);
  cache.putAll(entries, ttlSeconds); return true;
}
function _cacheDeleteJson_(cache, key) {
  const manifest = _safeJsonParse_(cache.get(key + ':manifest'), null);
  const keys = [key + ':manifest'];
  const parts = manifest && Number(manifest.parts) > 0 ? Math.min(40, Number(manifest.parts)) : 0;
  for (let i = 0; i < parts; i += 1) keys.push(key + ':part:' + i);
  cache.removeAll(keys);
}
function _withApplicationLock_(callback) {
  const lock = LockService.getScriptLock();
  _assert_(lock.tryLock(20000), 'Hay otra actualización en curso. Reinténtalo en unos segundos.', 'LOCK_TIMEOUT');
  try { return callback(); } finally { lock.releaseLock(); }
}
function _publicError_(err) {
  const code = _text_(err && err.code) || 'INTERNAL_ERROR';
  const safeCodes = ['AUTH_REQUIRED', 'FORBIDDEN', 'CONTRACT_ERROR', 'VALIDATION_ERROR', 'INVALID_URL', 'INVALID_KEY', 'NOT_FOUND', 'LOCK_TIMEOUT', 'UPLOAD_EXPIRED', 'SECRET_FIELD_REJECTED', 'TRANSFER_INVALID', 'TRANSFER_TOO_LARGE', 'TRANSFER_STAGING_FAILED', 'DRIVE_FOLDER_INVALID', 'REPORT_GENERATION_FAILED', 'APP_URL_INVALID', 'SHARE_INVALID', 'SNAPSHOT_NOT_FOUND', 'SNAPSHOT_CORRUPT', 'VIEW_NOT_MATERIALIZED', 'READ_ONLY_SNAPSHOT', 'NEWSLETTER_VALIDATION_FAILED', 'NEWSLETTER_STALE', 'NEWSLETTER_NO_RECIPIENTS', 'NEWSLETTER_SEND_FAILED', 'NEWSLETTER_IN_PROGRESS', 'NEWSLETTER_ALREADY_SENT', 'NEWSLETTER_TEST_REQUIRED', 'NEWSLETTER_SENDER_UNAVAILABLE'];
  return { ok: false, error: { code: safeCodes.indexOf(code) >= 0 ? code : 'INTERNAL_ERROR', message: safeCodes.indexOf(code) >= 0 ? _text_(err.message) : 'No se pudo completar la operación.' } };
}
function _webSafe_(value) {
  if (value instanceof Date || Object.prototype.toString.call(value) === '[object Date]') return value.toISOString();
  if (Array.isArray(value)) return value.map(_webSafe_);
  if (value && typeof value === 'object') {
    const out = {};
    Object.keys(value).forEach(function (key) { out[key] = _webSafe_(value[key]); });
    return out;
  }
  return value;
}
function _rpc_(callback) {
  try {
    _resetRuntimeMemo_();
    return { ok: true, data: _webSafe_(callback()) };
  } catch (err) {
    console.error('radar_error', { code: err && err.code, message: err && err.message });
    return _publicError_(err);
  }
}
