/** Gemini selects only immutable desktop-authored facts; Gmail attaches the exact PPTX. */
function _newsletterReports_() {
  return _workspaceManifest_().scopes.map(function (scope) {
    const record = _snapshotRecordById_(scope.snapshotId, false);
    if (!record || !_text_(record.report_id)) return null;
    return {
      reportId: _text_(record.report_id),
      snapshotId: _text_(record.snapshot_id),
      scopeKey: _text_(scope.scopeKey),
      label: _text_(scope.scopeLabel),
      country: _text_(scope.country),
      sourceIds: (scope.sourceIds || []).map(_text_),
      dataVersion: _text_(scope.dataVersion),
      reportUrl: _text_(record.slides_url),
      createdAt: record.created_at
    };
  }).filter(Boolean);
}

function _newsletterSenderReady_() {
  const cache = CacheService.getUserCache();
  const cacheKey = 'newsletter-sender:' + _canonicalEmail_(RADAR.newsletterFrom);
  const cached = cache.get(cacheKey);
  if (cached === '1' || cached === '0') return cached === '1';
  try {
    const ready = GmailApp.getAliases().map(_canonicalEmail_)
      .indexOf(_canonicalEmail_(RADAR.newsletterFrom)) >= 0;
    cache.put(cacheKey, ready ? '1' : '0', 60);
    return ready;
  } catch (err) {
    return false;
  }
}

function _newsletterGeminiConfiguration_() {
  const properties = PropertiesService.getScriptProperties();
  return {
    configured: Boolean(_text_(properties.getProperty('GEMINI_API_KEY'))),
    model: _text_(properties.getProperty('GEMINI_MODEL')) || RADAR.geminiModel
  };
}

function _newsletterUsers_() {
  return _readRecords_(RADAR.sheets.users).filter(function (row) {
    return row.active === true;
  }).map(function (row) {
    return {
      email: _canonicalEmail_(row.email),
      displayName: _text_(row.display_name),
      role: _text_(row.role)
    };
  }).filter(function (user) {
    return Boolean(user.email);
  }).sort(function (left, right) {
    return left.displayName.localeCompare(right.displayName, 'es', { sensitivity: 'base' }) ||
      left.email.localeCompare(right.email);
  });
}

function _newsletterSettingsPayload_() {
  const reports = _newsletterReports_();
  const activeReportIds = new Set(reports.map(function (report) { return report.reportId; }));
  const recipients = _readRecords_(RADAR.sheets.newsletterRecipients).filter(function (row) {
    return activeReportIds.has(_text_(row.report_id));
  }).map(function (row) {
    return {
      recipientUid: _text_(row.recipient_uid),
      reportId: _text_(row.report_id),
      snapshotId: _text_(row.snapshot_id),
      scopeKey: _text_(row.scope_key),
      scopeLabel: _text_(row.scope_label),
      email: _canonicalEmail_(row.email),
      displayName: _text_(row.display_name),
      active: row.active === true,
      updatedAt: row.updated_at
    };
  }).sort(function (left, right) {
    return left.scopeLabel.localeCompare(right.scopeLabel, 'es', { sensitivity: 'base' }) ||
      left.displayName.localeCompare(right.displayName, 'es', { sensitivity: 'base' }) ||
      left.email.localeCompare(right.email);
  });
  const gemini = _newsletterGeminiConfiguration_();
  return {
    sender: RADAR.newsletterFrom,
    senderReady: _newsletterSenderReady_(),
    geminiConfigured: gemini.configured,
    geminiModel: gemini.model,
    reports: reports,
    users: _newsletterUsers_(),
    recipients: recipients
  };
}

function getNewsletterSettings() {
  return _rpc_(function () {
    _requireAdmin_();
    return _newsletterSettingsPayload_();
  });
}

