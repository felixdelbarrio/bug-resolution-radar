/** Google Drive destination and exact desktop-authored PPTX publication. */
const REPORT_FOLDER_MIME = 'application/vnd.google-apps.folder';
const REPORT_PRESENTATION_MIME = 'application/vnd.google-apps.presentation';

function _reportDriveFolderId_(reference) {
  const raw = _text_(reference).replace(/^folder:/, '').replace(/^drive:/, '');
  if (!raw || raw === 'root' || raw === 'root:my-drive') return DriveApp.getRootFolder().getId();
  const match = raw.match(/\/folders\/([A-Za-z0-9_-]+)/) || raw.match(/[?&]id=([A-Za-z0-9_-]+)/);
  const token = match ? match[1] : raw;
  _assert_(/^[A-Za-z0-9_-]{10,}$/.test(token),
    'La referencia no contiene un identificador válido de carpeta.', 'DRIVE_FOLDER_INVALID');
  return token;
}

function _reportFolderUrl_(folderId) {
  return 'https://drive.google.com/drive/folders/' + encodeURIComponent(_text_(folderId));
}

function _periodPresentationUrl_(fileId) {
  return 'https://docs.google.com/presentation/d/' + encodeURIComponent(_text_(fileId)) + '/edit';
}

function _reportFolderDescriptorFromResource_(resource, rootId, kind) {
  const id = _text_(resource && resource.id);
  return {
    id: id,
    reference: (kind === 'drive' ? 'drive:' : 'folder:') + id,
    name: _text_(resource && resource.name) || (id === rootId ? 'Mi unidad' : 'Carpeta'),
    url: _text_(resource && resource.webViewLink) || _reportFolderUrl_(id),
    driveId: _text_(resource && resource.driveId) || (kind === 'drive' ? id : ''),
    kind: kind || 'folder',
    selectable: !resource || !resource.capabilities || resource.capabilities.canAddChildren !== false,
    isRoot: id === rootId
  };
}

function _reportFolderResource_(reference) {
  try {
    const id = _reportDriveFolderId_(reference);
    return Drive.Files.get(id, {
      supportsAllDrives: true,
      fields: 'id,name,mimeType,parents,driveId,webViewLink,capabilities(canAddChildren)'
    });
  } catch (err) {
    const error = new Error('No se puede acceder a esa carpeta de Google Drive con tu usuario.');
    error.code = 'DRIVE_FOLDER_INVALID';
    throw error;
  }
}

function _reportDriveFolder_(reference) {
  const resource = _reportFolderResource_(reference);
  _assert_(_text_(resource.mimeType) === REPORT_FOLDER_MIME,
    'La referencia no corresponde a una carpeta de Google Drive.', 'DRIVE_FOLDER_INVALID');
  return resource;
}

