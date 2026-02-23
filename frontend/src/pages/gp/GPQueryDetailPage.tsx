import { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { Header } from '../../components/Header';
import { ChatMessage } from '../../components/ChatMessage';
import { ChatInput } from '../../components/ChatInput';
import { useAuth } from '../../contexts/AuthContext';
import { getChat, sendMessage as apiSendMessage } from '../../services/api';
import type { BackendChat, BackendMessage } from '../../types/api';
import type { Message } from '../../types';

/** Map a backend message to the frontend Message shape */
function toFrontendMessage(msg: BackendMessage, currentUser: string): Message {
  const isAI = msg.role === 'assistant';
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
  const [chat, setChat] = useState<BackendChat | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
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
      // Backend creates user message + AI response, returns the AI response
      const aiResponse = await apiSendMessage(chat.id, content);
      const aiMsg = toFrontendMessage(aiResponse, username || 'GP User');
      setMessages(prev => [...prev, aiMsg]);
    } catch {
      setError('Failed to send message');
    } finally {
      setSending(false);
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
                </div>
              </div>
            </div>
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
