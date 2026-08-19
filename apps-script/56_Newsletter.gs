/** Deterministic delivery of the exact newsletter authored by the desktop snapshot. */
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

function _newsletterSenderIdentity_() {
  const requested = _canonicalEmail_(RADAR.newsletterFrom);
  let response = null;
  try {
    response = Gmail.Users.Settings.SendAs.list('me');
  } catch (err) {
    return {
      requested: requested,
      effective: '',
      ready: false,
      verificationStatus: 'unavailable',
      mode: 'Gmail API · remitente corporativo no disponible',
      error: _sanitizeText_(err && err.message, 500)
    };
  }
  const sendAs = ((response && response.sendAs) || []).find(function (item) {
    return _canonicalEmail_(item.sendAsEmail) === requested;
  });
  const verificationStatus = _text_(sendAs && sendAs.verificationStatus).toLowerCase() || 'unknown';
  const ready = Boolean(sendAs) && verificationStatus === 'accepted';
  return {
    requested: requested,
    effective: ready ? requested : '',
    ready: ready,
    verificationStatus: verificationStatus,
    mode: ready ? 'Gmail API · remitente corporativo verificado' : 'Gmail API · remitente pendiente',
    error: ''
  };
}

function _newsletterAuditPayload_() {
  return _readRecords_(RADAR.sheets.newsletterAudit).slice(-100).reverse().map(function (row) {
    return {
      newsletterId: _text_(row.newsletter_id),
      reportId: _text_(row.report_id),
      mode: _text_(row.mode),
      scopeKey: _text_(row.scope_key),
      recipients: _safeJsonParse_(row.recipients_json, []),
      recipientCount: Number(row.recipient_count || 0),
      subject: _text_(row.subject),
      bodyText: _text_(row.body_text),
      slidesUrl: _text_(row.slides_url),
      effectiveSender: _canonicalEmail_(row.effective_sender),
      createdAt: row.created_at,
      createdBy: _canonicalEmail_(row.created_by),
      status: _text_(row.status),
      details: _text_(row.details)
    };
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
  return {
    sender: _newsletterSenderIdentity_(),
    reports: reports,
    recipients: recipients,
    audit: _newsletterAuditPayload_()
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
    _assertExactFields_(input, ['reportId', 'email', 'displayName', 'active'], 'newsletterRecipient');
    const report = _newsletterReports_().find(function (item) {
      return item.reportId === _text_(input.reportId);
    });
    _assert_(report, 'El informe seleccionado no existe o ya no está activo.', 'SNAPSHOT_NOT_FOUND');
    const email = _canonicalEmail_(input.email);
    _assert_(/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email),
      'Introduce un correo válido.', 'VALIDATION_ERROR');
    _assert_(email.endsWith('@' + RADAR.allowedDomain),
      'El destinatario debe pertenecer al dominio @' + RADAR.allowedDomain + '.',
      'VALIDATION_ERROR');
    const displayName = _sanitizeText_(input.displayName, 200) || email.split('@')[0];
    const uid = report.reportId + '::' + email;
    _withApplicationLock_(function () {
      const current = _readRecords_(RADAR.sheets.newsletterRecipients).find(function (row) {
        return _text_(row.recipient_uid) === uid;
      });
      const createdAt = current ? current.created_at : _nowIso_();
      const createdBy = current ? current.created_by : user.email;
      _upsertRecord_(RADAR.sheets.newsletterRecipients, {
        recipient_uid: uid,
        report_id: report.reportId,
        snapshot_id: report.snapshotId,
        scope_key: report.scopeKey,
        scope_label: report.label,
        email: email,
        display_name: displayName,
        active: input.active === true,
        created_at: createdAt,
        created_by: createdBy,
        updated_at: _nowIso_(),
        updated_by: user.email
      });
    });
    return _newsletterSettingsPayload_();
  });
}

