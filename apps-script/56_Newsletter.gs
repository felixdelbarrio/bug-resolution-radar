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

function _newsletterSenderIdentity_(userEmail) {
  const requested = _canonicalEmail_(RADAR.newsletterFrom);
  let aliases = [];
  try {
    aliases = GmailApp.getAliases().map(_canonicalEmail_);
  } catch (err) {
    aliases = [];
  }
  const usesAlias = aliases.indexOf(requested) >= 0;
  return {
    requested: requested,
    effective: usesAlias ? requested : _canonicalEmail_(userEmail),
    usesAlias: usesAlias,
    mode: usesAlias ? 'alias' : 'cuenta administradora con reply-to del grupo'
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

function _newsletterSettingsPayload_(userEmail) {
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
    sender: _newsletterSenderIdentity_(userEmail),
    reports: reports,
    users: _newsletterUsers_(),
    recipients: recipients,
    audit: _newsletterAuditPayload_()
  };
}

function getNewsletterSettings() {
  return _rpc_(function () {
    const user = _requireAdmin_();
    return _newsletterSettingsPayload_(user.email);
  });
}

function saveNewsletterRecipient(payload) {
  return _rpc_(function () {
    const user = _requireAdmin_();
    const input = payload || {};
    _assertExactFields_(input, ['reportId', 'email', 'active'], 'newsletterRecipient');
    const report = _newsletterReports_().find(function (item) {
      return item.reportId === _text_(input.reportId);
    });
    _assert_(report, 'El informe seleccionado no existe o ya no está activo.', 'SNAPSHOT_NOT_FOUND');
    const email = _canonicalEmail_(input.email);
    const recipientUser = _newsletterUsers_().find(function (candidate) {
      return candidate.email === email;
    });
    _assert_(recipientUser,
      'El destinatario debe ser un usuario activo y autorizado de la aplicación.',
      'VALIDATION_ERROR');
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
        display_name: recipientUser.displayName,
        active: input.active === true,
        created_at: createdAt,
        created_by: createdBy,
        updated_at: _nowIso_(),
        updated_by: user.email
      });
    });
    return _newsletterSettingsPayload_(user.email);
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

