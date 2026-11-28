import React, { useState, useEffect } from 'react';
import {
  FileCheck2,
  Users,
  History,
  UserCog,
  CheckCircle2,
  AlertCircle,
  XCircle,
  MessageSquare,
  FileText,
  ExternalLink,
  Clock,
  ArrowRight,
  PlusCircle,
  Send,
  FileUp,
  Download,
  FileSpreadsheet,
  RefreshCw,
} from 'lucide-react';
import { api } from '../api';
import Modal from '../components/Modal';
import TablePagination from '../components/TablePagination';

export default function ManagerViews({ currentView, onNavigate, addToast, user }) {
  const [loading, setLoading] = useState(false);
  const [requests, setRequests] = useState(() => {
    try {
      const c = localStorage.getItem(`pc_mgr_reqs_${user?.id}`);
      return c ? JSON.parse(c) : [];
    } catch { return []; }
  });
  const [assignments, setAssignments] = useState([]);
  const [financeAssignments, setFinanceAssignments] = useState([]);
  const [projects, setProjects] = useState([]);
  const [ledgers, setLedgers] = useState([]);

  // Manager New Request state
  const [reqAmount, setReqAmount] = useState('');
  const [reqPurpose, setReqPurpose] = useState('');
  const [reqDate, setReqDate] = useState(new Date().toISOString().split('T')[0]);
  const [reqProject, setReqProject] = useState('');
  const [reqLedger, setReqLedger] = useState('');
  const [reqCategory, setReqCategory] = useState('');
  const [reqNotes, setReqNotes] = useState('');
  const [submittingReq, setSubmittingReq] = useState(false);

  // Voucher upload modal for Manager requests
  const [voucherModalOpen, setVoucherModalOpen] = useState(false);
  const [targetVoucherRequest, setTargetVoucherRequest] = useState(null);
  const [voucherFile, setVoucherFile] = useState(null);
  const [uploadingVoucher, setUploadingVoucher] = useState(false);

  // Reports (view-only) state
  const [reportMonth, setReportMonth] = useState(new Date().toISOString().slice(0, 7));
  const [monthlyReport, setMonthlyReport] = useState(null);
  const [reportPage, setReportPage] = useState(1);
  const [reportPageSize, setReportPageSize] = useState(10);

  // Pagination state
  const [historyPage, setHistoryPage] = useState(1);
  const [historyPageSize, setHistoryPageSize] = useState(10);
  const [myReqPage, setMyReqPage] = useState(1);
  const [myReqPageSize, setMyReqPageSize] = useState(10);

  // Decision Modal state
  const [decisionModalOpen, setDecisionModalOpen] = useState(false);
  const [decisionType, setDecisionType] = useState('APPROVE'); // 'APPROVE' | 'CHANGES' | 'REJECT'
  const [targetRequest, setTargetRequest] = useState(null);
  const [decisionReason, setDecisionReason] = useState('');
  const [submittingDecision, setSubmittingDecision] = useState(false);
  const [assignmentTab, setAssignmentTab] = useState('pending'); // 'pending' | 'active'

  const loadData = async () => {
    try {
      setLoading(true);
      const promises = [
        api.listRequests().then((d) => {
          setRequests(d || []);
          try { localStorage.setItem(`pc_mgr_reqs_${user?.id}`, JSON.stringify(d || [])); } catch (_) {}
        }),
        api.listAssignments().then((d) => setAssignments(d || [])),
        api.listFinanceAssignments().then((d) => setFinanceAssignments(d || [])).catch(() => []),
      ];
      if (currentView === 'manager_new_request') {
        promises.push(
          api.getProjects().then((d) => {
            const active = (d || []).filter((p) => p.is_active);
            setProjects(active);
            if (active.length > 0 && !reqProject) setReqProject(active[0].id);
          }),
          api.getLedgers().then((d) => {
            const active = (d || []).filter((l) => l.is_active);
            setLedgers(active);
            if (active.length > 0 && !reqLedger) setReqLedger(active[0].id);
          })
        );
      }
      if (currentView === 'manager_reports') {
        promises.push(
          api.getMonthlyReport(reportMonth).then((d) => setMonthlyReport(d)).catch(() => null)
        );
      }
      await Promise.all(promises);
    } catch (e) {
      console.error(e);
      addToast({ type: 'error', message: 'Failed to load manager queue data.' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [currentView, reportMonth]);

  const assignedFinance = financeAssignments.find(
    (fa) => fa.manager_id === user?.id && fa.status === 'APPROVED'
  );
  const myRequests = requests.filter((r) => r.requester_id === user?.id);

  const handleSubmitManagerRequest = async (e) => {
    e.preventDefault();
    if (!assignedFinance) {
      addToast({ type: 'error', message: 'You must be assigned to a Finance user first.' });
      return;
    }
    try {
      setSubmittingReq(true);
      const draft = await api.createRequest({
        project_id: reqProject,
        ledger_id: reqLedger,
        category: reqCategory.trim(),
        request_date: reqDate,
        amount: parseFloat(reqAmount),
        purpose: reqPurpose.trim(),
        notes: reqNotes.trim() || null,
        approving_manager_id: assignedFinance.finance_user_id,
      });
      await api.submitRequest(draft.id);
      addToast({
        type: 'success',
        title: 'Request Submitted',
        message: `Request routed to Finance user ${assignedFinance.finance_username} for posting.`,
      });
      setReqAmount('');
      setReqPurpose('');
      setReqCategory('');
      setReqNotes('');
      onNavigate('manager_my_requests');
    } catch (err) {
      addToast({ type: 'error', title: 'Submission Failed', message: err.message });
    } finally {
      setSubmittingReq(false);
    }
  };

  const handleUploadManagerVoucher = async (e) => {
    e.preventDefault();
    if (!voucherFile || !targetVoucherRequest) return;
    try {
      setUploadingVoucher(true);
      await api.uploadSupportingFile(targetVoucherRequest.id, voucherFile);
      addToast({
        type: 'success',
        title: 'Voucher Uploaded',
        message: `Supporting voucher attached and reflected in reports.`,
      });
      setVoucherModalOpen(false);
      setVoucherFile(null);
      loadData();
    } catch (err) {
      addToast({ type: 'error', title: 'Upload Failed', message: err.message });
    } finally {
      setUploadingVoucher(false);
    }
  };

  // Filter queues
  const pendingQueue = requests.filter(
    (r) => r.status === 'SUBMITTED' && r.approving_manager_id === user?.id
  );
  const pendingAssignments = assignments.filter(
    (a) => a.manager_id === user?.id && a.status === 'PENDING'
  );
  const activeEmployees = assignments.filter(
    (a) => a.manager_id === user?.id && a.status === 'APPROVED'
  );
  const decisionHistory = requests.filter(
    (r) =>
      r.approving_manager_id === user?.id &&
      (r.status === 'APPROVED' || r.status === 'REJECTED' || r.status === 'DRAFT' || r.status === 'POSTED')
  );

  const totalApprovedAmount = requests
    .filter(
      (r) =>
        r.approving_manager_id === user?.id &&
        (r.status === 'APPROVED' || r.status === 'POSTED')
    )
    .reduce((sum, r) => sum + parseFloat(r.amount || 0), 0);

  const openDecisionModal = (reqItem, type) => {
    setTargetRequest(reqItem);
    setDecisionType(type);
    setDecisionReason('');
    setDecisionModalOpen(true);
  };

  const executeDecision = async () => {
    if (!targetRequest) return;

    if (decisionType !== 'APPROVE' && !decisionReason.trim()) {
      addToast({ type: 'error', message: 'Reason / feedback is required for this action.' });
      return;
    }

    try {
      setSubmittingDecision(true);
      if (decisionType === 'APPROVE') {
        await api.approveRequest(targetRequest.id);
        addToast({
          type: 'success',
          title: 'Request Approved',
          message: `Request for ₹${targetRequest.amount} approved and forwarded to Finance/Admin.`,
        });
      } else if (decisionType === 'CHANGES') {
        await api.requestChanges(targetRequest.id, decisionReason.trim());
        addToast({
          type: 'success',
          title: 'Changes Requested',
          message: 'Returned to employee draft with your feedback notes.',
        });
      } else if (decisionType === 'REJECT') {
        await api.rejectRequest(targetRequest.id, decisionReason.trim());
        addToast({
          type: 'success',
          title: 'Request Rejected',
          message: 'Request has been rejected.',
        });
      }
      setDecisionModalOpen(false);
      loadData();
    } catch (err) {
      addToast({ type: 'error', title: 'Decision Failed', message: err.message });
    } finally {
      setSubmittingDecision(false);
    }
  };

  const handleReviewAssignment = async (assignmentId, decision) => {
    try {
      await api.reviewAssignment(assignmentId, decision, 'Manager review');
      addToast({
        type: 'success',
        title: 'Assignment Updated',
        message: `Employee assignment ${decision.toLowerCase()}.`,
      });
      loadData();
    } catch (err) {
      addToast({ type: 'error', title: 'Action Failed', message: err.message });
    }
  };

  return (
    <div className="space-y-6">
      {/* ── View: Manager Dashboard */}
      {currentView === 'manager_dashboard' && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-4">
            <div>
              <h1 className="text-xl font-bold text-slate-100">Manager Dashboard</h1>
              <p className="text-xs text-slate-400 mt-1">
                Review assigned team reimbursement submissions and verify expenditure evidence.
              </p>
            </div>
          </div>

          {/* KPI Stat Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div
              onClick={() => onNavigate('manager_approvals')}
              className="p-5 bg-slate-900 border border-slate-800 rounded-lg shadow-sm hover:border-slate-700 cursor-pointer transition-all"
            >
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-xs font-medium uppercase tracking-wider">Approval Queue</span>
                <FileCheck2 className="w-5 h-5 text-emerald-400" />
              </div>
              <div className="text-2xl font-bold text-slate-100">{pendingQueue.length}</div>
              <div className="text-[11px] text-slate-400 mt-1">
                Submissions awaiting your approval decision
              </div>
            </div>

            <div
              onClick={() => {
                setAssignmentTab('pending');
                onNavigate('manager_assignments');
              }}
              className="p-5 bg-slate-900 border border-slate-800 rounded-lg shadow-sm hover:border-slate-700 cursor-pointer transition-all"
            >
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-xs font-medium uppercase tracking-wider">Pending Assignments</span>
                <UserCog className="w-5 h-5 text-amber-400" />
              </div>
              <div className="text-2xl font-bold text-slate-100">{pendingAssignments.length}</div>
              <div className="text-[11px] text-slate-400 mt-1">
                Assignments awaiting your confirmation
              </div>
            </div>

            <div
              onClick={() => {
                setAssignmentTab('active');
                onNavigate('manager_assignments');
              }}
              className="p-5 bg-slate-900 border border-slate-800 rounded-lg shadow-sm hover:border-slate-700 cursor-pointer transition-all"
            >
              <div className="flex items-center justify-between text-slate-400 mb-2">
                <span className="text-xs font-medium uppercase tracking-wider">Active Team</span>
                <Users className="w-5 h-5 text-purple-400" />
              </div>
              <div className="text-2xl font-bold text-slate-100">{activeEmployees.length}</div>
              <div className="text-[11px] text-slate-400 mt-1">
                Active employees in your designated team
              </div>
            </div>
          </div>

          {/* Quick Pending Approvals Table Preview */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-200">Pending Review Submissions</h2>
              {pendingQueue.length > 0 && (
                <button
                  type="button"
                  onClick={() => onNavigate('manager_approvals')}
                  className="text-xs text-emerald-400 hover:text-emerald-300 font-semibold flex items-center gap-1"
                >
                  View All ({pendingQueue.length}) <ArrowRight className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {pendingQueue.length === 0 ? (
              <div className="text-center py-8 text-xs text-slate-400">
                All caught up! No requests waiting for your approval.
              </div>
            ) : (
              <div className="divide-y divide-slate-800/80">
                {pendingQueue.slice(0, 5).map((r) => (
                  <div key={r.id} className="py-3 flex items-center justify-between text-xs">
                    <div>
                      <div className="font-semibold text-slate-200">{r.purpose}</div>
                      <div className="text-slate-400 text-[11px] mt-0.5">
                        Requester: {r.requester_username || r.requester_id} • {r.request_date} • {r.category}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="font-bold text-slate-100 text-sm">
                        ₹{parseFloat(r.amount).toFixed(2)}
                      </span>
                      <button
                        type="button"
                        onClick={() => openDecisionModal(r, 'APPROVE')}
                        className="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-semibold text-[11px]"
                      >
                        Review
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── View: Approval Queue */}
      {currentView === 'manager_approvals' && (
        <div className="space-y-4">
          <div className="border-b border-slate-800 pb-3">
            <h1 className="text-lg font-bold text-slate-100">Team Approval Queue</h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Review receipts, verify purpose authenticity, and make financial approval decisions.
            </p>
          </div>

          {pendingQueue.length === 0 ? (
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-10 text-center text-xs text-slate-400">
              No reimbursement requests pending approval right now.
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4">
              {pendingQueue.map((r) => {
                const isSelfRequest = r.requester_id === user?.id;

                return (
                  <div
                    key={r.id}
                    className="bg-slate-900 border border-slate-800 rounded-lg p-5 shadow-sm space-y-4"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                      <div>
                        <div className="flex items-center gap-2">
                          <span className="text-base font-bold text-slate-100">{r.purpose}</span>
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-950 text-blue-300 border border-blue-800">
                            SUBMITTED
                          </span>
                        </div>
                        <div className="text-xs text-slate-400 mt-1">
                          Requester: <strong className="text-slate-300">{r.requester_username || r.requester_email || r.requester_id}</strong> • Date: {r.request_date} • Category: {r.category}
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-xl font-extrabold text-emerald-400">
                          ₹{parseFloat(r.amount).toFixed(2)}
                        </div>
                        <div className="text-[10px] text-slate-500 font-mono">ID: {r.id}</div>
                      </div>
                    </div>

                    {r.notes && (
                      <div className="p-3 bg-slate-950 rounded border border-slate-800/80 text-xs text-slate-300">
                        <strong className="text-slate-400 block mb-0.5">Employee Notes:</strong>
                        {r.notes}
                      </div>
                    )}

                    {/* Supporting files preview/download */}
                    {r.supporting_files && r.supporting_files.length > 0 && (
                      <div className="space-y-1.5">
                        <span className="text-xs font-semibold text-slate-400 block">
                          Attached Receipt Evidence:
                        </span>
                        <div className="flex flex-wrap gap-2">
                          {r.supporting_files.map((file) => (
                            <button
                              key={file.id}
                              type="button"
                              onClick={() => api.downloadFile(api.getSupportingFileDownloadUrl(file.id), file.original_filename)}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-950 border border-slate-800 hover:border-slate-700 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
                            >
                              <FileText className="w-3.5 h-3.5" />
                              <span className="truncate max-w-[200px]">{file.original_filename}</span>
                              <ExternalLink className="w-3 h-3 text-slate-500" />
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Self-approval guard warning */}
                    {isSelfRequest && (
                      <div className="p-3 bg-amber-950/60 border border-amber-800 rounded text-xs text-amber-200 flex items-center gap-2">
                        <AlertCircle className="w-4 h-4 shrink-0 text-amber-400" />
                        <span>
                          Self-approval restriction: As the requester, you cannot approve your own submission.
                        </span>
                      </div>
                    )}

                    {/* Decision Action Buttons */}
                    <div className="flex items-center justify-end gap-2.5 pt-3 border-t border-slate-800/80">
                      <button
                        type="button"
                        onClick={() => openDecisionModal(r, 'CHANGES')}
                        className="px-3.5 py-1.5 rounded-md bg-slate-800 hover:bg-slate-700 text-amber-300 text-xs font-semibold transition-colors cursor-pointer"
                      >
                        Request Changes
                      </button>
                      <button
                        type="button"
                        onClick={() => openDecisionModal(r, 'REJECT')}
                        className="px-3.5 py-1.5 rounded-md bg-rose-950/80 hover:bg-rose-900 border border-rose-800 text-rose-300 text-xs font-semibold transition-colors cursor-pointer"
                      >
                        Reject
                      </button>
                      <button
                        type="button"
                        disabled={isSelfRequest}
                        onClick={() => openDecisionModal(r, 'APPROVE')}
                        className="flex items-center gap-1 px-4 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-bold disabled:opacity-40 transition-colors cursor-pointer"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" /> Approve Request
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── View: Assignments (Pending Review & Active Team) */}
      {(currentView === 'manager_assignments' || currentView === 'manager_employees') && (
        <div className="space-y-6">
          <div className="border-b border-slate-800 pb-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div>
              <h1 className="text-lg font-bold text-slate-100">Team Assignments Management</h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Review pending administrative assignments and view active employees in your review team.
              </p>
            </div>

            {/* Sub-Tabs: Pending vs Active */}
            <div className="flex items-center gap-2 bg-slate-900 p-1 rounded-lg border border-slate-800">
              <button
                type="button"
                onClick={() => setAssignmentTab('pending')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors cursor-pointer ${
                  assignmentTab === 'pending'
                    ? 'bg-emerald-600 text-slate-950'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>Pending Review</span>
                {pendingAssignments.length > 0 && (
                  <span
                    className={`px-1.5 py-0.2 rounded-full text-[10px] font-bold ${
                      assignmentTab === 'pending'
                        ? 'bg-slate-950 text-emerald-400'
                        : 'bg-amber-500 text-slate-950'
                    }`}
                  >
                    {pendingAssignments.length}
                  </span>
                )}
              </button>

              <button
                type="button"
                onClick={() => setAssignmentTab('active')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors cursor-pointer ${
                  assignmentTab === 'active'
                    ? 'bg-emerald-600 text-slate-950'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>Active Assigned Team</span>
              </button>
            </div>
          </div>

          {/* Sub-tab: Pending Assignments */}
          {assignmentTab === 'pending' && (
            <div className="space-y-3">
              <div className="text-xs font-semibold text-slate-300 flex items-center justify-between">
                <span>Pending Assignment Requests ({pendingAssignments.length})</span>
                <span className="text-[11px] text-slate-500">Only unconfirmed employee requests</span>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-sm">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs text-slate-200">
                  <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                    <tr>
                      <th className="p-3">Employee</th>
                      <th className="p-3">Email</th>
                      <th className="p-3">Assigned Date</th>
                      <th className="p-3">Status</th>
                      <th className="p-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60">
                    {pendingAssignments.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="p-8 text-center text-slate-500">
                          <CheckCircle2 className="w-6 h-6 mx-auto mb-1 text-emerald-500/50" />
                          No pending assignment requests waiting for your review.
                        </td>
                      </tr>
                    ) : (
                      pendingAssignments.map((a) => (
                        <tr key={a.id} className="hover:bg-slate-800/40 transition-colors">
                          <td className="p-3 font-semibold text-slate-100">{a.employee_username || 'Employee'}</td>
                          <td className="p-3 text-slate-400">{a.employee_email || '—'}</td>
                          <td className="p-3 text-slate-400">{a.created_at?.split('T')[0] || a.assigned_at?.split('T')[0] || '—'}</td>
                          <td className="p-3">
                            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-amber-950 text-amber-300 border border-amber-800">
                              PENDING
                            </span>
                          </td>
                          <td className="p-3 text-right space-x-2">
                            <button
                              type="button"
                              onClick={() => handleReviewAssignment(a.id, 'APPROVED')}
                              className="px-3 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-xs cursor-pointer shadow-sm"
                            >
                              Accept
                            </button>
                            <button
                              type="button"
                              onClick={() => handleReviewAssignment(a.id, 'REJECTED')}
                              className="px-3 py-1 rounded bg-rose-950 hover:bg-rose-900 text-rose-300 border border-rose-800 text-xs font-semibold cursor-pointer"
                            >
                              Decline
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
                </div>
              </div>
            </div>
          )}

          {/* Sub-tab: Active Assigned Team */}
          {assignmentTab === 'active' && (
            <div className="space-y-4">
              <div className="text-xs font-semibold text-slate-300 flex items-center justify-between">
                <span>Active Assigned Team Members ({activeEmployees.length})</span>
                <span className="text-[11px] text-slate-500">Reimbursement submissions from these members route to your approval queue</span>
              </div>

              {activeEmployees.length === 0 ? (
                <div className="p-10 bg-slate-900 border border-slate-800 rounded-lg text-center text-xs text-slate-500">
                  <Users className="w-8 h-8 mx-auto mb-2 text-slate-600" />
                  No active employee team members assigned yet.
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
                  {activeEmployees.map((e) => (
                    <div key={e.id} className="p-4 bg-slate-900 border border-slate-800 rounded-lg shadow-sm space-y-3">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center font-bold text-emerald-400 text-sm">
                          {e.employee_username ? e.employee_username.substring(0, 2).toUpperCase() : 'EM'}
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="font-semibold text-slate-100 text-sm truncate">{e.employee_username || 'Employee'}</div>
                          <div className="text-[11px] text-slate-400 truncate">{e.employee_email || '—'}</div>
                        </div>
                      </div>
                      <div className="pt-2 border-t border-slate-800 flex items-center justify-between text-[11px] text-slate-400">
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                          Active Team
                        </span>
                        <span>
                          Since {e.reviewed_at?.split('T')[0] || e.assigned_at?.split('T')[0] || '—'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* ── View: Decision History */}
      {currentView === 'manager_history' && (
        <div className="space-y-4">
          <div className="border-b border-slate-800 pb-3">
            <h1 className="text-lg font-bold text-slate-100">Manager Decision History</h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Audit log of past approvals, change requests, and rejections.
            </p>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-200">
                <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                  <tr>
                    <th className="p-3">Date</th>
                    <th className="p-3">Requester</th>
                    <th className="p-3">Purpose</th>
                    <th className="p-3">Amount</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Reason / Feedback</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {decisionHistory.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-6 text-center text-slate-500">
                        No decision history recorded yet.
                      </td>
                    </tr>
                  ) : (
                    decisionHistory
                      .slice((historyPage - 1) * historyPageSize, historyPage * historyPageSize)
                      .map((h) => (
                      <tr key={h.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="p-3 font-mono">{h.request_date}</td>
                        <td className="p-3 text-slate-300 font-medium">{h.requester_username || h.requester_id}</td>
                        <td className="p-3 text-slate-100">{h.purpose}</td>
                        <td className="p-3 font-bold text-slate-100">₹{parseFloat(h.amount).toFixed(2)}</td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                            h.status === 'APPROVED' || h.status === 'POSTED'
                              ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                              : h.status === 'REJECTED'
                              ? 'bg-rose-950 text-rose-300 border border-rose-800'
                              : 'bg-amber-950 text-amber-300 border border-amber-800'
                          }`}>
                            {h.status}
                          </span>
                        </td>
                        <td className="p-3 text-slate-400 italic">
                          {h.decision_reason || '—'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <TablePagination
              totalItems={decisionHistory.length}
              currentPage={historyPage}
              pageSize={historyPageSize}
              onPageChange={setHistoryPage}
              onPageSizeChange={(s) => { setHistoryPageSize(s); setHistoryPage(1); }}
            />
          </div>
        </div>
      )}

      {/* ── View: Manager New Request */}
      {currentView === 'manager_new_request' && (
        <div className="max-w-2xl space-y-6">
          <div className="border-b border-slate-800 pb-3">
            <h1 className="text-lg font-bold text-slate-100">Raise Petty Cash Request</h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Submit an expenditure request to your assigned Finance user for posting.
            </p>
          </div>

          {!assignedFinance ? (
            <div className="p-4 bg-amber-950/30 border border-amber-800 rounded-lg text-xs text-amber-200 flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <strong>Finance Assignment Required:</strong> You must be assigned to a Finance user before raising a request. Please contact Finance to assign your account.
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmitManagerRequest} className="bg-slate-900 border border-slate-800 rounded-lg p-6 space-y-4 text-xs shadow-sm">
              <div className="p-3 bg-slate-950 border border-slate-800 rounded flex items-center justify-between">
                <span className="text-slate-400">Assigned Finance Reviewer:</span>
                <span className="font-semibold text-emerald-400">
                  {assignedFinance.finance_username} ({assignedFinance.finance_email})
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Request Date *</label>
                  <input type="date" value={reqDate} onChange={(e) => setReqDate(e.target.value)} className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded text-slate-100" required />
                </div>
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Amount (₹) *</label>
                  <input type="number" step="0.01" min="0.01" value={reqAmount} onChange={(e) => setReqAmount(e.target.value)} placeholder="0.00" className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded text-slate-100" required />
                </div>
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Project *</label>
                  <select value={reqProject} onChange={(e) => setReqProject(e.target.value)} className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded text-slate-100" required>
                    {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                  </select>
                </div>
                <div>
                  <label className="block text-slate-300 font-medium mb-1">Ledger *</label>
                  <select value={reqLedger} onChange={(e) => setReqLedger(e.target.value)} className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded text-slate-100" required>
                    {ledgers.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                  </select>
                </div>
              </div>
              <div>
                <label className="block text-slate-300 font-medium mb-1">Category *</label>
                <input type="text" value={reqCategory} onChange={(e) => setReqCategory(e.target.value)} placeholder="e.g. Travel, Client Lunch, Supplies" className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded text-slate-100" required />
              </div>
              <div>
                <label className="block text-slate-300 font-medium mb-1">Purpose *</label>
                <input type="text" maxLength={500} value={reqPurpose} onChange={(e) => setReqPurpose(e.target.value)} placeholder="Brief purpose of expense" className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded text-slate-100" required />
              </div>
              <div>
                <label className="block text-slate-300 font-medium mb-1">Notes (Optional)</label>
                <textarea rows={2} maxLength={2000} value={reqNotes} onChange={(e) => setReqNotes(e.target.value)} className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded text-slate-100" />
              </div>
              <div className="flex justify-end pt-2">
                <button type="submit" disabled={submittingReq} className="inline-flex items-center gap-1.5 px-4 py-2 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold cursor-pointer disabled:opacity-50">
                  <Send className="w-3.5 h-3.5" /> {submittingReq ? 'Submitting...' : 'Submit to Finance'}
                </button>
              </div>
            </form>
          )}
        </div>
      )}

      {/* ── View: Manager My Requests */}
      {currentView === 'manager_my_requests' && (
        <div className="space-y-4">
          <div className="border-b border-slate-800 pb-3 flex items-center justify-between">
            <div>
              <h1 className="text-lg font-bold text-slate-100">My Expense Requests</h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Track requests submitted to Finance and attach supporting vouchers anytime.
              </p>
            </div>
            <button type="button" onClick={() => onNavigate('manager_new_request')} className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-bold cursor-pointer">
              <PlusCircle className="w-3.5 h-3.5" /> New Request
            </button>
          </div>
          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-200">
                <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                  <tr>
                    <th className="p-3">Date</th>
                    <th className="p-3">Purpose</th>
                    <th className="p-3">Project / Category</th>
                    <th className="p-3">Amount</th>
                    <th className="p-3">Status</th>
                    <th className="p-3 text-right">Voucher</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {myRequests.length === 0 ? (
                    <tr><td colSpan={6} className="p-6 text-center text-slate-500">No personal requests submitted yet.</td></tr>
                  ) : (
                    myRequests.slice((myReqPage - 1) * myReqPageSize, myReqPage * myReqPageSize).map((r) => (
                      <tr key={r.id} className="hover:bg-slate-800/40">
                        <td className="p-3 font-mono">{r.request_date}</td>
                        <td className="p-3 font-medium text-slate-100">{r.purpose}</td>
                        <td className="p-3 text-slate-400">{r.project_name} / {r.category_name || r.category}</td>
                        <td className="p-3 font-bold text-slate-100">₹{parseFloat(r.amount).toFixed(2)}</td>
                        <td className="p-3">
                          {r.status === 'POSTED' ? (
                            <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${r.supporting_count > 0 ? 'bg-emerald-950 text-emerald-300 border-emerald-800' : 'bg-amber-950 text-amber-300 border-amber-800'}`}>
                              {r.supporting_count > 0 ? 'Posted (Voucher Attached)' : 'Posted (Voucher Pending)'}
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-purple-950 text-purple-300 border border-purple-800">
                              {r.status === 'APPROVED' ? 'Awaiting Finance Posting' : r.status}
                            </span>
                          )}
                        </td>
                        <td className="p-3 text-right">
                          {['APPROVED', 'SUPPORTING_UPLOADED', 'POSTED'].includes(r.status) && (
                            <button
                              type="button"
                              onClick={() => { setTargetVoucherRequest(r); setVoucherFile(null); setVoucherModalOpen(true); }}
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-emerald-400 text-[11px] font-semibold border border-slate-700 cursor-pointer"
                            >
                              <FileUp className="w-3 h-3" /> {r.supporting_count > 0 ? 'Add Voucher' : 'Upload Voucher'}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <TablePagination
              totalItems={myRequests.length}
              currentPage={myReqPage}
              pageSize={myReqPageSize}
              onPageChange={setMyReqPage}
              onPageSizeChange={(s) => { setMyReqPageSize(s); setMyReqPage(1); }}
            />
          </div>
        </div>
      )}

      {/* ── View: Manager Reports & ZIP Exports (View-Only) */}
      {currentView === 'manager_reports' && (
        <div className="space-y-5">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-3">
            <div>
              <h1 className="text-lg font-bold text-slate-100">Reports & ZIP Exports (View-Only)</h1>
              <p className="text-xs text-slate-400 mt-0.5">Inspect posted monthly ledger reports and download Excel/ZIP bundles.</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <input
                type="month"
                value={reportMonth}
                onChange={(e) => { setReportMonth(e.target.value); setReportPage(1); }}
                className="px-3 py-1.5 bg-slate-900 border border-slate-700 rounded text-xs text-slate-100"
              />
              <button
                type="button"
                onClick={() => api.downloadFile(api.exportMonthlyExcelUrl(reportMonth), `Petty_Cash_Report_${reportMonth}.xlsx`).catch((e) => addToast({ type: 'error', message: e.message }))}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-emerald-400 text-xs font-semibold border border-slate-700 cursor-pointer"
              >
                <FileSpreadsheet className="w-3.5 h-3.5" /> Excel
              </button>
              <button
                type="button"
                onClick={() => api.downloadFile(api.exportMonthlyZipUrl(reportMonth), `Petty_Cash_Bundle_${reportMonth}.zip`).catch((e) => addToast({ type: 'error', message: e.message }))}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-bold cursor-pointer"
              >
                <Download className="w-3.5 h-3.5" /> ZIP Bundle
              </button>
            </div>
          </div>

          {monthlyReport && (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
                <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg">
                  <div className="text-slate-400">Opening Balance</div>
                  <div className="text-lg font-bold text-slate-100 mt-1">₹{Number(monthlyReport.opening_balance || 0).toLocaleString('en-IN')}</div>
                </div>
                <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg">
                  <div className="text-slate-400">Total Receipts</div>
                  <div className="text-lg font-bold text-emerald-400 mt-1">₹{Number(monthlyReport.total_receipts || 0).toLocaleString('en-IN')}</div>
                </div>
                <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg">
                  <div className="text-slate-400">Total Payments</div>
                  <div className="text-lg font-bold text-rose-400 mt-1">₹{Number(monthlyReport.total_payments || 0).toLocaleString('en-IN')}</div>
                </div>
                <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg">
                  <div className="text-slate-400">Closing Balance</div>
                  <div className="text-lg font-bold text-cyan-400 mt-1">₹{Number(monthlyReport.closing_balance || 0).toLocaleString('en-IN')}</div>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-sm">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs text-slate-200">
                    <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                      <tr>
                        <th className="p-3">Date</th>
                        <th className="p-3">Description</th>
                        <th className="p-3">Project / Category</th>
                        <th className="p-3">Receipt</th>
                        <th className="p-3">Payment</th>
                        <th className="p-3">Voucher Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60">
                      {(monthlyReport.posted_entries || monthlyReport.transactions || []).length === 0 ? (
                        <tr><td colSpan={6} className="p-6 text-center text-slate-500">No posted transactions for {reportMonth}.</td></tr>
                      ) : (
                        (monthlyReport.posted_entries || monthlyReport.transactions || [])
                          .slice((reportPage - 1) * reportPageSize, reportPage * reportPageSize)
                          .map((t, idx) => (
                            <tr key={t.id || idx} className="hover:bg-slate-800/40">
                              <td className="p-3 font-mono">{t.date}</td>
                              <td className="p-3 font-medium text-slate-100">{t.description}</td>
                              <td className="p-3 text-slate-400">{t.project} / {t.category}</td>
                              <td className="p-3 font-mono text-emerald-400">{t.receipt ? `₹${Number(t.receipt).toFixed(2)}` : '—'}</td>
                              <td className="p-3 font-mono text-rose-400">{t.payment ? `₹${Number(t.payment).toFixed(2)}` : '—'}</td>
                              <td className="p-3">
                                <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                                  t.voucher_status === 'Posted (Voucher Attached)'
                                    ? 'bg-emerald-950 text-emerald-300 border-emerald-800'
                                    : t.voucher_status === 'Posted (Voucher Pending)'
                                    ? 'bg-amber-950 text-amber-300 border-amber-800'
                                    : 'bg-slate-800 text-slate-300 border-slate-700'
                                }`}>
                                  {t.voucher_status || (t.supporting_count > 0 ? 'Posted (Voucher Attached)' : 'Receipt')}
                                </span>
                              </td>
                            </tr>
                          ))
                      )}
                    </tbody>
                  </table>
                </div>
                <TablePagination
                  totalItems={(monthlyReport.posted_entries || monthlyReport.transactions || []).length}
                  currentPage={reportPage}
                  pageSize={reportPageSize}
                  onPageChange={setReportPage}
                  onPageSizeChange={(s) => { setReportPageSize(s); setReportPage(1); }}
                />
              </div>
            </>
          )}
        </div>
      )}

      {/* ── Manager Voucher Upload Modal */}
      <Modal
        isOpen={voucherModalOpen}
        onClose={() => setVoucherModalOpen(false)}
        title="Upload Supporting Voucher"
        size="sm"
      >
        <form onSubmit={handleUploadManagerVoucher} className="space-y-4 text-xs">
          <div className="p-3 bg-slate-950 border border-slate-800 rounded">
            <div className="text-slate-400">Request: <strong className="text-slate-100">{targetVoucherRequest?.purpose}</strong></div>
            <div className="text-slate-400 mt-0.5">Amount: <strong className="text-emerald-400">₹{parseFloat(targetVoucherRequest?.amount || 0).toFixed(2)}</strong></div>
          </div>
          <div>
            <label className="block text-slate-300 font-medium mb-1">Voucher File (PDF, PNG, JPG) *</label>
            <input type="file" accept=".pdf,.png,.jpg,.jpeg" onChange={(e) => setVoucherFile(e.target.files?.[0] || null)} className="w-full text-slate-300" required />
          </div>
          <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
            <button type="button" onClick={() => setVoucherModalOpen(false)} className="px-3 py-1.5 rounded bg-slate-800 text-slate-300">Cancel</button>
            <button type="submit" disabled={uploadingVoucher || !voucherFile} className="px-4 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold disabled:opacity-50">
              {uploadingVoucher ? 'Uploading...' : 'Upload Voucher'}
            </button>
          </div>
        </form>
      </Modal>

      {/* ── Decision Confirmation Modal */}
      <Modal
        isOpen={decisionModalOpen}
        onClose={() => setDecisionModalOpen(false)}
        title={
          decisionType === 'APPROVE'
            ? 'Confirm Approval Decision'
            : decisionType === 'CHANGES'
            ? 'Request Changes from Employee'
            : 'Reject Reimbursement Request'
        }
      >
        {targetRequest && (
          <div className="space-y-4 text-xs">
            <div className="p-3 bg-slate-950 rounded border border-slate-800 space-y-1">
              <div className="flex justify-between">
                <span className="text-slate-400">Purpose:</span>
                <span className="font-semibold text-slate-200">{targetRequest.purpose}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Amount:</span>
                <span className="font-bold text-emerald-400">
                  ₹{parseFloat(targetRequest.amount).toFixed(2)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Employee:</span>
                <span className="text-slate-200">{targetRequest.requester_username || targetRequest.requester_id}</span>
              </div>
            </div>

            {decisionType !== 'APPROVE' && (
              <div>
                <label className="block text-slate-300 font-medium mb-1">
                  {decisionType === 'CHANGES' ? 'Feedback Notes for Employee *' : 'Rejection Reason *'}
                </label>
                <textarea
                  rows={3}
                  required
                  value={decisionReason}
                  onChange={(e) => setDecisionReason(e.target.value)}
                  placeholder={
                    decisionType === 'CHANGES'
                      ? 'Specify what needs to be corrected or missing documents...'
                      : 'Provide justification for rejecting this expenditure...'
                  }
                  className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                />
              </div>
            )}

            <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setDecisionModalOpen(false)}
                className="px-3.5 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={submittingDecision}
                onClick={executeDecision}
                className={`px-4 py-1.5 rounded font-bold text-slate-950 cursor-pointer ${
                  decisionType === 'APPROVE'
                    ? 'bg-emerald-500 hover:bg-emerald-400'
                    : decisionType === 'CHANGES'
                    ? 'bg-amber-400 hover:bg-amber-300'
                    : 'bg-rose-500 hover:bg-rose-400 text-white'
                }`}
              >
                {submittingDecision ? 'Processing...' : 'Confirm Decision'}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
