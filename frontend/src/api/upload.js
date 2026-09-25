// src/api/upload.js
// Presigned-POST file upload via XHR (fetch has no upload progress events).
// Per 04-frontend-dashboard.md §4.2 and Design.md §5.1.

export class UploadError extends Error {
  constructor(status, kind) {
    super(kind);
    this.name = 'UploadError';
    this.status = status;
    this.kind = kind; // 'expired' | 'too_large' | 'rejected' | 'network'
  }
}

/**
 * Upload a File to S3 using a presigned POST.
 * The `file` field MUST be last in the FormData (S3 POST requirement).
 * @param {{ url: string, fields: Record<string,string> }} presigned
 * @param {File} file
 * @param {(progress: number) => void} onProgress  0..1
 * @returns {Promise<void>}
 */
export function uploadFile({ url, fields }, file, onProgress) {
  return new Promise((resolve, reject) => {
    const form = new FormData();
    // All policy fields first
    Object.entries(fields).forEach(([k, v]) => form.append(k, v));
    // 'file' MUST be last
    form.append('file', file);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress(e.loaded / e.total);
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress(1);
        return resolve();
      }
      const body = xhr.responseText || '';
      const kind =
        /Policy expired|Request has expired/i.test(body)
          ? 'expired'
          : /EntityTooLarge/i.test(body)
          ? 'too_large'
          : 'rejected';
      reject(new UploadError(xhr.status, kind));
    };

    xhr.onerror = () => reject(new UploadError(0, 'network'));
    xhr.send(form);
  });
}
