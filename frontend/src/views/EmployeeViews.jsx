import React, { useState, useEffect } from 'react';
import {
  PlusCircle,
  FileClock,
  Send,
  History,
  UserCheck,
  Upload,
  FileText,
  AlertCircle,
  CheckCircle2,
  Clock,
  Eye,
  Edit2,
  FileUp,
  X,
  ExternalLink,
} from 'lucide-react';
import { api } from '../api';
import Modal from '../components/Modal';
import TablePagination from '../components/TablePagination';

export default function EmployeeViews({ currentView, onNavigate, addToast, user }) {
  const [loading, setLoading] = useState(false);
  const [requests, setRequests] = useState(() => {
    try {
      const c = localStorage.getItem(`pc_emp_reqs_${user?.id}`);
      return c ? JSON.parse(c) : [];
    } catch { return []; }
  });
  const [projects, setProjects] = useState([]);
  const [ledgers, setLedgers] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [historyPage, setHistoryPage] = useState(1);
  const [historyPageSize, setHistoryPageSize] = useState(10);

  // Modals state
  const [selectedRequest, setSelectedRequest] = useState(null);
  const [isDetailOpen, setIsDetailOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [editingDraft, setEditingDraft] = useState(null);

  // New request form state
  const [newAmount, setNewAmount] = useState('');
  const [newPurpose, setNewPurpose] = useState('');
  const [newDate, setNewDate] = useState(new Date().toISOString().split('T')[0]);
  const [newProject, setNewProject] = useState('');
  const [newLedger, setNewLedger] = useState('');
  const [newCategory, setNewCategory] = useState('');
  const [newManager, setNewManager] = useState('');
  const [newNotes, setNewNotes] = useState('');
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState('');

  // Voucher upload modal state (for manager-approved requests)
  const [voucherModalOpen, setVoucherModalOpen] = useState(false);
  const [targetVoucherRequest, setTargetVoucherRequest] = useState(null);
  const [voucherFile, setVoucherFile] = useState(null);
  const [uploadingVoucher, setUploadingVoucher] = useState(false);
  const [submittingPostingId, setSubmittingPostingId] = useState(null);

  const loadAllData = async () => {
    try {
      setLoading(true);
      const [reqData, projData, ledgData, assignData] = await Promise.all([
        api.listRequests(),
        api.getProjects(),
        api.getLedgers(),
        api.listAssignments(),
      ]);
      setRequests(reqData || []);
      try {
        localStorage.setItem(`pc_emp_reqs_${user?.id}`, JSON.stringify(reqData || []));
      } catch (_) {}
      setProjects((projData || []).filter((p) => p.is_active));
      setLedgers((ledgData || []).filter((l) => l.is_active));
      
      const approvedAssignments = (assignData || []).filter(
        (a) => a.status === 'APPROVED' && a.employee_id === user?.id
      );
      setAssignments(approvedAssignments);

      // Pre-select defaults if empty
      if (projData && projData.length > 0 && !newProject) setNewProject(projData[0].id);
      if (ledgData && ledgData.length > 0 && !newLedger) setNewLedger(ledgData[0].id);
      if (approvedAssignments.length > 0 && !newManager) setNewManager(approvedAssignments[0].manager_id);
    } catch (e) {
      console.error(e);
      addToast({ type: 'error', message: 'Failed to load requests data.' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAllData();
  }, [currentView]);

  // Derived counts
  const drafts = requests.filter(
    (r) => r.status === 'DRAFT' || r.status === 'RETURNED_FOR_CORRECTION'
  );
  const submitted = requests.filter(
    (r) => r.status === 'SUBMITTED' || r.status === 'APPROVED' || r.status === 'SUPPORTING_UPLOADED'
  );
  const history = requests.filter(
    (r) => r.status === 'POSTED' || r.status === 'REJECTED' || r.status === 'REVERSED'
  );

  const resetForm = () => {
    setNewAmount('');
    setNewPurpose('');
    setNewNotes('');
    setFormError('');
  };

  const handleUploadVoucher = async (e) => {
    e.preventDefault();
    if (!targetVoucherRequest || !voucherFile) return;
    try {
      setUploadingVoucher(true);
      await api.uploadSupportingFile(targetVoucherRequest.id, voucherFile);
      addToast({
        type: 'success',
        title: 'Voucher Uploaded',
        message: `Attached ${voucherFile.name} successfully. You can now submit for admin posting.`,
      });
      setVoucherFile(null);
      setVoucherModalOpen(false);
      loadAllData();
    } catch (err) {
      addToast({ type: 'error', title: 'Upload Failed', message: err.message });
    } finally {
      setUploadingVoucher(false);
    }
  };

  const handleSubmitForPosting = async (requestId) => {
    try {
      setSubmittingPostingId(requestId);
      await api.submitForPosting(requestId);
      addToast({
        type: 'success',
        title: 'Submitted for Posting',
        message: 'Your request with attached vouchers has been submitted to Admin for final posting!',
      });
      loadAllData();
    } catch (err) {
      addToast({ type: 'error', title: 'Submission Failed', message: err.message });
    } finally {
      setSubmittingPostingId(null);
    }
  };

  const handleCreateRequest = async (submitImmediate = false) => {
    setFormError('');
    const amt = parseFloat(newAmount);
    if (isNaN(amt) || amt <= 0) {
      setFormError('Amount must be a positive number.');
      return;
    }
    if (!newPurpose.trim()) {
      setFormError('Purpose / description is required.');
      return;
    }
    if (!newProject) {
      setFormError('Please select a project.');
      return;
    }
    if (!newLedger) {
      setFormError('Please select a ledger.');
      return;
    }
    if (!newManager) {
      setFormError('Please select an approving manager.');
      return;
    }

    try {
      setFormSubmitting(true);
      const categoryName = newCategory.trim() || 'General Expense';
      const created = await api.createDraft({
        project_id: newProject,
        ledger_id: newLedger,
        category: categoryName,
        request_date: newDate,
        amount: amt,
        purpose: newPurpose.trim(),
        notes: newNotes.trim() || null,
        approving_manager_id: newManager,
      });

      // Submit immediately if requested
      if (submitImmediate) {
        await api.submitRequest(created.id);
        addToast({
          type: 'success',
          title: 'Request Submitted',
          message: 'Your request has been submitted to your manager for review and approval.',
        });
        onNavigate('employee_submitted');
      } else {
        addToast({
          type: 'success',
          title: 'Draft Saved',
          message: 'Request draft has been saved. You can submit it when ready.',
        });
        onNavigate('employee_drafts');
      }

      resetForm();
      loadAllData();
    } catch (err) {
      setFormError(err.message || 'Failed to create request.');
    } finally {
      setFormSubmitting(false);
    }
  };

  const handleSubmitDraft = async (id) => {
    try {
      await api.submitRequest(id);
      addToast({
        type: 'success',
        title: 'Submitted for Approval',
        message: 'Request sent to your manager for review.',
      });
      loadAllData();
    } catch (err) {
      addToast({ type: 'error', title: 'Submit Failed', message: err.message });
    }
  };

  const handleSaveEditDraft = async (e) => {
    e.preventDefault();
    if (!editingDraft) return;

    try {
      setFormSubmitting(true);
      await api.updateDraft(editingDraft.id, {
        amount: parseFloat(editingDraft.amount),
        purpose: editingDraft.purpose,
        notes: editingDraft.notes,
        category: editingDraft.category,
      });
      addToast({
        type: 'success',
        title: 'Draft Updated',
        message: 'Changes saved successfully.',
      });
      setIsEditOpen(false);
      loadAllData();
    } catch (err) {
      addToast({ type: 'error', title: 'Update Failed', message: err.message });
    } finally {
      setFormSubmitting(false);
    }
  };

  // ── Render Views
  return (
    <div className="space-y-6">
      {/* ── View: Dashboard */}
      {currentView === 'employee_dashboard' && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-4">
            <div>
              <h1 className="text-xl font-bold text-slate-100">Employee Workspace</h1>
              <p className="text-xs text-slate-400 mt-1">
                Create reimbursement drafts, track approval status, and manage voucher receipts.
              </p>
            </div>
            <button
              type="button"
              onClick={() => onNavigate('employee_new_request')}
              className="flex items-center gap-2 px-3.5 py-2 rounded-md bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-semibold shadow-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 transition-colors cursor-pointer"
            >
              <PlusCircle className="w-4 h-4" /> New Reimbursement Request
            </button>
          </div>

          {/* KPI Stat Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div
              onClick={() => onNavigate('employee_drafts')}
              className="p-5 bg-slate-900 border border-slate-800 rounded-lg shadow-sm hover:border-slate-700 cursor-pointer transition-all"
            >
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-xs font-medium uppercase tracking-wider">Drafts & Returned</span>
                <FileClock className="w-5 h-5 text-amber-400" />
              </div>
              <div className="text-2xl font-bold text-slate-100">{drafts.length}</div>
              <div className="text-[11px] text-slate-400 mt-1">
                {drafts.filter((d) => d.status === 'RETURNED_FOR_CORRECTION').length} returned for changes
              </div>
            </div>

            <div
              onClick={() => onNavigate('employee_submitted')}
              className="p-5 bg-slate-900 border border-slate-800 rounded-lg shadow-sm hover:border-slate-700 cursor-pointer transition-all"
            >
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-xs font-medium uppercase tracking-wider">In Review</span>
                <Send className="w-5 h-5 text-emerald-400" />
              </div>
              <div className="text-2xl font-bold text-slate-100">{submitted.length}</div>
              <div className="text-[11px] text-slate-400 mt-1">
                Awaiting manager decision or admin posting
              </div>
            </div>

            <div
              onClick={() => onNavigate('employee_history')}
              className="p-5 bg-slate-900 border border-slate-800 rounded-lg shadow-sm hover:border-slate-700 cursor-pointer transition-all"
            >
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-xs font-medium uppercase tracking-wider">Completed / History</span>
                <History className="w-5 h-5 text-slate-400" />
              </div>
              <div className="text-2xl font-bold text-slate-100">{history.length}</div>
              <div className="text-[11px] text-slate-400 mt-1">Posted or rejected requests</div>
            </div>
          </div>

          {/* Quick Recent Activity */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 shadow-sm space-y-3">
            <h2 className="text-sm font-semibold text-slate-200">Recent Request Activity</h2>
            {requests.length === 0 ? (
              <div className="text-center py-8 text-xs text-slate-400">
                No requests created yet. Click "New Reimbursement Request" to get started.
              </div>
            ) : (
              <div className="divide-y divide-slate-800/80">
                {requests.slice(0, 5).map((r) => (
                  <div key={r.id} className="py-3 flex items-center justify-between text-xs">
                    <div>
                      <div className="font-semibold text-slate-200">{r.purpose}</div>
                      <div className="text-slate-400 text-[11px] mt-0.5">
                        {r.request_date} • {r.project_name || 'Project'} • {r.category}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-bold text-slate-100">₹{parseFloat(r.amount).toFixed(2)}</div>
                      <span className={`inline-block mt-0.5 px-2 py-0.5 rounded text-[10px] font-semibold ${
                        r.status === 'POSTED'
                          ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                          : r.status === 'SUBMITTED'
                          ? 'bg-blue-950 text-blue-300 border border-blue-800'
                          : r.status === 'RETURNED_FOR_CORRECTION'
                          ? 'bg-amber-950 text-amber-300 border border-amber-800'
                          : 'bg-slate-800 text-slate-300'
                      }`}>
                        {r.status}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── View: New Request Form */}
      {currentView === 'employee_new_request' && (
        <div className="max-w-2xl mx-auto bg-slate-900 border border-slate-800 rounded-lg p-6 shadow-sm space-y-6">
          <div className="border-b border-slate-800 pb-3">
            <h1 className="text-lg font-bold text-slate-100">Create Reimbursement Request</h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Fill in the expenditure details and attach the official invoice or receipt.
            </p>
          </div>

          {formError && (
            <div className="p-3 bg-rose-950/80 border border-rose-800 rounded text-xs text-rose-200">
              {formError}
            </div>
          )}

          <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Amount (₹) *
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  required
                  value={newAmount}
                  onChange={(e) => setNewAmount(e.target.value)}
                  placeholder="0.00"
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-sm text-slate-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Request Date *
                </label>
                <input
                  type="date"
                  required
                  value={newDate}
                  onChange={(e) => setNewDate(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-sm text-slate-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Purpose / Memo *
              </label>
              <input
                type="text"
                required
                value={newPurpose}
                onChange={(e) => setNewPurpose(e.target.value)}
                placeholder="e.g. Travel tickets, client lunch, stationary supplies"
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-sm text-slate-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Project *
                </label>
                <select
                  value={newProject}
                  onChange={(e) => setNewProject(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-sm text-slate-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                >
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Ledger Head *
                </label>
                <select
                  value={newLedger}
                  onChange={(e) => setNewLedger(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-sm text-slate-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                >
                  {ledgers.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Category *
                </label>
                <input
                  type="text"
                  value={newCategory}
                  onChange={(e) => setNewCategory(e.target.value)}
                  placeholder="e.g. Travel, Office"
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-sm text-slate-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                />
              </div>
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Approving Manager *
              </label>
              {assignments.length === 0 ? (
                <div className="p-2.5 rounded bg-amber-950/40 border border-amber-800 text-amber-300 text-xs">
                  No active manager assignment found. Contact Admin to assign an approving manager.
                </div>
              ) : (
                <select
                  value={newManager}
                  onChange={(e) => setNewManager(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-sm text-slate-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                >
                  {assignments.map((a) => (
                    <option key={a.manager_id} value={a.manager_id}>
                      {a.manager_username || a.manager_email || a.manager_id}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Additional Notes
              </label>
              <textarea
                rows={2}
                value={newNotes}
                onChange={(e) => setNewNotes(e.target.value)}
                placeholder="Optional notes or context for manager review"
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-sm text-slate-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              />
            </div>

            {/* Workflow Notice */}
            <div className="p-3 bg-slate-950/80 rounded-lg border border-slate-800 text-xs text-slate-400 flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold text-slate-200">Two-Stage Workflow: </span>
                You do not need to attach receipt vouchers right now. Once your assigned manager reviews and approves your request, you will be prompted to attach your vouchers and submit for finance posting.
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-800">
              <button
                type="button"
                disabled={formSubmitting}
                onClick={() => handleCreateRequest(false)}
                className="px-4 py-2 rounded-md bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-slate-500 disabled:opacity-50 transition-colors cursor-pointer"
              >
                Save as Draft
              </button>
              <button
                type="button"
                disabled={formSubmitting || assignments.length === 0}
                onClick={() => handleCreateRequest(true)}
                className="flex items-center gap-1.5 px-4 py-2 rounded-md bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-50 transition-colors cursor-pointer"
              >
                <Send className="w-3.5 h-3.5" /> Submit for Approval
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ── View: Drafts & Returned */}
      {currentView === 'employee_drafts' && (
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h1 className="text-lg font-bold text-slate-100">Drafts & Returned for Changes</h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Review unsubmitted requests and address feedback on returned vouchers.
              </p>
            </div>
          </div>

          {drafts.length === 0 ? (
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-10 text-center text-xs text-slate-400">
              No drafts pending. Click "New Request" to create a new voucher.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {drafts.map((d) => (
                <div
                  key={d.id}
                  className="bg-slate-900 border border-slate-800 rounded-lg p-4 shadow-sm space-y-3"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="font-semibold text-slate-100 text-sm">{d.purpose}</div>
                      <div className="text-[11px] text-slate-400 mt-0.5">
                        {d.request_date} • {d.project_name || 'Project'} • {d.category}
                      </div>
                    </div>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      d.status === 'RETURNED_FOR_CORRECTION'
                        ? 'bg-amber-950 text-amber-300 border border-amber-800'
                        : 'bg-slate-800 text-slate-300'
                    }`}>
                      {d.status}
                    </span>
                  </div>

                  {d.status === 'RETURNED_FOR_CORRECTION' && d.decision_reason && (
                    <div className="p-2.5 rounded bg-amber-950/40 border border-amber-900 text-amber-200 text-xs">
                      <strong>Feedback:</strong> {d.decision_reason}
                    </div>
                  )}

                  <div className="flex items-center justify-between pt-2 border-t border-slate-800/80">
                    <span className="text-base font-bold text-slate-100">
                      ₹{parseFloat(d.amount).toFixed(2)}
                    </span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          setEditingDraft({ ...d });
                          setIsEditOpen(true);
                        }}
                        className="px-2.5 py-1.5 rounded text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 transition-colors"
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        onClick={() => handleSubmitDraft(d.id)}
                        className="flex items-center gap-1 px-3 py-1.5 rounded text-xs font-semibold text-slate-950 bg-emerald-500 hover:bg-emerald-400 transition-colors"
                      >
                        <Send className="w-3 h-3" /> Submit
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── View: Submitted Requests */}
      {currentView === 'employee_submitted' && (
        <div className="space-y-6">
          <div className="border-b border-slate-800 pb-3">
            <h1 className="text-lg font-bold text-slate-100">In-Flight Submitted Requests</h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Track requests through manager approval, voucher upload, and finance ledger posting.
            </p>
          </div>

          {/* Section 1: Approved - Ready for Finance Posting (Optional Voucher Upload) */}
          {submitted.filter((s) => s.status === 'APPROVED').length > 0 && (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-xs font-bold text-emerald-400 uppercase tracking-wider">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                Manager Approved — In Finance Posting Queue ({submitted.filter((s) => s.status === 'APPROVED').length})
              </div>

              {submitted
                .filter((s) => s.status === 'APPROVED')
                .map((s) => (
                  <div
                    key={s.id}
                    className="p-4 bg-emerald-950/20 border border-emerald-800/80 rounded-lg shadow-sm space-y-3"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div>
                        <div className="font-semibold text-slate-100 text-sm flex items-center gap-2">
                          <span>{s.purpose}</span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-700">
                            APPROVED • SENT TO FINANCE
                          </span>
                        </div>
                        <div className="text-xs text-slate-400 mt-1">
                          Date: {s.request_date} • Category: {s.category_name || s.category} • Amount: <strong className="text-slate-100">₹{parseFloat(s.amount).toFixed(2)}</strong>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() => {
                            setTargetVoucherRequest(s);
                            setVoucherFile(null);
                            setVoucherModalOpen(true);
                          }}
                          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-emerald-400 text-xs font-semibold border border-slate-700 cursor-pointer"
                        >
                          <FileUp className="w-3.5 h-3.5" />
                          {s.supporting_count > 0 ? 'Add Another Voucher' : 'Upload Voucher (Optional)'}
                        </button>
                      </div>
                    </div>

                    {s.supporting_count > 0 ? (
                      <div className="p-2.5 bg-slate-900/90 rounded border border-slate-800 flex flex-wrap items-center gap-2 text-xs">
                        <span className="text-emerald-400 font-medium">{s.supporting_count} voucher(s) attached.</span>
                      </div>
                    ) : (
                      <div className="text-[11px] text-slate-400 flex items-center gap-1.5">
                        <Clock className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        Finance can post this request directly. You may upload supporting vouchers now or later after posting.
                      </div>
                    )}
                  </div>
                ))}
            </div>
          )}

          {/* Section 2: Under Manager Review or Ready for Posting */}
          <div className="space-y-3">
            <div className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              Other In-Flight Requests
            </div>
            {submitted.filter((s) => s.status !== 'APPROVED').length === 0 &&
            submitted.filter((s) => s.status === 'APPROVED').length === 0 ? (
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-10 text-center text-xs text-slate-400">
                No submitted requests in flight right now.
              </div>
            ) : (
              submitted
                .filter((s) => s.status !== 'APPROVED')
                .map((s) => (
                  <div
                    key={s.id}
                    className="bg-slate-900 border border-slate-800 rounded-lg p-4 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4"
                  >
                    <div className="space-y-1">
                      <div className="font-semibold text-slate-100 text-sm">{s.purpose}</div>
                      <div className="text-xs text-slate-400">
                        Date: {s.request_date} • Category: {s.category}
                      </div>
                    </div>

                    <div className="flex items-center gap-6">
                      <div className="text-right">
                        <div className="font-bold text-slate-100 text-sm">
                          ₹{parseFloat(s.amount).toFixed(2)}
                        </div>
                        <span
                          className={`text-[10px] font-semibold px-2 py-0.5 rounded border ${
                            s.status === 'SUPPORTING_UPLOADED'
                              ? 'text-cyan-300 bg-cyan-950/60 border-cyan-800'
                              : 'text-amber-300 bg-amber-950/60 border-amber-800'
                          }`}
                        >
                          {s.status === 'SUPPORTING_UPLOADED'
                            ? 'Vouchers Submitted • Awaiting Admin Posting'
                            : 'Pending Manager Approval'}
                        </span>
                      </div>
                    </div>
                  </div>
                ))
            )}
          </div>
        </div>
      )}

      {/* ── View: Request History */}
      {currentView === 'employee_history' && (
        <div className="space-y-4">
          <div className="border-b border-slate-800 pb-3">
            <h1 className="text-lg font-bold text-slate-100">Request & Reimbursement History</h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Historical ledger entries, postings, and archived transactions.
            </p>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-200">
                <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                  <tr>
                    <th className="p-3">Date</th>
                    <th className="p-3">Purpose</th>
                    <th className="p-3">Project / Ledger</th>
                    <th className="p-3">Amount</th>
                    <th className="p-3">Status</th>
                    <th className="p-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {history.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-6 text-center text-slate-500">
                        No past history recorded.
                      </td>
                    </tr>
                  ) : (
                    history
                      .slice((historyPage - 1) * historyPageSize, historyPage * historyPageSize)
                      .map((h) => (
                      <tr key={h.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="p-3 font-mono">{h.request_date}</td>
                        <td className="p-3 font-medium text-slate-100">{h.purpose}</td>
                        <td className="p-3 text-slate-400">
                          {h.project_name || 'Project'} / {h.category_name || h.category}
                        </td>
                        <td className="p-3 font-bold text-slate-100">
                          ₹{parseFloat(h.amount).toFixed(2)}
                        </td>
                        <td className="p-3">
                          {h.status === 'POSTED' ? (
                            <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                              h.supporting_count > 0
                                ? 'bg-emerald-950 text-emerald-300 border-emerald-800'
                                : 'bg-amber-950 text-amber-300 border-amber-800'
                            }`}>
                              {h.supporting_count > 0 ? 'Posted (Voucher Attached)' : 'Posted (Voucher Pending)'}
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-950 text-rose-300 border border-rose-800">
                              {h.status}
                            </span>
                          )}
                        </td>
                        <td className="p-3 text-right">
                          <div className="inline-flex items-center gap-1 justify-end">
                            {h.status === 'POSTED' && (
                              <button
                                type="button"
                                onClick={() => {
                                  setTargetVoucherRequest(h);
                                  setVoucherFile(null);
                                  setVoucherModalOpen(true);
                                }}
                                className="inline-flex items-center gap-1 px-2 py-1 text-[10px] font-semibold rounded bg-slate-800 hover:bg-slate-700 text-emerald-400 border border-slate-700 cursor-pointer"
                                title="Upload supporting voucher"
                              >
                                <FileUp className="w-3 h-3" /> Voucher
                              </button>
                            )}
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedRequest(h);
                                setIsDetailOpen(true);
                              }}
                              className="p-1 text-slate-400 hover:text-white rounded hover:bg-slate-800 cursor-pointer"
                              title="View details"
                            >
                              <Eye className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <TablePagination
              totalItems={history.length}
              currentPage={historyPage}
              pageSize={historyPageSize}
              onPageChange={setHistoryPage}
              onPageSizeChange={(s) => { setHistoryPageSize(s); setHistoryPage(1); }}
            />
          </div>
        </div>
      )}

      {/* ── View: Assigned Managers */}
      {currentView === 'employee_managers' && (
        <div className="space-y-4">
          <div className="border-b border-slate-800 pb-3">
            <h1 className="text-lg font-bold text-slate-100">Authorized Approving Managers</h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Management personnel authorized to review and approve your reimbursement vouchers.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {assignments.length === 0 ? (
              <div className="col-span-2 p-8 bg-slate-900 border border-slate-800 rounded-lg text-center text-xs text-slate-400">
                No active approving manager assignments configured for your profile. Contact system administration.
              </div>
            ) : (
              assignments.map((a) => (
                <div key={a.id} className="p-4 bg-slate-900 border border-slate-800 rounded-lg shadow-sm flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center font-bold text-emerald-400">
                    M
                  </div>
                  <div>
                    <div className="font-semibold text-sm text-slate-100">{a.manager_username || 'Manager'}</div>
                    <div className="text-xs text-slate-400">{a.manager_email}</div>
                    <span className="inline-block mt-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800">
                      Active Approver
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* ── Edit Draft Modal */}
      <Modal
        isOpen={isEditOpen}
        onClose={() => setIsEditOpen(false)}
        title="Edit Reimbursement Draft"
      >
        {editingDraft && (
          <form onSubmit={handleSaveEditDraft} className="space-y-4 text-xs">
            <div>
              <label className="block font-medium text-slate-300 mb-1">Amount (₹)</label>
              <input
                type="number"
                step="0.01"
                required
                value={editingDraft.amount}
                onChange={(e) =>
                  setEditingDraft({ ...editingDraft, amount: e.target.value })
                }
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block font-medium text-slate-300 mb-1">Purpose / Description</label>
              <input
                type="text"
                required
                value={editingDraft.purpose}
                onChange={(e) =>
                  setEditingDraft({ ...editingDraft, purpose: e.target.value })
                }
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block font-medium text-slate-300 mb-1">Category</label>
              <input
                type="text"
                value={editingDraft.category || ''}
                onChange={(e) =>
                  setEditingDraft({ ...editingDraft, category: e.target.value })
                }
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block font-medium text-slate-300 mb-1">Notes</label>
              <textarea
                rows={2}
                value={editingDraft.notes || ''}
                onChange={(e) =>
                  setEditingDraft({ ...editingDraft, notes: e.target.value })
                }
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              />
            </div>

            <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setIsEditOpen(false)}
                className="px-3 py-1.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={formSubmitting}
                className="px-4 py-1.5 rounded bg-emerald-600 text-slate-950 font-semibold hover:bg-emerald-500"
              >
                {formSubmitting ? 'Saving...' : 'Save Draft'}
              </button>
            </div>
          </form>
        )}
      </Modal>

      {/* ── Detail Modal */}
      <Modal
        isOpen={isDetailOpen}
        onClose={() => setIsDetailOpen(false)}
        title="Request Details & Evidence"
      >
        {selectedRequest && (
          <div className="space-y-4 text-xs">
            <div className="grid grid-cols-2 gap-3 p-3 bg-slate-950 rounded-md border border-slate-800">
              <div>
                <span className="text-slate-400 block mb-0.5">Request ID</span>
                <span className="font-mono font-medium text-slate-200">{selectedRequest.id}</span>
              </div>
              <div>
                <span className="text-slate-400 block mb-0.5">Amount</span>
                <span className="font-bold text-emerald-400 text-sm">
                  ₹{parseFloat(selectedRequest.amount).toFixed(2)}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block mb-0.5">Status</span>
                <span className="font-semibold text-slate-100">{selectedRequest.status}</span>
              </div>
              <div>
                <span className="text-slate-400 block mb-0.5">Date</span>
                <span className="text-slate-100">{selectedRequest.request_date}</span>
              </div>
            </div>

            <div className="p-3 bg-slate-950 rounded-md border border-slate-800 space-y-1">
              <span className="text-slate-400 block">Purpose</span>
              <p className="text-slate-200 font-medium">{selectedRequest.purpose}</p>
              {selectedRequest.notes && (
                <p className="text-slate-400 italic pt-1">Notes: {selectedRequest.notes}</p>
              )}
            </div>

            {selectedRequest.supporting_files && selectedRequest.supporting_files.length > 0 && (
              <div className="space-y-2">
                <span className="font-semibold text-slate-300">Attached Supporting Voucher</span>
                <div className="space-y-1">
                  {selectedRequest.supporting_files.map((f) => (
                    <div
                      key={f.id}
                      className="p-2.5 rounded bg-slate-950 border border-slate-800 flex items-center justify-between"
                    >
                      <div className="flex items-center gap-2">
                        <FileText className="w-4 h-4 text-emerald-400" />
                        <span className="text-slate-200">{f.original_filename}</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => api.downloadFile(api.getSupportingFileDownloadUrl(f.id), f.original_filename)}
                        className="flex items-center gap-1 text-emerald-400 hover:underline text-xs"
                      >
                        Download <ExternalLink className="w-3 h-3" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
      {/* ── Voucher Upload Modal */}
      <Modal
        isOpen={voucherModalOpen}
        onClose={() => setVoucherModalOpen(false)}
        title="Upload Supporting Voucher / Receipt"
      >
        <form onSubmit={handleUploadVoucher} className="space-y-4 text-xs">
          {targetVoucherRequest && (
            <div className="p-3 bg-slate-950 rounded border border-slate-800 space-y-1">
              <div className="font-semibold text-slate-100">{targetVoucherRequest.purpose}</div>
              <div className="text-slate-400">
                Amount: <span className="font-bold text-emerald-400">₹{parseFloat(targetVoucherRequest.amount).toFixed(2)}</span>
              </div>
            </div>
          )}

          <div>
            <label className="block text-slate-300 font-medium mb-1">
              Select Voucher File (PDF, PNG, JPEG) *
            </label>
            <div className="p-4 border-2 border-dashed border-slate-700 hover:border-slate-500 rounded-lg text-center bg-slate-950/60 transition-colors">
              <input
                type="file"
                id="modal-voucher-file-input"
                accept=".pdf,image/png,image/jpeg"
                required
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    const f = e.target.files[0];
                    if (f.size > 10 * 1024 * 1024) {
                      addToast({ type: 'error', message: 'File exceeds 10MB limit.' });
                      return;
                    }
                    setVoucherFile(f);
                  }
                }}
                className="sr-only"
              />
              <label
                htmlFor="modal-voucher-file-input"
                className="cursor-pointer flex flex-col items-center justify-center gap-1.5"
              >
                <FileUp className="w-6 h-6 text-emerald-400" />
                <span className="text-xs text-slate-300 font-medium">
                  {voucherFile ? voucherFile.name : 'Click to select receipt or invoice file'}
                </span>
                <span className="text-[10px] text-slate-500">Max size 10MB (PDF, PNG, JPEG)</span>
              </label>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setVoucherModalOpen(false)}
              className="px-3.5 py-1.5 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={uploadingVoucher || !voucherFile}
              className="px-4 py-1.5 rounded bg-emerald-600 text-slate-950 font-bold hover:bg-emerald-500 disabled:opacity-50 cursor-pointer"
            >
              {uploadingVoucher ? 'Uploading...' : 'Upload Voucher'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