function saveNewsletterRecipient(payload) {
  return _rpc_(function () {
    const user = _requireAdmin_();
    const input = payload || {};
    const reportId = _sanitizeText_(input.reportId, 100);
    const report = _newsletterReports_().find(function (item) {
      return item.reportId === reportId;
    });
    _assert_(report, 'El informe seleccionado no existe o ya no está activo.', 'SNAPSHOT_NOT_FOUND');
    const email = _canonicalEmail_(input.email);
    const recipientUser = _newsletterUsers_().find(function (candidate) {
      return candidate.email === email;
    });
    _assert_(recipientUser,
      'El destinatario debe ser un usuario activo y autorizado de la aplicación.',
      'VALIDATION_ERROR');
    const uid = _hash_(reportId + '\u001f' + email).slice(0, 32);
    _withApplicationLock_(function () {
      const current = _readRecords_(RADAR.sheets.newsletterRecipients).find(function (row) {
        return _text_(row.recipient_uid) === uid;
      });
      const now = _nowIso_();
      _upsertRecord_(RADAR.sheets.newsletterRecipients, {
        recipient_uid: uid,
        report_id: report.reportId,
        snapshot_id: report.snapshotId,
        scope_key: report.scopeKey,
        scope_label: report.label,
        email: email,
        display_name: recipientUser.displayName,
        active: input.active !== false,
        created_at: current ? current.created_at : now,
        created_by: current ? current.created_by : user.email,
        updated_at: now,
        updated_by: user.email
      });
    });
    return _newsletterSettingsPayload_();
  });
}

function _newsletterContext_(reportId) {
  const id = _text_(reportId);
  const report = _readRecords_(RADAR.sheets.reportAudit).find(function (row) {
    return _text_(row.report_id) === id && _text_(row.report_type) === 'period';
  });
  _assert_(report, 'No existe la presentación de seguimiento.', 'NOT_FOUND');
  const record = _snapshotRecordById_(report.snapshot_id, true);
  _assert_(
    _text_(record.report_id) === id &&
    _text_(record.scope_key) === _text_(report.scope_key) &&
    _text_(record.projection_sha256) === _text_(report.projection_sha256) &&
    _text_(record.facts_sha256) === _text_(report.facts_sha256) &&
    _text_(record.pptx_file_id) === _text_(report.pptx_file_id) &&
    _text_(record.pptx_sha256) === _text_(report.pptx_sha256) &&
    _text_(record.slides_file_id) === _text_(report.slides_file_id),
    'La auditoría del informe no coincide con su snapshot.', 'NEWSLETTER_VALIDATION_FAILED'
  );
  const active = _activeSnapshotRecordForScope_(record.scope_key, true);
  _assert_(_text_(active.snapshot_id) === _text_(record.snapshot_id),
    'Este informe ya no es el snapshot activo. Usa el seguimiento de la última recarga.',
    'NEWSLETTER_STALE');
  const header = _snapshotHeader_(record);
  const newsletterFacts = _snapshotNewsletter_(record);
  _assert_(
    _hash_(_stableJsonStringify_(newsletterFacts)) === _text_(report.facts_sha256),
    'Los hechos inmutables no coinciden con la auditoría del informe.',
    'NEWSLETTER_VALIDATION_FAILED'
  );
  return {
    report: report,
    record: record,
    header: header,
    newsletterFacts: newsletterFacts,
    grounding: {
      scopeKey: header.scope.scopeKey,
      scopeLabel: header.scope.scopeLabel,
      country: header.scope.country,
      sourceIds: header.scope.sourceIds,
      dataVersion: header.scope.dataVersion,
      referenceDate: header.scope.referenceDate,
      periodLabel: newsletterFacts.periodLabel,
      metrics: newsletterFacts.metrics,
      facts: newsletterFacts.facts,
      factsSha256: record.facts_sha256
    }
  };
}

function _newsletterDraftSchema_() {
  const evidence = { type: 'array', items: { type: 'string' } };
  return {
    type: 'object',
    required: ['summary_evidence_ids', 'sections'],
    properties: {
      summary_evidence_ids: evidence,
      sections: {
        type: 'array',
        items: {
          type: 'object',
          required: ['evidence_ids'],
          properties: { evidence_ids: evidence }
        }
      }
    }
  };
}

