/** Administrator console, Drive navigation and lightweight first-party analytics. */
const SUMMARY_CHART_DEFAULTS = Object.freeze([
  'timeseries',
  'open_priority_pie',
  'resolution_hist'
]);

/** Registra automáticamente la versión servida la primera vez que la abre un admin. */
function _registerAppVersion_(email) {
  const config = _getConfigMap_();
  if (_text_(config.APP_VERSION) === RADAR.appVersion) return;
  _setConfig_(
    'APP_VERSION',
    RADAR.appVersion,
    'string',
    'Versión de código de la WebApp desplegada',
    _canonicalEmail_(email) || RADAR.initialAdmin
  );
}

function registerAppVersion() {
  return _rpc_(function () {
    const user = _requireAdmin_();
    _registerAppVersion_(user.email);
    return { version: RADAR.appVersion };
  });
}

function _configuredSummaryChartIds_() {
  const allowed = new Set([
    'timeseries',
    'age_buckets',
    'open_status_bar',
    'open_priority_pie',
    'resolution_hist'
  ]);
  const configured = _getConfigMap_().SUMMARY_CHART_IDS;
  const values = Array.isArray(configured) ? configured : [];
  const selected = [];
  values.forEach(function (value) {
    const id = _text_(value);
    if (allowed.has(id) && selected.indexOf(id) < 0) selected.push(id);
  });
  SUMMARY_CHART_DEFAULTS.forEach(function (id) {
    if (selected.indexOf(id) < 0) selected.push(id);
  });
  return selected.slice(0, 3);
}

function saveSummaryChartIds(chartIds) {
  return _rpc_(function () {
    const user = _requireAdmin_();
    const values = Array.isArray(chartIds) ? chartIds : [];
    _assert_(values.length === 3, 'Selecciona exactamente tres gráficos.', 'VALIDATION_ERROR');
    const selected = [];
    values.forEach(function (value) {
      const id = _text_(value);
      _assert_([
        'timeseries', 'age_buckets', 'open_status_bar',
        'open_priority_pie', 'resolution_hist'
      ].indexOf(id) >= 0, 'Se ha seleccionado un gráfico no disponible.', 'VALIDATION_ERROR');
      _assert_(selected.indexOf(id) < 0, 'No se pueden repetir gráficos.', 'VALIDATION_ERROR');
      selected.push(id);
    });
    _setConfig_('SUMMARY_CHART_IDS', selected, 'json', 'Tres gráficos visibles en Resumen', user.email);
    _invalidateCaches_();
    return { chartIds: selected, defaults: SUMMARY_CHART_DEFAULTS.slice() };
  });
}

function _latestImportRun_() {
  return _readRecords_(RADAR.sheets.importRuns).filter(function (row) {
    return _text_(row.status) === 'completed';
  }).sort(function (left, right) {
    return (_date_(right.finished_at) || new Date(0)).getTime() -
      (_date_(left.finished_at) || new Date(0)).getTime();
  })[0] || null;
}

function _newsletterSentCountForReport_(reportId) {
  return _readRecords_(RADAR.sheets.newsletterAudit).filter(function (row) {
    return _text_(row.report_id) === _text_(reportId) &&
      _text_(row.mode) === 'send' &&
      _text_(row.status) === 'sent';
  }).reduce(function (count, row) {
    return count + Number(row.recipient_count || 0);
  }, 0);
}

