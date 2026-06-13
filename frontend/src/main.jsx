import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Cpu, MessageCircle, Send, Sparkles, UsersRound } from 'lucide-react';
import './styles.css';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const PERSONA_COLORS = {
  minh: 'persona-minh',
  an: 'persona-an',
  huy: 'persona-huy',
  linh: 'persona-linh',
  trang: 'persona-trang',
};

function App() {
  const [draft, setDraft] = useState('');
  const [post, setPost] = useState(null);
  const [loading, setLoading] = useState('');
  const [error, setError] = useState('');
  const [modelStatus, setModelStatus] = useState(null);
  const [modelLoading, setModelLoading] = useState(false);
  const inFlightRef = useRef(false);

  const isBusy = Boolean(loading);
  const modelOptions = modelStatus?.models || [];

  useEffect(() => {
    refreshModels();
  }, []);

  async function request(path, options = {}) {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `Request failed with ${response.status}`);
    }
    return response.json();
  }

  async function refreshPost(postId) {
    const detail = await request(`/posts/${postId}`);
    setPost(detail);
  }

  async function refreshModels() {
    setModelLoading(true);
    try {
      const status = await request('/models');
      setModelStatus(status);
    } catch (err) {
      setError(err.message);
    } finally {
      setModelLoading(false);
    }
  }

  async function selectModel(modelName) {
    if (!modelName || modelName === modelStatus?.current_model) return;
    const selected = modelOptions.find((model) => model.name === modelName);
    const shouldDownload =
      selected &&
      !selected.installed &&
      window.confirm(`${modelName} chưa được tải. Tải model này bằng Ollama bây giờ?`);

    if (selected && !selected.installed && !shouldDownload) return;

    setModelLoading(true);
    setError('');
    try {
      const status = await request(selected?.installed ? '/models' : '/models/pull', {
        method: 'POST',
        body: JSON.stringify({ model: modelName }),
      });
      setModelStatus(status);
    } catch (err) {
      setError(err.message);
    } finally {
      setModelLoading(false);
    }
  }

  async function sharePost() {
    if (inFlightRef.current) return;
    const content = draft.trim();
    if (!content) return;
    inFlightRef.current = true;
    setLoading('share');
    setError('');
    try {
      const created = await request('/posts', {
        method: 'POST',
        body: JSON.stringify({ content }),
      });
      setDraft('');
      await refreshPost(created.id);
      setLoading('comments');
      await request(`/posts/${created.id}/simulate`, { method: 'POST' });
      await refreshPost(created.id);
      setLoading('replies');
      await request(`/posts/${created.id}/simulate-reply`, { method: 'POST' });
      await refreshPost(created.id);
    } catch (err) {
      setError(err.message);
    } finally {
      inFlightRef.current = false;
      setLoading('');
    }
  }

  return (
    <main className="app-shell">
      <section className="composer">
        <div>
          <p className="eyebrow">local-first MVP</p>
          <h1>Local Friend Chat Simulator</h1>
        </div>

        <div className="composer-box">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="Share a thought with your simulated friend group..."
            rows={5}
          />

          <div className="actions">
            <div className="send-actions">
              <div className="model-switcher" aria-label="Ollama model switcher">
                <Cpu size={15} />
                <select
                  value={modelStatus?.current_model || ''}
                  onChange={(event) => selectModel(event.target.value)}
                  disabled={modelLoading || isBusy || modelOptions.length === 0}
                  title={
                    !modelStatus
                      ? 'Checking Ollama models'
                      : modelStatus.connected
                        ? 'Switch Ollama model'
                        : 'Ollama offline'
                  }
                >
                  {!modelStatus?.current_model && <option value="">Model</option>}
                  {modelOptions.map((model) => (
                    <option
                      key={model.name}
                      value={model.name}
                      className={model.installed ? 'model-option-ready' : 'model-option-missing'}
                    >
                      {model.name}
                    </option>
                  ))}
                </select>
              </div>

              <button className="send-button" onClick={sharePost} disabled={isBusy || !draft.trim()} aria-label="Share">
                {isBusy ? <Sparkles size={18} /> : <Send size={18} />}
              </button>
            </div>
          </div>
        </div>

        {error && <p className="error">{error}</p>}
      </section>

      <section className="thread" aria-live="polite">
        {!post ? (
          <div className="empty-state">
            <MessageCircle size={32} />
            <p>Your group chat will wake up here after you share a post.</p>
          </div>
        ) : (
          <div className="chat-window">
            <header className="chat-header">
              <div className="chat-title">
                <UsersRound size={20} />
                <div>
                  <strong>Friend group</strong>
                  <span>{post.comments.length ? `${countMessages(post.comments)} messages` : 'quiet for now'}</span>
                </div>
              </div>
              <div className="online-cluster" aria-label="Online personas">
                <span className="avatar persona-minh">M</span>
                <span className="avatar persona-an">A</span>
                <span className="avatar persona-huy">H</span>
                <span className="avatar persona-linh">L</span>
                <span className="avatar persona-trang">T</span>
              </div>
            </header>

            <div className="chat-messages">
              <article className="message-row mine">
                <div className="bubble post-bubble">
                  <div className="message-meta">
                    <strong>You</strong>
                    <span>{formatTime(post.created_at)}</span>
                  </div>
                  <p>{post.content}</p>
                  <small>{post.topic_summary}</small>
                </div>
              </article>

              {post.comments.length === 0 ? (
                <p className="hint">The room is listening.</p>
              ) : (
                post.comments.map((comment) => <Comment key={comment.id} comment={comment} />)
              )}

              {(loading === 'comments' || loading === 'replies') && <TypingIndicator mode={loading} />}
            </div>
          </div>
        )}
      </section>
    </main>
  );
}

function Comment({ comment }) {
  const personaClass = PERSONA_COLORS[comment.author_persona_id] || 'persona-default';
  const initials = initialsFor(comment.author_name);

  return (
    <article className="message-row">
      <span className={`avatar ${personaClass}`}>{initials}</span>
      <div className="message-stack">
        <div className="bubble friend-bubble">
          <div className="message-meta">
            <strong>{comment.author_name}</strong>
            <span>{formatTime(comment.created_at)}</span>
          </div>
          <p>{comment.content}</p>
        </div>
        {comment.replies.length > 0 && (
          <div className="replies">
            {comment.replies.map((reply) => (
              <Comment key={reply.id} comment={reply} />
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

function TypingIndicator({ mode }) {
  return (
    <article className="message-row typing-row">
      <span className="avatar persona-default">
        <Sparkles size={16} />
      </span>
      <div className="bubble typing-bubble">
        <strong>{mode === 'comments' ? 'Friends are typing' : 'Replies are landing'}</strong>
        <p>
          <span />
          <span />
          <span />
        </p>
      </div>
    </article>
  );
}

function countMessages(comments) {
  return comments.reduce((total, comment) => total + 1 + countMessages(comment.replies), 0);
}

function initialsFor(name) {
  return name
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase();
}

function formatTime(value) {
  if (!value) return '';
  const parsed = new Date(value.replace(' ', 'T'));
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

createRoot(document.getElementById('root')).render(<App />);
