import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2, ClipboardCheck } from 'lucide-react';
import { Header } from '../../components/Header';
import { ChatMessage } from '../../components/ChatMessage';
import { ChatInput } from '../../components/ChatInput';
import { useAuth } from '../../contexts/AuthContext';
import { StatusBadge, SeverityBadge } from '../../components/Badges';
import { getChat, sendMessage as apiSendMessage, updateChat as apiUpdateChat } from '../../services/api';
import type { BackendChatWithMessages, BackendMessage, ChatUpdateRequest } from '../../types/api';
import type { Message } from '../../types';

/** Map a backend message to the frontend Message shape */
function toFrontendMessage(msg: BackendMessage, currentUser: string): Message {
  const isAI = msg.sender === 'ai';
  return {
    id: String(msg.id),
    senderId: isAI ? 'ai' : 'user',
    senderName: isAI ? 'NHS AI Assistant' : currentUser,
    senderType: isAI ? 'ai' : 'gp',
    content: msg.content,
    timestamp: new Date(msg.created_at),
  };
}

export function GPQueryDetailPage() {
  const { queryId } = useParams<{ queryId: string }>();
  const navigate = useNavigate();
  const { username, logout } = useAuth();
  const [chat, setChat] = useState<BackendChatWithMessages | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const [editingMeta, setEditingMeta] = useState(false);
  const [savingMeta, setSavingMeta] = useState(false);
  const [editMeta, setEditMeta] = useState<ChatUpdateRequest>({});
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchChat();
  }, [queryId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const fetchChat = async () => {
    if (!queryId) return;
    setLoading(true);
    setError('');
    try {
      const found = await getChat(Number(queryId));
      setChat(found);
      setMessages(found.messages.map(m => toFrontendMessage(m, username || 'GP User')));
    } catch {
      setChat(null);
      setError('Failed to load consultation');
    } finally {
      setLoading(false);
    }
  };

  const handleSendMessage = async (content: string) => {
    if (!chat || sending) return;
    setSending(true);

    // Optimistically add user message
    const userMsg: Message = {
      id: `temp-${Date.now()}`,
      senderId: 'user',
      senderName: username || 'GP User',
      senderType: 'gp',
      content,
      timestamp: new Date(),
    };
    setMessages(prev => [...prev, userMsg]);

    try {
      // Backend returns { status, ai_response }
      const aiResponse = await apiSendMessage(chat.id, content);
      const aiMsg: Message = {
        id: `ai-${Date.now()}`,
        senderId: 'ai',
        senderName: 'NHS AI Assistant',
        senderType: 'ai',
        content: aiResponse.ai_response,
        timestamp: new Date(),
      };
      setMessages(prev => [...prev, aiMsg]);
      setChat(prev => {
        if (!prev) return prev;
        if (prev.status === 'open') return { ...prev, status: 'submitted' };
        return prev;
      });
    } catch {
      setError('Failed to send message');
    } finally {
      setSending(false);
    }
  };

  const openMetaEditor = () => {
    if (!chat) return;
    setEditMeta({
      title: chat.title,
      specialty: chat.specialty,
      severity: chat.severity,
    });
    setEditingMeta(true);
  };

  const saveMeta = async () => {
    if (!chat) return;
    setSavingMeta(true);
    setError('');
    try {
      const updated = await apiUpdateChat(chat.id, {
        title: editMeta.title,
        specialty: editMeta.specialty || undefined,
        severity: editMeta.severity || undefined,
      });
      setChat(prev => (prev ? { ...prev, ...updated } : prev));
      setEditingMeta(false);
    } catch {
      setError('Failed to update consultation details');
    } finally {
      setSavingMeta(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
        <Header userRole="gp" userName={username || 'GP User'} onLogout={logout} />
        <main className="flex-1 flex items-center justify-center">
          <Loader2 className="w-8 h-8 text-[#005eb8] animate-spin" />
        </main>
      </div>
    );
  }

  if (!chat) {
    return (
      <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
        <Header userRole="gp" userName={username || 'GP User'} onLogout={logout} />
        <main className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <h1 className="text-2xl font-bold text-gray-900 mb-4">Consultation not found</h1>
            <button
              onClick={() => navigate('/gp/queries')}
              className="text-[#005eb8] hover:text-[#003087] font-medium"
            >
              Back to Consultations
            </button>
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#f0f4f5] flex flex-col">
      <Header userRole="gp" userName={username || 'GP User'} onLogout={logout} />

      <main className="flex-1 max-w-5xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8 flex flex-col">
        {/* Back Button */}
        <button
          onClick={() => navigate('/gp/queries')}
          className="inline-flex items-center gap-2 text-gray-600 hover:text-gray-900 mb-6"
        >
          <ArrowLeft className="w-5 h-5" />
          Back to Consultations
        </button>

        <div className="bg-white rounded-xl shadow-sm flex-1 flex flex-col overflow-hidden">
          {/* Chat Header */}
          <div className="p-6 border-b border-gray-200">
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
              <div className="flex-1">
                <h1 className="text-xl font-bold text-gray-900 mb-2">{chat.title || 'Untitled Consultation'}</h1>
                <div className="flex flex-wrap items-center gap-3 text-sm text-gray-600">
                  <span className="font-medium">{username || 'GP User'}</span>
                  <span>•</span>
                  <span>{new Date(chat.created_at).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
                  {chat.specialty && (
                    <>
                      <span>•</span>
                      <span className="capitalize">{chat.specialty}</span>
                    </>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {chat.severity && <SeverityBadge severity={chat.severity} />}
                <StatusBadge status={chat.status} />
                {!editingMeta && (
                  <button
                    onClick={openMetaEditor}
                    className="px-3 py-1.5 text-xs font-medium text-[#005eb8] border border-[#005eb8] rounded-lg hover:bg-[#005eb8] hover:text-white transition-colors"
                  >
                    Edit details
                  </button>
                )}
              </div>
            </div>

            {editingMeta && (
              <div className="mt-4 p-4 border border-gray-200 rounded-lg bg-gray-50">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <input
                    type="text"
                    value={editMeta.title || ''}
                    onChange={(e) => setEditMeta(prev => ({ ...prev, title: e.target.value }))}
                    className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
                    placeholder="Consultation title"
                  />
                  <input
                    type="text"
                    value={editMeta.specialty || ''}
                    onChange={(e) => setEditMeta(prev => ({ ...prev, specialty: e.target.value || null }))}
                    className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent"
                    placeholder="Specialty"
                  />
                  <select
                    value={editMeta.severity || ''}
                    onChange={(e) => setEditMeta(prev => ({ ...prev, severity: e.target.value || null }))}
                    className="px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#005eb8] focus:border-transparent bg-white"
                  >
                    <option value="">No severity</option>
                    <option value="low">Low</option>
                    <option value="medium">Medium</option>
                    <option value="high">High</option>
                    <option value="urgent">Urgent</option>
                  </select>
                </div>
                <div className="flex items-center justify-end gap-2 mt-3">
                  <button
                    onClick={() => setEditingMeta(false)}
                    className="px-3 py-1.5 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-100 text-sm"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={saveMeta}
                    disabled={savingMeta}
                    className="px-3 py-1.5 bg-[#005eb8] text-white rounded-lg hover:bg-[#003087] disabled:opacity-50 text-sm"
                  >
                    {savingMeta ? 'Saving…' : 'Save'}
                  </button>
                </div>
              </div>
            )}

            {/* Specialist review status banner */}
            {chat.status === 'submitted' && (
              <div className="mt-4 flex items-center gap-2 bg-amber-50 text-amber-800 px-4 py-3 rounded-lg border border-amber-200">
                <ClipboardCheck className="w-5 h-5 shrink-0" />
                <p className="text-sm">This consultation has been submitted for specialist review. You will be notified once a specialist responds.</p>
              </div>
            )}
            {(chat.status === 'assigned' || chat.status === 'reviewing') && (
              <div className="mt-4 flex items-center gap-2 bg-blue-50 text-blue-800 px-4 py-3 rounded-lg border border-blue-200">
                <ClipboardCheck className="w-5 h-5 shrink-0" />
                <p className="text-sm">A specialist is currently reviewing this consultation.</p>
              </div>
            )}
            {chat.status === 'approved' && (
              <div className="mt-4 flex items-center gap-2 bg-green-50 text-green-800 px-4 py-3 rounded-lg border border-green-200">
                <ClipboardCheck className="w-5 h-5 shrink-0" />
                <p className="text-sm">A specialist has approved the AI response.{chat.review_feedback ? ` Feedback: ${chat.review_feedback}` : ''}</p>
              </div>
            )}
            {chat.status === 'rejected' && (
              <div className="mt-4 flex items-center gap-2 bg-red-50 text-red-800 px-4 py-3 rounded-lg border border-red-200">
                <ClipboardCheck className="w-5 h-5 shrink-0" />
                <p className="text-sm">A specialist has requested changes.{chat.review_feedback ? ` Feedback: ${chat.review_feedback}` : ''}</p>
              </div>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="mx-6 mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {error}
            </div>
          )}

          {/* Chat Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {messages.map(message => (
              <ChatMessage
                key={message.id}
                message={message}
                isOwnMessage={message.senderType === 'gp'}
              />
            ))}
            <div ref={messagesEndRef} />
          </div>

          {/* Chat Input */}
          <div className="border-t border-gray-200 p-4">
            <ChatInput onSendMessage={handleSendMessage} disabled={sending} />
          </div>
        </div>
      </main>
    </div>
  );
}