function getAdminConsole(scopeKey) {
  return _rpc_(function () {
    _requireAdmin_();
    const record = _activeSnapshotRecordForScope_(_text_(scopeKey), false);
    const latestImport = _latestImportRun_();
    const folder = _reportDriveFolderSetting_();
    const header = record ? _snapshotHeader_(record) : null;
    const administration = record ? _snapshotAdministration_(record) : { jiraSources: [] };
    const analyticsSheet = _sheet_(RADAR.sheets.analyticsEvents);
    const analyticsEvents = Math.max(0, analyticsSheet.getLastRow() - 1);
    const analyticsUserColumn = _headersFor_(RADAR.sheets.analyticsEvents).indexOf('user_email') + 1;
    const analyticsUsers = analyticsEvents
      ? new Set(analyticsSheet.getRange(2, analyticsUserColumn, analyticsEvents, 1)
        .getDisplayValues().map(function (row) { return _canonicalEmail_(row[0]); }).filter(Boolean)).size
      : 0;
    return {
      health: {
        status: record ? 'Operativa' : 'Sin snapshot',
        appVersion: RADAR.appVersion,
        contractVersion: RADAR.contractVersion,
        lastImportAt: latestImport ? latestImport.finished_at : null,
        importedRecords: record ? Number(record.row_count || 0) : 0,
        newsletterRecipientsSent: record
          ? _newsletterSentCountForReport_(record.report_id)
          : 0,
        snapshotId: record ? _text_(record.snapshot_id) : '',
        dataVersion: record ? _text_(record.data_version) : '',
        projectionBytes: record ? Number(record.projection_bytes || 0) : 0,
        reportSlides: record ? Number(record.slide_count || 0) : 0,
        applicationUrl: _applicationBaseUrl_(),
        versionUrl: record
          ? _applicationBaseUrl_() + '?v=' + encodeURIComponent(_text_(record.data_version))
          : _applicationBaseUrl_(),
        slidesUrl: record ? _text_(record.slides_url) : '',
        generatedAt: header ? header.generatedAt : null,
        accessPolicy: 'Dominio @' + RADAR.allowedDomain,
        analyticsUsers: analyticsUsers,
        analyticsEvents: analyticsEvents
      },
      reportDriveFolder: folder,
      summaryCharts: {
        selected: _configuredSummaryChartIds_(),
        defaults: SUMMARY_CHART_DEFAULTS.slice()
      },
      jiraSources: administration.jiraSources || []
    };
  });
}

function recordAnalyticsEvents(events) {
  return _rpc_(function () {
    const user = _requireUser_();
    const batch = Array.isArray(events) ? events.slice(0, 20) : [];
    if (!batch.length) return { accepted: 0 };
    const rows = batch.map(function (event) {
      const input = event || {};
      return {
        event_id: _uuid_(),
        event_at: _date_(input.eventAt) || _nowIso_(),
        user_email: user.email,
        session_id: _sanitizeText_(input.sessionId, 100),
        event_name: _sanitizeText_(input.eventName, 100),
        route: _sanitizeText_(input.route, 100),
        panel: _sanitizeText_(input.panel, 100),
        scope_key: _sanitizeText_(input.scopeKey, 300),
        duration_ms: Math.max(0, Math.min(600000, Number(input.durationMs || 0))),
        status: _sanitizeText_(input.status, 40),
        details_json: _safeJsonStringify_(_webSafe_(input.details || {})),
        user_agent: _sanitizeText_(input.userAgent, 500)
      };
    }).filter(function (row) {
      return Boolean(row.event_name && row.session_id);
    });
    if (!rows.length) return { accepted: 0 };
    _withApplicationLock_(function () {
      _appendRecords_(RADAR.sheets.analyticsEvents, rows);
      const sheet = _sheet_(RADAR.sheets.analyticsEvents);
      const excess = Math.max(0, sheet.getLastRow() - 50001);
      if (excess) {
        sheet.deleteRows(2, excess);
        _forgetSheet_(RADAR.sheets.analyticsEvents);
      }
    });
    return { accepted: rows.length };
  });
}

function _analyticsPercentile_(values, percentile) {
  if (!values.length) return 0;
  const sorted = values.slice().sort(function (left, right) { return left - right; });
  return sorted[Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * percentile))];
}

function _analyticsCanonicalJson_(value) {
  const normalize = function (item) {
    if (item instanceof Date || Object.prototype.toString.call(item) === '[object Date]') {
      return item.toISOString();
    }
    if (Array.isArray(item)) return item.map(normalize);
    if (item && typeof item === 'object') {
      const out = {};
      Object.keys(item).sort().forEach(function (key) {
        out[key] = normalize(item[key]);
      });
      return out;
    }
    return item;
  };
  return JSON.stringify(normalize(value));
}

