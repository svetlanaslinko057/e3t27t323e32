/**
 * Reusable proof uploader. Drag/drop OR file picker.
 * Validates: PDF/PNG/JPG/JPEG, max 10MB.
 */
import { useCallback, useRef, useState } from 'react';
import { lumen, lumenError } from '@/lib/lumenApi';
import { Upload, FileCheck2, AlertTriangle, Loader2 } from 'lucide-react';

const ACCEPT = '.pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg';
const MAX_BYTES = 10 * 1024 * 1024;

export default function ProofUploader({ transferId, t, onUploaded }) {
  const [drag, setDrag] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [note, setNote] = useState('');
  const [err, setErr] = useState('');
  const [ok, setOk] = useState('');
  const inputRef = useRef(null);

  const doUpload = useCallback(async (file) => {
    setErr(''); setOk('');
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setErr(t('documents.upload.err') + ' (>10MB)');
      return;
    }
    const fd = new FormData();
    fd.append('file', file);
    if (note) fd.append('note', note);
    setUploading(true);
    try {
      const r = await lumen.post(
        `/lumen/institutional/rails/transfers/${transferId}/proof`,
        fd,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      );
      setOk(t('documents.upload.ok'));
      setNote('');
      if (onUploaded) onUploaded(r.data);
      if (inputRef.current) inputRef.current.value = '';
    } catch (e) {
      setErr(lumenError(e, t('documents.upload.err')));
    } finally {
      setUploading(false);
    }
  }, [transferId, note, onUploaded, t]);

  const onDrop = useCallback((e) => {
    e.preventDefault();
    setDrag(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) doUpload(f);
  }, [doUpload]);

  return (
    <div className="space-y-3" data-testid={`proof-uploader-${transferId}`}>
      <input
        type="text"
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder={t('documents.upload.note')}
        className="w-full px-3 py-2 rounded-lg border border-border bg-background text-sm"
        data-testid="proof-note-input"
      />
      <label
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center justify-center gap-2 px-4 py-8 rounded-xl border-2 border-dashed cursor-pointer transition-colors ${
          drag ? 'border-signal bg-signal/5' : 'border-border bg-muted/30 hover:bg-muted/50'
        }`}
        data-testid="proof-dropzone"
      >
        <Upload className="w-6 h-6 text-muted-foreground" />
        <span className="text-sm font-medium">{t('documents.upload.drag')}</span>
        <span className="text-xs text-muted-foreground">{t('documents.upload.formats')}</span>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          onChange={(e) => doUpload(e.target.files?.[0])}
          className="hidden"
          data-testid="proof-file-input"
        />
      </label>
      {uploading && (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" /> {t('documents.upload.uploading')}
        </div>
      )}
      {ok && (
        <div className="flex items-center gap-2 text-sm text-emerald-700 dark:text-emerald-300">
          <FileCheck2 className="w-4 h-4" /> {ok}
        </div>
      )}
      {err && (
        <div className="flex items-center gap-2 text-sm text-rose-700 dark:text-rose-300">
          <AlertTriangle className="w-4 h-4" /> {err}
        </div>
      )}
    </div>
  );
}
