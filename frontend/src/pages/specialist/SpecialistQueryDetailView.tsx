import type { ComponentType, RefObject } from 'react';
import {
  ArrowLeft,
  ClipboardCheck,
  Lock,
  Loader2,
  MessageSquare,
  Paperclip,
  PenLine,
  RefreshCw,
  UserMinus,
  UserPlus,
} from 'lucide-react';

import { SeverityBadge, StatusBadge } from '../../components/Badges';
import { ChatInput } from '../../components/ChatInput';
import { ChatMessage } from '../../components/ChatMessage';
import { Header } from '../../components/Header';
import { PatientContextBanner } from '../../components/PatientContextBanner';
import type { Message } from '../../types';
import type { BackendChatWithMessages } from '../../types/api';
import { orFallback } from '../../utils/value';
import {
  ApproveConfirmModal,
  ApproveWithCommentModal,
  CloseApproveModal,
  EditResponseModal,
  ManualResponseModal,
  RequestChangesModal,
  SendCommentModal,
  UnassignConfirmModal,
} from './SpecialistReviewModals';

interface TerminalState {
  label: string;
  className: string;
  icon: ComponentType<{ className?: string }>;
}

interface SpecialistQueryDetailViewProps {
  username: string | null;
  logout: () => void;
  chat: BackendChatWithMessages | null;
  messages: Message[];
  loading: boolean;
  error: string;
  actionLoading: boolean;
  canAssign: boolean;
  canReview: boolean;
  isTerminal: boolean;
  hasPendingAIResponse: boolean;
  allAIReviewed: boolean;
  closeReviewTitle: string;
  terminalState: TerminalState;
  unreviewedAIIds: Set<string | number>;
  approveComment: string;
  rejectReason: string;
  manualResponseContent: string;
  manualResponseSources: string;
  manualResponseFiles: File[];
  editResponseContent: string;
  editResponseSources: string;
  editResponseFeedback: string;
  showEditResponseModal: boolean;
  showApproveConfirm: boolean;
  showApproveWithCommentModal: boolean;
  showRejectModal: boolean;
  showManualResponseModal: boolean;
  showCloseConfirm: boolean;
  messagesEndRef: RefObject<HTMLDivElement | null>;
  onBack: () => void;
  onAssign: () => void;
  onApprove: () => void;
  onApproveCommentChange: (value: string) => void;
  onApproveWithComment: () => void;
  onRejectReasonChange: (value: string) => void;
  onRequestChanges: () => void;
  onManualResponseContentChange: (value: string) => void;
  onManualResponseSourcesChange: (value: string) => void;
  onManualResponseFilesChange: (files: File[]) => void;
  onManualResponse: () => void;
  onEditResponseContentChange: (value: string) => void;
  onEditResponseSourcesChange: (value: string) => void;
  onEditResponseFeedbackChange: (value: string) => void;
  onEditResponse: () => void;
  onSendMessage: (content: string, files?: File[]) => void;
  onOpenApproveConfirm: (messageId: number | string) => void;
  onOpenApproveWithComment: (messageId: number | string) => void;
  onOpenRequestChanges: (messageId: number | string) => void;
  onOpenManualResponse: (messageId: number | string) => void;
  onOpenEditResponse: (messageId: number | string, currentContent: string) => void;
  onCloseAndApprove: () => void;
  onCloseApproveConfirm: () => void;
  onCloseApproveWithComment: () => void;
  onCloseRejectModal: () => void;
  onCloseManualResponseModal: () => void;
  onCloseEditResponseModal: () => void;
  onOpenCloseConfirm: () => void;
  onCloseCloseConfirm: () => void;
  // Consultation-level actions
  showConsultationRejectModal: boolean;
  consultationRejectReason: string;
  showSendCommentModal: boolean;
  commentContent: string;
  showUnassignConfirm: boolean;
  showConsultationManualResponseModal: boolean;
  consultationManualContent: string;
  consultationManualSources: string;
  consultationManualFiles: File[];
  onOpenConsultationRequestRevision: () => void;
  onConsultationRejectReasonChange: (value: string) => void;
  onConsultationRequestRevision: () => void;
  onCloseConsultationRejectModal: () => void;
  onOpenSendComment: () => void;
  onCommentContentChange: (value: string) => void;
  onSendComment: () => void;
  onCloseSendCommentModal: () => void;
  onOpenUnassignConfirm: () => void;
  onUnassign: () => void;
  onCloseUnassignConfirm: () => void;
  onOpenConsultationManualResponse: () => void;
  onConsultationManualContentChange: (value: string) => void;
  onConsultationManualSourcesChange: (value: string) => void;
  onConsultationManualFilesChange: (files: File[]) => void;
  onConsultationManualResponse: () => void;
  onCloseConsultationManualResponseModal: () => void;
}

