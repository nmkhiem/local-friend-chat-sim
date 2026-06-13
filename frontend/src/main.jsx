import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { MessageCircle, RefreshCw, Send, Sparkles } from 'lucide-react';
import './styles.css';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

function App() {
  const [draft, setDraft] = useState('');
  const [post, setPost] = useState(null);
  const [loading, setLoading] = useState('');
  const [error, setError] = useState('');

  const hasComments = useMemo(() => Boolean(post?.comments?.length), [post]);

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

  async function sharePost() {
    const content = draft.trim();
    if (!content) return;
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
      setLoading('');
    }
  }

  async function simulate(path, mode) {
    if (!post) return;
    setLoading(mode);
    setError('');
    try {
      await request(`/posts/${post.id}/${path}`, { method: 'POST' });
      await refreshPost(post.id);
    } catch (err) {
      setError(err.message);
    } finally {
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

        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Share a thought with your simulated friend group..."
          rows={5}
        />

        <div className="actions">
          <button onClick={sharePost} disabled={loading === 'share' || !draft.trim()}>
            <Send size={18} />
            {loading === 'share' ? 'Sharing...' : 'Share'}
          </button>
          <button onClick={() => simulate('simulate', 'comments')} disabled={!post || loading === 'comments'}>
            <Sparkles size={18} />
            {loading === 'comments' ? 'Simulating...' : 'Simulate comments'}
          </button>
          <button onClick={() => simulate('simulate-reply', 'replies')} disabled={!hasComments || loading === 'replies'}>
            <RefreshCw size={18} />
            {loading === 'replies' ? 'Replying...' : 'Simulate replies'}
          </button>
        </div>

        {error && <p className="error">{error}</p>}
      </section>

      <section className="thread" aria-live="polite">
        {!post ? (
          <div className="empty-state">
            <MessageCircle size={32} />
            <p>Your shared post and simulated discussion will appear here.</p>
          </div>
        ) : (
          <>
            <article className="post">
              <span>Original post</span>
              <p>{post.content}</p>
              <small>{post.topic_summary}</small>
            </article>

            <div className="comments">
              {post.comments.length === 0 ? (
                <p className="hint">No comments yet. Simulate the first wave when you are ready.</p>
              ) : (
                post.comments.map((comment) => <Comment key={comment.id} comment={comment} />)
              )}
            </div>
          </>
        )}
      </section>
    </main>
  );
}

function Comment({ comment }) {
  return (
    <article className="comment">
      <div className="comment-body">
        <strong>{comment.author_name}</strong>
        <p>{comment.content}</p>
      </div>
      {comment.replies.length > 0 && (
        <div className="replies">
          {comment.replies.map((reply) => (
            <Comment key={reply.id} comment={reply} />
          ))}
        </div>
      )}
    </article>
  );
}

createRoot(document.getElementById('root')).render(<App />);