function _newsletterGeminiPrompt_(grounding) {
  return [
    'Selecciona la estructura de una newsletter ejecutiva en español.',
    'Usa exclusivamente los identificadores de los hechos suministrados.',
    'No redactes, completes, interpretes ni calcules ningún dato.',
    'Selecciona de uno a tres hechos para el resumen y de cero a cuatro secciones con uno a tres hechos cada una.',
    'No repitas identificadores. Prioriza cambios de backlog, criticidad, antigüedad y acciones explícitas si existen.',
    _safeJsonStringify_({
      periodLabel: grounding.periodLabel,
      metrics: grounding.metrics,
      facts: grounding.facts
    })
  ].join('\n\n');
}

function _newsletterGenerateDraft_(grounding) {
  const configuration = _newsletterGeminiConfiguration_();
  _assert_(configuration.configured,
    'Configura GEMINI_API_KEY en las propiedades del script antes de generar newsletters.',
    'GEMINI_NOT_CONFIGURED');
  const apiKey = _text_(
    PropertiesService.getScriptProperties().getProperty('GEMINI_API_KEY')
  );
  const endpoint = 'https://generativelanguage.googleapis.com/v1beta/models/' +
    encodeURIComponent(configuration.model) + ':generateContent';
  const response = UrlFetchApp.fetch(endpoint, {
    method: 'post',
    contentType: 'application/json',
    headers: { 'x-goog-api-key': apiKey },
    payload: _safeJsonStringify_({
      systemInstruction: {
        parts: [{
          text: 'Eres el editor ejecutivo del Bug Resolution Radar. Solo seleccionas evidencias canónicas.'
        }]
      },
      contents: [{
        role: 'user',
        parts: [{ text: _newsletterGeminiPrompt_(grounding) }]
      }],
      generationConfig: {
        responseMimeType: 'application/json',
        responseSchema: _newsletterDraftSchema_(),
        maxOutputTokens: 2048
      }
    }),
    muteHttpExceptions: true
  });
  const status = response.getResponseCode();
  if (status < 200 || status >= 300) {
    console.error('gemini_newsletter_failed', {
      status: status,
      model: configuration.model
    });
    const error = new Error(
      'Gemini no ha podido seleccionar el resumen. Revisa la clave, el modelo y la cuota.'
    );
    error.code = 'GEMINI_GENERATION_FAILED';
    throw error;
  }
  const payload = _safeJsonParse_(response.getContentText(), null);
  const parts = payload && payload.candidates && payload.candidates[0] &&
    payload.candidates[0].content && payload.candidates[0].content.parts;
  const text = Array.isArray(parts)
    ? parts.map(function (part) { return _text_(part.text); }).join('')
    : '';
  const draft = _safeJsonParse_(text, null);
  _assert_(draft,
    'Gemini devolvió una respuesta que no cumple el contrato de newsletter.',
    'GEMINI_GENERATION_FAILED');
  return { draft: draft, model: configuration.model };
}

function _newsletterSectionTitle_(evidenceIds) {
  const joined = evidenceIds.join(' ').toLowerCase();
  if (/owner|person|assignee|respons/.test(joined)) return 'Foco por responsables';
  if (/function|area|domain/.test(joined)) return 'Concentración funcional';
  if (/risk|priority|high|aged|age/.test(joined)) return 'Riesgos a vigilar';
  if (/flow|created|closed/.test(joined)) return 'Flujo del periodo';
  return 'Seguimiento ejecutivo';
}

