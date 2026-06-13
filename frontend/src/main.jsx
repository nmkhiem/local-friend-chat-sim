import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Cpu, MessageCircle, RefreshCw, Send, Sparkles, UsersRound } from 'lucide-react';
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

  const hasComments = useMemo(() => Boolean(post?.comments?.length), [post]);
  const isBusy = Boolean(loading);
  const availableModels = useMemo(
    () => modelStatus?.models?.filter((model) => model.installed) || [],
    [modelStatus],
  );
  const missingModels = useMemo(
    () => modelStatus?.models?.filter((model) => !model.installed) || [],
    [modelStatus],
  );

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
    setModelLoading(true);
    setError('');
    try {
      const status = await request('/models', {
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
    } catch (err) {
      setError(err.message);
    } finally {
      inFlightRef.current = false;
      setLoading('');
    }
  }

  async function simulate(path, mode) {
    if (!post || inFlightRef.current) return;
    inFlightRef.current = true;
    setLoading(mode);
    setError('');
    try {
      await request(`/posts/${post.id}/${path}`, { method: 'POST' });
      await refreshPost(post.id);
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

        <section className="model-panel" aria-label="Ollama model">
          <div className="model-heading">
            <Cpu size={18} />
            <strong>{modelStatus?.current_model || 'Model'}</strong>
            <span className={modelStatus?.connected ? 'status-ok' : 'status-missing'}>
              {!modelStatus ? 'Checking...' : modelStatus.connected ? 'Ollama connected' : 'Ollama offline'}
            </span>
            <button
              className="icon-button"
              onClick={refreshModels}
              disabled={modelLoading || isBusy}
              title="Refresh models"
              aria-label="Refresh models"
            >
              <RefreshCw size={16} />
            </button>
          </div>

          <select
            value={modelStatus?.current_model || ''}
            onChange={(event) => selectModel(event.target.value)}
            disabled={modelLoading || isBusy || availableModels.length === 0}
          >
            {!modelStatus?.current_model && <option value="">Loading models...</option>}
            {modelStatus?.current_model && !availableModels.some((model) => model.name === modelStatus.current_model) && (
              <option value={modelStatus.current_model}>{modelStatus.current_model} (not downloaded)</option>
            )}
            {availableModels.map((model) => (
              <option key={model.name} value={model.name}>
                {model.name}
              </option>
            ))}
          </select>

          <div className="model-lists">
            <div>
              <span>Available</span>
              <p>{availableModels.length ? availableModels.map((model) => model.name).join(', ') : 'None'}</p>
            </div>
            <div>
              <span>Not downloaded</span>
              <p>{missingModels.length ? missingModels.map((model) => model.name).join(', ') : 'None'}</p>
            </div>
          </div>
        </section>

        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Share a thought with your simulated friend group..."
          rows={5}
        />

        <div className="actions">
          <button onClick={sharePost} disabled={isBusy || !draft.trim()}>
            <Send size={18} />
            {loading === 'share' ? 'Sharing...' : 'Share'}
          </button>
          <button onClick={() => simulate('simulate', 'comments')} disabled={!post || isBusy}>
            <Sparkles size={18} />
            {loading === 'comments' ? 'Simulating comments...' : 'Simulate comments'}
          </button>
          <button onClick={() => simulate('simulate-reply', 'replies')} disabled={!hasComments || isBusy}>
            <RefreshCw size={18} />
            {loading === 'replies' ? 'Simulating replies...' : 'Simulate replies'}
          </button>
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