function _newsletterContext_(reportId) {
  const report = _readRecords_(RADAR.sheets.reportAudit).find(function (row) {
    return _text_(row.report_id) === _text_(reportId);
  });
  _assert_(report, 'No existe la presentación seleccionada.', 'NOT_FOUND');
  const record = _snapshotRecordById_(report.snapshot_id, true);
  _assert_(
    _text_(record.report_id) === _text_(report.report_id) &&
    _text_(record.projection_sha256) === _text_(report.projection_sha256) &&
    _text_(record.facts_sha256) === _text_(report.facts_sha256),
    'La auditoría del informe no coincide con su snapshot.',
    'NEWSLETTER_VALIDATION_FAILED'
  );
  const active = _activeSnapshotRecordForScope_(record.scope_key, true);
  _assert_(_text_(active.snapshot_id) === _text_(record.snapshot_id),
    'Este informe ya no es el snapshot activo. Usa el seguimiento de la última recarga.',
    'NEWSLETTER_STALE');
  const header = _snapshotHeader_(record);
  const newsletter = _snapshotNewsletter_(record);
  _assert_(
    _hash_(_stableJsonStringify_(newsletter)) === _text_(report.facts_sha256),
    'La newsletter local no supera la validación de integridad.',
    'NEWSLETTER_VALIDATION_FAILED'
  );
  return {
    report: report,
    record: record,
    header: header,
    newsletter: newsletter
  };
}

