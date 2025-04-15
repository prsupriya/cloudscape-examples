import { ChangeEvent, useState } from 'react';
import { Button, SpaceBetween } from "@cloudscape-design/components";
import styles from "../../styles/chat-ui.module.scss";

export interface FileUploadProps {
  onFileSelect?: (file: File) => void;
  onFileRemove?: () => void;
  acceptedFileTypes?: string;
  maxFileSizeMB?: number;
}

export default function FileUploadComponent({
  onFileSelect,
  onFileRemove,
  acceptedFileTypes = "image/*,.pdf,.doc,.docx",
  maxFileSizeMB = 10
}: FileUploadProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [error, setError] = useState<string>("");

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    setError("");

    if (file) {
      // Check file size
      if (file.size > maxFileSizeMB * 1024 * 1024) {
        setError(`File size must be less than ${maxFileSizeMB}MB`);
        return;
      }

      setSelectedFile(file);
      onFileSelect?.(file);
    }
  };

  const handleRemoveFile = () => {
    setSelectedFile(null);
    setError("");
    onFileRemove?.();
  };

  return (
    <div className={styles.fileUploadContainer}>
      <SpaceBetween direction="horizontal" size="xs">
        <input
          type="file"
          onChange={handleFileChange}
          accept={acceptedFileTypes}
          style={{ display: 'block' }}
          id="file-upload"
        />
        <label htmlFor="file-upload">
          <Button
            iconName="upload"
            variant="inline-icon"
            formAction="none"
          >
            {selectedFile ? selectedFile.name : "Attach file"}
          </Button>
        </label>
        {selectedFile && (
          <Button
            iconName="close"
            variant="inline-icon"
            onClick={handleRemoveFile}
            formAction="none"
          />
        )}
      </SpaceBetween>
      {error && <div className={styles.errorText}>{error}</div>}
    </div>
  );
}