function _reportFolderList_(folder) {
  const driveId = _text_(folder.driveId);
  const options = {
    q: "'" + _text_(folder.id).replace(/'/g, "\\'") +
      "' in parents and trashed = false and mimeType = '" + REPORT_FOLDER_MIME + "'",
    includeItemsFromAllDrives: true,
    supportsAllDrives: true,
    pageSize: 100,
    fields: 'nextPageToken,files(id,name,mimeType,parents,driveId,webViewLink,capabilities(canAddChildren))'
  };
  options.corpora = driveId ? 'drive' : 'user';
  if (driveId) options.driveId = driveId;
  const response = Drive.Files.list(options);
  return {
    children: (response.files || []).map(function (item) {
      return _reportFolderDescriptorFromResource_(item, folder.id, 'folder');
    }).sort(function (left, right) {
      return left.name.localeCompare(right.name, 'es', { sensitivity: 'base' });
    }),
    truncated: Boolean(response.nextPageToken)
  };
}

function listReportDriveFolders(reference) {
  return _rpc_(function () {
    _requireAdmin_();
    const raw = _text_(reference) || 'root:my-drive';
    const roots = [
      { reference: 'root:my-drive', name: 'Mi unidad', kind: 'root' },
      { reference: 'root:starred', name: 'Destacados', kind: 'root' },
      { reference: 'root:shared-drives', name: 'Unidades compartidas', kind: 'root' }
    ];
    if (raw === 'root:starred') {
      const starred = Drive.Files.list({
        q: "starred = true and trashed = false and mimeType = '" + REPORT_FOLDER_MIME + "'",
        corpora: 'user',
        spaces: 'drive',
        includeItemsFromAllDrives: true,
        supportsAllDrives: true,
        pageSize: 100,
        fields: 'nextPageToken,files(id,name,mimeType,parents,driveId,webViewLink,capabilities(canAddChildren))'
      });
      return {
        roots: roots,
        current: {
          id: '', reference: raw, name: 'Destacados',
          url: 'https://drive.google.com/drive/starred',
          kind: 'collection', selectable: false, isRoot: true
        },
        parent: null,
        children: (starred.files || []).map(function (item) {
          return _reportFolderDescriptorFromResource_(item, item.driveId || '', 'folder');
        }).sort(function (left, right) {
          return left.name.localeCompare(right.name, 'es', { sensitivity: 'base' });
        }),
        truncated: Boolean(starred.nextPageToken)
      };
    }
    if (raw === 'root:shared-drives') {
      const shared = Drive.Drives.list({
        pageSize: 100,
        fields: 'nextPageToken,drives(id,name,capabilities(canAddChildren))'
      });
      return {
        roots: roots,
        current: {
          id: '', reference: raw, name: 'Unidades compartidas',
          url: 'https://drive.google.com/drive/shared-drives',
          kind: 'collection', selectable: false, isRoot: true
        },
        parent: null,
        children: (shared.drives || []).map(function (item) {
          return _reportFolderDescriptorFromResource_(item, item.id, 'drive');
        }).sort(function (left, right) {
          return left.name.localeCompare(right.name, 'es', { sensitivity: 'base' });
        }),
        truncated: Boolean(shared.nextPageToken)
      };
    }
    const folder = _reportDriveFolder_(raw);
    const listed = _reportFolderList_(folder);
    const rootId = _text_(folder.driveId) || DriveApp.getRootFolder().getId();
    let parent = null;
    const parentId = (folder.parents || [])[0];
    if (parentId) {
      const parentResource = Drive.Files.get(parentId, {
        supportsAllDrives: true,
        fields: 'id,name,mimeType,parents,driveId,webViewLink,capabilities(canAddChildren)'
      });
      parent = _reportFolderDescriptorFromResource_(parentResource, rootId, 'folder');
    } else if (_text_(folder.driveId) && _text_(folder.id) !== _text_(folder.driveId)) {
      const drive = Drive.Drives.get(folder.driveId, {
        fields: 'id,name,capabilities(canAddChildren)'
      });
      parent = _reportFolderDescriptorFromResource_(drive, drive.id, 'drive');
    }
    return {
      roots: roots,
      current: _reportFolderDescriptorFromResource_(
        folder,
        rootId,
        _text_(folder.id) === _text_(folder.driveId) ? 'drive' : 'folder'
      ),
      parent: parent,
      children: listed.children,
      truncated: listed.truncated
    };
  });
}

function saveReportDriveFolder(reference) {
  return _rpc_(function () {
    const user = _requireAdmin_();
    const folder = _reportDriveFolder_(reference);
    _assert_(!folder.capabilities || folder.capabilities.canAddChildren !== false,
      'No tienes permiso para publicar informes en esa carpeta.', 'DRIVE_FOLDER_INVALID');
    const descriptor = _reportFolderDescriptorFromResource_(
      folder,
      _text_(folder.driveId) || DriveApp.getRootFolder().getId(),
      _text_(folder.id) === _text_(folder.driveId) ? 'drive' : 'folder'
    );
    _upsertRecord_(RADAR.sheets.preferences, {
      pref_uid: user.email + '::report_drive_folder',
      email: user.email,
      preference_key: 'report_drive_folder',
      value_json: _safeJsonStringify_(descriptor),
      updated_at: _nowIso_()
    });
    return descriptor;
  });
}

function _configuredReportDriveFolder_(preferences) {
  const preference = (preferences || {}).report_drive_folder;
  _assert_(preference && preference.id,
    'Configura primero la carpeta de Google Drive en Preferencias.', 'DRIVE_FOLDER_INVALID');
  const folder = _reportDriveFolder_(preference.id);
  _assert_(!folder.capabilities || folder.capabilities.canAddChildren !== false,
    'No tienes permiso para publicar informes en la carpeta configurada.', 'DRIVE_FOLDER_INVALID');
  return folder;
}

function _exactReportBlob_(fileId, expectedSha256, expectedBytes, fileName) {
  _assert_(Number(expectedBytes) <= RADAR.maxReportBytes,
    'El PPTX supera 20 MB y no puede adjuntarse de forma segura a la newsletter.',
    'ATTACHMENT_TOO_LARGE');
  let blob;
  try {
    blob = DriveApp.getFileById(_text_(fileId)).getBlob().setName(_text_(fileName));
  } catch (err) {
    const error = new Error('El PPTX exacto ya no está disponible en Google Drive.');
    error.code = 'NOT_FOUND';
    throw error;
  }
  const bytes = blob.getBytes();
  _assert_(bytes.length === Number(expectedBytes) &&
    _sha256Bytes_(bytes) === _text_(expectedSha256),
  'El PPTX conservado no coincide con el artefacto importado.', 'SNAPSHOT_CORRUPT');
  return blob;
}

function _importExactReportArtifacts_(reportBlob, projection, folder) {
  const report = projection.report;
  _assert_(Number(report.bytes) <= RADAR.maxReportBytes,
    'El PPTX supera 20 MB y no puede publicarse y adjuntarse con garantías.',
    'ATTACHMENT_TOO_LARGE');
  const fileName = _sanitizeText_(report.fileName, 240);
  const slidesName = fileName.replace(/\.pptx$/i, '');
  let pptxId = '';
  let slidesId = '';
  try {
    const pptx = Drive.Files.create({
      name: fileName,
      mimeType: REPORT_PPTX_MIME,
      parents: [_text_(folder.id)],
      appProperties: {
        radarArtifact: 'period-followup-pptx',
        radarFactsSha256: _text_(projection.factsSha256)
      }
    }, reportBlob.setName(fileName).setContentType(REPORT_PPTX_MIME), {
      supportsAllDrives: true,
      fields: 'id,name,mimeType,webViewLink,size'
    });
    pptxId = _text_(pptx.id);
    _assert_(pptxId && _text_(pptx.mimeType) === REPORT_PPTX_MIME,
      'No se pudo conservar el PPTX original.', 'REPORT_GENERATION_FAILED');
    const slides = Drive.Files.create({
      name: slidesName,
      mimeType: REPORT_PRESENTATION_MIME,
      parents: [_text_(folder.id)],
      appProperties: {
        radarArtifact: 'period-followup-google-slides',
        radarFactsSha256: _text_(projection.factsSha256)
      }
    }, reportBlob.setName(fileName).setContentType(REPORT_PPTX_MIME), {
      supportsAllDrives: true,
      fields: 'id,name,mimeType,webViewLink'
    });
    slidesId = _text_(slides.id);
    _assert_(slidesId && _text_(slides.mimeType) === REPORT_PRESENTATION_MIME,
      'Drive no pudo convertir el PPTX a Google Slides.', 'REPORT_GENERATION_FAILED');
    const deck = SlidesApp.openById(slidesId);
    const slideCount = deck.getSlides().length;
    deck.saveAndClose();
    _assert_(slideCount === Number(report.slideCount),
      'La conversión a Google Slides no conserva todas las diapositivas del PPTX.',
      'REPORT_GENERATION_FAILED');
    return {
      reportName: fileName,
      pptxFileId: pptxId,
      pptxSha256: _text_(report.sha256),
      pptxBytes: Number(report.bytes),
      slidesFileId: slidesId,
      slidesUrl: _text_(slides.webViewLink) || _periodPresentationUrl_(slidesId),
      slideCount: slideCount
    };
  } catch (err) {
    _trashDriveFileQuietly_(pptxId);
    _trashDriveFileQuietly_(slidesId);
    if (err && err.code) throw err;
    const error = new Error('No se pudo publicar el PPTX exacto en Google Drive.');
    error.code = 'REPORT_GENERATION_FAILED';
    throw error;
  }
}
