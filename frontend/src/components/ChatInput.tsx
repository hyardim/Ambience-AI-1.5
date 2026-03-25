import { useEffect, useRef, useState } from 'react';
import { Send, Paperclip, MoreVertical } from 'lucide-react';

const CHAT_UPLOAD_ACCEPT =
  '.pdf,.txt,.md,.rtf,.doc,.docx,.csv,.json,.xml';

interface ChatInputProps {
  onSendMessage: (message: string, files?: File[]) => void;
  placeholder?: string;
  disabled?: boolean;
  existingFileNames?: string[];
}

export function ChatInput({ onSendMessage, placeholder = 'Type your message here...', disabled = false, existingFileNames = [] }: ChatInputProps) {
  const [message, setMessage] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [duplicateNotice, setDuplicateNotice] = useState<string>('');
  const filesRef = useRef<File[]>([]);
  const duplicateNoticeTimerRef = useRef<number | null>(null);

  useEffect(() => () => {
    if (duplicateNoticeTimerRef.current !== null) {
      window.clearTimeout(duplicateNoticeTimerRef.current);
    }
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (message.trim() || filesRef.current.length > 0) {
      onSendMessage(message, filesRef.current);
      setMessage('');
      filesRef.current = [];
      setFiles([]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const currentNames = new Set([
        ...existingFileNames,
        ...filesRef.current.map(f => f.name),
      ]);
      const selected = Array.from(e.target.files);
      const duplicates = selected.filter(f => currentNames.has(f.name));
      const incoming = selected.filter(f => !currentNames.has(f.name));
      if (duplicates.length > 0) {
        if (duplicateNoticeTimerRef.current !== null) {
          window.clearTimeout(duplicateNoticeTimerRef.current);
        }
        setDuplicateNotice(
          `Already in this chat: ${duplicates.map(f => f.name).join(', ')}`
        );
        duplicateNoticeTimerRef.current = window.setTimeout(() => {
          setDuplicateNotice('');
          duplicateNoticeTimerRef.current = null;
        }, 4000);
      } else {
        setDuplicateNotice('');
      }
      filesRef.current = [...filesRef.current, ...incoming];
      setFiles([...filesRef.current]);
      // Reset input value so the same file can be picked again later
      e.target.value = '';
    }
  };

  const removeFile = (index: number) => {
    filesRef.current = filesRef.current.filter((_, i) => i !== index);
    setFiles([...filesRef.current]);
  };

  return (
    <form onSubmit={handleSubmit} className="border-t border-gray-200 bg-white p-4 sm:p-6">
      <p className="text-xs text-gray-400 mb-2">For best results, ask specific clinical questions about a condition or treatment.</p>
      {duplicateNotice && (
        <p className="mb-2 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
          {duplicateNotice}
        </p>
      )}
      {files.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {files.map((file, index) => (
            <div key={index} className="flex items-center gap-2 bg-gray-100 px-3 py-1 rounded-full text-sm">
              <span className="truncate max-w-32">{file.name}</span>
              <button
                type="button"
                onClick={() => removeFile(index)}
                aria-label={`Remove ${file.name}`}
                className="text-gray-500 hover:text-gray-700"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2 sm:gap-3">
        <input
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={placeholder}
          disabled={disabled}
          className="flex-1 px-3 sm:px-4 py-2 sm:py-3 border border-gray-300 rounded-lg text-sm sm:text-base focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent disabled:bg-gray-100 disabled:cursor-not-allowed"
        />

        {/* File input triggered natively via label — no JS .click() needed */}
        <label
          htmlFor="chat-file-input"
          aria-label="Attach files"
          aria-disabled={disabled}
          className={`p-3 rounded-lg transition-colors cursor-pointer ${
            disabled
              ? 'text-gray-300 cursor-not-allowed'
              : 'text-gray-500 hover:text-[var(--nhs-blue)] hover:bg-gray-100'
          }`}
        >
          <Paperclip className="w-5 h-5" />
        </label>
        <input
          id="chat-file-input"
          type="file"
          onChange={handleFileChange}
          multiple
          accept={CHAT_UPLOAD_ACCEPT}
          disabled={disabled}
          className="hidden"
        />

        <button
          type="submit"
          aria-label="Send message"
          disabled={disabled || (!message.trim() && files.length === 0)}
          className="p-3 bg-[var(--nhs-blue)] text-white rounded-lg hover:bg-[var(--nhs-dark-blue)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Send className="w-5 h-5" />
        </button>

        <button
          type="button"
          aria-label="More options"
          className="p-3 text-gray-500 hover:text-[var(--nhs-blue)] hover:bg-gray-100 rounded-lg transition-colors"
        >
          <MoreVertical className="w-5 h-5" />
        </button>
      </div>
    </form>
  );
}
