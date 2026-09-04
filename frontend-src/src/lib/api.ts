// API client for SocraticAI backend

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const api = {
  // Auth
  async register(name: string, email: string, password: string) {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || 'Registration failed');
    return res.json();
  },

  async login(email: string, password: string) {
    const form = new URLSearchParams({ username: email, password });
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form,
    });
    if (!res.ok) throw new Error((await res.json()).detail || 'Login failed');
    return res.json();
  },

  async getMe(token: string) {
    const res = await fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to get user');
    return res.json();
  },

  // Documents
  async uploadDocument(file: File, token: string) {
    const formData = new FormData();
    formData.append('file', file);
    const res = await fetch(`${API_BASE}/documents/upload`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    });
    if (!res.ok) throw new Error((await res.json()).detail || 'Upload failed');
    return res.json();
  },

  async getDocuments(token: string) {
    const res = await fetch(`${API_BASE}/documents/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to fetch documents');
    return res.json();
  },

  async getDocument(id: string, token: string) {
    const res = await fetch(`${API_BASE}/documents/${id}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Document not found');
    return res.json();
  },

  async deleteDocument(id: string, token: string) {
    const res = await fetch(`${API_BASE}/documents/${id}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to delete');
    return res.json();
  },

  // Chat
  async startSession(token: string, documentId?: string, topic?: string) {
    const res = await fetch(`${API_BASE}/chat/session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ document_id: documentId, topic }),
    });
    if (!res.ok) throw new Error('Failed to start session');
    return res.json();
  },

  async sendMessage(sessionId: string, message: string, token: string) {
    const res = await fetch(`${API_BASE}/chat/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    if (!res.ok) throw new Error('Failed to send message');
    return res.json();
  },

  async getSessions(token: string) {
    const res = await fetch(`${API_BASE}/chat/sessions`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to get sessions');
    return res.json();
  },

  async getSessionMessages(sessionId: string, token: string) {
    const res = await fetch(`${API_BASE}/chat/sessions/${sessionId}/messages`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to get messages');
    return res.json();
  },

  async getKnowledgeState(token: string) {
    const res = await fetch(`${API_BASE}/chat/knowledge-state`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error('Failed to get knowledge state');
    return res.json();
  },
};
