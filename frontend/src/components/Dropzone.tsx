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
    if (selected) {
      onFileSelected(selected);
    }
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
      <div className="dropzone__icon" aria-hidden="true">
        <FileArchive size={34} />
      </div>
      <div>
        <h1>Maquetador MLS automático</h1>
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