function _newsletterValidateDraft_(draft, grounding) {
  const factById = {};
  grounding.facts.forEach(function (fact) {
    factById[_text_(fact.id)] = fact;
  });
  const used = new Set();
  function evidence(raw, minimum, maximum) {
    const ids = Array.from(new Set(
      (Array.isArray(raw) ? raw : []).map(_text_).filter(Boolean)
    ));
    _assert_(ids.length >= minimum && ids.length <= maximum,
      'Gemini ha generado un bloque con un número de evidencias no válido.',
      'NEWSLETTER_VALIDATION_FAILED');
    ids.forEach(function (id) {
      _assert_(factById[id],
        'Gemini ha citado una evidencia inexistente.', 'NEWSLETTER_VALIDATION_FAILED');
      _assert_(!used.has(id),
        'Gemini ha repetido una evidencia.', 'NEWSLETTER_VALIDATION_FAILED');
      used.add(id);
    });
    return ids;
  }
  const summaryIds = evidence(draft && draft.summary_evidence_ids, 1, 3);
  const rawSections = Array.isArray(draft && draft.sections) ? draft.sections : [];
  _assert_(rawSections.length <= 4,
    'Gemini ha generado demasiadas secciones.', 'NEWSLETTER_VALIDATION_FAILED');
  const sections = rawSections.map(function (section) {
    const ids = evidence(section && section.evidence_ids, 1, 3);
    return {
      title: _newsletterSectionTitle_(ids),
      text: ids.map(function (id) { return factById[id].statement; }).join(' '),
      evidenceIds: ids
    };
  });
  return {
    preheader: grounding.periodLabel + ' · ' + grounding.scopeLabel,
    summary: {
      text: summaryIds.map(function (id) { return factById[id].statement; }).join(' '),
      evidenceIds: summaryIds
    },
    sections: sections
  };
}

function _newsletterCountryCode_(country) {
  const codes = {
    mexico: 'MX', argentina: 'AR', colombia: 'CO', peru: 'PE',
    uruguay: 'UY', chile: 'CL', espana: 'ES'
  };
  return codes[_fold_(country)] ||
    (_fold_(country).replace(/[^a-z]/g, '').slice(0, 2).toUpperCase() || 'BR');
}

function _newsletterSubject_(grounding) {
  const stamp = _text_(grounding.referenceDate).replace(/-/g, '');
  return '[' + _newsletterCountryCode_(grounding.country) + '][' + stamp +
    '] Seguimiento de incidencias · ' + grounding.scopeLabel;
}

