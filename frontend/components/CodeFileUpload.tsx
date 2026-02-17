"use client";

import { useState, useCallback, useRef } from "react";
import styles from "./CodeFileUpload.module.css";

interface CodeFile {
  name: string;
  content: string;
  size: number;
}

interface CodeFileUploadProps {
  onFilesChange: (files: Record<string, string>) => void;
  disabled?: boolean;
}

export default function CodeFileUpload({
  onFilesChange,
  disabled = false,
}: CodeFileUploadProps) {
  const [files, setFiles] = useState<CodeFile[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    async (fileList: FileList) => {
      const newFiles: CodeFile[] = [];

      for (let i = 0; i < fileList.length; i++) {
        const file = fileList[i];

        // Only accept Python files for now
        if (!file.name.endsWith(".py")) {
          continue;
        }

        try {
          const content = await file.text();
          newFiles.push({
            name: file.name,
            content,
            size: file.size,
          });
        } catch (error) {
          console.error(`Failed to read ${file.name}:`, error);
        }
      }

      const updatedFiles = [...files, ...newFiles];
      setFiles(updatedFiles);

      // Convert to API format: { filename: content }
      const filesDict = updatedFiles.reduce(
        (acc, f) => {
          acc[f.name] = f.content;
          return acc;
        },
        {} as Record<string, string>,
      );

      onFilesChange(filesDict);
    },
    [files, onFilesChange],
  );

  const handleDragOver = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      if (!disabled) {
        setIsDragging(true);
      }
    },
    [disabled],
  );

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      setIsDragging(false);

      if (disabled) return;

      const { files: droppedFiles } = e.dataTransfer;
      if (droppedFiles.length > 0) {
        handleFiles(droppedFiles);
      }
    },
    [disabled, handleFiles],
  );

  const handleFileSelect = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const { files: selectedFiles } = e.target;
      if (selectedFiles && selectedFiles.length > 0) {
        handleFiles(selectedFiles);
      }
    },
    [handleFiles],
  );

  const handleBrowseClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const removeFile = useCallback(
    (fileName: string) => {
      const updatedFiles = files.filter((f) => f.name !== fileName);
      setFiles(updatedFiles);

      const filesDict = updatedFiles.reduce(
        (acc, f) => {
          acc[f.name] = f.content;
          return acc;
        },
        {} as Record<string, string>,
      );

      onFilesChange(filesDict);
    },
    [files, onFilesChange],
  );

  const clearAll = useCallback(() => {
    setFiles([]);
    onFilesChange({});
  }, [onFilesChange]);

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <label className={styles.label}>
          📁 Code Files <span className={styles.optional}>(Optional)</span>
        </label>
        <p className={styles.description}>
          Upload Python source files to extract real enums, validators, and
          business rules
        </p>
      </div>

      <div
        className={`${styles.dropzone} ${isDragging ? styles.dropzoneDragging : ""} ${disabled ? styles.dropzoneDisabled : ""}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".py"
          onChange={handleFileSelect}
          style={{ display: "none" }}
          disabled={disabled}
        />

        <div className={styles.dropzoneContent}>
          <div className={styles.dropzoneIcon}>📄</div>
          <div className={styles.dropzoneText}>
            <strong>Drop Python files here</strong> or{" "}
            <button
              type="button"
              className={styles.browseBtn}
              onClick={handleBrowseClick}
              disabled={disabled}
            >
              browse
            </button>
          </div>
          <div className={styles.dropzoneHint}>
            Supports: .py files (Pydantic models, Enums, SQLAlchemy)
          </div>
        </div>
      </div>

      {files.length > 0 && (
        <div className={styles.fileList}>
          <div className={styles.fileListHeader}>
            <span className={styles.fileCount}>
              {files.length} file{files.length !== 1 ? "s" : ""} uploaded
            </span>
            <button
              type="button"
              className={styles.clearBtn}
              onClick={clearAll}
              disabled={disabled}
            >
              Clear all
            </button>
          </div>

          {files.map((file) => (
            <div key={file.name} className={styles.fileItem}>
              <div className={styles.fileIcon}>🐍</div>
              <div className={styles.fileInfo}>
                <div className={styles.fileName}>{file.name}</div>
                <div className={styles.fileSize}>{formatSize(file.size)}</div>
              </div>
              <button
                type="button"
                className={styles.removeBtn}
                onClick={() => removeFile(file.name)}
                disabled={disabled}
                title="Remove file"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {files.length > 0 && (
        <div className={styles.benefit}>
          ✨ <strong>Code analysis will extract:</strong> Enums, validators,
          business rules, and model constraints
        </div>
      )}
    </div>
  );
}
