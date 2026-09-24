import { FileArchive, Upload } from "lucide-react";
import { useRef, useState } from "react";

interface DropzoneProps {
  file: File | null;
  disabled: boolean;
  onFileSelected: (file: File) => void;
  onSubmit: () => void;
}

export function Dropzone({ file, disabled, onFileSelected, onSubmit }: DropzoneProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [dragging, setDragging] = useState(false);

  function handleFiles(files: FileList | null) {
    const selected = files?.[0];
    if (!selected) return;
    
    const allowedTypes = [
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/zip'
    ];
    const allowedExtensions = ['.docx', '.zip'];
    
    const hasValidType = allowedTypes.includes(selected.type);
    const hasValidExtension = allowedExtensions.some(ext => selected.name.toLowerCase().endsWith(ext));
    
    if (!hasValidType && !hasValidExtension) {
      alert('Solo se permiten archivos .docx o .zip');
      return;
    }
    
    const maxSize = 100 * 1024 * 1024;
    if (selected.size > maxSize) {
      alert('El archivo no puede superar 100MB');
      return;
    }
    
    onFileSelected(selected);
  }

  return (
    <section
      className={`dropzone ${dragging ? "dropzone--active" : ""}`}
      onDragOver={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        handleFiles(event.dataTransfer.files);
      }}
    >
      <div className="brand-lockup">
        <PhoenixMark />
        <div>
          <span className="brand-eyebrow">Hecho por Fénix</span>
          <h1>Maquetador MLS automático</h1>
        </div>
      </div>
      <div>
        <p>Arrastra el DOCX o ZIP del artículo, o selecciónalo desde el equipo.</p>
      </div>
      {file ? (
        <div className="selected-file">
          <FileArchive size={18} />
          <span>{file.name}</span>
        </div>
      ) : null}
      <div className="dropzone__actions">
        <button type="button" className="button button--secondary" onClick={() => inputRef.current?.click()}>
          <Upload size={17} />
          Seleccionar archivo
        </button>
        <button type="button" className="button button--primary" disabled={!file || disabled} onClick={onSubmit}>
          Maquetar artículo
        </button>
      </div>
      <input
        ref={inputRef}
        type="file"
        accept=".docx,.zip,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/zip"
        hidden
        onChange={(event) => handleFiles(event.target.files)}
      />
    </section>
  );
}

function PhoenixMark() {
  return (
    <svg className="phoenix-mark" viewBox="0 0 96 96" role="img" aria-label="Fénix">
      <defs>
        <linearGradient id="phoenixGradient" x1="48" x2="48" y1="8" y2="88" gradientUnits="userSpaceOnUse">
          <stop stopColor="#ffca3a" />
          <stop offset="0.52" stopColor="#f97316" />
          <stop offset="1" stopColor="#7f1d1d" />
        </linearGradient>
      </defs>
      <path
        fill="url(#phoenixGradient)"
        d="M47.9 15.2c4.8 8.4 3 16.4-3.1 21.7 8.1-1.3 15.3-6.7 21.2-16.8 1.8 11.8-2.9 21.1-13 25.2 10.9.4 20.8-3.7 31.1-13.6-2.2 12.5-10.3 21-24.5 25.6 8.6 1.5 16.8.9 25.2-2.6-6.5 9-16.2 13.8-29.8 13.3l7.4 17.9-14.5-12.6-14.4 12.6L41 68c-13.4.3-23-4.4-29.6-13.3 8.3 3.5 16.5 4.1 25 2.6-14-4.6-22.1-13.1-24.3-25.6 10.2 9.9 20.1 14 30.9 13.6-9.9-4.1-14.6-13.4-12.9-25.2 5.9 10.1 13 15.5 21 16.8-6.1-5.3-7.9-13.3-3.2-21.7Z"
      />
      <path
        fill="#fff"
        d="M48.1 38.8c6.1 0 11.1 4.9 11.1 11.1 0 3.4-1.6 6.5-4.2 8.6l5.6 13.4-12.6-11-12.4 11 5.6-13.4a11 11 0 0 1-4.1-8.6c0-6.2 4.9-11.1 11-11.1Zm6.2 9.2c-3.2-2.5-6.8-2.6-10.2-.5l-2.4 1.5 2.6-5.4c-3 1.3-5 4.1-5 7.5 0 4.5 3.7 8.2 8.7 8.2 5.1 0 8.9-3.7 8.9-8.2 0-1.1-.2-2.1-.6-3.1h-2Z"
        opacity="0.92"
      />
    </svg>
  );
}
