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
    const eventRows = _readRecords_(RADAR.sheets.analyticsEvents);
    const uniqueUsers = new Set(eventRows.map(function (row) {
      return _canonicalEmail_(row.user_email);
    }).filter(Boolean));
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
        analyticsUsers: uniqueUsers.size,
        analyticsEvents: eventRows.length
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

function getDrivePickerConfig() {
  return _rpc_(function () {
    _requireAdmin_();
    const properties = PropertiesService.getScriptProperties();
    const developerKey = _text_(properties.getProperty('RADAR_PICKER_API_KEY'));
    const appId = _text_(properties.getProperty('RADAR_PICKER_APP_ID'));
    const configured = /^AIza[A-Za-z0-9_-]{20,}$/.test(developerKey) && /^\d{6,30}$/.test(appId);
    return {
      configured: configured,
      developerKey: configured ? developerKey : '',
      appId: appId,
      oauthToken: configured ? ScriptApp.getOAuthToken() : '',
      message: configured ? '' :
        'Google Drive Picker requiere RADAR_PICKER_API_KEY y RADAR_PICKER_APP_ID en las propiedades del script.'
    };
  });
}

/** Configuración operativa única, administrable desde la propia WebApp. */
function configureDrivePicker(apiKey, cloudProjectNumber) {
  return _rpc_(function () {
    _requireAdmin_();
    const developerKey = _text_(apiKey);
    const appId = _text_(cloudProjectNumber);
    _assert_(/^AIza[A-Za-z0-9_-]{20,}$/.test(developerKey),
      'La API key de Google Picker no es válida.', 'VALIDATION_ERROR');
    _assert_(/^\d{6,30}$/.test(appId),
      'El número del proyecto de Google Cloud no es válido.', 'VALIDATION_ERROR');
    PropertiesService.getScriptProperties().setProperties({
      RADAR_PICKER_API_KEY: developerKey,
      RADAR_PICKER_APP_ID: appId
    });
    return { configured: true, appId: appId };
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

function getAnalyticsReport(request) {
  return _rpc_(function () {
    _requireAdmin_();
    const input = request || {};
    _assertExactFields_(input, ['userEmail', 'days'], 'analyticsReport');
    const days = Math.max(1, Math.min(365, Math.floor(Number(input.days || 30))));
    const userEmail = _canonicalEmail_(input.userEmail);
    const now = Date.now();
    const dayMs = 24 * 60 * 60 * 1000;
    const cutoff = now - days * dayMs;
    const selectedUserRows = _readRecords_(RADAR.sheets.analyticsEvents).filter(function (row) {
      return !userEmail || _canonicalEmail_(row.user_email) === userEmail;
    });
    const rows = selectedUserRows.filter(function (row) {
      const stamp = _date_(row.event_at);
      return stamp && stamp.getTime() >= cutoff;
    });
    const currentWeekStart = now - 7 * dayMs;
    const previousWeekStart = now - 14 * dayMs;
    const currentWeekEvents = selectedUserRows.filter(function (row) {
      const stamp = _date_(row.event_at);
      return stamp && stamp.getTime() >= currentWeekStart;
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
    const users = new Set();
    const sessions = new Set();
    const durations = [];
    let errors = 0;
    rows.forEach(function (row) {
      const eventName = _text_(row.event_name);
      const panel = _text_(row.panel || row.route) || 'sin-sección';
      const day = _dayKey_(row.event_at);
      byEvent[eventName] = Number(byEvent[eventName] || 0) + 1;
      byPanel[panel] = Number(byPanel[panel] || 0) + 1;
      byDay[day] = Number(byDay[day] || 0) + 1;
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
    return {
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
      timeline: Object.keys(byDay).sort().map(function (day) {
        return { day: day, count: byDay[day] };
      }),
      rows: rows.slice(-2000).reverse().map(function (row) {
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
          details: _safeJsonParse_(row.details_json, {})
        };
      })
    };
  });
}
