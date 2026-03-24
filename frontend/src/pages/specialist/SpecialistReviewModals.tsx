import { useState } from 'react';
import { AlertTriangle, CheckCircle, Edit2, Lock, MessageSquare, PenLine } from 'lucide-react';

import { filesFromInput } from '../../utils/control';

const MAX_FILE_SIZE_MB = 10;
const MAX_FILE_SIZE = MAX_FILE_SIZE_MB * 1024 * 1024;

interface ApproveConfirmModalProps {
  open: boolean;
  actionLoading: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ApproveConfirmModal({
  open,
  actionLoading,
  onCancel,
  onConfirm,
}: ApproveConfirmModalProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6" role="dialog" aria-modal="true" aria-labelledby="approve-confirm-title">
        <div className="flex items-center gap-3 text-[#007f3b] mb-4">
          <CheckCircle className="w-8 h-8" />
          <h2 id="approve-confirm-title" className="text-xl font-bold">Approve Response</h2>
        </div>
        <p className="text-gray-600 mb-6">
          By approving, you confirm that the AI-generated response is clinically accurate
          and appropriate to send to the GP.
        </p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={actionLoading}
            className="px-4 py-2 bg-[#007f3b] text-white rounded-lg font-medium hover:bg-[#00662f] disabled:opacity-50"
          >
            {actionLoading ? 'Approving…' : 'Confirm Approval'}
          </button>
        </div>
      </div>
    </div>
  );
}

interface ApproveWithCommentModalProps {
  open: boolean;
  actionLoading: boolean;
  approveComment: string;
  onChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ApproveWithCommentModal({
  open,
  actionLoading,
  approveComment,
  onChange,
  onCancel,
  onConfirm,
}: ApproveWithCommentModalProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6" role="dialog" aria-modal="true" aria-labelledby="approve-comment-title">
        <div className="flex items-center gap-3 text-[var(--nhs-blue)] mb-4">
          <MessageSquare className="w-8 h-8" />
          <h2 id="approve-comment-title" className="text-xl font-bold">Approve with Comment</h2>
        </div>
        <p className="text-gray-600 mb-4">
          Your comment will be sent as a message to the GP before the consultation is approved.
        </p>
        <textarea
          value={approveComment}
          onChange={(e) => onChange(e.target.value)}
          rows={4}
          autoFocus
          className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent resize-none mb-6"
          placeholder="Add your comment for the GP..."
        />
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!approveComment.trim() || actionLoading}
            className="px-4 py-2 bg-[var(--nhs-blue)] text-white rounded-lg font-medium hover:bg-[var(--nhs-dark-blue)] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {actionLoading ? 'Approving…' : 'Send & Approve'}
          </button>
        </div>
      </div>
    </div>
  );
}

interface RequestChangesModalProps {
  open: boolean;
  actionLoading: boolean;
  rejectReason: string;
  onChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}

export function RequestChangesModal({
  open,
  actionLoading,
  rejectReason,
  onChange,
  onCancel,
  onConfirm,
}: RequestChangesModalProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6" role="dialog" aria-modal="true" aria-labelledby="request-changes-title">
        <div className="flex items-center gap-3 text-amber-600 mb-4">
          <AlertTriangle className="w-8 h-8" />
          <h2 id="request-changes-title" className="text-xl font-bold">Request Changes</h2>
        </div>
        <p className="text-gray-600 mb-4">
          Please describe what changes are needed to the AI response:
        </p>
        <textarea
          value={rejectReason}
          onChange={(e) => onChange(e.target.value)}
          rows={4}
          autoFocus
          className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--nhs-blue)] focus:border-transparent resize-none mb-6"
          placeholder="Describe the required changes..."
        />
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!rejectReason.trim() || actionLoading}
            className="px-4 py-2 bg-amber-600 text-white rounded-lg font-medium hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {actionLoading ? 'Submitting…' : 'Submit Feedback'}
          </button>
        </div>
      </div>
    </div>
  );
}

interface ManualResponseModalProps {
  open: boolean;
  actionLoading: boolean;
  manualResponseContent: string;
  manualResponseSources: string;
  manualResponseFiles: File[];
  onContentChange: (value: string) => void;
  onSourcesChange: (value: string) => void;
  onFilesChange: (files: File[]) => void;
  onCancel: () => void;
  onConfirm: () => void;
}