function formatSpecialty(specialty: string | null): string {
  return specialty ? specialty.charAt(0).toUpperCase() + specialty.slice(1) : '—';
}

export function SpecialistQueryDetailView({
  username,
  logout,
  chat,
  messages,
  loading,
  error,
  actionLoading,
  canAssign,
  canReview,
  isTerminal,
  hasPendingAIResponse,
  terminalState,
  unreviewedAIIds,
  approveComment,
  rejectReason,
  manualResponseContent,
  manualResponseSources,
  manualResponseFiles,
  editResponseContent,
  editResponseSources,
  editResponseFeedback,
  showEditResponseModal,
  showApproveConfirm,
  showApproveWithCommentModal,
  showRejectModal,
  showManualResponseModal,
  showCloseConfirm,
  messagesEndRef,
  onBack,
  onAssign,
  onApprove,
  onApproveCommentChange,
  onApproveWithComment,
  onRejectReasonChange,
  onRequestChanges,
  onManualResponseContentChange,
  onManualResponseSourcesChange,
  onManualResponseFilesChange,
  onManualResponse,
  onEditResponseContentChange,
  onEditResponseSourcesChange,
  onEditResponseFeedbackChange,
  onEditResponse,
  onSendMessage,
  onOpenApproveConfirm,
  onOpenApproveWithComment,
  onOpenRequestChanges,
  onOpenManualResponse,
  onOpenEditResponse,
  onCloseAndApprove,
  onCloseApproveConfirm,
  onCloseApproveWithComment,
  onCloseRejectModal,
  onCloseManualResponseModal,
  onCloseEditResponseModal,
  onOpenCloseConfirm,
  onCloseCloseConfirm,
  showConsultationRejectModal,
  consultationRejectReason,
  showSendCommentModal,
  commentContent,
  showUnassignConfirm,
  showConsultationManualResponseModal,
  consultationManualContent,
  consultationManualSources,
  consultationManualFiles,
  onOpenConsultationRequestRevision,
  onConsultationRejectReasonChange,
  onConsultationRequestRevision,
  onCloseConsultationRejectModal,
  onOpenSendComment,
  onCommentContentChange,
  onSendComment,
  onCloseSendCommentModal,
  onOpenUnassignConfirm,
  onUnassign,
  onCloseUnassignConfirm,
  onOpenConsultationManualResponse,
  onConsultationManualContentChange,
  onConsultationManualSourcesChange,
  onConsultationManualFilesChange,
  onConsultationManualResponse,
  onCloseConsultationManualResponseModal,
}: SpecialistQueryDetailViewProps) {
  const hasGeneratingAIResponse = messages.some(
    (message) => message.senderType === 'ai' && message.isGenerating === true,
  );

  if (loading) {
    return (
      <div className="min-h-screen bg-[var(--nhs-page-bg)] flex flex-col">
        <Header userRole="specialist" userName={orFallback(username, 'Specialist User')} onLogout={logout} />
        <main className="flex-1 flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-[var(--nhs-blue)] animate-spin" />
        </main>
      </div>
    );
  }

  if (!chat) {
    return (
      <div className="min-h-screen bg-[var(--nhs-page-bg)] flex flex-col">
        <Header userRole="specialist" userName={orFallback(username, 'Specialist User')} onLogout={logout} />
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-gray-900 mb-2">Query not found</h1>
            {error && <p className="text-red-600 mb-4">{error}</p>}
            <button
              onClick={onBack}
              className="text-[var(--nhs-blue)] hover:text-[var(--nhs-dark-blue)] font-medium"
            >
              Back to Queries
            </button>
          </div>
        </main>
      </div>
    );
  }

  const TerminalStatusIcon = terminalState.icon;

  return (
    <div className="min-h-screen bg-[var(--nhs-page-bg)] flex flex-col">
      <Header userRole="specialist" userName={orFallback(username, 'Specialist User')} onLogout={logout} />

      <main className="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 flex flex-col">
        <button
          onClick={onBack}
          className="inline-flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-6"
        >
          <ArrowLeft className="w-5 h-5" />
          Back to Queries
        </button>

        <div className="bg-white rounded-xl shadow-sm flex-1 flex flex-col overflow-hidden">
          <div className="p-6 border-b border-gray-200">
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
              <div className="flex-1">
                <h1 className="text-xl font-bold text-gray-900 mb-2">
                  {chat.title || 'Untitled Consultation'}
                </h1>
                <div className="flex flex-wrap items-center gap-3 text-sm text-gray-600">
                  <span className="capitalize">{formatSpecialty(chat.specialty)}</span>
                  <span>·</span>
                  <span>
                    {new Date(chat.created_at).toLocaleDateString('en-GB', {
                      day: 'numeric', month: 'short', year: 'numeric',
                    })}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {chat.severity && <SeverityBadge severity={chat.severity} />}
                <StatusBadge status={chat.status} />
              </div>
            </div>

            {error && (
              <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                {error}
              </div>
            )}

            <div className="flex flex-wrap gap-3 mt-6 pt-4 border-t border-gray-200">
              {canAssign && (
                <button
                  onClick={onAssign}
                  disabled={actionLoading}
                  className="inline-flex items-center gap-2 bg-[var(--nhs-blue)] text-white px-4 py-2 rounded-lg font-medium hover:bg-[var(--nhs-dark-blue)] transition-colors disabled:opacity-50"
                >
                  <UserPlus className="w-5 h-5" />
                  {actionLoading ? 'Assigning…' : 'Assign to Me'}
                </button>
              )}

              {canReview && (
                <>
                  <button
                    onClick={onOpenCloseConfirm}
                    disabled={actionLoading}
                    className="inline-flex items-center gap-2 bg-[#007f3b] text-white px-4 py-2 rounded-lg font-medium hover:bg-[#00662f] transition-colors disabled:opacity-50"
                  >
                    <Lock className="w-5 h-5" />
                    Approve and Send
                  </button>
                  <button
                    onClick={onOpenConsultationRequestRevision}
                    disabled={actionLoading}
                    className="inline-flex items-center gap-2 bg-amber-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-amber-700 transition-colors disabled:opacity-50"
                  >
                    <RefreshCw className="w-5 h-5" />
                    Request Revision
                  </button>
                  <button
                    onClick={onOpenConsultationManualResponse}
                    disabled={actionLoading}
                    className="inline-flex items-center gap-2 bg-purple-600 text-white px-4 py-2 rounded-lg font-medium hover:bg-purple-700 transition-colors disabled:opacity-50"
                  >
                    <PenLine className="w-5 h-5" />
                    Replace with Manual Response
                  </button>
                  <button
                    onClick={onOpenSendComment}
                    disabled={actionLoading}
                    className="inline-flex items-center gap-2 bg-[var(--nhs-blue)] text-white px-4 py-2 rounded-lg font-medium hover:bg-[var(--nhs-dark-blue)] transition-colors disabled:opacity-50"
                  >
                    <MessageSquare className="w-5 h-5" />
                    Send Comment to GP
                  </button>
                  <button
                    onClick={onOpenUnassignConfirm}
                    disabled={actionLoading}
                    className="inline-flex items-center gap-2 bg-white text-gray-700 border border-gray-300 px-4 py-2 rounded-lg font-medium hover:bg-gray-50 transition-colors disabled:opacity-50"
                  >
                    <UserMinus className="w-5 h-5" />
                    Unassign
                  </button>
                </>
              )}

              {isTerminal && (
                <div className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium ${terminalState.className}`}>
                  <TerminalStatusIcon className="w-5 h-5" />
                  {terminalState.label}
                </div>
              )}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-6 space-y-6">
            <PatientContextBanner
              age={chat.patient_age}
              sex={chat.patient_gender}
              specialty={chat.specialty}
              severity={chat.severity}
              notes={chat.patient_notes}
            />

            {chat.files && chat.files.length > 0 && (
              <div className="rounded-xl border border-gray-200 bg-gray-50 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-600 mb-3">
                  Consultation Files
                </p>
                <div className="flex flex-wrap gap-2">
                  {chat.files.map((file) => (
                    <span
                      key={file.id}
                      className="inline-flex items-center gap-2 rounded-full bg-white px-3 py-1 text-xs text-gray-700 border border-gray-200"
                    >
                      <ClipboardCheck className="w-3.5 h-3.5 text-[var(--nhs-blue)]" />
                      <span>{file.filename}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {messages.length === 0 ? (
              <p className="text-center text-gray-500 py-8">No messages yet.</p>
            ) : (
              messages.map((message) => {
                const isUnreviewedAI = canReview && unreviewedAIIds.has(message.id);

                return (
                  <ChatMessage
                    key={message.id}
                    message={message}
                    isOwnMessage={message.senderType === 'specialist'}
                    showReviewStatus={canReview || isTerminal}
                    showReviewActions={isUnreviewedAI}
                    onApprove={() => onOpenApproveConfirm(message.id)}
                    onApproveWithComment={() => onOpenApproveWithComment(message.id)}
                    onRequestChanges={() => onOpenRequestChanges(message.id)}
                    onManualResponse={() => onOpenManualResponse(message.id)}
                    onEditResponse={() => onOpenEditResponse(message.id, message.content)}
                    actionLoading={actionLoading}
                  />
                );
              })
            )}

            {hasPendingAIResponse && !hasGeneratingAIResponse && (
              <div className="flex gap-4">
                <div className="shrink-0">
                  <div className="w-10 h-10 sm:w-12 sm:h-12 rounded-full bg-blue-100 flex items-center justify-center">
                    <Loader2 className="w-5 h-5 text-[var(--nhs-blue)] animate-spin" />
                  </div>
                </div>
                <div className="flex-1 max-w-3xl">
                  <div className="font-semibold text-gray-900 text-sm sm:text-base mb-2">NHS AI Assistant</div>
                  <div className="rounded-2xl px-4 sm:px-5 py-3 sm:py-4 bg-white border-l-4 border-[var(--nhs-blue)] shadow-sm">
                    <div className="flex items-center gap-1.5 py-1">
                      <span className="w-2 h-2 rounded-full bg-[var(--nhs-blue)] animate-bounce [animation-delay:-0.3s]"></span>
                      <span className="w-2 h-2 rounded-full bg-[var(--nhs-blue)] animate-bounce [animation-delay:-0.15s]"></span>
                      <span className="w-2 h-2 rounded-full bg-[var(--nhs-blue)] animate-bounce"></span>
                    </div>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {chat?.files && chat.files.length > 0 && (
            <div className="border-t border-gray-200 px-4 pt-3 pb-0">
              <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-1.5">
                <Paperclip className="w-3 h-3" />
                <span className="font-medium">Consultation files</span>
              </div>
              <div className="flex flex-wrap gap-1.5 pb-2">
                {chat.files.map((f) => (
                  <span key={f.id} className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-50 border border-blue-100 rounded text-xs text-blue-700">
                    {f.filename}
                    {f.file_size ? <span className="text-blue-400 ml-0.5">· {(f.file_size / 1024).toFixed(0)} KB</span> : null}
                  </span>
                ))}
              </div>
            </div>
          )}

          {!isTerminal && (
            <div className="border-t border-gray-200 p-4">
              <ChatInput
                onSendMessage={onSendMessage}
                placeholder="Add a comment or ask for clarification..."
                existingFileNames={chat.files?.map((file) => file.filename) ?? []}
              />
            </div>
          )}
        </div>
      </main>

      <ApproveConfirmModal
        open={showApproveConfirm}
        actionLoading={actionLoading}
        onCancel={onCloseApproveConfirm}
        onConfirm={onApprove}
      />

      <ApproveWithCommentModal
        open={showApproveWithCommentModal}
        actionLoading={actionLoading}
        approveComment={approveComment}
        onChange={onApproveCommentChange}
        onCancel={onCloseApproveWithComment}
        onConfirm={onApproveWithComment}
      />

      <RequestChangesModal
        open={showRejectModal}
        actionLoading={actionLoading}
        rejectReason={rejectReason}
        onChange={onRejectReasonChange}
        onCancel={onCloseRejectModal}
        onConfirm={onRequestChanges}
      />

      <ManualResponseModal
        open={showManualResponseModal}
        actionLoading={actionLoading}
        manualResponseContent={manualResponseContent}
        manualResponseSources={manualResponseSources}
        manualResponseFiles={manualResponseFiles}
        onContentChange={onManualResponseContentChange}
        onSourcesChange={onManualResponseSourcesChange}
        onFilesChange={onManualResponseFilesChange}
        onCancel={onCloseManualResponseModal}
        onConfirm={onManualResponse}
      />

      <EditResponseModal
        open={showEditResponseModal}
        actionLoading={actionLoading}
        editedContent={editResponseContent}
        editedSources={editResponseSources}
        feedback={editResponseFeedback}
        onContentChange={onEditResponseContentChange}
        onSourcesChange={onEditResponseSourcesChange}
        onFeedbackChange={onEditResponseFeedbackChange}
        onCancel={onCloseEditResponseModal}
        onConfirm={onEditResponse}
      />

      <CloseApproveModal
        open={showCloseConfirm}
        actionLoading={actionLoading}
        onCancel={onCloseCloseConfirm}
        onConfirm={onCloseAndApprove}
      />

      <RequestChangesModal
        open={showConsultationRejectModal}
        actionLoading={actionLoading}
        rejectReason={consultationRejectReason}
        onChange={onConsultationRejectReasonChange}
        onCancel={onCloseConsultationRejectModal}
        onConfirm={onConsultationRequestRevision}
      />

      <ManualResponseModal
        open={showConsultationManualResponseModal}
        actionLoading={actionLoading}
        manualResponseContent={consultationManualContent}
        manualResponseSources={consultationManualSources}
        manualResponseFiles={consultationManualFiles}
        onContentChange={onConsultationManualContentChange}
        onSourcesChange={onConsultationManualSourcesChange}
        onFilesChange={onConsultationManualFilesChange}
        onCancel={onCloseConsultationManualResponseModal}
        onConfirm={onConsultationManualResponse}
      />

      <SendCommentModal
        open={showSendCommentModal}
        actionLoading={actionLoading}
        commentContent={commentContent}
        onChange={onCommentContentChange}
        onCancel={onCloseSendCommentModal}
        onConfirm={onSendComment}
      />

      <UnassignConfirmModal
        open={showUnassignConfirm}
        actionLoading={actionLoading}
        onCancel={onCloseUnassignConfirm}
        onConfirm={onUnassign}
      />
    </div>
  );
}
