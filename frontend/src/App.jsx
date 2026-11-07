import React, { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import {
  Upload, Download, Plus, Trash2, Edit2, Search,
  FileSpreadsheet, Calendar, DollarSign, TrendingUp,
  TrendingDown, PieChart, Table, CheckCircle2, AlertCircle,
  X, ExternalLink, Eye, FileDown, History, Save, FolderOpen,
  Clock, ChevronRight, ChevronLeft, Pencil, RefreshCw, FilePlus2
} from 'lucide-react';

// ─── Formatters ──────────────────────────────────────────────────────────────

const formatCurrency = (val) => {
  if (val === null || val === undefined || isNaN(val)) return '—';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency', currency: 'INR', maximumFractionDigits: 2,
  }).format(Number(val));
};

const formatDateDisplay = (val) => {
  if (!val) return '—';
  const num = Number(val);
  if (
    !isNaN(num) && num >= 20000 && num <= 80000 &&
    !String(val).includes('-') && !String(val).includes('/') && !String(val).includes('.')
  ) {
    const utc_days = Math.floor(num - 25569);
    const date = new Date(utc_days * 86400 * 1000);
    return date.toISOString().split('T')[0];
  }
  return String(val).split('T')[0];
};

const formatRelativeTime = (isoStr) => {
  if (!isoStr) return '';
  const diff = Date.now() - new Date(isoStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
};

const formatFullDate = (isoStr) => {
  if (!isoStr) return '';
  return new Date(isoStr).toLocaleString('en-IN', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit'
  });
};

const CUSTOM_PROJECT_VALUE = '__custom_project__';

const readAttachment = (file) => new Promise((resolve, reject) => {
  const reader = new FileReader();
  reader.onload = () => resolve({
    name: file.name,
    type: file.type || 'application/octet-stream',
    size: file.size,
    data: String(reader.result).split(',')[1] || '',
  });
  reader.onerror = reject;
  reader.readAsDataURL(file);
});

// ─── Main App ─────────────────────────────────────────────────────────────────