function _newsletterEscapeHtml_(value) {
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function _newsletterEmailFont_(value) {
  return String(value || '')
    .split(String.fromCharCode(34))
    .join(String.fromCharCode(39));
}

function _newsletterEncodedHeader_(value) {
  return '=?UTF-8?B?' +
    Utilities.base64Encode(_text_(value), Utilities.Charset.UTF_8) + '?=';
}

function _newsletterWrapBase64_(value) {
  return (String(value || '').match(/.{1,76}/g) || ['']).join('\r\n');
}

function _newsletterMimeText_(value) {
  return _newsletterWrapBase64_(
    Utilities.base64Encode(String(value || ''), Utilities.Charset.UTF_8)
  );
}

function _newsletterMimeBytes_(bytes) {
  return _newsletterWrapBase64_(Utilities.base64Encode(bytes));
}

function _newsletterMimeMessage_(recipient, subject, rendered, attachment, sender) {
  const normalizedRecipient = _canonicalEmail_(recipient);
  _assert_(normalizedRecipient, 'El destinatario de la newsletter no es válido.', 'VALIDATION_ERROR');
  const token = Utilities.getUuid().replace(/-/g, '');
  const mixedBoundary = 'radar_mixed_' + token;
  const alternativeBoundary = 'radar_alternative_' + token;
  const fileName = _text_(attachment.getName()) || 'bug-resolution-radar.pptx';
  const crlf = '\r\n';
  const mime = [
    'From: ' + _newsletterEncodedHeader_(RADAR.corporateBrand) + ' <' + sender.effective + '>',
    'Reply-To: ' + sender.effective,
    'To: ' + normalizedRecipient,
    'Subject: ' + _newsletterEncodedHeader_(subject),
    'Date: ' + new Date().toUTCString(),
    'Message-ID: <' + token + '@voc-commercial.bbva.com>',
    'X-Bug-Resolution-Radar-Version: ' + RADAR.appVersion,
    'MIME-Version: 1.0',
    'Content-Type: multipart/mixed; boundary="' + mixedBoundary + '"',
    '',
    '--' + mixedBoundary,
    'Content-Type: multipart/alternative; boundary="' + alternativeBoundary + '"',
    '',
    '--' + alternativeBoundary,
    'Content-Type: text/plain; charset="UTF-8"',
    'Content-Transfer-Encoding: base64',
    '',
    _newsletterMimeText_(rendered.plain),
    '--' + alternativeBoundary,
    'Content-Type: text/html; charset="UTF-8"',
    'Content-Transfer-Encoding: base64',
    '',
    _newsletterMimeText_(rendered.html),
    '--' + alternativeBoundary + '--',
    '',
    '--' + mixedBoundary,
    'Content-Type: application/vnd.openxmlformats-officedocument.presentationml.presentation; name="' +
      _newsletterEncodedHeader_(fileName) + '"',
    'Content-Transfer-Encoding: base64',
    'Content-Disposition: attachment; filename="' + _newsletterEncodedHeader_(fileName) + '"',
    '',
    _newsletterMimeBytes_(attachment.getBytes()),
    '--' + mixedBoundary + '--',
    ''
  ].join(crlf);
  return {
    raw: Utilities.base64EncodeWebSafe(mime, Utilities.Charset.UTF_8).replace(/=+$/g, ''),
    recipient: normalizedRecipient
  };
}

function _newsletterDeliver_(recipients, subject, rendered, attachment, sender) {
  const deliveries = [];
  const failures = [];
  recipients.forEach(function (recipient) {
    try {
      const message = _newsletterMimeMessage_(recipient, subject, rendered, attachment, sender);
      const accepted = Gmail.Users.Messages.send({ raw: message.raw }, 'me');
      if (!accepted || !_text_(accepted.id)) {
        throw new Error('Gmail API no ha devuelto un identificador de mensaje.');
      }
      deliveries.push({
        recipient: message.recipient,
        messageId: _text_(accepted.id),
        threadId: _text_(accepted.threadId)
      });
    } catch (err) {
      failures.push({
        recipient: _canonicalEmail_(recipient),
        error: _sanitizeText_(err && err.message, 500) || 'Gmail API no ha aceptado el mensaje.'
      });
    }
  });
  return { deliveries: deliveries, failures: failures };
}

function _newsletterPeriodOnly_(value) {
  const label = _text_(value);
  const match = label.match(/(?:^|·\s*)(Periodo\s+.+)$/i);
  return match ? match[1].replace(/^periodo/i, 'Periodo') : label;
}

function _newsletterSnapshotTimestamp_(value) {
  const stamp = _date_(value);
  return stamp
    ? Utilities.formatDate(stamp, Session.getScriptTimeZone() || 'Europe/Madrid', 'dd/MM/yyyy HH:mm')
    : 'fecha no disponible';
}

function _newsletterRender_(newsletter, reportUrl, applicationUrl, publication) {
  const draft = newsletter.draft || {};
  const reportLink = _sanitizeUrl_(reportUrl);
  const appLink = _sanitizeUrl_(applicationUrl);
  const metrics = newsletter.metrics || {};
  const backlogDelta = Number(newsletter.backlogDelta || 0);
  const rollups = newsletter.responsibleRollups || [];
  const scopeLabel = _text_(publication && publication.scopeLabel);
  const periodLabel = _newsletterPeriodOnly_(newsletter.periodLabel);
  const snapshotTimestamp = _newsletterSnapshotTimestamp_(publication && publication.generatedAt);
  const color = DESIGN_TOKENS.color;
  // Email styles live inside double-quoted HTML attributes. Use single quotes
  // around family names so the generated markup remains valid in Gmail.
  const font = _newsletterEmailFont_(DESIGN_TOKENS.font.webBody);
  const headline = _newsletterEmailFont_(DESIGN_TOKENS.font.webHeadline);
  const movementColor = backlogDelta <= 0 ? color.success : color.warningStrong;
  const movementBackground = backlogDelta <= 0 ? color.successSoft : color.warningSoft;
  const movementLabel = backlogDelta < 0
    ? 'Backlog reducido en ' + Math.abs(backlogDelta)
    : backlogDelta > 0
      ? 'Backlog incrementado en ' + backlogDelta
      : 'Backlog estable';

  function metricCell_(label, value, caption) {
    return '<td class="metric-cell" width="25%" valign="top" style="padding:0 6px 12px">' +
      '<div style="min-height:104px;padding:16px;background:' + color.grey200 +
      ';border:1px solid ' + color.grey300 + ';border-radius:' + DESIGN_TOKENS.radius.component + '">' +
      '<span style="display:block;margin-bottom:8px;color:' + color.grey600 +
      ';font-size:12px;line-height:16px;font-weight:500;text-transform:uppercase;letter-spacing:.04em">' +
      _newsletterEscapeHtml_(label) + '</span>' +
      '<strong style="display:block;color:' + color.midnight + ';font-family:' + headline +
      ';font-size:32px;line-height:40px">' + _newsletterEscapeHtml_(value) + '</strong>' +
      '<small style="display:block;margin-top:4px;color:' + color.grey600 +
      ';font-size:12px;line-height:16px">' + _newsletterEscapeHtml_(caption) + '</small></div></td>';
  }

  const responsibleRows = rollups.map(function (row) {
    const name = _newsletterEscapeHtml_(row.name);
    const linkedName = _text_(row.dashboardUrl)
      ? '<a href="' + _newsletterEscapeHtml_(_sanitizeUrl_(row.dashboardUrl)) +
        '" style="color:' + color.electric + ';font-weight:700;text-decoration:none">' + name + '</a>'
      : '<strong>' + name + '</strong>';
    const dashboardAction = _text_(row.dashboardUrl)
      ? '<a href="' + _newsletterEscapeHtml_(_sanitizeUrl_(row.dashboardUrl)) +
        '" style="color:' + color.electric + ';font-size:12px;line-height:16px;font-weight:700;text-decoration:none">Abrir cuadro JIRA&nbsp;↗</a>'
      : '';
    return '<tr><td style="padding:0 0 12px"><table role="presentation" width="100%" style="border-collapse:separate;background:' +
      color.white + ';border:1px solid ' + color.grey300 + ';border-radius:' +
      DESIGN_TOKENS.radius.component + '"><tr><td style="padding:16px 20px">' +
      '<table role="presentation" width="100%"><tr><td style="color:' + color.midnight +
      ';font-size:15px;line-height:24px">' + linkedName + '</td><td align="right">' + dashboardAction + '</td></tr></table>' +
      '<table role="presentation" width="100%" style="margin-top:12px;border-collapse:collapse"><tr>' +
      '<td width="33%" style="padding-right:8px;color:' + color.grey600 + ';font-size:12px;line-height:16px">Abiertas<br><strong style="color:' + color.midnight + ';font-size:20px;line-height:24px">' + _newsletterEscapeHtml_(row.openIssues) + '</strong></td>' +
      '<td width="33%" style="padding:0 8px;border-left:1px solid ' + color.grey300 + ';color:' + color.grey600 + ';font-size:12px;line-height:16px">Causas raíz<br><strong style="color:' + color.midnight + ';font-size:20px;line-height:24px">' + _newsletterEscapeHtml_(row.rootCauseEvolutives) + '</strong></td>' +
      '<td width="34%" style="padding-left:8px;border-left:1px solid ' + color.grey300 + ';color:' + color.grey600 + ';font-size:12px;line-height:16px">Discrepancias estados finalistas<br><strong style="color:' + color.midnight + ';font-size:20px;line-height:24px">' + _newsletterEscapeHtml_(row.finalistDiscrepancies) + '</strong></td>' +
      '</tr></table></td></tr></table></td></tr>';
  }).join('');

  const preheader = 'Seguimiento quincenal de incidencias · ' + periodLabel;
  const html =
    '<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent">' +
    _newsletterEscapeHtml_(preheader) + '</div>' +
    '<div style="margin:0;background:' + color.grey200 + ';padding:24px 16px">' +
    '<style>@media only screen and (max-width:620px){.email-shell{width:100%!important}.email-pad{padding:24px 16px!important}.metric-cell{display:block!important;width:100%!important}.brand-division{display:block!important;margin:8px 0 0!important;padding:0!important;border:0!important}.email-actions td{display:block!important;width:100%!important;padding:0 0 8px!important}}</style>' +
    '<table class="email-shell" role="presentation" width="100%" style="max-width:720px;margin:auto;border-collapse:separate;background:' +
    color.white + ';border-radius:' + DESIGN_TOKENS.radius.container + ';overflow:hidden;box-shadow:' +
    DESIGN_TOKENS.effect.emailShadow + '">' +
    '<tr><td style="padding:24px 32px;background:' + color.midnight + ';font-family:' + font + ';color:' + color.white + '">' +
    '<table role="presentation" width="100%" style="font-family:' + font + ';color:' + color.white + '"><tr><td valign="middle"><strong style="color:' + color.white + ';font-size:24px;line-height:32px;letter-spacing:-.04em">BBVA</strong>' +
    '<span class="brand-division" style="display:inline-block;margin-left:12px;padding-left:12px;border-left:1px solid ' +
    color.serene + ';color:' + color.blueLight + ';font-size:10px;line-height:12px;font-weight:500">Banca de Empresas<br>e Instituciones</span></td>' +
    '<td align="right" valign="middle" style="color:' + color.serene + ';font-size:12px;line-height:16px;font-weight:500">BUG RESOLUTION RADAR</td></tr></table></td></tr>' +
    '<tr><td class="email-pad" style="padding:32px;font-family:' + font + ';font-size:15px;line-height:24px;color:' + color.grey800 + '">' +
    '<p style="margin:0 0 8px;color:' + color.royalDark + ';font-size:12px;line-height:16px;font-weight:700;letter-spacing:.08em;text-transform:uppercase">Seguimiento quincenal</p>' +
    '<h1 style="margin:0;color:' + color.midnight + ';font-family:' + headline + ';font-size:32px;line-height:40px">' + _newsletterEscapeHtml_(scopeLabel) + '</h1>' +
    '<p style="margin:8px 0 24px;color:' + color.grey600 + '">' + _newsletterEscapeHtml_(periodLabel) + '</p>' +
    '<p style="margin:0 0 24px">Resultado correspondiente al seguimiento de incidencias de la última quincena:</p>' +
    '<table role="presentation" width="100%" style="margin:0 -6px 12px;border-collapse:separate"><tr>' +
    metricCell_('Backlog abierto', metrics.currentOpen, 'Antes: ' + _text_(newsletter.previousOpen)) +
    metricCell_('Creadas', metrics.createdCurrent, 'Quincena actual') +
    metricCell_('Cerradas', metrics.closedCurrent, 'Quincena actual') +
    metricCell_('Resolución', metrics.resolutionCurrent, 'Tiempo medio') +
    '</tr></table>' +
    '<div style="margin:0 0 24px;padding:16px 20px;border-left:4px solid ' + movementColor + ';border-radius:' +
    DESIGN_TOKENS.radius.component + ';background:' + movementBackground + '">' +
    '<strong style="display:block;color:' + movementColor + ';font-size:20px;line-height:24px">' +
    _newsletterEscapeHtml_(movementLabel) + '</strong><span style="display:block;margin-top:4px;color:' +
    color.grey700 + '">' + _newsletterEscapeHtml_(draft.summary) + '</span></div>' +
    '<table class="email-actions" role="presentation" style="margin-bottom:32px"><tr>' +
    '<td style="padding-right:8px"><a href="' + _newsletterEscapeHtml_(reportLink) +
    '" style="display:inline-block;padding:12px 20px;border-radius:' + DESIGN_TOKENS.radius.component + ';background:' +
    color.electric + ';color:' + color.white + ';font-weight:700;text-decoration:none">Abrir presentación&nbsp;↗</a></td>' +
    '<td><a href="' + _newsletterEscapeHtml_(appLink) + '" style="display:inline-block;padding:11px 20px;border:1px solid ' +
    color.electric + ';border-radius:' + DESIGN_TOKENS.radius.component + ';color:' + color.electric +
    ';font-weight:700;text-decoration:none">Abrir Radar&nbsp;↗</a></td></tr></table>' +
    '<div style="margin:0 0 16px"><p style="margin:0;color:' + color.midnight + ';font-family:' + headline +
    ';font-size:24px;line-height:32px">Responsables y focos de actuación</p><p style="margin:4px 0 0;color:' +
    color.grey600 + '">' + _newsletterEscapeHtml_(draft.responsibleIntro) + '</p></div>' +
    '<table role="presentation" width="100%" style="border-collapse:collapse">' + responsibleRows + '</table>' +
    '<p style="margin:20px 0 0;color:' + color.grey700 + '">' + _newsletterEscapeHtml_(draft.closing) + '</p>' +
    '</td></tr><tr><td style="padding:20px 32px;border-top:1px solid ' + color.grey300 + ';background:' + color.grey200 +
    ';font-family:' + font + ';color:' + color.grey600 + ';font-size:12px;line-height:16px">' +
    '<strong style="color:' + color.midnight + '">BBVA Banca de Empresas e Instituciones</strong><br>' +
    'Información generada a ' + _newsletterEscapeHtml_(snapshotTimestamp) + '</td></tr></table></div>';
  const plain = [
    RADAR.corporateBrand,
    'Bug Resolution Radar',
    scopeLabel,
    periodLabel,
    '',
    'Resultado correspondiente al seguimiento de incidencias de la última quincena:',
    reportLink,
    '',
    draft.summary,
    '',
    draft.responsibleIntro,
    ...(draft.responsibleParagraphs || []),
    '',
    draft.closing,
    '',
    appLink,
    '',
    'Información generada a ' + snapshotTimestamp
  ].join('\n');
  return { html: html, plain: plain };
}

function _newsletterRecipientsForReport_(reportId) {
  return Array.from(new Set(
    _readRecords_(RADAR.sheets.newsletterRecipients).filter(function (row) {
      return _text_(row.report_id) === _text_(reportId) && row.active === true;
    }).map(function (row) {
      return _canonicalEmail_(row.email);
    }).filter(Boolean)
  )).sort();
}

function _newsletterTestWasSentBy_(reportId, email) {
  const admin = _canonicalEmail_(email);
  return Boolean(reportId && admin) && _readRecords_(RADAR.sheets.newsletterAudit).some(function (row) {
    return _text_(row.report_id) === _text_(reportId) &&
      _text_(row.mode) === 'test' &&
      _text_(row.status) === 'sent' &&
      _canonicalEmail_(row.created_by) === admin;
  });
}

function _newsletterPreviouslyDeliveredRecipients_(reportId, mode) {
  const delivered = new Set();
  _readRecords_(RADAR.sheets.newsletterAudit).filter(function (row) {
    return _text_(row.report_id) === _text_(reportId) &&
      _text_(row.mode) === _text_(mode) &&
      _text_(row.status) === 'partial';
  }).forEach(function (row) {
    const details = _safeJsonParse_(row.details, {});
    (details.deliveredRecipients || []).forEach(function (recipient) {
      const email = _canonicalEmail_(recipient);
      if (email) delivered.add(email);
    });
  });
  return delivered;
}

function _newsletterAuditRecord_(
  newsletterId, reportId, mode, context, recipients, subject,
  bodyText, sender, status, details, user
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
    body_text: _sanitizeText_(bodyText, 45000),
    slides_url: context.record.slides_url,
    recipient_count: recipients.length,
    effective_sender: sender.effective,
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
    const sender = _newsletterSenderIdentity_();
    _assert_(sender.ready,
      'El remitente corporativo ' + sender.requested + ' no está aceptado para el propietario del despliegue (' + sender.verificationStatus + '). Reautoriza Gmail API desde Apps Script.',
      'NEWSLETTER_SENDER_UNAVAILABLE');
    const attachment = _exactReportBlob_(
      context.record.pptx_file_id,
      context.record.pptx_sha256,
      context.record.pptx_bytes,
      context.record.report_name
    );
    const authoredSubject = _sanitizeText_(context.newsletter.draft.subject, 220);
    const subject = deliveryMode === 'test' ? '[PRUEBA] ' + authoredSubject : authoredSubject;
    const newsletterId = _uuid_();
    let reportShare = null;
    let rendered = null;
    let deliveries = [];
    let deliveryFailures = [];
    let stage = 'preparación';

    try {
      stage = 'enlace seguro';
      reportShare = _createReportShare_(context, user);
      stage = 'renderizado';
      rendered = _newsletterRender_(
        context.newsletter,
        context.record.slides_url,
        reportShare.url,
        {
          scopeLabel: context.record.scope_label,
          generatedAt: context.header.generatedAt || context.record.created_at
        }
      );
      const baseAudit = _newsletterAuditRecord_(
        newsletterId, _text_(reportId), deliveryMode, context, recipients, subject,
        rendered.plain, sender, 'processing', 'Newsletter local validada y preparada.', user
      );
      stage = 'reserva de envío';
      _withApplicationLock_(function () {
        // A second click must observe the processing row written by the first
        // execution, even when this execution had memoized a previous audit.
        _forgetSheet_(RADAR.sheets.newsletterAudit);
        const existing = _readRecords_(RADAR.sheets.newsletterAudit).filter(function (row) {
          return _text_(row.report_id) === _text_(reportId) && _text_(row.mode) === deliveryMode;
        });
        _assert_(!existing.some(function (row) {
          const created = _date_(row.created_at);
          return _text_(row.status) === 'processing' &&
            created && Date.now() - created.getTime() < 10 * 60 * 1000;
        }), 'Ya hay una newsletter de esta presentación en proceso.', 'NEWSLETTER_IN_PROGRESS');
        _assert_(!(deliveryMode === 'send' && existing.some(function (row) {
          return _text_(row.status) === 'sent';
        })), 'Esta presentación ya fue enviada. Importa una nueva versión para volver a enviar.',
        'NEWSLETTER_ALREADY_SENT');
        _appendRecords_(RADAR.sheets.newsletterAudit, [baseAudit]);
      });
      stage = 'Gmail API';
      const previouslyDelivered = deliveryMode === 'send'
        ? _newsletterPreviouslyDeliveredRecipients_(reportId, deliveryMode)
        : new Set();
      const pendingRecipients = recipients.filter(function (recipient) {
        return !previouslyDelivered.has(_canonicalEmail_(recipient));
      });
      const outcome = _newsletterDeliver_(pendingRecipients, subject, rendered, attachment, sender);
      deliveries = outcome.deliveries;
      deliveryFailures = outcome.failures;
      _assert_(!deliveryFailures.length,
        'Gmail API no ha aceptado ' + deliveryFailures.length + ' mensaje(s): ' +
          deliveryFailures.map(function (item) { return item.recipient; }).join(', '),
        'NEWSLETTER_SEND_FAILED');
      stage = 'auditoría final';
      _upsertRecord_(RADAR.sheets.newsletterAudit, Object.assign({}, baseAudit, {
        status: 'sent',
        details: deliveryMode === 'test'
          ? 'Prueba aceptada por Gmail API con el PPTX exacto adjunto. Message ID: ' + deliveries[0].messageId
          : 'Newsletter aceptada por Gmail API para ' + deliveries.length + ' destinatarios con el PPTX exacto adjunto.'
      }));
    } catch (err) {
      if (reportShare && !deliveries.length) _deactivateReportShare_(reportShare.shareId);
      const technicalDetail = _sanitizeText_(err && err.message, 600) || 'Error no detallado por Google Workspace.';
      const failed = _newsletterAuditRecord_(
        newsletterId, _text_(reportId), deliveryMode, context, recipients, subject,
        rendered ? rendered.plain : 'No se llegó a generar el cuerpo de la newsletter.', sender,
        deliveries.length ? 'partial' : 'failed',
        deliveries.length ? _safeJsonStringify_({
          stage: stage,
          error: technicalDetail,
          deliveredRecipients: deliveries.map(function (item) { return item.recipient; }),
          messageIds: deliveries.map(function (item) { return item.messageId; }),
          failures: deliveryFailures
        }) : 'Fallo en ' + stage + ': ' + technicalDetail,
        user
      );
      try { _upsertRecord_(RADAR.sheets.newsletterAudit, failed); } catch (auditError) {
        console.error('newsletter_failure_audit_error', {
          stage: stage, message: auditError && auditError.message
        });
      }
      if (err && err.code) throw err;
      const failure = new Error(
        'No se pudo completar la newsletter durante ' + stage + ': ' + technicalDetail
      );
      failure.code = 'NEWSLETTER_SEND_FAILED';
      throw failure;
    }
    return {
      newsletterId: newsletterId,
      mode: deliveryMode,
      subject: subject,
      recipientCount: recipients.length,
      testRecipient: deliveryMode === 'test' ? user.email : '',
      sender: sender.effective,
      senderMode: sender.mode,
      messageIds: deliveries.map(function (item) { return item.messageId; }),
      reportUrl: context.record.slides_url,
      applicationUrl: reportShare.url,
      pptxSha256: context.record.pptx_sha256,
      factsSha256: context.record.facts_sha256,
      sentAt: _nowIso_()
    };
  });
}