function _newsletterEscapeHtml_(value) {
  return _text_(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function _newsletterSignedDelta_(value) {
  const number = Number(value || 0);
  return number > 0 ? '+' + number : String(number);
}

function _newsletterRender_(draft, grounding, reportUrl, applicationUrl) {
  const colors = DESIGN_TOKENS.color;
  const radius = DESIGN_TOKENS.radius;
  const slidesUrl = _newsletterEscapeHtml_(_sanitizeUrl_(reportUrl));
  const appUrl = _newsletterEscapeHtml_(_sanitizeUrl_(applicationUrl));
  const metrics = grounding.metrics;
  const sections = draft.sections.map(function (section) {
    return '<tr><td style="padding:0 32px 18px">' +
      '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" ' +
      'style="border-collapse:collapse;background:' + colors.grey200 +
      ';border-left:4px solid ' + colors.royal + ';border-radius:' + radius.component + '">' +
      '<tr><td style="padding:18px 22px"><h2 style="margin:0 0 7px;color:' +
      colors.midnight + ';font:700 19px/25px Arial,sans-serif">' +
      _newsletterEscapeHtml_(section.title) + '</h2><p style="margin:0;color:' +
      colors.grey700 + ';font:400 15px/23px Arial,sans-serif">' +
      _newsletterEscapeHtml_(section.text) + '</p></td></tr></table></td></tr>';
  }).join('');
  const html = '<!doctype html><html><body style="margin:0;padding:0;background:' +
    colors.grey200 + '"><div style="display:none;max-height:0;overflow:hidden">' +
    _newsletterEscapeHtml_(draft.preheader) + '</div>' +
    '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" ' +
    'style="border-collapse:collapse;background:' + colors.grey200 +
    '"><tr><td align="center" style="padding:24px 12px"><table role="presentation" ' +
    'width="640" cellpadding="0" cellspacing="0" style="width:100%;max-width:640px;' +
    'border-collapse:separate;background:' + colors.white +
    ';border-radius:' + radius.container + ';overflow:hidden;box-shadow:' +
    DESIGN_TOKENS.effect.emailShadow + '">' +
    '<tr><td style="padding:28px 32px;background:' + colors.electric +
    ';border-bottom:8px solid ' + colors.serene + '"><table role="presentation" ' +
    'width="100%"><tr><td style="color:' + colors.white +
    ';font:700 26px/30px Arial,sans-serif">BBVA</td><td align="right" style="color:' +
    colors.blueLight + ';font:700 11px/16px Arial,sans-serif;letter-spacing:1.2px">' +
    'BUG RESOLUTION RADAR</td></tr></table><p style="margin:34px 0 6px;color:' +
    colors.serene + ';font:700 12px/16px Arial,sans-serif">' +
    _newsletterEscapeHtml_(grounding.scopeLabel) + '</p><h1 style="margin:0;color:' +
    colors.white + ';font:700 34px/40px Georgia,serif">' +
    _newsletterEscapeHtml_(grounding.periodLabel) + '</h1></td></tr>' +
    '<tr><td style="padding:28px 32px 20px"><p style="margin:0;color:' +
    colors.midnight + ';font:700 18px/27px Arial,sans-serif">' +
    _newsletterEscapeHtml_(draft.summary.text) + '</p></td></tr>' +
    '<tr><td style="padding:0 32px 24px"><table role="presentation" width="100%" ' +
    'cellpadding="0" cellspacing="8" style="table-layout:fixed"><tr>' +
    '<td style="padding:15px;background:' + colors.blueLight +
    ';border-radius:' + radius.component + '"><span style="display:block;color:' + colors.grey600 +
    ';font:700 10px/14px Arial,sans-serif">BACKLOG</span><strong style="color:' +
    colors.electric + ';font:700 28px/34px Arial,sans-serif">' +
    metrics.currentOpen + '</strong></td><td style="padding:15px;background:' +
    (metrics.backlogDelta > 0 ? colors.dangerSoft : colors.successSoft) +
    ';border-radius:' + radius.component + '"><span style="display:block;color:' + colors.grey600 +
    ';font:700 10px/14px Arial,sans-serif">VARIACIÓN</span><strong style="color:' +
    (metrics.backlogDelta > 0 ? colors.danger : colors.success) +
    ';font:700 28px/34px Arial,sans-serif">' +
    _newsletterSignedDelta_(metrics.backlogDelta) + '</strong></td></tr><tr>' +
    '<td style="padding:15px;background:' + colors.warningSoft +
    ';border-radius:' + radius.component + '"><span style="display:block;color:' + colors.grey600 +
    ';font:700 10px/14px Arial,sans-serif">ALTA / MUY ALTA</span><strong style="color:' +
    colors.warningStrong + ';font:700 28px/34px Arial,sans-serif">' +
    metrics.highOpen + '</strong></td><td style="padding:15px;background:' +
    colors.grey200 + ';border-radius:' + radius.component + '"><span style="display:block;color:' +
    colors.grey600 + ';font:700 10px/14px Arial,sans-serif">&gt; 30 DÍAS</span>' +
    '<strong style="color:' + colors.midnight +
    ';font:700 28px/34px Arial,sans-serif">' + metrics.agedOpen +
    '</strong></td></tr></table></td></tr>' + sections +
    '<tr><td style="padding:6px 32px 32px"><table role="presentation" width="100%" ' +
    'cellpadding="0" cellspacing="0"><tr><td style="padding-bottom:10px"><a href="' +
    appUrl + '" style="display:block;padding:14px 20px;border-radius:' + radius.component + ';background:' +
    colors.electric + ';color:' + colors.white +
    ';font:700 15px/21px Arial,sans-serif;text-align:center;text-decoration:none">' +
    'Abrir vista web de solo lectura</a></td></tr><tr><td><a href="' + slidesUrl +
    '" style="display:block;padding:12px 20px;border:1px solid ' + colors.electric +
    ';border-radius:' + radius.component + ';color:' + colors.electric +
    ';font:700 14px/20px Arial,sans-serif;text-align:center;text-decoration:none">' +
    'Abrir el mismo informe en Google Slides</a></td></tr></table>' +
    '<p style="margin:12px 0 0;color:' + colors.grey600 +
    ';font:400 11px/17px Arial,sans-serif">Se adjunta el PPTX original generado por escritorio.</p>' +
    '</td></tr><tr><td style="padding:20px 32px;background:' + colors.midnight +
    '"><p style="margin:0;color:' + colors.white +
    ';font:700 13px/18px Arial,sans-serif">BBVA · Bug Resolution Radar</p>' +
    '<p style="margin:6px 0 0;color:' + colors.serene +
    ';font:400 11px/17px Arial,sans-serif">Datos ' +
    _newsletterEscapeHtml_(grounding.dataVersion) + ' · hechos ' +
    _newsletterEscapeHtml_(grounding.factsSha256.slice(0, 12)) +
    '</p></td></tr></table></td></tr></table></body></html>';
  const plain = [
    'BBVA · BUG RESOLUTION RADAR',
    grounding.scopeLabel,
    grounding.periodLabel,
    '',
    draft.summary.text,
    '',
    'Backlog: ' + metrics.currentOpen,
    'Variación: ' + _newsletterSignedDelta_(metrics.backlogDelta),
    'Alta / muy alta: ' + metrics.highOpen,
    '> 30 días: ' + metrics.agedOpen,
    ''
  ].concat(draft.sections.reduce(function (lines, section) {
    return lines.concat([section.title.toUpperCase(), section.text, '']);
  }, [])).concat([
    'Abrir vista web: ' + applicationUrl,
    'Abrir Google Slides: ' + reportUrl,
    'El PPTX original generado por escritorio se adjunta a este mensaje.',
    '',
    'Datos ' + grounding.dataVersion,
    'Hechos ' + grounding.factsSha256
  ]).join('\n');
  return { html: html, plain: plain };
}

function _newsletterRecipientsForReport_(reportId) {
  return Array.from(new Set(
    _readRecords_(RADAR.sheets.newsletterRecipients).filter(function (row) {
      return _text_(row.report_id) === _text_(reportId) && row.active === true;
    }).map(function (row) {
      return _canonicalEmail_(row.email);
    }).filter(Boolean)
  ));
}

function _newsletterTestWasSentBy_(reportId, email) {
  const id = _text_(reportId);
  const admin = _canonicalEmail_(email);
  return Boolean(id && admin) && _readRecords_(RADAR.sheets.newsletterAudit).some(function (row) {
    return _text_(row.report_id) === id &&
      _text_(row.mode) === 'test' &&
      _text_(row.status) === 'sent' &&
      _canonicalEmail_(row.created_by) === admin;
  });
}

function _newsletterAssertSender_() {
  _assert_(_newsletterSenderReady_(),
    'Configura ' + RADAR.newsletterFrom +
    ' como alias «Enviar como» de la cuenta administradora antes de enviar.',
    'NEWSLETTER_SENDER_INVALID');
}

function _newsletterAuditRecord_(
  newsletterId, reportId, mode, context, recipients, subject,
  model, status, details, user
) {
  return {
    newsletter_id: newsletterId,
    report_id: reportId,
    mode: mode,
    scope_key: context.record.scope_key,
    data_version: context.record.data_version,
    recipients_json: _safeJsonStringify_(recipients),
    subject: subject,
    facts_sha256: context.record.facts_sha256,
    gemini_model: model,
    created_at: _nowIso_(),
    created_by: user.email,
    status: status,
    details: _sanitizeText_(details, 1000)
  };
}

function sendPeriodNewsletter(reportId, mode) {
  return _rpc_(function () {
    const user = _requireAdmin_();
    const deliveryMode = _text_(mode) === 'send' ? 'send' : 'test';
    const context = _newsletterContext_(reportId);
    if (deliveryMode === 'send') {
      _assert_(
        _newsletterTestWasSentBy_(reportId, user.email),
        'Envía y revisa primero una prueba de esta newsletter con tu cuenta administradora.',
        'NEWSLETTER_TEST_REQUIRED'
      );
    }
    const recipients = deliveryMode === 'test'
      ? [user.email]
      : _newsletterRecipientsForReport_(reportId);
    _assert_(recipients.length,
      'No hay destinatarios activos para esta vista.', 'NEWSLETTER_NO_RECIPIENTS');
    _newsletterAssertSender_();
    const configuration = _newsletterGeminiConfiguration_();
    _assert_(configuration.configured,
      'Configura GEMINI_API_KEY en las propiedades del script antes de generar newsletters.',
      'GEMINI_NOT_CONFIGURED');
    const attachment = _exactReportBlob_(
      context.record.pptx_file_id,
      context.record.pptx_sha256,
      context.record.pptx_bytes,
      context.record.report_name
    );
    const subject = _newsletterSubject_(context.grounding);
    const newsletterId = _uuid_();
    const baseAudit = _newsletterAuditRecord_(
      newsletterId,
      _text_(reportId),
      deliveryMode,
      context,
      recipients,
      subject,
      configuration.model,
      'processing',
      'Solicitando a Gemini una selección de hechos canónicos.',
      user
    );
    _withApplicationLock_(function () {
      const previous = _readRecords_(RADAR.sheets.newsletterAudit).filter(function (row) {
        return _text_(row.report_id) === _text_(reportId) &&
          _text_(row.mode) === deliveryMode;
      });
      const inProgress = previous.some(function (row) {
        const created = _date_(row.created_at);
        return _text_(row.status) === 'processing' &&
          created && Date.now() - created.getTime() < 10 * 60 * 1000;
      });
      _assert_(!inProgress,
        'Ya hay una newsletter de esta presentación en proceso.',
        'NEWSLETTER_IN_PROGRESS');
      const alreadySent = deliveryMode === 'send' && previous.some(function (row) {
        return _text_(row.status) === 'sent';
      });
      _assert_(!alreadySent,
        'Esta presentación ya fue enviada. Importa una nueva versión para volver a enviar.',
        'NEWSLETTER_ALREADY_SENT');
      _appendRecords_(RADAR.sheets.newsletterAudit, [baseAudit]);
    });

    let draft;
    try {
      draft = _newsletterValidateDraft_(
        _newsletterGenerateDraft_(context.grounding).draft,
        context.grounding
      );
    } catch (err) {
      _upsertRecord_(RADAR.sheets.newsletterAudit, Object.assign({}, baseAudit, {
        status: 'failed',
        details: err && err.code === 'NEWSLETTER_VALIDATION_FAILED'
          ? 'La salida de Gemini fue bloqueada por la validación factual.'
          : 'Gemini no pudo completar la selección editorial.'
      }));
      throw err;
    }

    let reportShare = null;
    try {
      reportShare = _createReportShare_(context, user);
      const rendered = _newsletterRender_(
        draft,
        context.grounding,
        context.record.slides_url,
        reportShare.url
      );
      GmailApp.sendEmail(recipients.join(','), subject, rendered.plain, {
        htmlBody: rendered.html,
        name: 'BBVA · Bug Resolution Radar',
        from: RADAR.newsletterFrom,
        replyTo: RADAR.newsletterFrom,
        attachments: [attachment]
      });
    } catch (err) {
      if (reportShare) _deactivateReportShare_(reportShare.shareId);
      _upsertRecord_(RADAR.sheets.newsletterAudit, Object.assign({}, baseAudit, {
        status: 'failed',
        details: 'No se pudo completar el envío con el PPTX exacto.'
      }));
      if (err && err.code) throw err;
      const failure = new Error(
        'Gmail no ha podido enviar la newsletter desde el alias configurado.'
      );
      failure.code = 'NEWSLETTER_SEND_FAILED';
      throw failure;
    }

    _upsertRecord_(RADAR.sheets.newsletterAudit, Object.assign({}, baseAudit, {
      status: 'sent',
      details: deliveryMode === 'test'
        ? 'Prueba enviada al administrador con el PPTX exacto adjunto.'
        : 'Newsletter enviada con el PPTX exacto adjunto.'
    }));
    return {
      newsletterId: newsletterId,
      mode: deliveryMode,
      subject: subject,
      recipientCount: recipients.length,
      testRecipient: deliveryMode === 'test' ? user.email : '',
      sender: RADAR.newsletterFrom,
      reportUrl: context.record.slides_url,
      applicationUrl: reportShare.url,
      pptxSha256: context.record.pptx_sha256,
      factsSha256: context.record.facts_sha256,
      sentAt: _nowIso_()
    };
  });
}