export default function App() {
  // ── Core state
  const [loading, setLoading] = useState(true);
  const [openingBalance, setOpeningBalance] = useState(-105100.87);
  const [startDate, setStartDate] = useState('01-10-2026');
  const [endDate, setEndDate] = useState('06.11.2026');
  const [transactions, setTransactions] = useState([]);
  const [summary, setSummary] = useState(null);
  const [sourceExcelBase64, setSourceExcelBase64] = useState(null);
  const [sourceExcelFilename, setSourceExcelFilename] = useState(null);
  const [activeTab, setActiveTab] = useState('transactions');

  // ── Session state
  const [sessions, setSessions] = useState([]);
  const [activeSessionId, setActiveSessionId] = useState(null);
  const [activeSessionName, setActiveSessionName] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [renameSessionId, setRenameSessionId] = useState(null);
  const [renameValue, setRenameValue] = useState('');
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  // ── Filtering & Search
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedProject, setSelectedProject] = useState('ALL');
  const [selectedLedger, setSelectedLedger] = useState('ALL');

  // ── Modals
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [isEditModalOpen, setIsEditModalOpen] = useState(false);
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const [isSaveAsModalOpen, setIsSaveAsModalOpen] = useState(false);
  const [saveAsName, setSaveAsName] = useState('');
  const [drilldownData, setDrilldownData] = useState(null);
  const [currentEditTx, setCurrentEditTx] = useState(null);
  const [toast, setToast] = useState(null);
  const [isExporting, setIsExporting] = useState(false);
  const fileInputRef = useRef(null);

  const initialTxForm = {
    date: new Date().toISOString().split('T')[0],
    ledger: 'Petty Cash', memo: '', receipt: 0, payment: 0,
    approved: 'Rajesh Sir', requested_by: 'Bhaskar', category: '',
    project: '', status: 'NA', supportings: [], notes: '',
  };
  const [txForm, setTxForm] = useState(initialTxForm);
  const [isCustomProject, setIsCustomProject] = useState(false);
  const [isCustomEditProject, setIsCustomEditProject] = useState(false);
  const projectOptions = useMemo(() => Array.from(new Set([
    ...transactions.map(t => t.project).filter(Boolean),
    txForm.project,
    currentEditTx?.project,
  ].filter(Boolean))).sort(), [transactions, txForm.project, currentEditTx?.project]);

  // ─── Toast ────────────────────────────────────────────────────────────────

  const showToast = (message, type = 'success') => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3500);
  };

  // ─── Session List ─────────────────────────────────────────────────────────

  const fetchSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const res = await fetch('/api/sessions');
      if (res.ok) setSessions(await res.json());
    } catch (e) { console.error(e); }
    finally { setSessionsLoading(false); }
  }, []);

  // ─── Boot: load default data + sessions list ───────────────────────────────

  useEffect(() => {
    (async () => {
      await fetchSessions();
      setLoading(false);
    })();
  }, []);

  const loadDefaultData = async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/default-data');
      if (!res.ok) throw new Error('Failed to load default data');
      const data = await res.json();
      applyData(data);
      setActiveSessionId(null);
      setActiveSessionName('');
      setHasUnsavedChanges(false);
      showToast('Loaded sample petty cash sheet!');
    } catch (err) {
      showToast(err.message, 'error');
    } finally { setLoading(false); }
  };

  const applyData = (data) => {
    setOpeningBalance(data.opening_balance ?? 0);
    setStartDate(data.start_date ?? '');
    setEndDate(data.end_date ?? '');
    setTransactions(data.transactions ?? []);
    setSummary(data.summary ?? null);
    setSourceExcelBase64(data.source_excel_base64 ?? null);
    setSourceExcelFilename(data.source_excel_filename ?? data.filename ?? null);
  };

  const handleNewSession = async () => {
    if (hasUnsavedChanges && activeSessionId) {
      await saveSession();
    }

    setLoading(true);
    try {
      const res = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: `Petty Cash ${new Date().toLocaleString('en-IN', {
            dateStyle: 'medium',
            timeStyle: 'short',
          })}`,
          opening_balance: 0,
          start_date: '',
          end_date: '',
          transactions: [],
          source_excel_base64: null,
          source_excel_filename: null,
        }),
      });
      if (!res.ok) throw new Error('Failed to create a new session');
      const created = await res.json();
      const sessionRes = await fetch(`/api/sessions/${created.id}`);
      if (!sessionRes.ok) throw new Error('Failed to load the new session');
      const session = await sessionRes.json();
      applyData(session);
      setActiveSessionId(session.id);
      setActiveSessionName(session.name);
      setHasUnsavedChanges(false);
      setSearchTerm('');
      setSelectedProject('ALL');
      setSelectedLedger('ALL');
      setActiveTab('transactions');
      await fetchSessions();
      showToast('New empty session created.');
      return session;
    } catch (err) {
      showToast(err.message, 'error');
      return null;
    } finally {
      setLoading(false);
    }
  };

  // ─── Load a saved session ─────────────────────────────────────────────────

  const loadSession = async (sessionId) => {
    if (hasUnsavedChanges && activeSessionId) {
      if (!window.confirm('You have unsaved changes. Leave without saving?')) return;
    }
    setLoading(true);
    try {
      const res = await fetch(`/api/sessions/${sessionId}`);
      if (!res.ok) throw new Error('Session not found');
      const data = await res.json();
      applyData(data);
      setActiveSessionId(data.id);
      setActiveSessionName(data.name);
      setHasUnsavedChanges(false);
      showToast(`Loaded: "${data.name}"`);
    } catch (err) {
      showToast(err.message, 'error');
    } finally { setLoading(false); }
  };

  // ─── Save current state to active session ─────────────────────────────────

  const saveSession = async () => {
    if (!activeSessionId) {
      // No active session → open "Save As" dialog
      setSaveAsName(activeSessionName || `Petty Cash ${startDate} – ${endDate}`);
      setIsSaveAsModalOpen(true);
      return;
    }
    setIsSaving(true);
    try {
      const res = await fetch(`/api/sessions/${activeSessionId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          opening_balance: openingBalance,
          start_date: startDate,
          end_date: endDate,
          transactions,
          source_excel_base64: sourceExcelBase64,
          source_excel_filename: sourceExcelFilename,
        }),
      });
      if (!res.ok) throw new Error('Save failed');
      setHasUnsavedChanges(false);
      showToast('Session saved!');
      fetchSessions();
    } catch (err) {
      showToast(err.message, 'error');
    } finally { setIsSaving(false); }
  };

  // Persist changes shortly after the user stops editing the active session.
  useEffect(() => {
    if (!activeSessionId || !hasUnsavedChanges || isSaving) return undefined;
    const timer = setTimeout(() => {
      saveSession();
    }, 800);
    return () => clearTimeout(timer);
  }, [activeSessionId, hasUnsavedChanges, openingBalance, startDate, endDate, transactions, isSaving]);

  // ─── Save As (new session) ────────────────────────────────────────────────

  const handleSaveAs = async () => {
    setIsSaving(true);
    try {
      const res = await fetch('/api/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: saveAsName.trim() || `Petty Cash ${startDate} – ${endDate}`,
          opening_balance: openingBalance,
          start_date: startDate,
          end_date: endDate,
          transactions,
          source_excel_base64: sourceExcelBase64,
          source_excel_filename: sourceExcelFilename,
        }),
      });
      if (!res.ok) throw new Error('Failed to save');
      const newSession = await res.json();
      setActiveSessionId(newSession.id);
      setActiveSessionName(newSession.name);
      setHasUnsavedChanges(false);
      setIsSaveAsModalOpen(false);
      setSaveAsName('');
      showToast(`Saved as "${newSession.name}"!`);
      fetchSessions();
    } catch (err) {
      showToast(err.message, 'error');
    } finally { setIsSaving(false); }
  };

  // ─── Delete session ───────────────────────────────────────────────────────

  const handleDeleteSession = async (sessionId, sessionName, e) => {
    e.stopPropagation();
    if (!window.confirm(`Delete session "${sessionName}"? This cannot be undone.`)) return;
    try {
      const res = await fetch(`/api/sessions/${sessionId}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Delete failed');
      if (activeSessionId === sessionId) {
        setActiveSessionId(null);
        setActiveSessionName('');
      }
      showToast(`Deleted "${sessionName}"`);
      fetchSessions();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  // ─── Rename session ───────────────────────────────────────────────────────

  const handleRenameSession = async (sessionId) => {
    if (!renameValue.trim()) { setRenameSessionId(null); return; }
    try {
      const res = await fetch(`/api/sessions/${sessionId}/rename`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: renameValue.trim() }),
      });
      if (!res.ok) throw new Error('Rename failed');
      if (activeSessionId === sessionId) setActiveSessionName(renameValue.trim());
      setRenameSessionId(null);
      setRenameValue('');
      fetchSessions();
    } catch (err) {
      showToast(err.message, 'error');
    }
  };

  // ─── File Upload ──────────────────────────────────────────────────────────

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    let uploadSessionId = activeSessionId;
    if (!uploadSessionId) {
      const newSession = await handleNewSession();
      uploadSessionId = newSession?.id;
      if (!uploadSessionId) {
        if (fileInputRef.current) fileInputRef.current.value = '';
        return;
      }
    }
    const formData = new FormData();
    formData.append('file', file);
    setLoading(true);
    try {
      const res = await fetch('/api/upload', { method: 'POST', body: formData });
      if (!res.ok) { const err = await res.json(); throw new Error(err.detail || 'Upload failed'); }
      const data = await res.json();
      applyData(data);
      setActiveSessionId(uploadSessionId);
      setActiveSessionName(data.filename || file.name.replace(/\.[^.]+$/, ''));
      setHasUnsavedChanges(true);
      showToast(`"${file.name}" uploaded (${data.transactions.length} rows). Saving automatically…`);
    } catch (err) {
      showToast('Error: ' + err.message, 'error');
    } finally {
      setLoading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  // ─── Recalculate ──────────────────────────────────────────────────────────

  const triggerRecalculate = async (opBal, sDate, eDate, txs) => {
    try {
      const res = await fetch('/api/recalculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ opening_balance: opBal, start_date: sDate, end_date: eDate, transactions: txs }),
      });
      if (!res.ok) throw new Error('Recalculate failed');
      const result = await res.json();
      setSummary(result);
      setTransactions(result.transactions);
      setHasUnsavedChanges(true);
    } catch (err) {
      showToast('Recalculation error: ' + err.message, 'error');
    }
  };

  // ─── Export ───────────────────────────────────────────────────────────────

  const handleExport = async () => {
    setIsExporting(true);
    try {
      const res = await fetch('/api/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ opening_balance: openingBalance, start_date: startDate, end_date: endDate, transactions }),
      });
      if (!res.ok) throw new Error('Export failed');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Petty_Cash_${startDate}_to_${endDate}.xlsx`.replace(/\s+/g, '_');
      document.body.appendChild(a); a.click();
      window.URL.revokeObjectURL(url); a.remove();
      showToast('Excel downloaded!');
    } catch (err) {
      showToast('Export failed: ' + err.message, 'error');
    } finally { setIsExporting(false); }
  };

  // ─── Drilldown ────────────────────────────────────────────────────────────

  const openDrilldown = (project, type, amount) => {
    if (!amount || amount === 0) return;
    let rows = project === 'Grand Total'
      ? transactions.filter(t => type === 'receipt' ? Number(t.receipt) > 0 : Number(t.payment) > 0)
      : transactions.filter(t => t.project === project && (type === 'receipt' ? Number(t.receipt) > 0 : Number(t.payment) > 0));
    setDrilldownData({ project, type, amount, rows });
  };

  const handleDownloadDrilldown = async () => {
    if (!drilldownData) return;
    try {
      const res = await fetch('/api/export-drilldown', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project: drilldownData.project, type: drilldownData.type, transactions: drilldownData.rows }),
      });
      if (!res.ok) throw new Error('Failed to export');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Details_${drilldownData.project}_${drilldownData.type}.xlsx`.replace(/\s+/g, '_');
      document.body.appendChild(a); a.click();
      window.URL.revokeObjectURL(url); a.remove();
      showToast('Drill-down table downloaded!');
    } catch (err) { showToast(err.message, 'error'); }
  };

  const redirectToLedger = (project) => {
    setDrilldownData(null);
    setSelectedProject(project === 'Grand Total' ? 'ALL' : project);
    setActiveTab('transactions');
    showToast(`Filtered to: ${project}`);
  };

  // ─── CRUD ─────────────────────────────────────────────────────────────────

  const handleAddTransaction = () => {
    const newTx = { ...txForm, id: `tx-${Date.now()}`, receipt: Number(txForm.receipt) || 0, payment: Number(txForm.payment) || 0 };
    const updated = [...transactions, newTx];
    triggerRecalculate(openingBalance, startDate, endDate, updated);
    setIsAddModalOpen(false);
    setTxForm(initialTxForm);
    showToast('Transaction added!');
  };

  const handleSupportingUpload = async (event, update) => {
    const files = Array.from(event.target.files || []);
    if (!files.length) return;
    try {
      const attachments = await Promise.all(files.map(readAttachment));
      update(previous => ({
        ...previous,
        supportings: [...(previous.supportings || []), ...attachments],
      }));
    } catch (err) {
      showToast(`Supporting upload failed: ${err.message}`, 'error');
    } finally {
      event.target.value = '';
    }
  };

  const handleUpdateTransaction = () => {
    if (!currentEditTx) return;
    const updated = transactions.map(t =>
      t.id === currentEditTx.id ? { ...currentEditTx, receipt: Number(currentEditTx.receipt) || 0, payment: Number(currentEditTx.payment) || 0 } : t
    );
    triggerRecalculate(openingBalance, startDate, endDate, updated);
    setIsEditModalOpen(false);
    setCurrentEditTx(null);
    showToast('Transaction updated!');
  };

  const handleDeleteTransaction = (id) => {
    if (!window.confirm('Delete this transaction?')) return;
    triggerRecalculate(openingBalance, startDate, endDate, transactions.filter(t => t.id !== id));
    showToast('Transaction deleted!');
  };

  // ─── Derived ──────────────────────────────────────────────────────────────

  const uniqueProjects = useMemo(() => Array.from(new Set(transactions.map(t => t.project).filter(Boolean))).sort(), [transactions]);
  const uniqueLedgers = useMemo(() => Array.from(new Set(transactions.map(t => t.ledger).filter(Boolean))).sort(), [transactions]);
  const sortedTransactions = useMemo(() => [...transactions].sort((a, b) => {
    const normalizeDate = value => {
      const text = String(value || '').split('T')[0].replace(/\./g, '-').replace(/\//g, '-');
      const parts = text.split('-');
      if (parts.length === 3 && parts[0].length === 2) return `${parts[2]}-${parts[1]}-${parts[0]}`;
      return text || '9999-12-31';
    };
    const dateA = new Date(normalizeDate(a.date)).getTime();
    const dateB = new Date(normalizeDate(b.date)).getTime();
    return dateA - dateB;
  }), [transactions]);

  const filteredTransactions = useMemo(() => sortedTransactions.filter(t => {
    const q = searchTerm.toLowerCase();
    const matchSearch = !q || [t.memo, t.ledger, t.project, t.category, t.requested_by, t.approved].some(f => f && f.toLowerCase().includes(q));
    return matchSearch && (selectedProject === 'ALL' || t.project === selectedProject) && (selectedLedger === 'ALL' || t.ledger === selectedLedger);
  }), [sortedTransactions, searchTerm, selectedProject, selectedLedger]);

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-slate-100 flex flex-col font-sans">

      {/* Toast */}
      {toast && (
        <div className={`fixed bottom-5 right-5 z-50 flex items-center gap-2 px-4 py-3 rounded-lg shadow-xl text-white text-sm font-medium ${toast.type === 'error' ? 'bg-red-600' : 'bg-emerald-600'}`}>
          {toast.type === 'error' ? <AlertCircle className="w-5 h-5" /> : <CheckCircle2 className="w-5 h-5" />}
          {toast.message}
        </div>
      )}

      {/* Top Nav */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-sm">
        <div className="px-4 h-14 flex items-center justify-between gap-3">
          {/* Left: logo + sidebar toggle */}
          <div className="flex items-center gap-3">
            <button onClick={() => setSidebarOpen(o => !o)} className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 transition" title="Toggle Sessions Panel">
              {sidebarOpen ? <ChevronLeft className="w-5 h-5" /> : <History className="w-5 h-5" />}
            </button>
            <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-amber-500 to-yellow-400 flex items-center justify-center shadow-md shadow-amber-500/20">
              <FileSpreadsheet className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-base font-bold text-slate-900 tracking-tight flex items-center gap-2">
                PettyCash Pro
                <span className="text-xs bg-amber-100 text-amber-800 font-semibold px-2 py-0.5 rounded-full border border-amber-300">R-TEAM Edition</span>
              </h1>
              {activeSessionName && (
                <p className="text-xs text-slate-500 flex items-center gap-1">
                  <FolderOpen className="w-3 h-3" />
                  {activeSessionName}
                  {hasUnsavedChanges && <span className="text-amber-600 font-semibold">• unsaved</span>}
                </p>
              )}
            </div>
          </div>

          {/* Right: actions */}
          <div className="flex items-center gap-2">
            <input type="file" ref={fileInputRef} onChange={handleFileUpload} accept=".xlsx,.xls,.xlsm" className="hidden" />
            <button
              onClick={handleNewSession}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-lg shadow-sm transition"
            >
              <FilePlus2 className="w-3.5 h-3.5" /> New Session
            </button>
            <button
              onClick={() => fileInputRef.current?.click()}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold rounded-lg border border-slate-300 transition"
            >
              <Upload className="w-3.5 h-3.5" /> Upload Sheet
            </button>

            <button
              onClick={saveSession}
              disabled={isSaving}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg border transition ${hasUnsavedChanges
                ? 'bg-amber-500 hover:bg-amber-600 text-white border-amber-500 shadow-sm'
                : 'bg-white hover:bg-slate-50 text-slate-600 border-slate-300'}`}
              title={activeSessionId ? 'Save changes to current session' : 'Save as new session'}
            >
              <Save className={`w-3.5 h-3.5 ${isSaving ? 'animate-spin' : ''}`} />
              {isSaving ? 'Saving…' : activeSessionId ? 'Save Session' : 'Save As Session'}
            </button>

            <button
              onClick={handleExport}
              disabled={isExporting || transactions.length === 0}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg shadow-sm transition disabled:opacity-50"
            >
              <Download className={`w-3.5 h-3.5 ${isExporting ? 'animate-bounce' : ''}`} />
              {isExporting ? 'Generating…' : 'Download Excel'}
            </button>
          </div>
        </div>
      </header>

      {/* Body: Sidebar + Main */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── Sessions Sidebar ─────────────────────────────────────────── */}
        {sidebarOpen && (
          <aside className="w-64 bg-white border-r border-slate-200 flex flex-col shrink-0 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <History className="w-4 h-4 text-slate-500" />
                <span className="text-sm font-bold text-slate-800">Session History</span>
              </div>
              <button
                onClick={handleNewSession}
                className="p-1 rounded-lg hover:bg-amber-50 text-amber-600 hover:text-amber-700 transition"
                title="Create new empty session"
              >
                <FilePlus2 className="w-4 h-4" />
              </button>
            </div>

            {/* Session list */}
            <div className="flex-1 overflow-y-auto">
              {sessionsLoading && (
                <div className="p-4 text-xs text-center text-slate-400">Loading sessions…</div>
              )}
              {!sessionsLoading && sessions.length === 0 && (
                <div className="p-5 text-center">
                  <Clock className="w-8 h-8 text-slate-200 mx-auto mb-2" />
                  <p className="text-xs text-slate-400 font-medium">No saved sessions yet.</p>
                  <p className="text-[11px] text-slate-300 mt-1">Upload an Excel sheet and save it to build your history.</p>
                </div>
              )}
              {sessions.map(sess => (
                <div
                  key={sess.id}
                  onClick={() => loadSession(sess.id)}
                  className={`group flex items-start gap-2 px-3 py-2.5 cursor-pointer border-b border-slate-50 hover:bg-blue-50 transition relative ${activeSessionId === sess.id ? 'bg-blue-50 border-l-2 border-blue-500' : ''}`}
                >
                  <FolderOpen className={`w-4 h-4 mt-0.5 shrink-0 ${activeSessionId === sess.id ? 'text-blue-600' : 'text-slate-400'}`} />
                  <div className="flex-1 min-w-0">
                    {renameSessionId === sess.id ? (
                      <input
                        autoFocus
                        value={renameValue}
                        onChange={e => setRenameValue(e.target.value)}
                        onBlur={() => handleRenameSession(sess.id)}
                        onKeyDown={e => { if (e.key === 'Enter') handleRenameSession(sess.id); if (e.key === 'Escape') setRenameSessionId(null); }}
                        onClick={e => e.stopPropagation()}
                        className="w-full text-xs border border-blue-400 rounded px-1 py-0.5 focus:outline-none"
                      />
                    ) : (
                      <p className="text-xs font-semibold text-slate-800 truncate leading-tight">{sess.name}</p>
                    )}
                    <p className="text-[11px] text-slate-400 mt-0.5">{sess.tx_count} rows · {formatRelativeTime(sess.updated_at)}</p>
                    <p className="text-[10px] text-slate-300">{sess.start_date} → {sess.end_date}</p>
                  </div>
                  {/* Actions: appear on hover */}
                  <div className="hidden group-hover:flex items-center gap-1 absolute right-2 top-2.5">
                    <button
                      onClick={e => { e.stopPropagation(); setRenameSessionId(sess.id); setRenameValue(sess.name); }}
                      className="p-1 rounded hover:bg-blue-100 text-slate-400 hover:text-blue-600"
                      title="Rename"
                    ><Pencil className="w-3 h-3" /></button>
                    <button
                      onClick={e => handleDeleteSession(sess.id, sess.name, e)}
                      className="p-1 rounded hover:bg-red-100 text-slate-400 hover:text-red-600"
                      title="Delete"
                    ><Trash2 className="w-3 h-3" /></button>
                  </div>
                </div>
              ))}
            </div>

            {/* Sidebar footer: refresh */}
            <div className="px-3 py-2 border-t border-slate-100">
              <button onClick={fetchSessions} className="w-full flex items-center justify-center gap-1.5 py-1.5 text-xs text-slate-400 hover:text-slate-600 hover:bg-slate-50 rounded-lg transition">
                <RefreshCw className="w-3.5 h-3.5" /> Refresh
              </button>
            </div>
          </aside>
        )}

        {/* ── Main Content ──────────────────────────────────────────────── */}
        <main className="flex-1 overflow-y-auto px-4 sm:px-6 py-5 flex flex-col gap-5 min-w-0">

          {/* Loading overlay */}
          {loading && (
            <div className="fixed inset-0 z-40 bg-white/70 backdrop-blur-sm flex items-center justify-center">
              <div className="flex flex-col items-center gap-3">
                <RefreshCw className="w-8 h-8 text-amber-500 animate-spin" />
                <p className="text-sm font-semibold text-slate-700">Loading…</p>
              </div>
            </div>
          )}

          {/* KPI Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col gap-1">
              <div className="flex items-center justify-between text-slate-500">
                <span className="text-xs font-semibold uppercase tracking-wider">Opening Balance</span>
                <button onClick={() => setIsConfigModalOpen(true)} className="text-xs text-blue-600 hover:underline font-medium">Configure</button>
              </div>
              <span className={`text-xl font-bold ${openingBalance < 0 ? 'text-red-600' : 'text-slate-900'}`}>{formatCurrency(openingBalance)}</span>
              <span className="text-xs text-slate-400 flex items-center gap-1"><Calendar className="w-3 h-3" /> {startDate}</span>
            </div>

            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Total Receipts</span>
                <TrendingUp className="w-4 h-4 text-emerald-500" />
              </div>
              <span className="text-xl font-bold text-emerald-600">{formatCurrency(summary?.total_receipts ?? 0)}</span>
              <span className="text-xs text-slate-400">{summary?.additions?.length || 0} inflow heads</span>
            </div>

            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col gap-1">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Total Payments</span>
                <TrendingDown className="w-4 h-4 text-amber-500" />
              </div>
              <span className="text-xl font-bold text-amber-600">{formatCurrency(summary?.total_payments ?? 0)}</span>
              <span className="text-xs text-slate-400">{summary?.withdrawals?.length || 0} projects</span>
            </div>

            <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col gap-1 bg-gradient-to-br from-white to-blue-50/50">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Closing Balance</span>
                <DollarSign className="w-4 h-4 text-blue-600" />
              </div>
              <span className={`text-xl font-bold ${(summary?.closing_balance ?? 0) < 0 ? 'text-red-600' : 'text-blue-700'}`}>{formatCurrency(summary?.closing_balance ?? 0)}</span>
              <span className="text-xs text-slate-400 flex items-center gap-1"><Calendar className="w-3 h-3" /> {endDate}</span>
            </div>
          </div>

          {/* Tabs */}
          <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 rounded-xl shadow-sm">
            <div className="flex gap-1">
              {[
                { key: 'transactions', label: `Petty Cash Sheet (${transactions.length})`, icon: <Table className="w-4 h-4" />, color: 'amber' },
                { key: 'summary', label: 'Petty Cash Summary', icon: <FileSpreadsheet className="w-4 h-4" />, color: 'blue' },
                { key: 'analytics', label: 'Visual Analytics', icon: <PieChart className="w-4 h-4" />, color: 'purple' },
              ].map(tab => (
                <button key={tab.key} onClick={() => setActiveTab(tab.key)}
                  className={`flex items-center gap-2 py-3 px-4 font-semibold text-sm border-b-2 transition ${activeTab === tab.key
                    ? `border-${tab.color}-500 text-${tab.color}-700 bg-${tab.color}-50/40`
                    : 'border-transparent text-slate-500 hover:text-slate-800'}`}>
                  {tab.icon}{tab.label}
                </button>
              ))}
            </div>
            {activeTab === 'transactions' && (
              <button onClick={() => { setTxForm(initialTxForm); setIsCustomProject(false); setIsAddModalOpen(true); }}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-amber-500 hover:bg-amber-600 text-white text-xs font-semibold rounded-lg shadow-sm transition">
                <Plus className="w-4 h-4" /> Add Transaction
              </button>
            )}
          </div>

          {/* TAB 1: Transactions */}
          {activeTab === 'transactions' && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col overflow-hidden">
              {/* Filter bar */}
              <div className="p-3 border-b border-slate-100 flex flex-wrap items-center justify-between gap-3 bg-slate-50/50">
                <div className="flex items-center gap-2 flex-1 min-w-[220px] max-w-sm bg-white border border-slate-300 rounded-lg px-3 py-1.5 shadow-sm focus-within:ring-2 focus-within:ring-amber-400">
                  <Search className="w-4 h-4 text-slate-400" />
                  <input type="text" placeholder="Search…" value={searchTerm} onChange={e => setSearchTerm(e.target.value)} className="w-full text-xs text-slate-800 focus:outline-none" />
                  {searchTerm && <button onClick={() => setSearchTerm('')}><X className="w-3.5 h-3.5 text-slate-400" /></button>}
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium text-slate-500">Project:</span>
                    <select value={selectedProject} onChange={e => setSelectedProject(e.target.value)} className="text-xs bg-white border border-slate-300 rounded-lg px-2.5 py-1.5 text-slate-700 focus:ring-1 focus:ring-amber-500 focus:outline-none">
                      <option value="ALL">All Projects ({uniqueProjects.length})</option>
                      {uniqueProjects.map(p => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium text-slate-500">Ledger:</span>
                    <select value={selectedLedger} onChange={e => setSelectedLedger(e.target.value)} className="text-xs bg-white border border-slate-300 rounded-lg px-2.5 py-1.5 text-slate-700 focus:ring-1 focus:ring-amber-500 focus:outline-none">
                      <option value="ALL">All Ledgers ({uniqueLedgers.length})</option>
                      {uniqueLedgers.map(l => <option key={l} value={l}>{l}</option>)}
                    </select>
                  </div>
                  {(searchTerm || selectedProject !== 'ALL' || selectedLedger !== 'ALL') && (
                    <button onClick={() => { setSearchTerm(''); setSelectedProject('ALL'); setSelectedLedger('ALL'); }} className="text-xs text-red-600 hover:underline font-medium">Reset</button>
                  )}
                </div>
              </div>

              {/* Table */}
              <div className="overflow-x-auto max-h-[560px]">
                <table className="w-full text-left border-collapse text-xs">
                  <thead className="bg-[#FFFF00] text-slate-900 uppercase font-bold sticky top-0 z-10 shadow-sm border-b-2 border-slate-400">
                    <tr>
                      {['Date', 'Ledger', 'Memo / Description', 'Receipt', 'Payment', 'Outstanding Balance', 'Approved', 'Requested By', 'Category', 'Project', 'Status', 'Supportings', 'Notes', 'Actions'].map(h => (
                        <th key={h} className="py-2.5 px-3 border border-slate-300">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {filteredTransactions.length === 0 ? (
                      <tr><td colSpan={14} className="py-12 text-center text-slate-400">No transactions match filters.</td></tr>
                    ) : filteredTransactions.map((tx, idx) => (
                      <tr key={tx.id || idx} className="hover:bg-amber-50/40 transition">
                        <td className="py-2 px-3 border border-slate-200 text-center font-mono font-medium text-slate-700">{formatDateDisplay(tx.date)}</td>
                        <td className="py-2 px-3 border border-slate-200 font-medium text-slate-800">{tx.ledger || '—'}</td>
                        <td className="py-2 px-3 border border-slate-200 text-slate-700 max-w-xs truncate" title={tx.memo}>{tx.memo || '—'}</td>
                        <td className="py-2 px-3 border border-slate-200 text-right font-medium text-emerald-600">{tx.receipt ? formatCurrency(tx.receipt) : '—'}</td>
                        <td className="py-2 px-3 border border-slate-200 text-right font-medium text-amber-700">{tx.payment ? formatCurrency(tx.payment) : '—'}</td>
                        <td className={`py-2 px-3 border border-slate-200 text-right font-semibold font-mono ${tx.balance < 0 ? 'text-red-600' : 'text-slate-900'}`}>{formatCurrency(tx.balance)}</td>
                        <td className="py-2 px-3 border border-slate-200 text-slate-700">{tx.approved || '—'}</td>
                        <td className="py-2 px-3 border border-slate-200 text-slate-700">{tx.requested_by || '—'}</td>
                        <td className="py-2 px-3 border border-slate-200 text-slate-600 text-[11px] truncate" title={tx.category}>{tx.category || '—'}</td>
                        <td className="py-2 px-3 border border-slate-200 text-slate-800 font-medium text-[11px] truncate" title={tx.project}>{tx.project || '—'}</td>
                        <td className="py-2 px-3 border border-slate-200 text-slate-700 whitespace-nowrap">{tx.status || 'NA'}</td>
                        <td className="py-2 px-3 border border-slate-200 text-slate-700">
                          {(tx.supportings || []).length
                            ? tx.supportings.map(file => (
                              <a key={`${file.name}-${file.size}`} href={`data:${file.type};base64,${file.data}`} download={file.name} className="block text-blue-600 hover:underline truncate max-w-xs">{file.name}</a>
                            ))
                            : '—'}
                        </td>
                        <td className="py-2 px-3 border border-slate-200 text-slate-600 max-w-xs truncate" title={tx.notes}>{tx.notes || '—'}</td>
                        <td className="py-2 px-3 border border-slate-200 text-center">
                          <div className="flex items-center justify-center gap-1.5">
                            <button onClick={() => { setCurrentEditTx({ ...tx, date: formatDateDisplay(tx.date) }); setIsCustomEditProject(false); setIsEditModalOpen(true); }} className="p-1 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded" title="Edit"><Edit2 className="w-3.5 h-3.5" /></button>
                            <button onClick={() => handleDeleteTransaction(tx.id)} className="p-1 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded" title="Delete"><Trash2 className="w-3.5 h-3.5" /></button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="p-3 bg-slate-50 border-t border-slate-200 flex items-center justify-between text-xs text-slate-500">
                <span>Showing <b>{filteredTransactions.length}</b> of <b>{transactions.length}</b> transactions</span>
                <span className="italic">Balances computed sequentially from opening balance</span>
              </div>
            </div>
          )}

          {/* TAB 2: Summary */}
          {activeTab === 'summary' && summary && (
            <div className="space-y-4">
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 flex items-center gap-2 text-xs text-amber-900">
                <Eye className="w-4 h-4 text-amber-600 shrink-0" />
                <span><b>Interactive Pivot Drill-Down:</b> Click any value in <b>Sum of Receipt</b> or <b>Sum of Payment</b> to inspect the background table.</span>
              </div>
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
                {/* Pivot Table */}
                <div className="lg:col-span-6 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                  <div className="bg-slate-100 px-4 py-3 border-b border-slate-200 flex items-center justify-between">
                    <div>
                      <h3 className="text-sm font-bold text-slate-800">Pivot Breakdown by Project</h3>
                      <p className="text-xs text-slate-500">Columns A:C in template</p>
                    </div>
                    <span className="text-xs bg-slate-200 text-slate-700 font-semibold px-2 py-0.5 rounded">{summary.pivot_rows?.length || 0} Projects</span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs border-collapse">
                      <thead>
                        <tr className="bg-slate-50 font-bold border-b border-slate-200">
                          <th className="py-2.5 px-3 border border-slate-200 text-left">Row Labels (Project)</th>
                          <th className="py-2.5 px-3 border border-slate-200 text-right w-36">Sum of Receipt</th>
                          <th className="py-2.5 px-3 border border-slate-200 text-right w-36">Sum of Payment</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {summary.pivot_rows?.map((prow, idx) => (
                          <tr key={idx} className="hover:bg-slate-50">
                            <td className="py-2 px-3 border border-slate-200 font-medium text-slate-800">{prow.project}</td>
                            <td className="py-1.5 px-3 border border-slate-200 text-right">
                              {prow.sum_receipt ? (
                                <button onClick={() => openDrilldown(prow.project, 'receipt', prow.sum_receipt)} className="group inline-flex items-center gap-1 font-semibold text-emerald-700 hover:text-emerald-900 bg-emerald-50 hover:bg-emerald-100 px-2 py-0.5 rounded transition font-mono">
                                  {formatCurrency(prow.sum_receipt)}<ExternalLink className="w-3 h-3 opacity-40 group-hover:opacity-100" />
                                </button>
                              ) : ''}
                            </td>
                            <td className="py-1.5 px-3 border border-slate-200 text-right">
                              {prow.sum_payment ? (
                                <button onClick={() => openDrilldown(prow.project, 'payment', prow.sum_payment)} className="group inline-flex items-center gap-1 font-semibold text-amber-800 hover:text-amber-950 bg-amber-50 hover:bg-amber-100 px-2 py-0.5 rounded transition font-mono">
                                  {formatCurrency(prow.sum_payment)}<ExternalLink className="w-3 h-3 opacity-40 group-hover:opacity-100" />
                                </button>
                              ) : ''}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                      <tfoot>
                        <tr className="bg-slate-100 font-bold border-t-2 border-slate-300">
                          <td className="py-2.5 px-3 border border-slate-300 text-slate-900">Grand Total</td>
                          <td className="py-2 px-3 border border-slate-300 text-right">
                            <button onClick={() => openDrilldown('Grand Total', 'receipt', summary.total_receipts)} className="group inline-flex items-center gap-1 font-bold text-emerald-800 bg-emerald-100 hover:bg-emerald-200 px-2 py-0.5 rounded transition font-mono">
                              {formatCurrency(summary.total_receipts)}<ExternalLink className="w-3 h-3 opacity-50 group-hover:opacity-100" />
                            </button>
                          </td>
                          <td className="py-2 px-3 border border-slate-300 text-right">
                            <button onClick={() => openDrilldown('Grand Total', 'payment', summary.total_payments)} className="group inline-flex items-center gap-1 font-bold text-amber-900 bg-amber-100 hover:bg-amber-200 px-2 py-0.5 rounded transition font-mono">
                              {formatCurrency(summary.total_payments)}<ExternalLink className="w-3 h-3 opacity-50 group-hover:opacity-100" />
                            </button>
                          </td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                </div>

                {/* Reconciliation */}
                <div className="lg:col-span-6 bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
                  <div className="bg-[#4F81BD] text-white px-4 py-3 text-center border-b border-slate-200">
                    <h3 className="text-base font-bold tracking-wide">Petty Cash Summary</h3>
                    <p className="text-xs text-blue-100">Official Reconciliation Statement (Columns I:K)</p>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs border-collapse">
                      <thead>
                        <tr className="bg-[#4F81BD] text-white font-bold border-b border-blue-400">
                          <th className="py-2 px-3 border border-slate-300 text-left">Particulares</th>
                          <th className="py-2 px-3 border border-slate-300 text-right w-28">Amount</th>
                          <th className="py-2 px-3 border border-slate-300 text-right w-32">Amount</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="border-b border-slate-200">
                          <td className="py-2 px-3 border border-slate-200 font-semibold text-slate-800">
                            Petty Cash Opening Balance
                            <div className="text-[11px] font-normal text-slate-500">({startDate})</div>
                          </td>
                          <td className="py-2 px-3 border border-slate-200"></td>
                          <td className="py-2 px-3 border border-slate-200 text-right font-bold text-red-600 font-mono">{formatCurrency(summary.opening_balance)}</td>
                        </tr>
                        <tr className="bg-[#FFFF00] font-bold border-b border-slate-300">
                          <td className="py-1.5 px-3 border border-slate-300 text-slate-900">Additions</td>
                          <td className="py-1.5 px-3 border border-slate-300"></td>
                          <td className="py-1.5 px-3 border border-slate-300 text-right font-mono">
                            <button onClick={() => openDrilldown('Grand Total', 'receipt', summary.total_receipts)} className="font-bold text-emerald-800 hover:underline">{formatCurrency(summary.total_receipts)}</button>
                          </td>
                        </tr>
                        {summary.additions?.map((item, idx) => (
                          <tr key={`add-${idx}`} className="hover:bg-slate-50">
                            <td className="py-1.5 px-3 border border-slate-200 pl-6 text-slate-700">{item.particular}</td>
                            <td className="py-1.5 px-3 border border-slate-200 text-right font-mono">
                              <button onClick={() => openDrilldown(item.project, 'receipt', item.amount)} className="font-medium text-emerald-700 hover:underline">{formatCurrency(item.amount)}</button>
                            </td>
                            <td className="py-1.5 px-3 border border-slate-200"></td>
                          </tr>
                        ))}
                        <tr className="bg-[#FFFF00] font-bold border-b border-slate-300">
                          <td className="py-1.5 px-3 border border-slate-300 text-slate-900">Withdraw</td>
                          <td className="py-1.5 px-3 border border-slate-300"></td>
                          <td className="py-1.5 px-3 border border-slate-300 text-right font-mono">
                            <button onClick={() => openDrilldown('Grand Total', 'payment', summary.total_payments)} className="font-bold text-amber-800 hover:underline">-{formatCurrency(summary.total_payments)}</button>
                          </td>
                        </tr>
                        {summary.withdrawals?.map((item, idx) => (
                          <tr key={`with-${idx}`} className="hover:bg-slate-50">
                            <td className="py-1.5 px-3 border border-slate-200 pl-6 text-slate-700">{item.particular}</td>
                            <td className="py-1.5 px-3 border border-slate-200 text-right font-mono">
                              <button onClick={() => openDrilldown(item.project, 'payment', item.amount)} className="font-medium text-amber-700 hover:underline">{formatCurrency(item.amount)}</button>
                            </td>
                            <td className="py-1.5 px-3 border border-slate-200"></td>
                          </tr>
                        ))}
                        <tr className="bg-blue-50/80 font-bold border-t-2 border-slate-400">
                          <td className="py-3 px-3 border border-slate-300 text-blue-900">Closing balance as on {endDate}</td>
                          <td className="py-3 px-3 border border-slate-300"></td>
                          <td className={`py-3 px-3 border border-slate-300 text-right text-sm font-bold font-mono ${summary.closing_balance < 0 ? 'text-red-600' : 'text-blue-900'}`}>
                            {formatCurrency(summary.closing_balance)}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: Analytics */}
          {activeTab === 'analytics' && summary && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
                <h3 className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2"><TrendingDown className="w-4 h-4 text-amber-600" /> Expenses by Project</h3>
                <div className="space-y-3">
                  {summary.withdrawals?.map((item, i) => {
                    const pct = Math.round((item.amount / (summary.total_payments || 1)) * 100);
                    return (
                      <div key={i} className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <button onClick={() => openDrilldown(item.project, 'payment', item.amount)} className="font-medium text-slate-700 hover:text-blue-600 hover:underline flex items-center gap-1">
                            {item.particular} <ExternalLink className="w-2.5 h-2.5 opacity-60" />
                          </button>
                          <span className="font-semibold text-slate-900">{formatCurrency(item.amount)} ({pct}%)</span>
                        </div>
                        <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div className="h-full bg-amber-500 rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
              <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
                <h3 className="text-sm font-bold text-slate-800 mb-4 flex items-center gap-2"><TrendingUp className="w-4 h-4 text-emerald-600" /> Inflows by Source</h3>
                <div className="space-y-3">
                  {summary.additions?.map((item, i) => {
                    const pct = Math.round((item.amount / (summary.total_receipts || 1)) * 100);
                    return (
                      <div key={i} className="space-y-1">
                        <div className="flex justify-between text-xs">
                          <button onClick={() => openDrilldown(item.project, 'receipt', item.amount)} className="font-medium text-slate-700 hover:text-blue-600 hover:underline flex items-center gap-1">
                            {item.particular} <ExternalLink className="w-2.5 h-2.5 opacity-60" />
                          </button>
                          <span className="font-semibold text-slate-900">{formatCurrency(item.amount)} ({pct}%)</span>
                        </div>
                        <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div className="h-full bg-emerald-500 rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* ── MODAL: Drill-Down ───────────────────────────────────────────────── */}
      {drilldownData && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-3 sm:p-5">
          <div className="bg-white rounded-2xl shadow-2xl max-w-7xl w-full max-h-[92vh] flex flex-col border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-blue-100 text-blue-800 border border-blue-200">Background Table</span>
                  <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full uppercase ${drilldownData.type === 'receipt' ? 'bg-emerald-100 text-emerald-800 border border-emerald-200' : 'bg-amber-100 text-amber-800 border border-amber-200'}`}>
                    {drilldownData.type === 'receipt' ? 'Receipts (Inflows)' : 'Payments (Outflows)'}
                  </span>
                </div>
                <h3 className="text-base font-bold text-slate-900 mt-1">{drilldownData.project}</h3>
              </div>
              <div className="flex items-center gap-3">
                <div className="text-right">
                  <span className="text-xs text-slate-500 block">Total Sum</span>
                  <span className={`text-lg font-bold font-mono ${drilldownData.type === 'receipt' ? 'text-emerald-700' : 'text-amber-800'}`}>{formatCurrency(drilldownData.amount)}</span>
                </div>
                <button onClick={() => setDrilldownData(null)} className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-200 transition"><X className="w-5 h-5" /></button>
              </div>
            </div>
            <div className="px-6 py-2.5 bg-slate-100/60 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3 text-xs">
              <span className="text-slate-600 font-medium">Found <b>{drilldownData.rows.length}</b> records contributing to this total</span>
              <div className="flex items-center gap-2">
                <button onClick={handleDownloadDrilldown} className="flex items-center gap-1.5 px-3 py-1.5 bg-white hover:bg-slate-50 text-slate-700 font-medium rounded-lg border border-slate-300 shadow-sm transition"><FileDown className="w-3.5 h-3.5 text-slate-500" /> Export Table (.xlsx)</button>
                <button onClick={() => redirectToLedger(drilldownData.project)} className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg shadow-sm transition"><ExternalLink className="w-3.5 h-3.5" /> View & Edit in Sheet</button>
              </div>
            </div>
            <div className="overflow-auto flex-1 p-4 sm:p-6">
              <table className="w-full text-left border-collapse text-xs">
                <thead className="bg-[#FFFF00] text-slate-900 uppercase font-bold sticky top-0 z-10 shadow-sm border-b-2 border-slate-400">
                  <tr>
                    {['Date', 'Ledger', 'Memo / Description', 'Receipt', 'Payment', 'Outstanding Balance', 'Approved', 'Requested By', 'Category', 'Project', 'Status', 'Supportings', 'Notes'].map(h => (
                      <th key={h} className="py-2.5 px-3 border border-slate-300">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {drilldownData.rows.map((tx, idx) => (
                    <tr key={tx.id || idx} className="hover:bg-amber-50/30 transition">
                      <td className="py-2 px-3 border border-slate-200 text-center font-mono text-slate-600 whitespace-nowrap">{formatDateDisplay(tx.date)}</td>
                      <td className="py-2 px-3 border border-slate-200 font-medium text-slate-800">{tx.ledger || '—'}</td>
                      <td className="py-2 px-3 border border-slate-200 text-slate-700 max-w-xs truncate" title={tx.memo}>{tx.memo || '—'}</td>
                      <td className="py-2 px-3 border border-slate-200 text-right font-medium text-emerald-600 font-mono">{tx.receipt ? formatCurrency(tx.receipt) : '—'}</td>
                      <td className="py-2 px-3 border border-slate-200 text-right font-medium text-amber-700 font-mono">{tx.payment ? formatCurrency(tx.payment) : '—'}</td>
                      <td className={`py-2 px-3 border border-slate-200 text-right font-semibold font-mono ${tx.balance < 0 ? 'text-red-600' : 'text-slate-900'}`}>{formatCurrency(tx.balance)}</td>
                      <td className="py-2 px-3 border border-slate-200 text-slate-600">{tx.approved || '—'}</td>
                      <td className="py-2 px-3 border border-slate-200 text-slate-600">{tx.requested_by || '—'}</td>
                      <td className="py-2 px-3 border border-slate-200 text-slate-600 text-[11px] truncate" title={tx.category}>{tx.category || '—'}</td>
                      <td className="py-2 px-3 border border-slate-200 text-slate-800 font-medium text-[11px] truncate" title={tx.project}>{tx.project || '—'}</td>
                      <td className="py-2 px-3 border border-slate-200 text-slate-600">{tx.status || 'NA'}</td>
                      <td className="py-2 px-3 border border-slate-200 text-slate-600">{(tx.supportings || []).map(file => file.name).join(', ') || '—'}</td>
                      <td className="py-2 px-3 border border-slate-200 text-slate-600">{tx.notes || '—'}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="bg-slate-100 font-bold border-t-2 border-slate-300">
                    <td colSpan={3} className="py-2 px-3 border border-slate-300 text-slate-900 text-right">Subtotals:</td>
                    <td className="py-2 px-3 border border-slate-300 text-right font-mono text-emerald-700">{formatCurrency(drilldownData.rows.reduce((acc, t) => acc + (Number(t.receipt) || 0), 0))}</td>
                    <td className="py-2 px-3 border border-slate-300 text-right font-mono text-amber-800">{formatCurrency(drilldownData.rows.reduce((acc, t) => acc + (Number(t.payment) || 0), 0))}</td>
                    <td colSpan={5} className="py-2 px-3 border border-slate-300"></td>
                  </tr>
                </tfoot>
              </table>
            </div>
            <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-end">
              <button onClick={() => setDrilldownData(null)} className="px-4 py-1.5 bg-slate-200 hover:bg-slate-300 text-slate-700 font-medium rounded-lg text-xs transition">Close</button>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL: Save As Session ──────────────────────────────────────────── */}
      {isSaveAsModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 border border-slate-200">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900 flex items-center gap-2"><Save className="w-4 h-4 text-blue-600" /> Save As New Session</h3>
              <button onClick={() => setIsSaveAsModalOpen(false)} className="text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="mt-4 space-y-3 text-xs">
              <div>
                <label className="block text-slate-600 font-medium mb-1">Session Name</label>
                <input
                  type="text"
                  value={saveAsName}
                  onChange={e => setSaveAsName(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') handleSaveAs(); }}
                  placeholder={`Petty Cash ${startDate} – ${endDate}`}
                  className="w-full border border-slate-300 rounded-lg p-2 focus:ring-1 focus:ring-blue-500 focus:outline-none text-sm"
                  autoFocus
                />
                <p className="text-[11px] text-slate-400 mt-1">Give a descriptive name, e.g. "Oct–Nov 2026 Sheet"</p>
              </div>
              <div className="bg-slate-50 rounded-lg p-3 text-slate-600 space-y-1">
                <div className="flex justify-between"><span>Period:</span><b>{startDate} → {endDate}</b></div>
                <div className="flex justify-between"><span>Transactions:</span><b>{transactions.length} rows</b></div>
                <div className="flex justify-between"><span>Opening Balance:</span><b>{formatCurrency(openingBalance)}</b></div>
              </div>
            </div>
            <div className="mt-6 flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
              <button onClick={() => setIsSaveAsModalOpen(false)} className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg text-xs font-semibold">Cancel</button>
              <button onClick={handleSaveAs} disabled={isSaving} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold shadow-sm disabled:opacity-50 flex items-center gap-1.5">
                <Save className="w-3.5 h-3.5" /> {isSaving ? 'Saving…' : 'Save Session'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL: Add Transaction ──────────────────────────────────────────── */}
      {isAddModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full p-6 border border-slate-200">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900">Add New Petty Cash Entry</h3>
              <button onClick={() => setIsAddModalOpen(false)} className="text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4 text-xs">
              <div>
                <label className="block text-slate-600 font-medium mb-1">Date</label>
                <input type="date" value={txForm.date} onChange={e => setTxForm({ ...txForm, date: e.target.value })} className="w-full border border-slate-300 rounded-lg p-2 focus:ring-1 focus:ring-amber-500 focus:outline-none" />
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">Ledger Head</label>
                <input type="text" list="ledger-list" value={txForm.ledger} onChange={e => setTxForm({ ...txForm, ledger: e.target.value })} placeholder="e.g. Travel" className="w-full border border-slate-300 rounded-lg p-2 focus:ring-1 focus:ring-amber-500 focus:outline-none" />
                <datalist id="ledger-list">{uniqueLedgers.map(l => <option key={l} value={l} />)}</datalist>
              </div>
              <div className="col-span-2">
                <label className="block text-slate-600 font-medium mb-1">Memo / Description</label>
                <textarea rows={2} value={txForm.memo} onChange={e => setTxForm({ ...txForm, memo: e.target.value })} placeholder="Narration or purpose…" className="w-full border border-slate-300 rounded-lg p-2 focus:ring-1 focus:ring-amber-500 focus:outline-none" />
              </div>
              <div>
                <label className="block text-emerald-700 font-semibold mb-1">Receipt (Inflow ₹)</label>
                <input type="number" step="0.01" value={txForm.receipt || ''} onChange={e => setTxForm({ ...txForm, receipt: e.target.value, payment: 0 })} placeholder="0.00" className="w-full border border-slate-300 rounded-lg p-2 focus:ring-1 focus:ring-emerald-500 font-semibold text-emerald-700 focus:outline-none" />
              </div>
              <div>
                <label className="block text-amber-700 font-semibold mb-1">Payment (Outflow ₹)</label>
                <input type="number" step="0.01" value={txForm.payment || ''} onChange={e => setTxForm({ ...txForm, payment: e.target.value, receipt: 0 })} placeholder="0.00" className="w-full border border-slate-300 rounded-lg p-2 focus:ring-1 focus:ring-amber-500 font-semibold text-amber-700 focus:outline-none" />
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">Approved By</label>
                <input type="text" value={txForm.approved} onChange={e => setTxForm({ ...txForm, approved: e.target.value })} placeholder="e.g. Rajesh Sir" className="w-full border border-slate-300 rounded-lg p-2 focus:ring-1 focus:ring-amber-500 focus:outline-none" />
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">Requested By</label>
                <input type="text" value={txForm.requested_by} onChange={e => setTxForm({ ...txForm, requested_by: e.target.value })} placeholder="e.g. Bhaskar" className="w-full border border-slate-300 rounded-lg p-2 focus:ring-1 focus:ring-amber-500 focus:outline-none" />
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">Category</label>
                <input type="text" value={txForm.category} onChange={e => setTxForm({ ...txForm, category: e.target.value })} placeholder="e.g. Office Closure" className="w-full border border-slate-300 rounded-lg p-2 focus:ring-1 focus:ring-amber-500 focus:outline-none" />
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">Project / Account</label>
                <select value={isCustomProject ? CUSTOM_PROJECT_VALUE : (txForm.project || (projectOptions[0] || CUSTOM_PROJECT_VALUE))} onChange={e => {
                  const value = e.target.value;
                  setIsCustomProject(value === CUSTOM_PROJECT_VALUE);
                  if (value !== CUSTOM_PROJECT_VALUE) setTxForm({ ...txForm, project: value });
                }} className="w-full border border-slate-300 rounded-lg p-2 focus:ring-1 focus:ring-amber-500 focus:outline-none">
                  {projectOptions.map(project => <option key={project} value={project}>{project}</option>)}
                  <option value={CUSTOM_PROJECT_VALUE}>Other (enter custom project)</option>
                </select>
                {(isCustomProject || (!projectOptions.length && !txForm.project)) && (
                  <input type="text" value={txForm.project} onChange={e => setTxForm({ ...txForm, project: e.target.value })} placeholder="Enter project name" autoFocus className="w-full mt-2 border border-slate-300 rounded-lg p-2 focus:ring-1 focus:ring-amber-500 focus:outline-none" />
                )}
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">Status</label>
                <select value={txForm.status} onChange={e => setTxForm({ ...txForm, status: e.target.value })} className="w-full border border-slate-300 rounded-lg p-2">
                  {['Paid', 'Unpaid', 'Progress', 'NA'].map(status => <option key={status}>{status}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">Supportings</label>
                <input type="file" multiple onChange={e => handleSupportingUpload(e, setTxForm)} accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg" className="w-full text-xs" />
                <p className="text-[11px] text-slate-400 mt-1">{(txForm.supportings || []).map(file => file.name).join(', ') || 'No files selected'}</p>
              </div>
              <div className="col-span-2">
                <label className="block text-slate-600 font-medium mb-1">Notes (optional)</label>
                <textarea rows={2} value={txForm.notes} onChange={e => setTxForm({ ...txForm, notes: e.target.value })} className="w-full border border-slate-300 rounded-lg p-2" />
              </div>
            </div>
            <div className="mt-6 flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
              <button onClick={() => setIsAddModalOpen(false)} className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg text-xs font-semibold">Cancel</button>
              <button onClick={handleAddTransaction} className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white rounded-lg text-xs font-semibold shadow-sm">Add Transaction</button>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL: Edit Transaction ─────────────────────────────────────────── */}
      {isEditModalOpen && currentEditTx && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full p-6 border border-slate-200">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900">Edit Transaction Row</h3>
              <button onClick={() => setIsEditModalOpen(false)} className="text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-4 text-xs">
              <div>
                <label className="block text-slate-600 font-medium mb-1">Date</label>
                <input type="text" value={currentEditTx.date || ''} onChange={e => setCurrentEditTx({ ...currentEditTx, date: e.target.value })} className="w-full border border-slate-300 rounded-lg p-2" />
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">Ledger Head</label>
                <input type="text" value={currentEditTx.ledger || ''} onChange={e => setCurrentEditTx({ ...currentEditTx, ledger: e.target.value })} className="w-full border border-slate-300 rounded-lg p-2" />
              </div>
              <div className="col-span-2">
                <label className="block text-slate-600 font-medium mb-1">Memo / Description</label>
                <textarea rows={2} value={currentEditTx.memo || ''} onChange={e => setCurrentEditTx({ ...currentEditTx, memo: e.target.value })} className="w-full border border-slate-300 rounded-lg p-2" />
              </div>
              <div>
                <label className="block text-emerald-700 font-semibold mb-1">Receipt (Inflow ₹)</label>
                <input type="number" step="0.01" value={currentEditTx.receipt || ''} onChange={e => setCurrentEditTx({ ...currentEditTx, receipt: parseFloat(e.target.value) || 0, payment: 0 })} className="w-full border border-slate-300 rounded-lg p-2 text-emerald-700 font-semibold" />
              </div>
              <div>
                <label className="block text-amber-700 font-semibold mb-1">Payment (Outflow ₹)</label>
                <input type="number" step="0.01" value={currentEditTx.payment || ''} onChange={e => setCurrentEditTx({ ...currentEditTx, payment: parseFloat(e.target.value) || 0, receipt: 0 })} className="w-full border border-slate-300 rounded-lg p-2 text-amber-700 font-semibold" />
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">Approved By</label>
                <input type="text" value={currentEditTx.approved || ''} onChange={e => setCurrentEditTx({ ...currentEditTx, approved: e.target.value })} className="w-full border border-slate-300 rounded-lg p-2" />
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">Requested By</label>
                <input type="text" value={currentEditTx.requested_by || ''} onChange={e => setCurrentEditTx({ ...currentEditTx, requested_by: e.target.value })} className="w-full border border-slate-300 rounded-lg p-2" />
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">Category</label>
                <input type="text" value={currentEditTx.category || ''} onChange={e => setCurrentEditTx({ ...currentEditTx, category: e.target.value })} className="w-full border border-slate-300 rounded-lg p-2" />
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">Project / Account</label>
                <select value={isCustomEditProject ? CUSTOM_PROJECT_VALUE : (currentEditTx.project || projectOptions[0] || '')} onChange={e => {
                  const value = e.target.value;
                  setIsCustomEditProject(value === CUSTOM_PROJECT_VALUE);
                  if (value !== CUSTOM_PROJECT_VALUE) setCurrentEditTx({ ...currentEditTx, project: value });
                }} className="w-full border border-slate-300 rounded-lg p-2">
                  {projectOptions.map(project => <option key={project} value={project}>{project}</option>)}
                  <option value={CUSTOM_PROJECT_VALUE}>Other (enter custom project)</option>
                </select>
                {(isCustomEditProject || (!projectOptions.length && !currentEditTx.project)) && (
                  <input type="text" value={currentEditTx.project || ''} onChange={e => setCurrentEditTx({ ...currentEditTx, project: e.target.value })} placeholder="Enter project name" autoFocus className="w-full mt-2 border border-slate-300 rounded-lg p-2" />
                )}
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">Status</label>
                <select value={currentEditTx.status || 'NA'} onChange={e => setCurrentEditTx({ ...currentEditTx, status: e.target.value })} className="w-full border border-slate-300 rounded-lg p-2">
                  {['Paid', 'Unpaid', 'Progress', 'NA'].map(status => <option key={status}>{status}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">Supportings</label>
                <input type="file" multiple onChange={e => handleSupportingUpload(e, setCurrentEditTx)} accept=".pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg" className="w-full text-xs" />
                <p className="text-[11px] text-slate-400 mt-1">{(currentEditTx.supportings || []).map(file => file.name).join(', ') || 'No files selected'}</p>
              </div>
              <div className="col-span-2">
                <label className="block text-slate-600 font-medium mb-1">Notes (optional)</label>
                <textarea rows={2} value={currentEditTx.notes || ''} onChange={e => setCurrentEditTx({ ...currentEditTx, notes: e.target.value })} className="w-full border border-slate-300 rounded-lg p-2" />
              </div>
            </div>
            <div className="mt-6 flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
              <button onClick={() => setIsEditModalOpen(false)} className="px-4 py-2 text-slate-600 hover:bg-slate-100 rounded-lg text-xs font-semibold">Cancel</button>
              <button onClick={handleUpdateTransaction} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold shadow-sm">Save Changes</button>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL: Configure Period & Balance ──────────────────────────────── */}
      {isConfigModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-full p-6 border border-slate-200">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900">Period & Balance Config</h3>
              <button onClick={() => setIsConfigModalOpen(false)} className="text-slate-400 hover:text-slate-600"><X className="w-5 h-5" /></button>
            </div>
            <div className="mt-4 space-y-3 text-xs">
              <div>
                <label className="block text-slate-600 font-medium mb-1">Opening Balance (₹)</label>
                <input type="number" step="0.01" value={openingBalance} onChange={e => { setOpeningBalance(parseFloat(e.target.value) || 0); setHasUnsavedChanges(true); }} className="w-full border border-slate-300 rounded-lg p-2 font-mono font-bold" />
                <p className="text-[11px] text-slate-400 mt-0.5">Negative = prior liability/overdraw.</p>
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">Start Date String</label>
                <input type="text" value={startDate} onChange={e => { setStartDate(e.target.value); setHasUnsavedChanges(true); }} placeholder="e.g. 01-10-2026" className="w-full border border-slate-300 rounded-lg p-2" />
              </div>
              <div>
                <label className="block text-slate-600 font-medium mb-1">End Date String</label>
                <input type="text" value={endDate} onChange={e => { setEndDate(e.target.value); setHasUnsavedChanges(true); }} placeholder="e.g. 06.11.2026" className="w-full border border-slate-300 rounded-lg p-2" />
              </div>
            </div>
            <div className="mt-6 flex items-center justify-end gap-3 pt-3 border-t border-slate-100">
              <button onClick={() => { setOpeningBalance(-105100.87); setStartDate('01-10-2026'); setEndDate('06.11.2026'); triggerRecalculate(-105100.87, '01-10-2026', '06.11.2026', transactions); setIsConfigModalOpen(false); showToast('Reset to default!'); }} className="px-3 py-2 text-slate-500 hover:bg-slate-100 rounded-lg text-xs font-semibold">Reset Default</button>
              <button onClick={() => { triggerRecalculate(openingBalance, startDate, endDate, transactions); setIsConfigModalOpen(false); showToast('Recalculated!'); }} className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-semibold shadow-sm">Apply & Recalculate</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