export function ManualResponseModal({
  open,
  actionLoading,
  manualResponseContent,
  manualResponseSources,
  manualResponseFiles,
  onContentChange,
  onSourcesChange,
  onFilesChange,
  onCancel,
  onConfirm,
}: ManualResponseModalProps) {
  const [fileError, setFileError] = useState('');

  if (!open) {
    return null;
  }

  const handleFilesChange = (files: File[]) => {
    const oversized = files.filter(f => f.size > MAX_FILE_SIZE);
    if (oversized.length > 0) {
      setFileError(`File(s) exceed the ${MAX_FILE_SIZE_MB} MB limit: ${oversized.map(f => f.name).join(', ')}`);
      return;
    }
    setFileError('');
    onFilesChange(files);
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6" role="dialog" aria-modal="true" aria-labelledby="manual-response-title">
        <div className="flex items-center gap-3 text-purple-600 mb-4">
          <PenLine className="w-8 h-8" />
          <h2 id="manual-response-title" className="text-xl font-bold">Manual Response</h2>
        </div>
        <p className="text-gray-600 mb-4">
          The AI response will be rejected. Type your replacement response below —
          it will be sent to the GP as a specialist message.
        </p>
        <textarea
          value={manualResponseContent}
          onChange={(e) => onContentChange(e.target.value)}
          rows={6}
          autoFocus
          className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
          placeholder="Type your replacement response..."
        />
        <div className="mt-4 mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Sources <span className="text-gray-400 font-normal">(optional — one per line)</span>
          </label>
          <textarea
            value={manualResponseSources}
            onChange={(e) => onSourcesChange(e.target.value)}
            rows={3}
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent resize-none"
            placeholder="e.g. NICE NG228, BSR guideline 2023"
          />
        </div>
        <div className="mt-4 mb-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Attach files <span className="text-gray-400 font-normal">(optional — max {MAX_FILE_SIZE_MB} MB each)</span>
          </label>
          <input
            type="file"
            multiple
            accept=".pdf,.txt,.md,.rtf,.doc,.docx,.csv,.json,.xml"
            onChange={(e) => handleFilesChange(filesFromInput(e.target.files))}
            className="block w-full text-sm text-gray-600 file:mr-4 file:rounded-lg file:border-0 file:bg-purple-50 file:px-4 file:py-2 file:font-medium file:text-purple-700 hover:file:bg-purple-100"
          />
          {fileError && (
            <p className="mt-2 text-sm text-red-600">{fileError}</p>
          )}
          {!fileError && manualResponseFiles.length > 0 && (
            <div className="mt-2 space-y-2">
              <p className="text-sm text-gray-500">
                {manualResponseFiles.length} file(s) will be uploaded to this chat before the manual response is sent.
              </p>
              <div className="flex flex-wrap gap-2">
                {manualResponseFiles.map((file) => (
                  <span
                    key={`${file.name}-${file.size}`}
                    className="inline-flex items-center rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-700"
                  >
                    {file.name}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!manualResponseContent.trim() || actionLoading}
            className="px-4 py-2 bg-purple-600 text-white rounded-lg font-medium hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {actionLoading ? 'Sending…' : 'Send Manual Response'}
          </button>
        </div>
      </div>
    </div>
  );
}

interface CloseApproveModalProps {
  open: boolean;
  actionLoading: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}

export function CloseApproveModal({
  open,
  actionLoading,
  onCancel,
  onConfirm,
}: CloseApproveModalProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6" role="dialog" aria-modal="true" aria-labelledby="close-approve-title">
        <div className="flex items-center gap-3 text-[#007f3b] mb-4">
          <Lock className="w-8 h-8" />
          <h2 id="close-approve-title" className="text-xl font-bold">Close &amp; Approve Consultation</h2>
        </div>
        <p className="text-gray-600 mb-6">
          This will close the consultation and mark it as approved. The GP will be
          notified that the review is complete. This action cannot be undone.
        </p>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={actionLoading}
            className="px-4 py-2 bg-[#007f3b] text-white rounded-lg font-medium hover:bg-[#00662f] disabled:opacity-50"
          >
            {actionLoading ? 'Closing…' : 'Confirm Close & Approve'}
          </button>
        </div>
      </div>
    </div>
  );
}

interface EditResponseModalProps {
  open: boolean;
  actionLoading: boolean;
  editedContent: string;
  editedSources: string;
  feedback: string;
  onContentChange: (value: string) => void;
  onSourcesChange: (value: string) => void;
  onFeedbackChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}

export function EditResponseModal({
  open,
  actionLoading,
  editedContent,
  editedSources,
  feedback,
  onContentChange,
  onSourcesChange,
  onFeedbackChange,
  onCancel,
  onConfirm,
}: EditResponseModalProps) {
  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6" role="dialog" aria-modal="true" aria-labelledby="edit-response-title">
        <div className="flex items-center gap-3 text-indigo-600 mb-4">
          <Edit2 className="w-8 h-8" />
          <h2 id="edit-response-title" className="text-xl font-bold">Edit Response</h2>
        </div>
        <p className="text-gray-600 mb-4">
          Edit the AI-generated response below. Your changes will replace the
          original content and be sent to the GP.
        </p>
        <textarea
          value={editedContent}
          onChange={(e) => onContentChange(e.target.value)}
          rows={6}
          autoFocus
          className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
          placeholder="Edit the response..."
        />
        <div className="mt-4">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Sources
          </label>
          <textarea
            value={editedSources}
            onChange={(e) => onSourcesChange(e.target.value)}
            rows={4}
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
            placeholder="Optional. Add one source per line."
          />
        </div>
        <div className="mt-4 mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">
            Feedback
          </label>
          <textarea
            value={feedback}
            onChange={(e) => onFeedbackChange(e.target.value)}
            rows={3}
            className="w-full px-4 py-3 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent resize-none"
            placeholder="Optional. Explain what you changed and why."
          />
        </div>
        <div className="flex gap-3 justify-end">
          <button
            onClick={onCancel}
            className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 font-medium hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={!editedContent.trim() || actionLoading}
            className="px-4 py-2 bg-indigo-600 text-white rounded-lg font-medium hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {actionLoading ? 'Saving…' : 'Save Edited Response'}
          </button>
        </div>
      </div>
    </div>
  );
}