function getAnalyticsReport(request) {
  return _rpc_(function () {
    _requireAdmin_();
    const input = request || {};
    _assertExactFields_(input, ['userEmail', 'days', 'captureMode'], 'analyticsReport');
    const days = Math.max(1, Math.min(365, Math.floor(Number(input.days || 30))));
    const userEmail = _canonicalEmail_(input.userEmail);
    const captureMode = _text_(input.captureMode) === 'export' ? 'export' : 'preview';
    const allRows = _readRecords_(RADAR.sheets.analyticsEvents);
    const now = Date.now();
    const generatedAt = new Date(now).toISOString();
    const dayMs = 24 * 60 * 60 * 1000;
    const cutoff = now - days * dayMs;
    const selectedUserRows = allRows.filter(function (row) {
      return !userEmail || _canonicalEmail_(row.user_email) === userEmail;
    });
    let invalidTimestampRows = 0;
    let futureTimestampRows = 0;
    selectedUserRows.forEach(function (row) {
      const stamp = _date_(row.event_at);
      if (!stamp) invalidTimestampRows += 1;
      else if (stamp.getTime() > now) futureTimestampRows += 1;
    });
    const rows = selectedUserRows.filter(function (row) {
      const stamp = _date_(row.event_at);
      return stamp && stamp.getTime() >= cutoff && stamp.getTime() <= now;
    }).sort(function (left, right) {
      return _date_(left.event_at).getTime() - _date_(right.event_at).getTime();
    });
    const currentWeekStart = now - 7 * dayMs;
    const previousWeekStart = now - 14 * dayMs;
    const currentWeekEvents = selectedUserRows.filter(function (row) {
      const stamp = _date_(row.event_at);
      return stamp && stamp.getTime() >= currentWeekStart && stamp.getTime() <= now;
    }).length;
    const previousWeekEvents = selectedUserRows.filter(function (row) {
      const stamp = _date_(row.event_at);
      return stamp && stamp.getTime() >= previousWeekStart &&
        stamp.getTime() < currentWeekStart;
    }).length;
    const weekOverWeekPct = previousWeekEvents
      ? Math.round((currentWeekEvents - previousWeekEvents) / previousWeekEvents * 1000) / 10
      : (currentWeekEvents ? 100 : 0);
    const byEvent = {};
    const byPanel = {};
    const byDay = {};
    const byVersion = {};
    const users = new Set();
    const sessions = new Set();
    const durations = [];
    let errors = 0;
    let unversionedEvents = 0;
    rows.forEach(function (row) {
      const eventName = _text_(row.event_name);
      const details = _safeJsonParse_(row.details_json, {});
      const appVersion = _text_(details && details._telemetry && details._telemetry.appVersion);
      const versionLabel = appVersion || 'legacy-unknown';
      const panel = _text_(row.panel || row.route) || 'sin-sección';
      const day = _dayKey_(row.event_at);
      byEvent[eventName] = Number(byEvent[eventName] || 0) + 1;
      byPanel[panel] = Number(byPanel[panel] || 0) + 1;
      byDay[day] = Number(byDay[day] || 0) + 1;
      byVersion[versionLabel] = Number(byVersion[versionLabel] || 0) + 1;
      if (!appVersion) unversionedEvents += 1;
      users.add(_canonicalEmail_(row.user_email));
      sessions.add(_text_(row.session_id));
      const duration = Number(row.duration_ms || 0);
      if (duration > 0) durations.push(duration);
      if (_text_(row.status) === 'error' || eventName === 'client_error') errors += 1;
    });
    const descendingEntries = function (record) {
      return Object.keys(record).map(function (key) {
        return { label: key, count: Number(record[key] || 0) };
      }).sort(function (left, right) {
        return right.count - left.count || left.label.localeCompare(right.label);
      });
    };
    const detailLimit = captureMode === 'export' ? 2000 : 100;
    const detailRows = rows.slice(-detailLimit).reverse().map(function (row) {
      const details = _safeJsonParse_(row.details_json, {});
      return {
        eventAt: row.event_at,
        userEmail: _canonicalEmail_(row.user_email),
        sessionId: _text_(row.session_id),
        eventName: _text_(row.event_name),
        route: _text_(row.route),
        panel: _text_(row.panel),
        scopeKey: _text_(row.scope_key),
        durationMs: Number(row.duration_ms || 0),
        status: _text_(row.status),
        appVersion: _text_(details && details._telemetry && details._telemetry.appVersion) || 'legacy-unknown',
        details: details
      };
    });
    const report = {
      schemaVersion: '2.2',
      export: {
        captureMode: captureMode,
        generatedAt: generatedAt,
        appVersion: RADAR.appVersion,
        contractVersion: RADAR.contractVersion,
        queryStartAt: new Date(cutoff).toISOString(),
        queryEndAt: generatedAt,
        dataAsOf: rows.length ? _date_(rows[rows.length - 1].event_at).toISOString() : null,
        sourceRowsAvailable: allRows.length,
        matchingRows: rows.length,
        includedRows: detailRows.length,
        detailLimit: detailLimit,
        sourceRetentionLimit: 50000
      },
      filters: { userEmail: userEmail, days: days },
      summary: {
        events: rows.length,
        users: users.size,
        sessions: sessions.size,
        errors: errors,
        currentWeekEvents: currentWeekEvents,
        previousWeekEvents: previousWeekEvents,
        weekOverWeekPct: weekOverWeekPct,
        averageDurationMs: durations.length
          ? Math.round(durations.reduce(function (sum, value) { return sum + value; }, 0) / durations.length)
          : 0,
        p95DurationMs: Math.round(_analyticsPercentile_(durations, 0.95))
      },
      users: Array.from(users).filter(Boolean).sort(),
      events: descendingEntries(byEvent),
      panels: descendingEntries(byPanel),
      versions: descendingEntries(byVersion).map(function (item) {
        return { appVersion: item.label, count: item.count };
      }),
      timeline: Object.keys(byDay).sort().map(function (day) {
        return { day: day, count: byDay[day] };
      }),
      rows: detailRows,
      quality: {
        summaryCompleteForWindow: allRows.length < 50000,
        rowsTruncated: rows.length > detailLimit,
        invalidTimestampRows: invalidTimestampRows,
        futureTimestampRowsExcluded: futureTimestampRows,
        sourceAtRetentionLimit: allRows.length >= 50000,
        unversionedEvents: unversionedEvents
      },
      semantics: {
        summary: 'Calculado con todos los eventos conservados que coinciden con filtros y ventana, aunque rows esté truncado. Consulta quality.summaryCompleteForWindow.',
        rows: 'Detalle de los eventos más recientes, limitado por export.detailLimit y ordenado de más reciente a más antiguo.',
        duration: 'averageDurationMs y p95DurationMs excluyen duraciones iguales a cero.',
        errors: 'status=error o eventName=client_error.',
        weekOverWeek: 'Últimos 7 días móviles frente a los 7 días móviles inmediatamente anteriores; no son semanas naturales.',
        freshness: 'generatedAt identifica la captura del servidor; dataAsOf identifica el evento incluido más reciente.',
        versionAttribution: 'Usa versions y rows[].appVersion para atribuir rendimiento. legacy-unknown puede mezclar código ya eliminado y no debe justificar cambios en la versión actual.',
        exportProtocol: captureMode === 'export'
          ? 'La WebApp vació y confirmó su cola local antes de solicitar esta captura al servidor. La propia RPC de captura y el evento posterior de descarga quedan fuera por definición.'
          : 'Vista previa del servidor; utiliza una descarga con captureMode=export para análisis externo.'
      }
    };
    report.integrity = {
      algorithm: 'SHA-256',
      canonicalization: 'JSON con claves de objeto ordenadas alfabéticamente, sin integrity',
      sha256: _hash_(_analyticsCanonicalJson_(report))
    };
    return report;
  });
}
