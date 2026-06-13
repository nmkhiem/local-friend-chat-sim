import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import {
  Brain,
  Check,
  Copy,
  Cpu,
  History,
  MessageCircle,
  PanelRightOpen,
  Play,
  Plus,
  Save,
  Send,
  Settings,
  Sparkles,
  UsersRound,
} from 'lucide-react';
import './styles.css';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
const PERSONA_COLORS = {
  minh: 'persona-minh',
  an: 'persona-an',
  huy: 'persona-huy',
  linh: 'persona-linh',
  trang: 'persona-trang',
  advisor: 'persona-advisor',
  reviewer_2: 'persona-reviewer',
  statistician: 'persona-statistician',
  product_thinker: 'persona-product',
  ux_friend: 'persona-ux',
  tutor: 'persona-tutor',
};

function App() {
  const [draft, setDraft] = useState('');
  const [post, setPost] = useState(null);
  const [threads, setThreads] = useState([]);
  const [councils, setCouncils] = useState([]);
  const [personas, setPersonas] = useState([]);
  const [selectedCouncilId, setSelectedCouncilId] = useState('');
  const [selectedPersonaId, setSelectedPersonaId] = useState('');
  const [councilDraft, setCouncilDraft] = useState(null);
  const [personaDraft, setPersonaDraft] = useState(null);
  const [settingsOpen, setSettingsOpen] = useState(true);
  const [loading, setLoading] = useState('');
  const [error, setError] = useState('');
  const [saveStatus, setSaveStatus] = useState('');
  const [copyState, setCopyState] = useState('');
  const [modelStatus, setModelStatus] = useState(null);
  const [modelLoading, setModelLoading] = useState(false);
  const inFlightRef = useRef(false);

  const isBusy = Boolean(loading);
  const modelOptions = modelStatus?.models || [];
  const personasById = useMemo(
    () => Object.fromEntries(personas.map((persona) => [persona.id, persona])),
    [personas],
  );
  const selectedCouncil = useMemo(
    () => councils.find((council) => council.id === selectedCouncilId) || councils[0],
    [councils, selectedCouncilId],
  );
  const councilPersonas = useMemo(() => {
    if (!selectedCouncil) return [];
    return selectedCouncil.persona_ids.map((id) => personasById[id]).filter(Boolean);
  }, [selectedCouncil, personasById]);

  useEffect(() => {
    refreshModels();
    refreshBootstrap();
  }, []);

  useEffect(() => {
    if (!selectedCouncil) return;
    setCouncilDraft({
      name: selectedCouncil.name,
      description: selectedCouncil.description,
      simulation_style: selectedCouncil.simulation_style,
      persona_ids: [...selectedCouncil.persona_ids],
    });

    const firstPersonaId =
      selectedCouncil.persona_ids.find((id) => personasById[id]) || personas[0]?.id || '';
    setSelectedPersonaId((current) =>
      current && selectedCouncil.persona_ids.includes(current) ? current : firstPersonaId,
    );
  }, [selectedCouncil, personasById, personas]);

  useEffect(() => {
    const persona = personasById[selectedPersonaId];
    if (!persona) {
      setPersonaDraft(null);
      return;
    }
    setPersonaDraft({ ...persona });
  }, [selectedPersonaId, personasById]);

  async function requestJson(path, options = {}) {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
      ...options,
    });
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `Request failed with ${response.status}`);
    }
    return response.json();
  }

  async function requestText(path) {
    const response = await fetch(`${API_BASE_URL}${path}`);
    if (!response.ok) {
      const detail = await response.json().catch(() => ({}));
      throw new Error(detail.detail || `Request failed with ${response.status}`);
    }
    return response.text();
  }

  async function refreshBootstrap() {
    try {
      const [councilList, personaList, threadList] = await Promise.all([
        requestJson('/councils'),
        requestJson('/personas'),
        requestJson('/posts'),
      ]);
      setCouncils(councilList);
      setPersonas(personaList);
      setThreads(threadList);
      setSelectedCouncilId((current) => current || councilList.find((item) => item.id === 'friend')?.id || councilList[0]?.id || '');
    } catch (err) {
      setError(err.message);
    }
  }

  async function refreshThreads() {
    const threadList = await requestJson('/posts');
    setThreads(threadList);
  }

  async function refreshPersonas() {
    const personaList = await requestJson('/personas');
    setPersonas(personaList);
  }

  async function refreshCouncils() {
    const councilList = await requestJson('/councils');
    setCouncils(councilList);
    return councilList;
  }

  async function refreshPost(postId) {
    const detail = await requestJson(`/posts/${postId}`);
    setPost(detail);
    setSelectedCouncilId(detail.council_id);
    return detail;
  }

  async function refreshModels() {
    setModelLoading(true);
    try {
      const status = await requestJson('/models');
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
      window.confirm(`${modelName} is not downloaded. Pull it with Ollama now?`);

    if (selected && !selected.installed && !shouldDownload) return;

    setModelLoading(true);
    setError('');
    try {
      const status = await requestJson(selected?.installed ? '/models' : '/models/pull', {
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

  async function selectThread(threadId) {
    if (isBusy) return;
    setError('');
    try {
      await refreshPost(threadId);
    } catch (err) {
      setError(err.message);
    }
  }

  function newChat() {
    if (isBusy) return;
    setPost(null);
    setDraft('');
    setError('');
  }

  async function sharePost() {
    if (inFlightRef.current) return;
    const content = draft.trim();
    if (!content || !selectedCouncil) return;
    inFlightRef.current = true;
    setLoading('share');
    setError('');
    try {
      const created = await requestJson('/posts', {
        method: 'POST',
        body: JSON.stringify({ content, council_id: selectedCouncil.id }),
      });
      setDraft('');
      await refreshPost(created.id);
      await refreshThreads();

      setLoading('comments');
      await requestJson(`/posts/${created.id}/simulate`, { method: 'POST' });
      await refreshPost(created.id);
      await refreshThreads();

      setLoading('replies');
      await requestJson(`/posts/${created.id}/simulate-reply`, { method: 'POST' });
      await refreshPost(created.id);
      await refreshThreads();
    } catch (err) {
      setError(err.message);
    } finally {
      inFlightRef.current = false;
      setLoading('');
    }
  }

  async function continueDiscussion() {
    if (inFlightRef.current || !post) return;
    inFlightRef.current = true;
    setLoading('continue');
    setError('');
    try {
      const updated = await requestJson(`/posts/${post.id}/continue`, { method: 'POST' });
      setPost(updated);
      await refreshThreads();
    } catch (err) {
      setError(err.message);
    } finally {
      inFlightRef.current = false;
      setLoading('');
    }
  }

  async function copyMarkdown() {
    if (!post) return;
    setCopyState('');
    setError('');
    try {
      const markdown = await requestText(`/posts/${post.id}/export.md`);
      await copyToClipboard(markdown);
      setCopyState('copied');
      window.setTimeout(() => setCopyState(''), 1400);
    } catch (err) {
      setError(err.message);
    }
  }

  async function saveCouncil() {
    if (!selectedCouncil || !councilDraft) return;
    setSaveStatus('saving');
    setError('');
    try {
      const saved = await requestJson(`/councils/${selectedCouncil.id}`, {
        method: 'PUT',
        body: JSON.stringify(councilDraft),
      });
      setCouncils((current) => current.map((item) => (item.id === saved.id ? saved : item)));
      if (post?.council_id === saved.id) await refreshPost(post.id);
      setSaveStatus('saved');
      window.setTimeout(() => setSaveStatus(''), 1200);
    } catch (err) {
      setError(err.message);
      setSaveStatus('');
    }
  }

  async function savePersona() {
    if (!personaDraft) return;
    setSaveStatus('saving');
    setError('');
    try {
      const saved = await requestJson(`/personas/${personaDraft.id}`, {
        method: 'PUT',
        body: JSON.stringify({
          name: personaDraft.name,
          avatar_label: personaDraft.avatar_label,
          personality: personaDraft.personality,
          interests: personaDraft.interests,
          speech_style: personaDraft.speech_style,
          role: personaDraft.role,
          is_active: personaDraft.is_active,
        }),
      });
      const memory = await requestJson(`/personas/${personaDraft.id}/memory`, {
        method: 'PUT',
        body: JSON.stringify({ memory: personaDraft.memory || '' }),
      });
      const merged = { ...saved, memory: memory.memory };
      setPersonas((current) => current.map((item) => (item.id === merged.id ? merged : item)));
      await refreshPersonas();
      if (post) await refreshPost(post.id);
      setSaveStatus('saved');
      window.setTimeout(() => setSaveStatus(''), 1200);
    } catch (err) {
      setError(err.message);
      setSaveStatus('');
    }
  }

  function updateCouncilDraft(field, value) {
    setCouncilDraft((current) => ({ ...current, [field]: value }));
  }

  function toggleCouncilPersona(personaId) {
    setCouncilDraft((current) => {
      const selected = new Set(current.persona_ids);
      if (selected.has(personaId)) {
        selected.delete(personaId);
      } else {
        selected.add(personaId);
      }
      return { ...current, persona_ids: personas.map((persona) => persona.id).filter((id) => selected.has(id)) };
    });
  }

  function updatePersonaDraft(field, value) {
    setPersonaDraft((current) => ({ ...current, [field]: value }));
  }

  const currentCouncilName = post?.council_name || selectedCouncil?.name || 'Council';
  const visibleComments = post?.comments || [];

  return (
    <main className={`app-shell ${settingsOpen ? 'settings-visible' : ''}`}>
      <aside className="sidebar">
        <div className="brand-row">
          <div>
            <p className="eyebrow">local-first v0.2</p>
            <h1>Friend Council</h1>
          </div>
          <button
            className="icon-button"
            onClick={() => setSettingsOpen((current) => !current)}
            aria-label="Toggle settings"
            title="Settings"
          >
            <Settings size={18} />
          </button>
        </div>

        <button className="new-button" onClick={newChat} disabled={isBusy}>
          <Plus size={18} />
          New chat
        </button>

        <section className="side-section">
          <label className="field-label" htmlFor="council-select">
            Council
          </label>
          <select
            id="council-select"
            value={selectedCouncilId}
            onChange={(event) => setSelectedCouncilId(event.target.value)}
            disabled={isBusy || councils.length === 0}
          >
            {councils.map((council) => (
              <option key={council.id} value={council.id}>
                {council.name}
              </option>
            ))}
          </select>
          {selectedCouncil && (
            <div className="council-note">
              <strong>{selectedCouncil.name}</strong>
              <span>{selectedCouncil.description}</span>
            </div>
          )}
        </section>

        <section className="side-section history-section">
          <div className="section-title">
            <History size={16} />
            <span>Recent threads</span>
          </div>
          <div className="thread-list">
            {threads.length === 0 ? (
              <p className="muted">No threads yet.</p>
            ) : (
              threads.map((thread) => (
                <button
                  key={thread.id}
                  className={`thread-item ${post?.id === thread.id ? 'active' : ''}`}
                  onClick={() => selectThread(thread.id)}
                  disabled={isBusy}
                >
                  <strong>{thread.topic_summary}</strong>
                  <span>{thread.council_name || thread.council_id}</span>
                  <small>
                    {formatDate(thread.created_at)} · {thread.comment_count} messages
                  </small>
                </button>
              ))
            )}
          </div>
        </section>
      </aside>

      <section className="workspace">
        <header className="workspace-header">
          <div className="chat-title">
            <UsersRound size={20} />
            <div>
              <strong>{currentCouncilName}</strong>
              <span>{post ? `${countMessages(visibleComments)} messages` : 'Ready for a new thread'}</span>
            </div>
          </div>

          <div className="header-actions">
            <PersonaCluster personas={post?.council?.personas || councilPersonas} />
            <button
              className="ghost-button"
              onClick={continueDiscussion}
              disabled={!post || isBusy}
              title="Continue discussion"
            >
              <Play size={16} />
              Continue
            </button>
            <button className="ghost-button" onClick={copyMarkdown} disabled={!post || isBusy} title="Copy markdown">
              {copyState === 'copied' ? <Check size={16} /> : <Copy size={16} />}
              {copyState === 'copied' ? 'Copied' : 'Markdown'}
            </button>
            <button
              className="icon-button mobile-settings"
              onClick={() => setSettingsOpen((current) => !current)}
              aria-label="Toggle settings"
              title="Settings"
            >
              <PanelRightOpen size={18} />
            </button>
          </div>
        </header>

        <section className="chat-window" aria-live="polite">
          <div className="chat-messages">
            {!post ? (
              <div className="empty-state">
                <MessageCircle size={32} />
                <p>Start a council thread.</p>
              </div>
            ) : (
              <>
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

                {visibleComments.length === 0 ? (
                  <p className="hint">The room is listening.</p>
                ) : (
                  visibleComments.map((comment) => <Comment key={comment.id} comment={comment} />)
                )}
              </>
            )}

            {(loading === 'comments' || loading === 'replies' || loading === 'continue') && (
              <TypingIndicator mode={loading} />
            )}
          </div>

          {post?.discussion_summary && (
            <details className="summary-card" open>
              <summary>
                <Sparkles size={16} />
                Summary
              </summary>
              <div>{post.discussion_summary}</div>
            </details>
          )}

          <Composer
            draft={draft}
            isBusy={isBusy}
            loading={loading}
            modelLoading={modelLoading}
            modelOptions={modelOptions}
            modelStatus={modelStatus}
            onDraftChange={setDraft}
            onModelSelect={selectModel}
            onSend={sharePost}
          />
        </section>

        {error && <p className="error">{error}</p>}
      </section>

      <SettingsPanel
        councilDraft={councilDraft}
        councils={councils}
        isOpen={settingsOpen}
        personas={personas}
        personaDraft={personaDraft}
        saveStatus={saveStatus}
        selectedCouncil={selectedCouncil}
        selectedPersonaId={selectedPersonaId}
        onCouncilChange={updateCouncilDraft}
        onPersonaChange={updatePersonaDraft}
        onPersonaSelect={setSelectedPersonaId}
        onSaveCouncil={saveCouncil}
        onSavePersona={savePersona}
        onToggleCouncilPersona={toggleCouncilPersona}
      />
    </main>
  );
}

function Composer({
  draft,
  isBusy,
  loading,
  modelLoading,
  modelOptions,
  modelStatus,
  onDraftChange,
  onModelSelect,
  onSend,
}) {
  return (
    <section className="composer">
      <textarea
        value={draft}
        onChange={(event) => onDraftChange(event.target.value)}
        placeholder="Share a thought with the selected council..."
        rows={4}
      />

      <div className="actions">
        <div className="model-switcher" aria-label="Ollama model switcher">
          <Cpu size={15} />
          <select
            value={modelStatus?.current_model || ''}
            onChange={(event) => onModelSelect(event.target.value)}
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

        <button className="send-button" onClick={onSend} disabled={isBusy || !draft.trim()} aria-label="Share">
          {isBusy ? <Sparkles size={18} /> : <Send size={18} />}
          <span>{buttonLabel(loading)}</span>
        </button>
      </div>
    </section>
  );
}

function SettingsPanel({
  councilDraft,
  isOpen,
  personas,
  personaDraft,
  saveStatus,
  selectedCouncil,
  selectedPersonaId,
  onCouncilChange,
  onPersonaChange,
  onPersonaSelect,
  onSaveCouncil,
  onSavePersona,
  onToggleCouncilPersona,
}) {
  return (
    <aside className={`inspector ${isOpen ? 'open' : ''}`}>
      <section className="inspector-section">
        <div className="section-title">
          <Brain size={16} />
          <span>Council</span>
        </div>

        {selectedCouncil && councilDraft && (
          <div className="form-grid">
            <label>
              <span>Name</span>
              <input value={councilDraft.name} onChange={(event) => onCouncilChange('name', event.target.value)} />
            </label>
            <label>
              <span>Description</span>
              <textarea
                value={councilDraft.description}
                onChange={(event) => onCouncilChange('description', event.target.value)}
                rows={3}
              />
            </label>
            <label>
              <span>Style</span>
              <textarea
                value={councilDraft.simulation_style}
                onChange={(event) => onCouncilChange('simulation_style', event.target.value)}
                rows={3}
              />
            </label>

            <div className="membership-list">
              {personas.map((persona) => (
                <label key={persona.id} className="check-row">
                  <input
                    type="checkbox"
                    checked={councilDraft.persona_ids.includes(persona.id)}
                    onChange={() => onToggleCouncilPersona(persona.id)}
                  />
                  <span>{persona.name}</span>
                </label>
              ))}
            </div>

            <button className="save-button" onClick={onSaveCouncil}>
              <Save size={16} />
              {saveStatus === 'saved' ? 'Saved' : 'Save council'}
            </button>
          </div>
        )}
      </section>

      <section className="inspector-section">
        <div className="section-title">
          <UsersRound size={16} />
          <span>Personas</span>
        </div>

        <div className="persona-tabs">
          {personas
            .filter((persona) => selectedCouncil?.persona_ids.includes(persona.id))
            .map((persona) => (
              <button
                key={persona.id}
                className={selectedPersonaId === persona.id ? 'active' : ''}
                onClick={() => onPersonaSelect(persona.id)}
              >
                <span className={`avatar ${PERSONA_COLORS[persona.id] || 'persona-default'}`}>
                  {persona.avatar_label || initialsFor(persona.name)}
                </span>
                <span>{persona.name}</span>
              </button>
            ))}
        </div>

        {personaDraft && (
          <div className="form-grid persona-form">
            <label className="check-row active-toggle">
              <input
                type="checkbox"
                checked={Boolean(personaDraft.is_active)}
                onChange={(event) => onPersonaChange('is_active', event.target.checked)}
              />
              <span>Active</span>
            </label>
            <label>
              <span>Name</span>
              <input value={personaDraft.name} onChange={(event) => onPersonaChange('name', event.target.value)} />
            </label>
            <label>
              <span>Avatar</span>
              <input
                value={personaDraft.avatar_label}
                maxLength={8}
                onChange={(event) => onPersonaChange('avatar_label', event.target.value)}
              />
            </label>
            <label>
              <span>Role</span>
              <input value={personaDraft.role} onChange={(event) => onPersonaChange('role', event.target.value)} />
            </label>
            <label>
              <span>Personality</span>
              <textarea
                value={personaDraft.personality}
                onChange={(event) => onPersonaChange('personality', event.target.value)}
                rows={3}
              />
            </label>
            <label>
              <span>Interests</span>
              <textarea
                value={personaDraft.interests}
                onChange={(event) => onPersonaChange('interests', event.target.value)}
                rows={3}
              />
            </label>
            <label>
              <span>Speech style</span>
              <textarea
                value={personaDraft.speech_style}
                onChange={(event) => onPersonaChange('speech_style', event.target.value)}
                rows={3}
              />
            </label>
            <label>
              <span>Memory</span>
              <textarea
                value={personaDraft.memory || ''}
                onChange={(event) => onPersonaChange('memory', event.target.value)}
                rows={4}
              />
            </label>
            <button className="save-button" onClick={onSavePersona}>
              <Save size={16} />
              {saveStatus === 'saved' ? 'Saved' : 'Save persona'}
            </button>
          </div>
        )}
      </section>
    </aside>
  );
}

function PersonaCluster({ personas }) {
  const visible = personas.slice(0, 6);
  return (
    <div className="online-cluster" aria-label="Council personas">
      {visible.map((persona) => (
        <span key={persona.id} className={`avatar ${PERSONA_COLORS[persona.id] || 'persona-default'}`}>
          {persona.avatar_label || initialsFor(persona.name)}
        </span>
      ))}
    </div>
  );
}

function Comment({ comment }) {
  const personaClass = PERSONA_COLORS[comment.author_persona_id] || 'persona-default';
  const label = comment.author_avatar_label || initialsFor(comment.author_name);

  return (
    <article className="message-row">
      <span className={`avatar ${personaClass}`}>{label}</span>
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
  const label =
    mode === 'comments'
      ? 'Council is typing'
      : mode === 'continue'
        ? 'Continuing discussion'
        : 'Replies are landing';

  return (
    <article className="message-row typing-row">
      <span className="avatar persona-default">
        <Sparkles size={16} />
      </span>
      <div className="bubble typing-bubble">
        <strong>{label}</strong>
        <p>
          <span />
          <span />
          <span />
        </p>
      </div>
    </article>
  );
}

function buttonLabel(loading) {
  if (loading === 'share') return 'Sharing';
  if (loading === 'comments') return 'Simulating';
  if (loading === 'replies') return 'Replying';
  if (loading === 'continue') return 'Continuing';
  return 'Share';
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

function formatDate(value) {
  if (!value) return '';
  const parsed = new Date(value.replace(' ', 'T'));
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

async function copyToClipboard(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  document.body.removeChild(textarea);
}

createRoot(document.getElementById('root')).render(<App />);
