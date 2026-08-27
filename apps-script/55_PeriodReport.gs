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
    _setConfig_(
      'REPORT_DRIVE_FOLDER',
      descriptor,
      'json',
      'Carpeta compartida para PPTX y presentaciones nativas de Google',
      user.email
    );
    return descriptor;
  });
}

function _reportDriveFolderSetting_() {
  const descriptor = (_getConfigMap_() || {}).REPORT_DRIVE_FOLDER;
  if (!descriptor || typeof descriptor !== 'object' || Array.isArray(descriptor)) return null;
  const id = _text_(descriptor.id);
  if (!/^[A-Za-z0-9_-]{10,}$/.test(id)) return null;
  return {
    id: id,
    reference: 'folder:' + id,
    name: _sanitizeText_(descriptor.name, 240) || 'Carpeta de informes',
    url: _reportFolderUrl_(id),
    driveId: _text_(descriptor.driveId),
    kind: _text_(descriptor.kind) || 'folder',
    selectable: true,
    isRoot: descriptor.isRoot === true
  };
}

function _configuredReportDriveFolder_() {
  const setting = _reportDriveFolderSetting_();
  _assert_(setting,
    'Configura primero la carpeta de informes en Administración.', 'DRIVE_FOLDER_INVALID');
  const folder = _reportDriveFolder_(setting.id);
  _assert_(!folder.capabilities || folder.capabilities.canAddChildren !== false,
    'No tienes permiso para publicar informes en la carpeta configurada.', 'DRIVE_FOLDER_INVALID');
  return folder;
}

function _importExactReportArtifacts_(reportBlob, projection, folder) {
  const report = projection.report;
  _assert_(Number(report.bytes) <= RADAR.maxReportBytes,
    'El PPTX supera 20 MB y no puede publicarse con garantías.',
    'TRANSFER_TOO_LARGE');
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