function _newsletterRender_(newsletter, reportUrl, applicationUrl) {
  const draft = newsletter.draft || {};
  const reportLink = _sanitizeUrl_(reportUrl);
  const appLink = _sanitizeUrl_(applicationUrl);
  const rollups = newsletter.responsibleRollups || [];
  const paragraphs = rollups.map(function (row, index) {
    const text = (draft.responsibleParagraphs || [])[index] || '';
    const name = _newsletterEscapeHtml_(row.name);
    const linkedName = _text_(row.dashboardUrl)
      ? '<a href="' + _newsletterEscapeHtml_(_sanitizeUrl_(row.dashboardUrl)) +
        '" style="color:' + DESIGN_TOKENS.color.electric + ';font-weight:700">' + name + '</a>'
      : '<strong>' + name + '</strong>';
    return '<p style="margin:0 0 12px;color:' + DESIGN_TOKENS.color.grey800 + '">' +
      linkedName + _newsletterEscapeHtml_(text).replace(_newsletterEscapeHtml_(row.name), '') +
      '</p>';
  }).join('');
  const html =
    '<div style="margin:0;background:' + DESIGN_TOKENS.color.grey200 + ';padding:24px">' +
    '<table role="presentation" width="100%" style="max-width:720px;margin:auto;background:' +
    DESIGN_TOKENS.color.white + ';border-radius:' + DESIGN_TOKENS.radius.container +
    ';box-shadow:' + DESIGN_TOKENS.effect.emailShadow + ';border-collapse:separate">' +
    '<tr><td style="padding:28px;font-family:' + DESIGN_TOKENS.font.webBody + '">' +
    '<p style="margin:0 0 16px">' + _newsletterEscapeHtml_(draft.greeting) + '</p>' +
    '<p style="margin:0 0 12px">' + _newsletterEscapeHtml_(draft.intro) + '</p>' +
    '<p style="margin:0 0 20px"><a href="' + _newsletterEscapeHtml_(reportLink) +
    '" style="color:' + DESIGN_TOKENS.color.electric + ';font-weight:700">' +
    _newsletterEscapeHtml_(draft.reportLinkLabel) + ' ↗</a></p>' +
    '<p style="margin:0 0 20px;color:' + DESIGN_TOKENS.color.grey800 + '">' +
    _newsletterEscapeHtml_(draft.summary) + '</p>' +
    '<p style="margin:0 0 16px;color:' + DESIGN_TOKENS.color.grey800 + '">' +
    _newsletterEscapeHtml_(draft.responsibleIntro) + '</p>' + paragraphs +
    '<p style="margin:20px 0 0">' + _newsletterEscapeHtml_(draft.closing) + '</p>' +
    '<p style="margin:24px 0 0;font-size:12px"><a href="' +
    _newsletterEscapeHtml_(appLink) + '" style="color:' + DESIGN_TOKENS.color.electric +
    '">Abrir snapshot publicado ↗</a></p></td></tr></table></div>';
  const plain = [
    draft.greeting,
    '',
    draft.intro,
    reportLink,
    '',
    draft.summary,
    '',
    draft.responsibleIntro,
    ...(draft.responsibleParagraphs || []),
    '',
    draft.closing,
    '',
    appLink
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
    const attachment = _exactReportBlob_(
      context.record.pptx_file_id,
      context.record.pptx_sha256,
      context.record.pptx_bytes,
      context.record.report_name
    );
    const sender = _newsletterSenderIdentity_(user.email);
    const authoredSubject = _sanitizeText_(context.newsletter.draft.subject, 220);
    const subject = deliveryMode === 'test' ? '[PRUEBA] ' + authoredSubject : authoredSubject;
    const newsletterId = _uuid_();
    let reportShare = null;
    let rendered = null;
    let stage = 'preparación';

    try {
      stage = 'enlace seguro';
      reportShare = _createReportShare_(context, user);
      stage = 'renderizado';
      rendered = _newsletterRender_(
        context.newsletter,
        context.record.slides_url,
        reportShare.url
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
      const options = {
        htmlBody: rendered.html,
        name: 'BBVA · Bug Resolution Radar',
        replyTo: RADAR.newsletterFrom,
        attachments: [attachment]
      };
      if (sender.usesAlias) options.from = RADAR.newsletterFrom;
      _assert_(MailApp.getRemainingDailyQuota() >= recipients.length,
        'La cuota diaria de correo no permite completar este envío.', 'NEWSLETTER_SEND_FAILED');
      stage = 'Gmail';
      GmailApp.sendEmail(recipients.join(','), subject, rendered.plain, options);
      stage = 'auditoría final';
      _upsertRecord_(RADAR.sheets.newsletterAudit, Object.assign({}, baseAudit, {
        status: 'sent',
        details: deliveryMode === 'test'
          ? 'Prueba enviada al administrador con el PPTX exacto adjunto.'
          : 'Newsletter enviada con el PPTX exacto adjunto.'
      }));
    } catch (err) {
      if (reportShare) _deactivateReportShare_(reportShare.shareId);
      const technicalDetail = _sanitizeText_(err && err.message, 600) || 'Error no detallado por Google Workspace.';
      const failed = _newsletterAuditRecord_(
        newsletterId, _text_(reportId), deliveryMode, context, recipients, subject,
        rendered ? rendered.plain : 'No se llegó a generar el cuerpo de la newsletter.', sender, 'failed',
        'Fallo en ' + stage + ': ' + technicalDetail, user
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
      reportUrl: context.record.slides_url,
      applicationUrl: reportShare.url,
      pptxSha256: context.record.pptx_sha256,
      factsSha256: context.record.facts_sha256,
      sentAt: _nowIso_()
    };
  });
}
