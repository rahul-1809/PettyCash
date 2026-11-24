import React, { useState, useEffect } from 'react';
import {
  Users,
  FolderTree,
  Receipt,
  FileCheck2,
  FileSpreadsheet,
  Activity,
  Archive,
  History,
  Shield,
  PlusCircle,
  CheckCircle2,
  AlertCircle,
  RotateCcw,
  Download,
  Key,
  Lock,
  Unlock,
  Eye,
  FileText,
  ExternalLink,
  RefreshCw,
  Search,
  Database,
  ArrowUpRight,
  ArrowDownLeft,
  Trash2,
  ToggleLeft,
  ToggleRight,
  Filter,
  Table,
  PieChart,
  FileDown,
  TrendingUp,
  TrendingDown,
  Calendar,
  IndianRupee,
  X,
} from 'lucide-react';
import { api } from '../api';
import Modal from '../components/Modal';
import TablePagination from '../components/TablePagination';

export default function AdminViews({ currentView, onNavigate, addToast, user }) {
  const [loading, setLoading] = useState(false);

  // Data states
  const [cashBalance, setCashBalance] = useState(null);
  const [usersList, setUsersList] = useState([]);
  const [assignments, setAssignments] = useState([]);
  const [projects, setProjects] = useState([]);
  const [ledgers, setLedgers] = useState([]);
  const [periods, setPeriods] = useState([]);
  const [adjustments, setAdjustments] = useState([]);
  const [receipts, setReceipts] = useState([]);
  const [postingsQueue, setPostingsQueue] = useState([]);
  const [auditEvents, setAuditEvents] = useState([]);
  const [auditFilter, setAuditFilter] = useState('ALL');
  const [auditSearch, setAuditSearch] = useState('');
  const [downloadingExcel, setDownloadingExcel] = useState(false);
  const [downloadingZip, setDownloadingZip] = useState(false);
  const [downloadingFileId, setDownloadingFileId] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [backups, setBackups] = useState([]);
  const [recentErrors, setRecentErrors] = useState([]);
  const [monthlyReport, setMonthlyReport] = useState(null);
  const [reportMonth, setReportMonth] = useState(new Date().toISOString().substring(0, 7));
  const [reportActiveTab, setReportActiveTab] = useState('summary'); // 'summary' | 'sheet' | 'analytics'
  const [reportSearchTerm, setReportSearchTerm] = useState('');
  const [reportSelectedProject, setReportSelectedProject] = useState('ALL');
  const [reportSelectedLedger, setReportSelectedLedger] = useState('ALL');
  const [reportDrilldownData, setReportDrilldownData] = useState(null);

  // Pagination states
  const [auditPage, setAuditPage] = useState(1);
  const [auditPageSize, setAuditPageSize] = useState(25);

  const [reportSheetPage, setReportSheetPage] = useState(1);
  const [reportSheetPageSize, setReportSheetPageSize] = useState(25);

  const [drilldownPage, setDrilldownPage] = useState(1);
  const [drilldownPageSize, setDrilldownPageSize] = useState(10);

  const [backupsPage, setBackupsPage] = useState(1);
  const [backupsPageSize, setBackupsPageSize] = useState(5);

  const [errorsPage, setErrorsPage] = useState(1);
  const [errorsPageSize, setErrorsPageSize] = useState(10);

  // Modals state
  const [provisionModalOpen, setProvisionModalOpen] = useState(false);
  const [newUsername, setNewUsername] = useState('');
  const [newUserEmail, setNewUserEmail] = useState('');
  const [newUserRole, setNewUserRole] = useState('Employee');
  const [onboardingTokenResult, setOnboardingTokenResult] = useState('');

  const [assignmentModalOpen, setAssignmentModalOpen] = useState(false);
  const [assignManagerId, setAssignManagerId] = useState('');
  const [assignEmployeeId, setAssignEmployeeId] = useState('');

  const [projectModalOpen, setProjectModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');

  const [ledgerModalOpen, setLedgerModalOpen] = useState(false);
  const [newLedgerName, setNewLedgerName] = useState('');

  const [balanceModalOpen, setBalanceModalOpen] = useState(false);
  const [newOpeningBalance, setNewOpeningBalance] = useState('');

  const [adjustmentModalOpen, setAdjustmentModalOpen] = useState(false);
  const [adjAmount, setAdjAmount] = useState('');
  const [adjDirection, setAdjDirection] = useState('INFLOW');
  const [adjDate, setAdjDate] = useState(new Date().toISOString().split('T')[0]);
  const [adjReason, setAdjReason] = useState('');

  const [periodModalOpen, setPeriodModalOpen] = useState(false);
  const [periodStart, setPeriodStart] = useState('');
  const [periodEnd, setPeriodEnd] = useState('');

  const [receiptModalOpen, setReceiptModalOpen] = useState(false);
  const [receiptAmount, setReceiptAmount] = useState('');
  const [receiptDate, setReceiptDate] = useState(new Date().toISOString().split('T')[0]);
  const [receiptDesc, setReceiptDesc] = useState('');
  const [receiptCategory, setReceiptCategory] = useState('Cash replenishment');
  const [receiptLedgerId, setReceiptLedgerId] = useState('');
  const [receiptProjectId, setReceiptProjectId] = useState('');

  // Posting & Reversal dialogs
  const [postModalOpen, setPostModalOpen] = useState(false);
  const [targetPostRequest, setTargetPostRequest] = useState(null);
  const [postEffectiveDate, setPostEffectiveDate] = useState(new Date().toISOString().split('T')[0]);

  const [returnModalOpen, setReturnModalOpen] = useState(false);
  const [returnReason, setReturnReason] = useState('');

  const [reversalModalOpen, setReversalModalOpen] = useState(false);
  const [reversalTarget, setReversalTarget] = useState(null); // { type: 'REQUEST'|'RECEIPT', item: ... }
  const [reversalReason, setReversalReason] = useState('');

  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [detailItem, setDetailItem] = useState(null);

  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadData = async (force = false) => {
    try {
      if (force) {
        api.clearCache();
      }

      const hasExistingData = (
        (currentView === 'admin_dashboard' && cashBalance) ||
        (currentView === 'admin_reports' && monthlyReport && monthlyReport.month === reportMonth) ||
        (currentView === 'admin_postings' && postingsQueue.length >= 0 && projects.length > 0) ||
        (currentView === 'admin_receipts' && receipts.length >= 0 && projects.length > 0) ||
        (currentView === 'admin_catalog' && projects.length > 0) ||
        (currentView === 'admin_users' && usersList.length > 0) ||
        (currentView === 'admin_operations' && metrics) ||
        (currentView === 'admin_audit' && auditEvents.length > 0)
      );

      if (!hasExistingData) {
        setLoading(true);
      }

      const promises = [];

      // 1. Core balance: needed in dashboard, reports, catalog, postings, receipts
      if (['admin_dashboard', 'admin_reports', 'admin_postings', 'admin_receipts', 'admin_catalog', 'admin_operations'].includes(currentView)) {
        promises.push(api.getCashBalance().then(d => setCashBalance(d)).catch(() => null));
      }

      // 2. Projects & Ledgers: needed in postings, receipts, catalog, reports
      if (['admin_postings', 'admin_receipts', 'admin_catalog', 'admin_reports'].includes(currentView)) {
        promises.push(
          api.getProjects().then(d => {
            const list = d || [];
            setProjects(list);
            if (list.length > 0 && !receiptProjectId) setReceiptProjectId(list[0].id);
          }).catch(() => [])
        );
        promises.push(
          api.getLedgers().then(d => {
            const list = d || [];
            setLedgers(list);
            if (list.length > 0 && !receiptLedgerId) setReceiptLedgerId(list[0].id);
          }).catch(() => [])
        );
      }

      // 3. Requests / Postings Queue: needed in dashboard & postings
      if (['admin_dashboard', 'admin_postings'].includes(currentView)) {
        promises.push(
          api.listRequests().then(reqData => {
            setPostingsQueue(
              (reqData || []).filter(
                (r) => r.status === 'SUPPORTING_UPLOADED' || (r.status === 'APPROVED' && r.supporting_files?.length > 0)
              )
            );
          }).catch(() => [])
        );
      }

      // 4. Company Receipts: needed in dashboard (count) & receipts
      if (['admin_dashboard', 'admin_receipts'].includes(currentView)) {
        promises.push(api.listCompanyReceipts().then(d => setReceipts(d || [])).catch(() => []));
      }

      // 5. Alerts: needed in dashboard & operations
      if (['admin_dashboard', 'admin_operations'].includes(currentView)) {
        promises.push(api.getAlerts().then(d => setAlerts(d?.alerts || [])).catch(() => ({ alerts: [] })));
      }

      // 6. Reports: needed in admin_reports (RUNS IMMEDIATELY IN PARALLEL!)
      if (currentView === 'admin_reports') {
        promises.push(api.getMonthlyReport(reportMonth).then(d => setMonthlyReport(d)).catch(() => null));
      }

      // 7. Users & Assignments: needed in admin_users
      if (currentView === 'admin_users') {
        promises.push(api.listUsers().then(d => setUsersList(d || [])).catch(() => []));
        promises.push(api.listAssignments().then(d => setAssignments(d || [])).catch(() => []));
      }

      // 8. Catalog: Periods & Adjustments: needed in admin_catalog
      if (currentView === 'admin_catalog') {
        promises.push(api.listFinancialPeriods().then(d => setPeriods(d || [])).catch(() => []));
        promises.push(api.listBalanceAdjustments().then(d => setAdjustments(d || [])).catch(() => []));
      }

      // 9. Operations: Metrics, Backups, Errors: needed in admin_operations
      if (currentView === 'admin_operations') {
        promises.push(api.getMetrics().then(d => setMetrics(d)).catch(() => null));
        promises.push(api.listBackups().then(d => setBackups(d || [])).catch(() => []));
        promises.push(api.getErrors(100).then(d => setRecentErrors(d?.errors || [])).catch(() => ({ errors: [] })));
      }

      // 10. Audit Trail: needed in admin_audit
      if (currentView === 'admin_audit') {
        promises.push(api.listAuditEvents({ limit: 1000 }).then(d => setAuditEvents(d || [])).catch(() => []));
      }

      await Promise.all(promises);
    } catch (e) {
      console.error(e);
      addToast({ type: 'error', message: 'Error loading admin data.' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [currentView, reportMonth]);

  // Reset pagination on filter adjustments
  useEffect(() => {
    setReportSheetPage(1);
  }, [reportMonth, reportSearchTerm, reportSelectedProject, reportSelectedLedger]);

  useEffect(() => {
    setAuditPage(1);
  }, [auditFilter, auditSearch]);

  // Handlers
  const handleProvisionUser = async (e) => {
    e.preventDefault();
    try {
      setIsSubmitting(true);
      const res = await api.provisionUser(newUsername.trim(), newUserEmail.trim(), newUserRole);
      addToast({ type: 'success', title: 'User Provisioned', message: `User ${res.username} added.` });
      if (res.onboarding_token) {
        setOnboardingTokenResult(res.onboarding_token);
      } else {
        setProvisionModalOpen(false);
        setNewUsername('');
        setNewUserEmail('');
      }
      loadData();
    } catch (err) {
      addToast({ type: 'error', title: 'Provision Failed', message: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteUser = async (userToDelete) => {
    if (!window.confirm(`Are you sure you want to delete user "${userToDelete.username}" (${userToDelete.email})?`)) {
      return;
    }
    try {
      setIsSubmitting(true);
      await api.deleteUser(userToDelete.id);
      addToast({
        type: 'success',
        title: 'User Deleted',
        message: `User ${userToDelete.username} has been removed.`,
      });
      loadData();
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCreateAssignment = async (e) => {
    e.preventDefault();
    if (!assignManagerId || !assignEmployeeId) return;
    try {
      setIsSubmitting(true);
      await api.createAssignment(assignManagerId, assignEmployeeId);
      addToast({ type: 'success', title: 'Assignment Created', message: 'Employee assigned to manager.' });
      setAssignmentModalOpen(false);
      loadData();
    } catch (err) {
      addToast({ type: 'error', title: 'Assignment Failed', message: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCreateProject = async (e) => {
    e.preventDefault();
    if (!newProjectName.trim()) return;
    try {
      setIsSubmitting(true);
      await api.createProject(newProjectName.trim());
      addToast({ type: 'success', message: 'Project created successfully.' });
      setProjectModalOpen(false);
      setNewProjectName('');
      loadData();
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCreateLedger = async (e) => {
    e.preventDefault();
    if (!newLedgerName.trim()) return;
    try {
      setIsSubmitting(true);
      await api.createLedger(newLedgerName.trim());
      addToast({ type: 'success', message: 'Ledger head created successfully.' });
      setLedgerModalOpen(false);
      setNewLedgerName('');
      loadData();
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDeleteProject = async (id, name) => {
    if (!window.confirm(`Are you sure you want to delete project "${name}"?`)) return;
    try {
      await api.deleteProject(id);
      addToast({ type: 'success', title: 'Project Deleted', message: `Project "${name}" was deleted.` });
      loadData();
    } catch (err) {
      addToast({ type: 'error', title: 'Cannot Delete Project', message: err.message });
    }
  };

  const handleToggleProjectStatus = async (id, currentStatus) => {
    try {
      await api.updateProjectStatus(id, !currentStatus);
      addToast({ type: 'success', message: `Project status updated.` });
      loadData();
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    }
  };

  const handleDeleteLedger = async (id, name) => {
    if (!window.confirm(`Are you sure you want to delete ledger "${name}"?`)) return;
    try {
      await api.deleteLedger(id);
      addToast({ type: 'success', title: 'Ledger Deleted', message: `Ledger "${name}" was deleted.` });
      loadData();
    } catch (err) {
      addToast({ type: 'error', title: 'Cannot Delete Ledger', message: err.message });
    }
  };

  const handleToggleLedgerStatus = async (id, currentStatus) => {
    try {
      await api.updateLedgerStatus(id, !currentStatus);
      addToast({ type: 'success', message: `Ledger status updated.` });
      loadData();
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    }
  };

  const handleUpdateVaultBalance = async (e) => {
    e.preventDefault();
    const bal = parseFloat(newOpeningBalance);
    if (isNaN(bal) || bal < 0) {
      addToast({ type: 'error', message: 'Outstanding balance cannot be negative.' });
      return;
    }
    try {
      setIsSubmitting(true);
      await api.updateCashBalance(bal);
      addToast({ type: 'success', message: 'Petty cash opening balance configured.' });
      setBalanceModalOpen(false);
      loadData();
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCreateAdjustment = async (e) => {
    e.preventDefault();
    const amt = parseFloat(adjAmount);
    if (isNaN(amt) || amt <= 0 || !adjReason.trim()) {
      addToast({ type: 'error', message: 'Positive amount and audit reason are required.' });
      return;
    }
    try {
      setIsSubmitting(true);
      await api.createBalanceAdjustment({
        amount: amt,
        effective_date: adjDate,
        reason: adjReason.trim(),
        direction: adjDirection,
      });
      addToast({ type: 'success', title: 'Adjustment Recorded', message: 'Vault balance adjusted.' });
      setAdjustmentModalOpen(false);
      setAdjAmount('');
      setAdjReason('');
      loadData();
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCreateReceipt = async (e) => {
    e.preventDefault();
    const amt = parseFloat(receiptAmount);
    if (isNaN(amt) || amt <= 0 || !receiptDesc.trim()) {
      addToast({ type: 'error', message: 'Valid amount and description required.' });
      return;
    }
    if (!receiptCategory.trim()) {
      addToast({ type: 'error', message: 'Category is required.' });
      return;
    }
    try {
      setIsSubmitting(true);
      await api.createCompanyReceipt({
        amount: amt,
        receipt_date: receiptDate,
        description: receiptDesc.trim(),
        category: receiptCategory.trim(),
        ledger_id: receiptLedgerId || undefined,
        project_id: receiptProjectId || undefined,
      });
      addToast({ type: 'success', title: 'Receipt Created', message: 'Company receipt posted directly.' });
      setReceiptModalOpen(false);
      setReceiptAmount('');
      setReceiptDesc('');
      loadData();
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePostRequest = async () => {
    if (!targetPostRequest) return;
    try {
      setIsSubmitting(true);
      await api.postRequest(targetPostRequest.id, postEffectiveDate);
      addToast({ type: 'success', title: 'Posted to Ledger', message: 'Transaction deducted atomically.' });
      setPostModalOpen(false);
      loadData();
    } catch (err) {
      addToast({ type: 'error', title: 'Posting Failed', message: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReturnForCorrection = async () => {
    if (!targetPostRequest || !returnReason.trim()) return;
    try {
      setIsSubmitting(true);
      await api.returnForCorrection(targetPostRequest.id, returnReason.trim());
      addToast({ type: 'success', message: 'Request returned to employee for correction.' });
      setReturnModalOpen(false);
      setReturnReason('');
      loadData();
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleExecuteReversal = async () => {
    if (!reversalTarget || !reversalReason.trim()) return;
    try {
      setIsSubmitting(true);
      if (reversalTarget.type === 'REQUEST') {
        await api.reverseRequest(reversalTarget.item.id, reversalReason.trim(), null);
        addToast({ type: 'success', title: 'Reversed', message: 'Transaction reversed and funds restored.' });
      } else {
        await api.reverseCompanyReceipt(reversalTarget.item.id, reversalReason.trim(), null);
        addToast({ type: 'success', title: 'Reversed', message: 'Company receipt reversed.' });
      }
      setReversalModalOpen(false);
      setReversalReason('');
      loadData();
    } catch (err) {
      addToast({ type: 'error', title: 'Reversal Failed', message: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTriggerBackup = async () => {
    try {
      setIsSubmitting(true);
      const b = await api.createBackup();
      addToast({ type: 'success', title: 'Backup Created', message: `Snapshot ${b.backup_id} saved.` });
      loadData();
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleVerifyBackup = async (backupId) => {
    try {
      const res = await api.verifyBackup(backupId);
      if (res.valid) {
        addToast({ type: 'success', title: 'Integrity Verified', message: 'SQLite PRAGMA check passed.' });
      } else {
        addToast({ type: 'error', title: 'Integrity Check Failed', message: res.error || 'Corrupted' });
      }
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    }
  };

  const handleDownloadBackup = async (backupId) => {
    try {
      addToast({ type: 'info', title: 'Downloading Snapshot', message: `Fetching ${backupId} from Supabase storage...` });
      await api.downloadBackup(backupId);
      addToast({ type: 'success', title: 'Download Complete', message: `Snapshot ${backupId} downloaded.` });
    } catch (err) {
      addToast({ type: 'error', title: 'Download Failed', message: err.message });
    }
  };

  const handleRestoreBackup = async (backupId) => {
    if (!window.confirm(`Are you sure you want to restore database from backup ${backupId}? Current database will be updated from this verified snapshot.`)) {
      return;
    }
    setIsSubmitting(true);
    try {
      const res = await api.restoreBackup(backupId);
      addToast({ type: 'success', title: 'Database Restored', message: `Restored from snapshot ${backupId} (${res.verified_tables} tables verified).` });
      loadData();
    } catch (err) {
      addToast({ type: 'error', title: 'Restore Failed', message: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTestAlert = async (scenario) => {
    try {
      const res = await api.testAlert(scenario);
      addToast({
        type: 'warning',
        title: 'Alert Fired (Simulation)',
        message: `Simulated ${scenario}: ${res.alert?.message}`,
      });
      if (res.alert) {
        setAlerts((prev) =>
          prev.map((alt) => (alt.rule_id === scenario ? { ...alt, ...res.alert } : alt))
        );
      }
      loadData();
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    }
  };

  const handleAcknowledgeAlert = async (ruleId) => {
    try {
      const res = await api.acknowledgeAlert(ruleId);
      addToast({
        type: 'success',
        title: 'Alert Acknowledged',
        message: res.message || `Rule ${ruleId} acknowledged and cleared.`,
      });
      loadData();
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    }
  };

  const handleCreatePeriod = async (e) => {
    e.preventDefault();
    if (!periodStart || !periodEnd) {
      addToast({ type: 'error', message: 'Both start and end dates are required.' });
      return;
    }
    if (periodStart > periodEnd) {
      addToast({ type: 'error', message: 'Start date cannot be after end date.' });
      return;
    }
    try {
      setIsSubmitting(true);
      await api.createFinancialPeriod(periodStart, periodEnd);
      addToast({ type: 'success', message: 'Financial accounting period created.' });
      setPeriodModalOpen(false);
      setPeriodStart('');
      setPeriodEnd('');
      loadData();
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClosePeriod = async (id) => {
    try {
      await api.closeFinancialPeriod(id);
      addToast({ type: 'success', message: 'Financial period closed and locked against edits.' });
      loadData();
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    }
  };

  const handleReopenPeriod = async (id) => {
    try {
      await api.reopenFinancialPeriod(id);
      addToast({ type: 'success', message: 'Financial period reopened for audited modifications.' });
      loadData();
    } catch (err) {
      addToast({ type: 'error', message: err.message });
    }
  };

  const handleDownloadExcel = async () => {
    try {
      setDownloadingExcel(true);
      await api.downloadFile(
        api.getMonthlyExcelUrl(reportMonth),
        `petty_cash_report_${reportMonth}.xlsx`
      );
      addToast({
        type: 'success',
        title: 'Download Complete',
        message: `Excel sheet for ${reportMonth} downloaded successfully.`,
      });
    } catch (err) {
      console.error(err);
      addToast({
        type: 'error',
        title: 'Download Failed',
        message: err.message || 'Could not download monthly Excel report.',
      });
    } finally {
      setDownloadingExcel(false);
    }
  };

  const handleDownloadZip = async () => {
    try {
      setDownloadingZip(true);
      await api.downloadFile(
        api.getMonthlyZipUrl(reportMonth),
        `petty_cash_evidence_${reportMonth}.zip`
      );
      addToast({
        type: 'success',
        title: 'Download Complete',
        message: `ZIP evidence bundle for ${reportMonth} downloaded successfully.`,
      });
    } catch (err) {
      console.error(err);
      addToast({
        type: 'error',
        title: 'Download Failed',
        message: err.message || 'Could not download ZIP evidence bundle.',
      });
    } finally {
      setDownloadingZip(false);
    }
  };

  const handleDownloadSupporting = async (file) => {
    try {
      setDownloadingFileId(file.id);
      await api.downloadFile(
        api.getSupportingFileDownloadUrl(file.id),
        file.original_filename || `voucher_${file.id}`
      );
    } catch (err) {
      console.error(err);
      addToast({
        type: 'error',
        title: 'Download Failed',
        message: err.message || 'Could not download voucher file.',
      });
    } finally {
      setDownloadingFileId(null);
    }
  };

  const formatReportCurrency = (val) => {
    if (val === null || val === undefined || isNaN(val)) return '—';
    const num = Number(val);
    const isNeg = num < 0;
    const formatted = Math.abs(num).toLocaleString('en-IN', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return isNeg ? `-₹${formatted}` : `₹${formatted}`;
  };

  const openReportDrilldown = (project, type, amount) => {
    if (!amount || amount === 0 || !monthlyReport?.posted_entries) return;
    const rows =
      project === 'Grand Total'
        ? monthlyReport.posted_entries.filter((t) =>
            type === 'receipt' ? Number(t.receipt) > 0 : Number(t.payment) > 0
          )
        : monthlyReport.posted_entries.filter(
            (t) =>
              (t.project || 'General') === project &&
              (type === 'receipt' ? Number(t.receipt) > 0 : Number(t.payment) > 0)
          );
    setReportDrilldownData({ project, type, amount, rows });
  };

  const handleDownloadReportDrilldown = async () => {
    if (!reportDrilldownData) return;
    try {
      const token = localStorage.getItem('pettycash_auth_token') || '';
      const res = await fetch('/api/export-drilldown', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          project: reportDrilldownData.project,
          type: reportDrilldownData.type,
          transactions: reportDrilldownData.rows.map((t) => ({
            id: t.id || '',
            date: t.date || '',
            ledger: t.ledger || '',
            memo: t.description || t.memo || '',
            receipt: Number(t.receipt) || 0,
            payment: Number(t.payment) || 0,
            balance: Number(t.outstanding_balance ?? t.balance) || 0,
            approved: t.approved_by || '',
            requested_by: t.requested_by || '',
            category: t.category || '',
            project: t.project || '',
            status: 'POSTED',
            notes: t.notes || '',
            supportings: t.all_supportings || [],
          })),
        }),
      });
      if (!res.ok) throw new Error('Failed to export drilldown table');
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `Details_${reportDrilldownData.project}_${reportDrilldownData.type}.xlsx`.replace(/\s+/g, '_');
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      a.remove();
      addToast({
        type: 'success',
        title: 'Drilldown Downloaded',
        message: `Drilldown for ${reportDrilldownData.project} saved.`,
      });
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Export Failed',
        message: err.message,
      });
    }
  };

  const redirectToSheetTab = (project) => {
    setReportDrilldownData(null);
    setReportSelectedProject(project === 'Grand Total' ? 'ALL' : project);
    setReportActiveTab('sheet');
  };

  const uniqueReportProjects = Array.from(
    new Set((monthlyReport?.posted_entries || []).map((t) => t.project || 'General'))
  ).filter(Boolean);

  const uniqueReportLedgers = Array.from(
    new Set((monthlyReport?.posted_entries || []).map((t) => t.ledger || 'General'))
  ).filter(Boolean);

  const filteredReportEntries = (monthlyReport?.posted_entries || []).filter((tx) => {
    const matchesProj =
      reportSelectedProject === 'ALL' || (tx.project || 'General') === reportSelectedProject;
    const matchesLedger =
      reportSelectedLedger === 'ALL' || (tx.ledger || 'General') === reportSelectedLedger;
    const term = reportSearchTerm.toLowerCase();
    const matchesSearch =
      !term ||
      (tx.description || '').toLowerCase().includes(term) ||
      (tx.ledger || '').toLowerCase().includes(term) ||
      (tx.project || '').toLowerCase().includes(term) ||
      (tx.category || '').toLowerCase().includes(term) ||
      (tx.date || '').includes(term);
    return matchesProj && matchesLedger && matchesSearch;
  });

  const paginatedReportEntries = filteredReportEntries.slice(
    (reportSheetPage - 1) * reportSheetPageSize,
    reportSheetPage * reportSheetPageSize
  );

  const filteredAuditEvents = auditEvents.filter((evt) => {
    if (auditFilter !== 'ALL') {
      if (auditFilter === 'REQUESTS' && !evt.action.includes('REQUEST')) return false;
      if (auditFilter === 'CATALOG' && !evt.action.includes('PROJECT') && !evt.action.includes('LEDGER')) return false;
      if (auditFilter === 'USERS' && !evt.action.includes('USER') && !evt.action.includes('ASSIGNMENT') && !evt.action.includes('AUTH')) return false;
      if (auditFilter === 'FINANCE' && !evt.action.includes('PERIOD') && !evt.action.includes('BALANCE') && !evt.action.includes('RECEIPT')) return false;
      if (auditFilter === 'EXPORTS' && !evt.action.includes('EXPORT')) return false;
    }
    if (auditSearch.trim()) {
      const q = auditSearch.toLowerCase();
      const matchAction = evt.action?.toLowerCase().includes(q);
      const matchActor = (evt.actor_username || evt.actor_user_id || '').toLowerCase().includes(q);
      const matchEntity = (evt.entity_type || '').toLowerCase().includes(q);
      const matchCorr = (evt.correlation_id || '').toLowerCase().includes(q);
      const matchBefore = (evt.before_json || '').toLowerCase().includes(q);
      const matchAfter = (evt.after_json || '').toLowerCase().includes(q);
      return matchAction || matchActor || matchEntity || matchCorr || matchBefore || matchAfter;
    }
    return true;
  });

  const paginatedAuditEvents = filteredAuditEvents.slice(
    (auditPage - 1) * auditPageSize,
    auditPage * auditPageSize
  );

  const paginatedBackups = backups.slice(
    (backupsPage - 1) * backupsPageSize,
    backupsPage * backupsPageSize
  );

  const paginatedErrors = recentErrors.slice(
    (errorsPage - 1) * errorsPageSize,
    errorsPage * errorsPageSize
  );

  const paginatedDrilldownRows = (reportDrilldownData?.rows || []).slice(
    (drilldownPage - 1) * drilldownPageSize,
    drilldownPage * drilldownPageSize
  );

  // ── Render Admin Views
  return (
    <div className="space-y-6">
      {/* ── View: Dashboard */}
      {currentView === 'admin_dashboard' && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-4">
            <div>
              <h1 className="text-xl font-bold text-slate-100">Administrator Command Center</h1>
              <p className="text-xs text-slate-400 mt-1">
                Financial controls, canonical ledger postings, vault balance, and operational health.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setReceiptModalOpen(true)}
                className="flex items-center gap-1.5 px-3 py-2 rounded-md bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-semibold cursor-pointer"
              >
                <PlusCircle className="w-3.5 h-3.5" /> New Company Receipt
              </button>
            </div>
          </div>

          {/* KPI Cards Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div
              onClick={() => onNavigate('admin_catalog')}
              className="p-5 bg-slate-900 border border-slate-800 rounded-lg shadow-sm hover:border-slate-700 cursor-pointer transition-all"
            >
              <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
                Petty Cash Vault Balance
              </div>
              <div className="text-2xl font-extrabold text-emerald-400">
                ₹{cashBalance?.current_balance ? parseFloat(cashBalance.current_balance).toFixed(2) : '0.00'}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                Min reserve: ₹{cashBalance?.minimum_balance || '0.00'}
              </div>
            </div>

            <div
              onClick={() => onNavigate('admin_postings')}
              className="p-5 bg-slate-900 border border-slate-800 rounded-lg shadow-sm hover:border-slate-700 cursor-pointer transition-all"
            >
              <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
                Requests for Posting
              </div>
              <div className="text-2xl font-extrabold text-amber-400">{postingsQueue.length}</div>
              <div className="text-[11px] text-slate-400 mt-1">
                Approved vouchers awaiting finance posting
              </div>
            </div>

            <div
              onClick={() => onNavigate('admin_receipts')}
              className="p-5 bg-slate-900 border border-slate-800 rounded-lg shadow-sm hover:border-slate-700 cursor-pointer transition-all"
            >
              <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
                Company Receipts Count
              </div>
              <div className="text-2xl font-extrabold text-slate-100">{receipts.length}</div>
              <div className="text-[11px] text-slate-400 mt-1">
                Direct inbound cash top-ups recorded
              </div>
            </div>

            <div
              onClick={() => onNavigate('admin_operations')}
              className="p-5 bg-slate-900 border border-slate-800 rounded-lg shadow-sm hover:border-slate-700 cursor-pointer transition-all"
            >
              <div className="text-xs font-medium text-slate-400 uppercase tracking-wider mb-1">
                Operational Alerts
              </div>
              <div className="text-2xl font-extrabold text-slate-100 flex items-center gap-2">
                <span>{alerts.filter((a) => a.status === 'FIRING').length}</span>
                <span className={`text-xs px-2 py-0.5 rounded font-semibold ${
                  alerts.filter((a) => a.status === 'FIRING').length === 0
                    ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                    : 'bg-rose-950 text-rose-300 border border-rose-800'
                }`}>
                  {alerts.filter((a) => a.status === 'FIRING').length === 0 ? 'Healthy' : 'Firing'}
                </span>
              </div>
              <div className="text-[11px] text-slate-400 mt-1">5 core production rules evaluated</div>
            </div>
          </div>

          {/* Quick Pending Postings Overview */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-200">
                Pending Ledger Postings Queue ({postingsQueue.length})
              </h2>
              {postingsQueue.length > 0 && (
                <button
                  type="button"
                  onClick={() => onNavigate('admin_postings')}
                  className="text-xs text-emerald-400 hover:text-emerald-300 font-semibold"
                >
                  Open Posting Queue →
                </button>
              )}
            </div>

            {postingsQueue.length === 0 ? (
              <div className="text-center py-8 text-xs text-slate-500">
                No approved requests currently waiting to be posted.
              </div>
            ) : (
              <div className="divide-y divide-slate-800/80">
                {postingsQueue.slice(0, 5).map((r) => (
                  <div key={r.id} className="py-3 flex items-center justify-between text-xs">
                    <div>
                      <div className="font-semibold text-slate-200">{r.purpose}</div>
                      <div className="text-slate-400 text-[11px] mt-0.5">
                        Requester: {r.requester_username || r.requester_id} • Manager: {r.manager_username || r.approving_manager_id} • {r.request_date}
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="font-bold text-slate-100 text-sm">₹{parseFloat(r.amount).toFixed(2)}</span>
                      <button
                        type="button"
                        onClick={() => {
                          setTargetPostRequest(r);
                          setPostModalOpen(true);
                        }}
                        className="px-2.5 py-1 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold text-[11px]"
                      >
                        Post
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── View: Users & Access */}
      {currentView === 'admin_users' && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-3">
            <div>
              <h1 className="text-lg font-bold text-slate-100">Users & Access Management</h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Provision role accounts (Admin, Manager, Employee) and configure review assignments.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setAssignmentModalOpen(true)}
                className="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold cursor-pointer"
              >
                Assign Employee
              </button>
              <button
                type="button"
                onClick={() => {
                  setOnboardingTokenResult('');
                  setProvisionModalOpen(true);
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-bold cursor-pointer"
              >
                <PlusCircle className="w-3.5 h-3.5" /> Provision User
              </button>
            </div>
          </div>

          {/* Users Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-sm">
            <div className="px-4 py-3 bg-slate-950 border-b border-slate-800 text-xs font-semibold text-slate-300">
              Active Organization Users
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-200">
              <thead className="bg-slate-950/80 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                <tr>
                  <th className="p-3">Username</th>
                  <th className="p-3">Email</th>
                  <th className="p-3">Role</th>
                  <th className="p-3">Created Date</th>
                  <th className="p-3">Status</th>
                  <th className="p-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {usersList.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-6 text-center text-slate-500">
                      No active users found.
                    </td>
                  </tr>
                ) : (
                  usersList.map((u) => (
                    <tr key={u.id} className="hover:bg-slate-800/40">
                      <td className="p-3 font-semibold text-slate-100">{u.username}</td>
                      <td className="p-3 text-slate-400">{u.email}</td>
                      <td className="p-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          u.role === 'Admin'
                            ? 'bg-amber-950 text-amber-300 border border-amber-800'
                            : u.role === 'Manager'
                            ? 'bg-purple-950 text-purple-300 border border-purple-800'
                            : 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                        }`}>
                          {u.role}
                        </span>
                      </td>
                      <td className="p-3 text-slate-400">{u.created_at?.split('T')[0]}</td>
                      <td className="p-3">
                        <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400 font-medium">
                          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Active
                        </span>
                      </td>
                      <td className="p-3 text-right">
                        {u.id !== user?.id ? (
                          <div className="inline-flex items-center gap-1 justify-end">
                            <button
                              type="button"
                              title={`Generate new setup token for ${u.username}`}
                              onClick={async () => {
                                try {
                                  const res = await api.generateUserToken(u.id);
                                  setOnboardingTokenResult(res.onboarding_token);
                                  setProvisionModalOpen(true);
                                  addToast({
                                    type: 'success',
                                    title: 'Token Generated',
                                    message: `Setup token generated for ${u.username}.`,
                                  });
                                } catch (err) {
                                  addToast({ type: 'error', message: err.message });
                                }
                              }}
                              className="p-1.5 rounded text-slate-400 hover:text-amber-400 hover:bg-amber-950/40 cursor-pointer transition-colors"
                            >
                              <Key className="w-3.5 h-3.5" />
                            </button>
                            <button
                              type="button"
                              title={`Delete ${u.username}`}
                              onClick={() => handleDeleteUser(u)}
                              className="p-1.5 rounded text-slate-400 hover:text-rose-400 hover:bg-rose-950/40 cursor-pointer transition-colors"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ) : (
                          <span className="text-[10px] text-slate-600 font-mono">Current User</span>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            </div>
          </div>

          {/* Assignments Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-sm">
            <div className="px-4 py-3 bg-slate-950 border-b border-slate-800 text-xs font-semibold text-slate-300">
              Manager-to-Employee Review Hierarchy
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-200">
                <thead className="bg-slate-950/80 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                  <tr>
                    <th className="p-3">Manager</th>
                    <th className="p-3">Assigned Employee</th>
                    <th className="p-3">Assigned Date</th>
                    <th className="p-3">Approval Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {assignments.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="p-6 text-center text-slate-500">
                        No assignments configured.
                      </td>
                    </tr>
                  ) : (
                    assignments.map((a) => (
                      <tr key={a.id} className="hover:bg-slate-800/40">
                        <td className="p-3 font-medium text-purple-300">
                          {a.manager_username || a.manager_email || a.manager_id}
                        </td>
                        <td className="p-3 font-medium text-emerald-300">
                          {a.employee_username || a.employee_email || a.employee_id}
                        </td>
                        <td className="p-3 text-slate-400">{a.assigned_at?.split('T')[0] || a.created_at?.split('T')[0] || '—'}</td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            a.status === 'APPROVED'
                              ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                              : a.status === 'PENDING'
                              ? 'bg-amber-950 text-amber-300 border border-amber-800'
                              : 'bg-rose-950 text-rose-300 border border-rose-800'
                          }`}>
                            {a.status}
                          </span>
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

      {/* ── View: Projects, Ledgers & Vault */}
      {currentView === 'admin_catalog' && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-3">
            <div>
              <h1 className="text-lg font-bold text-slate-100">Master Financial Catalog & Vault</h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Maintain accounting ledger heads, projects, vault balance adjustments, and period locks.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={() => setAdjustmentModalOpen(true)}
                className="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold cursor-pointer"
              >
                Balance Adjustment
              </button>
              <button
                type="button"
                onClick={() => {
                  setNewOpeningBalance(cashBalance?.opening_balance || '');
                  setBalanceModalOpen(true);
                }}
                className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-bold cursor-pointer"
              >
                Configure Vault Balance
              </button>
            </div>
          </div>

          {/* Master Catalog Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Projects */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 shadow-sm space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-200">Active Projects ({projects.length})</h2>
                <button
                  type="button"
                  onClick={() => setProjectModalOpen(true)}
                  className="text-xs text-emerald-400 hover:underline flex items-center gap-1"
                >
                  <PlusCircle className="w-3.5 h-3.5" /> Add Project
                </button>
              </div>
              <div className="max-h-60 overflow-y-auto divide-y divide-slate-800/80">
                {projects.map((p) => (
                  <div key={p.id} className="py-2.5 flex items-center justify-between text-xs">
                    <span className="font-medium text-slate-200">{p.name}</span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleToggleProjectStatus(p.id, p.is_active)}
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold cursor-pointer transition-colors ${
                          p.is_active
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800 hover:bg-emerald-900'
                            : 'bg-slate-800 text-slate-400 border border-slate-700 hover:bg-slate-700'
                        }`}
                        title={p.is_active ? 'Click to deactivate' : 'Click to activate'}
                      >
                        {p.is_active ? 'Active' : 'Disabled'}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteProject(p.id, p.name)}
                        className="p-1 rounded text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition-colors cursor-pointer"
                        title="Delete project"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Ledgers */}
            <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 shadow-sm space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-200">Ledger Heads ({ledgers.length})</h2>
                <button
                  type="button"
                  onClick={() => setLedgerModalOpen(true)}
                  className="text-xs text-emerald-400 hover:underline flex items-center gap-1"
                >
                  <PlusCircle className="w-3.5 h-3.5" /> Add Ledger
                </button>
              </div>
              <div className="max-h-60 overflow-y-auto divide-y divide-slate-800/80">
                {ledgers.map((l) => (
                  <div key={l.id} className="py-2.5 flex items-center justify-between text-xs">
                    <span className="font-medium text-slate-200">{l.name}</span>
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => handleToggleLedgerStatus(l.id, l.is_active)}
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold cursor-pointer transition-colors ${
                          l.is_active
                            ? 'bg-emerald-950 text-emerald-400 border border-emerald-800 hover:bg-emerald-900'
                            : 'bg-slate-800 text-slate-400 border border-slate-700 hover:bg-slate-700'
                        }`}
                        title={l.is_active ? 'Click to deactivate' : 'Click to activate'}
                      >
                        {l.is_active ? 'Active' : 'Disabled'}
                      </button>
                      <button
                        type="button"
                        onClick={() => handleDeleteLedger(l.id, l.name)}
                        className="p-1 rounded text-slate-400 hover:text-rose-400 hover:bg-slate-800 transition-colors cursor-pointer"
                        title="Delete ledger"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Financial Accounting Periods */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-4 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold text-slate-200">Financial Accounting Periods</h2>
                <p className="text-[11px] text-slate-400">
                  Closed periods are locked against new postings, receipts, or modifications.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setPeriodModalOpen(true)}
                className="px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold"
              >
                Create Period
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-200">
                <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                  <tr>
                    <th className="p-2.5">Period Window</th>
                    <th className="p-2.5">Status</th>
                    <th className="p-2.5">Closed By / Date</th>
                    <th className="p-2.5 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {periods.length === 0 ? (
                    <tr>
                      <td colSpan={4} className="p-4 text-center text-slate-500">
                        No financial periods configured.
                      </td>
                    </tr>
                  ) : (
                    periods.map((pd) => (
                      <tr key={pd.id}>
                        <td className="p-2.5 font-mono text-slate-200">
                          {pd.period_start} to {pd.period_end}
                        </td>
                        <td className="p-2.5">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            pd.status === 'CLOSED'
                              ? 'bg-rose-950 text-rose-300 border border-rose-800'
                              : 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                          }`}>
                            {pd.status}
                          </span>
                        </td>
                        <td className="p-2.5 text-slate-400">
                          {pd.status === 'CLOSED'
                            ? `${pd.closed_by_name || pd.closed_by_username || usersList.find((u) => u.id === pd.closed_by)?.username || 'Admin'} (${pd.closed_at?.split('T')[0]})`
                            : '—'}
                        </td>
                        <td className="p-2.5 text-right">
                          {pd.status === 'OPEN' ? (
                            <button
                              type="button"
                              onClick={() => handleClosePeriod(pd.id)}
                              className="px-2.5 py-1 rounded bg-rose-950 hover:bg-rose-900 border border-rose-800 text-rose-300 text-[10px] font-semibold"
                            >
                              Lock / Close
                            </button>
                          ) : (
                            <button
                              type="button"
                              onClick={() => handleReopenPeriod(pd.id)}
                              className="px-2.5 py-1 rounded bg-amber-950 hover:bg-amber-900 border border-amber-800 text-amber-300 text-[10px] font-semibold"
                            >
                              Reopen
                            </button>
                          )}
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

      {/* ── View: Company Receipts */}
      {currentView === 'admin_receipts' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-3">
            <div>
              <h1 className="text-lg font-bold text-slate-100">Company Inbound Receipts</h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Direct top-ups that increase petty cash vault balance immediately without approval delay.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setReceiptModalOpen(true)}
              className="flex items-center gap-1.5 px-3.5 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-bold cursor-pointer"
            >
              <PlusCircle className="w-3.5 h-3.5" /> Record Receipt
            </button>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-200">
              <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                <tr>
                  <th className="p-3">Receipt Date</th>
                  <th className="p-3">Description</th>
                  <th className="p-3">Category</th>
                  <th className="p-3">Project</th>
                  <th className="p-3">Ledger</th>
                  <th className="p-3 text-right">Receipt Amount</th>
                  <th className="p-3">Direct Post Status</th>
                  <th className="p-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {receipts.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="p-6 text-center text-slate-500">
                      No company receipts recorded yet.
                    </td>
                  </tr>
                ) : (
                  receipts.map((rc) => (
                    <tr key={rc.id} className="hover:bg-slate-800/40">
                      <td className="p-3 font-mono">{rc.receipt_date}</td>
                      <td className="p-3 font-medium text-slate-100">{rc.description}</td>
                      <td className="p-3">
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-300 border border-slate-700">
                          {rc.category_name || 'Cash replenishment'}
                        </span>
                      </td>
                      <td className="p-3 text-slate-400">{rc.project_name || 'Petty Cash HQ'}</td>
                      <td className="p-3 text-slate-400">{rc.ledger_name || 'Company Receipts'}</td>
                      <td className="p-3 text-right font-mono font-bold text-emerald-400">
                        +₹{parseFloat(rc.amount).toFixed(2)}
                      </td>
                      <td className="p-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                          rc.is_reversed
                            ? 'bg-rose-950 text-rose-300 border border-rose-800'
                            : 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                        }`}>
                          {rc.is_reversed ? 'REVERSED' : 'DIRECTLY POSTED'}
                        </span>
                      </td>
                      <td className="p-3 text-right">
                        {!rc.is_reversed && (
                          <button
                            type="button"
                            onClick={() => {
                              setReversalTarget({ type: 'RECEIPT', item: rc });
                              setReversalReason('');
                              setReversalModalOpen(true);
                            }}
                            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-[10px] font-semibold cursor-pointer"
                          >
                            Reverse
                          </button>
                        )}
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

      {/* ── View: Requests for Posting */}
      {currentView === 'admin_postings' && (
        <div className="space-y-4">
          <div className="border-b border-slate-800 pb-3">
            <h1 className="text-lg font-bold text-slate-100">Requests for Canonical Ledger Posting</h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Review vouchers approved by managers, execute atomic balance deduction, or return for correction.
            </p>
          </div>

          {postingsQueue.length === 0 ? (
            <div className="p-10 bg-slate-900 border border-slate-800 rounded-lg text-center text-xs text-slate-400">
              Posting queue is empty. All approved requests have been posted!
            </div>
          ) : (
            <div className="space-y-4">
              {postingsQueue.map((reqItem) => (
                <div
                  key={reqItem.id}
                  className="p-5 bg-slate-900 border border-slate-800 rounded-lg shadow-sm space-y-4"
                >
                  <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-base font-bold text-slate-100">{reqItem.purpose}</span>
                        <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 text-emerald-300 border border-emerald-800">
                          APPROVED BY MANAGER
                        </span>
                      </div>
                      <div className="text-xs text-slate-400 mt-1">
                        Employee: <strong className="text-slate-300">{reqItem.requester_username || reqItem.requester_id}</strong> • Date: {reqItem.request_date} • Category: {reqItem.category}
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="text-xl font-extrabold text-amber-400">
                        ₹{parseFloat(reqItem.amount).toFixed(2)}
                      </div>
                      <div className="text-[10px] text-slate-500 font-mono">ID: {reqItem.id}</div>
                    </div>
                  </div>

                  {/* Supporting files */}
                  {reqItem.supporting_files && reqItem.supporting_files.length > 0 && (
                    <div className="space-y-1.5">
                      <span className="text-xs font-semibold text-slate-400 block">Supporting Voucher:</span>
                      <div className="flex flex-wrap gap-2">
                        {reqItem.supporting_files.map((file) => (
                          <button
                            key={file.id}
                            type="button"
                            onClick={() => api.downloadFile(api.getSupportingFileDownloadUrl(file.id), file.original_filename)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-950 border border-slate-800 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
                          >
                            <FileText className="w-3.5 h-3.5" />
                            <span>{file.original_filename}</span>
                            <ExternalLink className="w-3 h-3 text-slate-500" />
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800">
                    <button
                      type="button"
                      onClick={() => {
                        setTargetPostRequest(reqItem);
                        setReturnReason('');
                        setReturnModalOpen(true);
                      }}
                      className="px-3.5 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-amber-300 text-xs font-semibold"
                    >
                      Return for Correction
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setTargetPostRequest(reqItem);
                        setPostEffectiveDate(new Date().toISOString().split('T')[0]);
                        setPostModalOpen(true);
                      }}
                      className="flex items-center gap-1.5 px-4 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-bold"
                    >
                      <CheckCircle2 className="w-4 h-4" /> Post to Canonical Ledger
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── View: Reports & ZIP Exports */}
      {currentView === 'admin_reports' && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-3">
            <div>
              <h1 className="text-lg font-bold text-slate-100">Standardized 12-Column Monthly Reporting</h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Audit-reconciled financial workbooks and packaged ZIP bundles with relative voucher hyperlinks.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <input
                type="month"
                value={reportMonth}
                onChange={(e) => setReportMonth(e.target.value)}
                className="px-3 py-1.5 bg-slate-950 border border-slate-700 rounded-md text-xs text-slate-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={loadData}
                className="flex items-center gap-1 px-2.5 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium cursor-pointer"
                title="Refresh Report Data"
              >
                <RefreshCw className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={handleDownloadExcel}
                disabled={downloadingExcel}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold cursor-pointer disabled:opacity-50"
              >
                <Download className={`w-3.5 h-3.5 ${downloadingExcel ? 'animate-bounce' : ''}`} />
                {downloadingExcel ? 'Downloading...' : 'Excel sheet'}
              </button>
              <button
                type="button"
                onClick={handleDownloadZip}
                disabled={downloadingZip}
                className="flex items-center gap-1.5 px-3.5 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-bold cursor-pointer disabled:opacity-50"
              >
                <Download className={`w-3.5 h-3.5 ${downloadingZip ? 'animate-bounce' : ''}`} />
                {downloadingZip ? 'Bundling...' : 'ZIP Evidence Bundle'}
              </button>
            </div>
          </div>

          {/* Monthly Report Top KPI Cards */}
          {monthlyReport && (
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
              <div className="bg-slate-900 p-4 rounded-lg border border-slate-800 shadow-sm flex flex-col gap-1">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Opening Balance</span>
                <span className={`text-xl font-bold font-mono ${(monthlyReport.opening_balance ?? 0) < 0 ? 'text-rose-400' : 'text-slate-100'}`}>
                  {formatReportCurrency(monthlyReport.opening_balance ?? 0)}
                </span>
                <span className="text-xs text-slate-500 flex items-center gap-1">
                  <Calendar className="w-3 h-3 text-slate-400" /> {monthlyReport.start_date || reportMonth}
                </span>
              </div>

              <div className="bg-slate-900 p-4 rounded-lg border border-slate-800 shadow-sm flex flex-col gap-1">
                <div className="flex items-center justify-between text-slate-400">
                  <span className="text-[11px] font-semibold uppercase tracking-wider">Total Receipts</span>
                  <TrendingUp className="w-4 h-4 text-emerald-400" />
                </div>
                <span className="text-xl font-bold font-mono text-emerald-400">
                  {formatReportCurrency(monthlyReport.total_receipts ?? 0)}
                </span>
                <span className="text-xs text-slate-500">
                  {monthlyReport.additions?.length || 0} inflow heads
                </span>
              </div>

              <div className="bg-slate-900 p-4 rounded-lg border border-slate-800 shadow-sm flex flex-col gap-1">
                <div className="flex items-center justify-between text-slate-400">
                  <span className="text-[11px] font-semibold uppercase tracking-wider">Total Payments</span>
                  <TrendingDown className="w-4 h-4 text-amber-400" />
                </div>
                <span className="text-xl font-bold font-mono text-amber-400">
                  {formatReportCurrency(monthlyReport.total_payments ?? 0)}
                </span>
                <span className="text-xs text-slate-500">
                  {monthlyReport.withdrawals?.length || 0} projects
                </span>
              </div>

              <div className="bg-slate-900 p-4 rounded-lg border border-slate-800 shadow-sm flex flex-col gap-1">
                <div className="flex items-center justify-between text-slate-400">
                  <span className="text-[11px] font-semibold uppercase tracking-wider">Closing Balance</span>
                  <IndianRupee className="w-4 h-4 text-emerald-400" />
                </div>
                <span className={`text-xl font-bold font-mono ${(monthlyReport.closing_balance ?? 0) < 0 ? 'text-rose-400' : 'text-slate-100'}`}>
                  {formatReportCurrency(monthlyReport.closing_balance ?? 0)}
                </span>
                <span className="text-xs text-slate-500 flex items-center gap-1">
                  <Calendar className="w-3 h-3 text-slate-400" /> {monthlyReport.end_date || reportMonth}
                </span>
              </div>
            </div>
          )}

          {/* Navigation Tabs */}
          <div className="flex items-center justify-between border-b border-slate-800 bg-slate-900 px-4 rounded-lg shadow-sm">
            <div className="flex gap-1">
              {[
                { key: 'summary', label: 'Petty Cash Summary', icon: <FileSpreadsheet className="w-4 h-4" /> },
                { key: 'sheet', label: `Petty Cash Sheet (${monthlyReport?.posted_entries?.length || 0})`, icon: <Table className="w-4 h-4" /> },
                { key: 'analytics', label: 'Visual Analytics', icon: <PieChart className="w-4 h-4" /> },
              ].map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setReportActiveTab(tab.key)}
                  className={`flex items-center gap-2 py-3 px-4 font-semibold text-xs border-b-2 transition cursor-pointer ${
                    reportActiveTab === tab.key
                      ? 'border-emerald-500 text-emerald-400 bg-slate-800/40'
                      : 'border-transparent text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </div>
          </div>

          {/* TAB 1: Petty Cash Summary (Matches Spreadsheet Utility) */}
          {reportActiveTab === 'summary' && monthlyReport && (
            <div className="space-y-4">
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-3 flex items-center gap-2 text-xs text-slate-300">
                <Eye className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>
                  <b className="text-slate-100">Interactive Pivot Drill-Down:</b> Click any value in{' '}
                  <b>Sum of Receipt</b> or <b>Sum of Payment</b> to inspect contributing records.
                </span>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
                {/* Left Pivot Breakdown by Project */}
                <div className="lg:col-span-6 bg-slate-900 rounded-lg border border-slate-800 shadow-sm overflow-hidden">
                  <div className="bg-slate-950 px-4 py-3 border-b border-slate-800 flex items-center justify-between">
                    <div>
                      <h3 className="text-xs font-bold text-slate-200">Pivot Breakdown by Project</h3>
                      <p className="text-[11px] text-slate-500">Columns A:C in template</p>
                    </div>
                    <span className="text-[10px] bg-slate-800 text-slate-300 font-semibold px-2 py-0.5 rounded border border-slate-700">
                      {monthlyReport.pivot_rows?.length || 0} Projects
                    </span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs border-collapse">
                      <thead>
                        <tr className="bg-slate-950 text-slate-400 font-semibold border-b border-slate-800 text-[10px] uppercase tracking-wider">
                          <th className="py-2.5 px-3 border border-slate-800 text-left">Row Labels (Project)</th>
                          <th className="py-2.5 px-3 border border-slate-800 text-right w-36">Sum of Receipt</th>
                          <th className="py-2.5 px-3 border border-slate-800 text-right w-36">Sum of Payment</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                        {!monthlyReport.pivot_rows || monthlyReport.pivot_rows.length === 0 ? (
                          <tr>
                            <td colSpan={3} className="py-8 text-center text-slate-500 font-sans">
                              No project movements posted for this period.
                            </td>
                          </tr>
                        ) : (
                          monthlyReport.pivot_rows.map((prow, idx) => (
                            <tr key={idx} className="hover:bg-slate-800/40">
                              <td className="py-2 px-3 border border-slate-800 font-sans font-medium text-slate-200">
                                {prow.project}
                              </td>
                              <td className="py-1.5 px-3 border border-slate-800 text-right">
                                {prow.sum_receipt ? (
                                  <button
                                    type="button"
                                    onClick={() => openReportDrilldown(prow.project, 'receipt', prow.sum_receipt)}
                                    className="group inline-flex items-center gap-1 font-semibold text-emerald-400 hover:text-emerald-300 bg-slate-950 hover:bg-slate-800 px-2 py-0.5 rounded border border-emerald-900/60 transition cursor-pointer"
                                  >
                                    {formatReportCurrency(prow.sum_receipt)}
                                    <ExternalLink className="w-3 h-3 opacity-60 group-hover:opacity-100" />
                                  </button>
                                ) : (
                                  ''
                                )}
                              </td>
                              <td className="py-1.5 px-3 border border-slate-800 text-right">
                                {prow.sum_payment ? (
                                  <button
                                    type="button"
                                    onClick={() => openReportDrilldown(prow.project, 'payment', prow.sum_payment)}
                                    className="group inline-flex items-center gap-1 font-semibold text-amber-400 hover:text-amber-300 bg-slate-950 hover:bg-slate-800 px-2 py-0.5 rounded border border-amber-900/60 transition cursor-pointer"
                                  >
                                    {formatReportCurrency(prow.sum_payment)}
                                    <ExternalLink className="w-3 h-3 opacity-60 group-hover:opacity-100" />
                                  </button>
                                ) : (
                                  ''
                                )}
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                      <tfoot>
                        <tr className="bg-slate-950 font-bold border-t-2 border-slate-800 text-[11px]">
                          <td className="py-2.5 px-3 border border-slate-800 text-slate-100 font-sans">Grand Total</td>
                          <td className="py-2 px-3 border border-slate-800 text-right">
                            <button
                              type="button"
                              onClick={() => openReportDrilldown('Grand Total', 'receipt', monthlyReport.total_receipts)}
                              className="group inline-flex items-center gap-1 font-bold text-emerald-400 bg-slate-950 px-2 py-0.5 rounded border border-emerald-800 hover:bg-slate-800 transition cursor-pointer font-mono"
                            >
                              {formatReportCurrency(monthlyReport.total_receipts)}
                              <ExternalLink className="w-3 h-3 opacity-70 group-hover:opacity-100" />
                            </button>
                          </td>
                          <td className="py-2 px-3 border border-slate-800 text-right">
                            <button
                              type="button"
                              onClick={() => openReportDrilldown('Grand Total', 'payment', monthlyReport.total_payments)}
                              className="group inline-flex items-center gap-1 font-bold text-amber-400 bg-slate-950 px-2 py-0.5 rounded border border-amber-800 hover:bg-slate-800 transition cursor-pointer font-mono"
                            >
                              {formatReportCurrency(monthlyReport.total_payments)}
                              <ExternalLink className="w-3 h-3 opacity-70 group-hover:opacity-100" />
                            </button>
                          </td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>
                </div>

                {/* Right Petty Cash Statement */}
                <div className="lg:col-span-6 bg-slate-900 rounded-lg border border-slate-800 shadow-sm overflow-hidden">
                  <div className="bg-slate-950 px-4 py-3 text-center border-b border-slate-800">
                    <h3 className="text-xs font-bold text-slate-100 uppercase tracking-wider">Petty Cash Statement</h3>
                    <p className="text-[11px] text-slate-500">Official Reconciliation (Columns I:K)</p>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs border-collapse font-mono text-[11px]">
                      <thead>
                        <tr className="bg-slate-950 text-slate-400 font-semibold border-b border-slate-800 text-[10px] uppercase">
                          <th className="py-2 px-3 border border-slate-800 text-left font-sans">Particulars</th>
                          <th className="py-2 px-3 border border-slate-800 text-right w-28">Amount</th>
                          <th className="py-2 px-3 border border-slate-800 text-right w-32">Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        <tr className="border-b border-slate-800">
                          <td className="py-2 px-3 border border-slate-800 font-semibold text-slate-200 font-sans">
                            Petty Cash Opening Balance
                            <div className="text-[10px] font-normal text-slate-500">
                              ({monthlyReport.start_date || reportMonth})
                            </div>
                          </td>
                          <td className="py-2 px-3 border border-slate-800"></td>
                          <td className="py-2 px-3 border border-slate-800 text-right font-bold text-rose-400">
                            {formatReportCurrency(monthlyReport.opening_balance)}
                          </td>
                        </tr>

                        <tr className="bg-slate-950/80 font-bold border-b border-slate-800">
                          <td className="py-1.5 px-3 border border-slate-800 text-slate-300 font-sans">Additions (Receipts)</td>
                          <td className="py-1.5 px-3 border border-slate-800"></td>
                          <td className="py-1.5 px-3 border border-slate-800 text-right">
                            <button
                              type="button"
                              onClick={() => openReportDrilldown('Grand Total', 'receipt', monthlyReport.total_receipts)}
                              className="font-bold text-emerald-400 hover:underline cursor-pointer"
                            >
                              {formatReportCurrency(monthlyReport.total_receipts)}
                            </button>
                          </td>
                        </tr>

                        {monthlyReport.additions?.map((item, idx) => (
                          <tr key={`add-${idx}`} className="hover:bg-slate-800/40">
                            <td className="py-1.5 px-3 border border-slate-800 pl-6 text-slate-300 font-sans">
                              {item.particular}
                            </td>
                            <td className="py-1.5 px-3 border border-slate-800 text-right">
                              <button
                                type="button"
                                onClick={() => openReportDrilldown(item.project, 'receipt', item.amount)}
                                className="font-medium text-emerald-400 hover:underline cursor-pointer"
                              >
                                {formatReportCurrency(item.amount)}
                              </button>
                            </td>
                            <td className="py-1.5 px-3 border border-slate-800"></td>
                          </tr>
                        ))}

                        <tr className="bg-slate-950/80 font-bold border-b border-slate-800">
                          <td className="py-1.5 px-3 border border-slate-800 text-slate-300 font-sans">Withdrawals (Payments)</td>
                          <td className="py-1.5 px-3 border border-slate-800"></td>
                          <td className="py-1.5 px-3 border border-slate-800 text-right">
                            <button
                              type="button"
                              onClick={() => openReportDrilldown('Grand Total', 'payment', monthlyReport.total_payments)}
                              className="font-bold text-amber-400 hover:underline cursor-pointer"
                            >
                              -{formatReportCurrency(monthlyReport.total_payments)}
                            </button>
                          </td>
                        </tr>

                        {monthlyReport.withdrawals?.map((item, idx) => (
                          <tr key={`with-${idx}`} className="hover:bg-slate-800/40">
                            <td className="py-1.5 px-3 border border-slate-800 pl-6 text-slate-300 font-sans">
                              {item.particular}
                            </td>
                            <td className="py-1.5 px-3 border border-slate-800 text-right">
                              <button
                                type="button"
                                onClick={() => openReportDrilldown(item.project, 'payment', item.amount)}
                                className="font-medium text-amber-400 hover:underline cursor-pointer"
                              >
                                {formatReportCurrency(item.amount)}
                              </button>
                            </td>
                            <td className="py-1.5 px-3 border border-slate-800"></td>
                          </tr>
                        ))}

                        <tr className="bg-slate-950 font-bold border-t-2 border-slate-700">
                          <td className="py-3 px-3 border border-slate-800 text-slate-100 font-sans">
                            Closing balance as on {monthlyReport.end_date || reportMonth}
                          </td>
                          <td className="py-3 px-3 border border-slate-800"></td>
                          <td
                            className={`py-3 px-3 border border-slate-800 text-right text-sm font-bold ${
                              monthlyReport.closing_balance < 0 ? 'text-rose-400' : 'text-slate-100'
                            }`}
                          >
                            {formatReportCurrency(monthlyReport.closing_balance)}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: Petty Cash Sheet (12-Column Table with Search & Filter) */}
          {reportActiveTab === 'sheet' && (
            <div className="bg-slate-900 rounded-lg border border-slate-800 shadow-sm flex flex-col overflow-hidden">
              {/* Filter bar */}
              <div className="p-3 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3 bg-slate-950/60">
                <div className="flex items-center gap-2 flex-1 min-w-[220px] max-w-sm bg-slate-950 border border-slate-700 rounded-md px-3 py-1.5 shadow-sm focus-within:ring-2 focus-within:ring-emerald-500">
                  <Search className="w-4 h-4 text-slate-400" />
                  <input
                    type="text"
                    placeholder="Search entries…"
                    value={reportSearchTerm}
                    onChange={(e) => setReportSearchTerm(e.target.value)}
                    className="w-full text-xs text-slate-100 bg-transparent focus:outline-none"
                  />
                  {reportSearchTerm && (
                    <button type="button" onClick={() => setReportSearchTerm('')}>
                      <X className="w-3.5 h-3.5 text-slate-400" />
                    </button>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium text-slate-400">Project:</span>
                    <select
                      value={reportSelectedProject}
                      onChange={(e) => setReportSelectedProject(e.target.value)}
                      className="text-xs bg-slate-950 border border-slate-700 rounded-md px-2.5 py-1.5 text-slate-200 focus:ring-1 focus:ring-emerald-500 focus:outline-none"
                    >
                      <option value="ALL">All Projects ({uniqueReportProjects.length})</option>
                      {uniqueReportProjects.map((p) => (
                        <option key={p} value={p}>
                          {p}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium text-slate-400">Ledger:</span>
                    <select
                      value={reportSelectedLedger}
                      onChange={(e) => setReportSelectedLedger(e.target.value)}
                      className="text-xs bg-slate-950 border border-slate-700 rounded-md px-2.5 py-1.5 text-slate-200 focus:ring-1 focus:ring-emerald-500 focus:outline-none"
                    >
                      <option value="ALL">All Ledgers ({uniqueReportLedgers.length})</option>
                      {uniqueReportLedgers.map((l) => (
                        <option key={l} value={l}>
                          {l}
                        </option>
                      ))}
                    </select>
                  </div>
                  {(reportSearchTerm || reportSelectedProject !== 'ALL' || reportSelectedLedger !== 'ALL') && (
                    <button
                      type="button"
                      onClick={() => {
                        setReportSearchTerm('');
                        setReportSelectedProject('ALL');
                        setReportSelectedLedger('ALL');
                      }}
                      className="text-xs text-rose-400 hover:underline font-medium cursor-pointer"
                    >
                      Reset
                    </button>
                  )}
                </div>
              </div>

              {/* Transactions Table */}
              <div className="overflow-x-auto max-h-[560px]">
                <table className="w-full text-left border-collapse text-xs">
                  <thead className="bg-slate-950 text-slate-300 uppercase font-semibold sticky top-0 z-10 shadow-sm border-b border-slate-800 text-[10px] tracking-wider">
                    <tr>
                      <th className="py-2.5 px-3 border border-slate-800">Date</th>
                      <th className="py-2.5 px-3 border border-slate-800">Ledger</th>
                      <th className="py-2.5 px-3 border border-slate-800">Memo / Description</th>
                      <th className="py-2.5 px-3 border border-slate-800 text-right">Receipt</th>
                      <th className="py-2.5 px-3 border border-slate-800 text-right">Payment</th>
                      <th className="py-2.5 px-3 border border-slate-800 text-right">Balance</th>
                      <th className="py-2.5 px-3 border border-slate-800">Approved By</th>
                      <th className="py-2.5 px-3 border border-slate-800">Requested By</th>
                      <th className="py-2.5 px-3 border border-slate-800">Category</th>
                      <th className="py-2.5 px-3 border border-slate-800">Project</th>
                      <th className="py-2.5 px-3 border border-slate-800">Supportings</th>
                      <th className="py-2.5 px-3 border border-slate-800">Notes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                    {filteredReportEntries.length === 0 ? (
                      <tr>
                        <td colSpan={12} className="py-12 text-center text-slate-500 font-sans">
                          No transactions match the selected filters for {reportMonth}.
                        </td>
                      </tr>
                    ) : (
                      paginatedReportEntries.map((tx, idx) => (
                        <tr key={tx.id || idx} className="hover:bg-slate-800/40 transition">
                          <td className="py-2 px-3 border border-slate-800 whitespace-nowrap">{tx.date}</td>
                          <td className="py-2 px-3 border border-slate-800 font-medium text-slate-200">{tx.ledger || '—'}</td>
                          <td className="py-2 px-3 border border-slate-800 text-slate-100 max-w-xs truncate font-sans" title={tx.description || tx.memo}>
                            {tx.description || tx.memo || '—'}
                          </td>
                          <td className="py-2 px-3 border border-slate-800 text-right font-medium text-emerald-400 font-mono">
                            {tx.receipt ? formatReportCurrency(tx.receipt) : '—'}
                          </td>
                          <td className="py-2 px-3 border border-slate-800 text-right font-medium text-amber-400 font-mono">
                            {tx.payment ? formatReportCurrency(tx.payment) : '—'}
                          </td>
                          <td className={`py-2 px-3 border border-slate-800 text-right font-bold font-mono ${(tx.outstanding_balance ?? tx.balance ?? 0) < 0 ? 'text-rose-400' : 'text-slate-100'}`}>
                            {formatReportCurrency(tx.outstanding_balance ?? tx.balance ?? 0)}
                          </td>
                          <td className="py-2 px-3 border border-slate-800 text-slate-300 font-sans">{tx.approved_by || '—'}</td>
                          <td className="py-2 px-3 border border-slate-800 text-slate-300 font-sans">{tx.requested_by || '—'}</td>
                          <td className="py-2 px-3 border border-slate-800 text-slate-400 font-sans text-[11px] truncate" title={tx.category}>
                            {tx.category || '—'}
                          </td>
                          <td className="py-2 px-3 border border-slate-800 text-slate-200 font-medium font-sans text-[11px] truncate" title={tx.project}>
                            {tx.project || '—'}
                          </td>
                          <td className="py-2 px-3 border border-slate-800 font-sans">
                            {tx.all_supportings && tx.all_supportings.length > 0 ? (
                              <button
                                type="button"
                                onClick={() => handleDownloadSupporting(tx.all_supportings[0])}
                                disabled={downloadingFileId === tx.all_supportings[0].id}
                                className="text-emerald-400 hover:text-emerald-300 flex items-center gap-1 cursor-pointer font-medium disabled:opacity-50"
                                title={tx.all_supportings[0].original_filename}
                              >
                                <FileText className="w-3.5 h-3.5" />
                                {downloadingFileId === tx.all_supportings[0].id ? 'Loading...' : 'Voucher'}
                              </button>
                            ) : tx.supportings ? (
                              <span className="text-slate-300 text-[10px]">{tx.supportings}</span>
                            ) : (
                              <span className="text-slate-600">—</span>
                            )}
                          </td>
                          <td className="py-2 px-3 border border-slate-800 text-slate-400 font-sans max-w-xs truncate" title={tx.notes}>
                            {tx.notes || '—'}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
              <TablePagination
                currentPage={reportSheetPage}
                totalItems={filteredReportEntries.length}
                pageSize={reportSheetPageSize}
                onPageChange={setReportSheetPage}
                onPageSizeChange={setReportSheetPageSize}
                pageSizeOptions={[10, 25, 50, 100]}
              />
            </div>
          )}

          {/* TAB 3: Visual Analytics */}
          {reportActiveTab === 'analytics' && monthlyReport && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                {/* Spending by Project */}
                <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 shadow-sm space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                    <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">Top Spending Projects (Withdrawals)</h3>
                    <span className="text-xs font-mono font-bold text-amber-400">
                      {formatReportCurrency(monthlyReport.total_payments)}
                    </span>
                  </div>
                  <div className="space-y-3">
                    {monthlyReport.withdrawals?.map((item, i) => {
                      const pct = Math.round((item.amount / (monthlyReport.total_payments || 1)) * 100);
                      return (
                        <div key={i} className="space-y-1">
                          <div className="flex justify-between text-xs">
                            <button
                              type="button"
                              onClick={() => openReportDrilldown(item.project, 'payment', item.amount)}
                              className="font-medium text-slate-300 hover:text-emerald-400 hover:underline flex items-center gap-1 cursor-pointer"
                            >
                              {item.particular} <ExternalLink className="w-3 h-3 opacity-60" />
                            </button>
                            <span className="font-mono text-slate-400">
                              {formatReportCurrency(item.amount)} ({pct}%)
                            </span>
                          </div>
                          <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                            <div className="bg-amber-500 h-2 rounded-full transition-all duration-300" style={{ width: `${Math.min(pct, 100)}%` }}></div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Receipts by Project / Head */}
                <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 shadow-sm space-y-4">
                  <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                    <h3 className="text-xs font-bold text-slate-200 uppercase tracking-wider">Inbound Cash Receipts (Additions)</h3>
                    <span className="text-xs font-mono font-bold text-emerald-400">
                      {formatReportCurrency(monthlyReport.total_receipts)}
                    </span>
                  </div>
                  <div className="space-y-3">
                    {monthlyReport.additions?.map((item, i) => {
                      const pct = Math.round((item.amount / (monthlyReport.total_receipts || 1)) * 100);
                      return (
                        <div key={i} className="space-y-1">
                          <div className="flex justify-between text-xs">
                            <button
                              type="button"
                              onClick={() => openReportDrilldown(item.project, 'receipt', item.amount)}
                              className="font-medium text-slate-300 hover:text-emerald-400 hover:underline flex items-center gap-1 cursor-pointer"
                            >
                              {item.particular} <ExternalLink className="w-3 h-3 opacity-60" />
                            </button>
                            <span className="font-mono text-slate-400">
                              {formatReportCurrency(item.amount)} ({pct}%)
                            </span>
                          </div>
                          <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                            <div className="bg-emerald-500 h-2 rounded-full transition-all duration-300" style={{ width: `${Math.min(pct, 100)}%` }}></div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              </div>

              {/* Daily Cash Movement Aggregate */}
              {monthlyReport.daily_movement && monthlyReport.daily_movement.length > 0 && (
                <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-sm">
                  <div className="px-4 py-3 bg-slate-950 border-b border-slate-800 text-xs font-semibold text-slate-300">
                    Daily Balance Movement Aggregate
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs text-slate-200">
                      <thead className="bg-slate-950/80 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                        <tr>
                          <th className="p-2.5">Date</th>
                          <th className="p-2.5 text-right">Inbound Receipts</th>
                          <th className="p-2.5 text-right">Outbound Payments</th>
                          <th className="p-2.5 text-right">Net Daily Movement</th>
                          <th className="p-2.5 text-right">Closing Day Balance</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                        {monthlyReport.daily_movement.map((dm, idx) => (
                          <tr key={idx} className="hover:bg-slate-800/40">
                            <td className="p-2.5 whitespace-nowrap">{dm.date}</td>
                            <td className="p-2.5 text-right text-emerald-400 font-mono">
                              {dm.receipts > 0 ? `+₹${Number(dm.receipts).toFixed(2)}` : '—'}
                            </td>
                            <td className="p-2.5 text-right text-amber-400 font-mono">
                              {dm.payments > 0 ? `-₹${Number(dm.payments).toFixed(2)}` : '—'}
                            </td>
                            <td
                              className={`p-2.5 text-right font-mono font-medium ${
                                dm.net_movement >= 0 ? 'text-emerald-400' : 'text-amber-400'
                              }`}
                            >
                              {dm.net_movement >= 0 ? '+' : ''}₹{Number(dm.net_movement).toFixed(2)}
                            </td>
                            <td className="p-2.5 text-right font-bold text-slate-100 font-mono">
                              ₹{Number(dm.closing_balance).toFixed(2)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── MODAL: Report Drill-Down ────────────────────────────────────────── */}
          {reportDrilldownData && (
            <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-center justify-center p-3 sm:p-5">
              <div className="bg-slate-900 rounded-xl shadow-2xl max-w-7xl w-full max-h-[92vh] flex flex-col border border-slate-800 overflow-hidden text-slate-100">
                <div className="px-6 py-4 border-b border-slate-800 bg-slate-950 flex items-center justify-between">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                        Audit Drilldown
                      </span>
                      <span
                        className={`text-[10px] font-semibold px-2 py-0.5 rounded uppercase ${
                          reportDrilldownData.type === 'receipt'
                            ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                            : 'bg-amber-950 text-amber-300 border border-amber-800'
                        }`}
                      >
                        {reportDrilldownData.type === 'receipt' ? 'Receipts (Inflows)' : 'Payments (Outflows)'}
                      </span>
                    </div>
                    <h3 className="text-base font-bold text-slate-100 mt-1">{reportDrilldownData.project}</h3>
                  </div>
                  <div className="flex items-center gap-4">
                    <div className="text-right">
                      <span className="text-[11px] text-slate-400 block">Total Sum</span>
                      <span
                        className={`text-base font-bold font-mono ${
                          reportDrilldownData.type === 'receipt' ? 'text-emerald-400' : 'text-amber-400'
                        }`}
                      >
                        {formatReportCurrency(reportDrilldownData.amount)}
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setReportDrilldownData(null)}
                      className="p-1.5 text-slate-400 hover:text-slate-200 rounded-md hover:bg-slate-800 transition cursor-pointer"
                    >
                      <X className="w-5 h-5" />
                    </button>
                  </div>
                </div>
                <div className="px-6 py-2.5 bg-slate-950/60 border-b border-slate-800 flex flex-wrap items-center justify-between gap-3 text-xs">
                  <span className="text-slate-400 font-medium">
                    Found <b className="text-slate-200">{reportDrilldownData.rows.length}</b> records contributing to this total
                  </span>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={handleDownloadReportDrilldown}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium rounded-md border border-slate-700 shadow-sm transition cursor-pointer"
                    >
                      <FileDown className="w-3.5 h-3.5 text-slate-400" /> Export Table (.xlsx)
                    </button>
                    <button
                      type="button"
                      onClick={() => redirectToSheetTab(reportDrilldownData.project)}
                      className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-bold rounded-md shadow-sm transition cursor-pointer"
                    >
                      <ExternalLink className="w-3.5 h-3.5" /> View in Sheet
                    </button>
                  </div>
                </div>
                <div className="overflow-auto flex-1 p-4 sm:p-6 bg-slate-900">
                  <table className="w-full text-left border-collapse text-xs">
                    <thead className="bg-slate-950 text-slate-300 uppercase font-semibold sticky top-0 z-10 shadow-sm border-b border-slate-800 text-[10px] tracking-wider">
                      <tr>
                        <th className="py-2.5 px-3 border border-slate-800">Date</th>
                        <th className="py-2.5 px-3 border border-slate-800">Ledger</th>
                        <th className="py-2.5 px-3 border border-slate-800">Memo / Description</th>
                        <th className="py-2.5 px-3 border border-slate-800 text-right">Receipt</th>
                        <th className="py-2.5 px-3 border border-slate-800 text-right">Payment</th>
                        <th className="py-2.5 px-3 border border-slate-800 text-right">Balance</th>
                        <th className="py-2.5 px-3 border border-slate-800">Approved By</th>
                        <th className="py-2.5 px-3 border border-slate-800">Requested By</th>
                        <th className="py-2.5 px-3 border border-slate-800">Category</th>
                        <th className="py-2.5 px-3 border border-slate-800">Project</th>
                        <th className="py-2.5 px-3 border border-slate-800">Supportings</th>
                        <th className="py-2.5 px-3 border border-slate-800">Notes</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                      {paginatedDrilldownRows.map((tx, idx) => (
                        <tr key={tx.id || idx} className="hover:bg-slate-800/40 transition">
                          <td className="py-2 px-3 border border-slate-800 whitespace-nowrap">{tx.date}</td>
                          <td className="py-2 px-3 border border-slate-800 font-medium text-slate-200">{tx.ledger || '—'}</td>
                          <td className="py-2 px-3 border border-slate-800 text-slate-100 max-w-xs truncate font-sans" title={tx.description || tx.memo}>
                            {tx.description || tx.memo || '—'}
                          </td>
                          <td className="py-2 px-3 border border-slate-800 text-right font-medium text-emerald-400 font-mono">
                            {tx.receipt ? formatReportCurrency(tx.receipt) : '—'}
                          </td>
                          <td className="py-2 px-3 border border-slate-800 text-right font-medium text-amber-400 font-mono">
                            {tx.payment ? formatReportCurrency(tx.payment) : '—'}
                          </td>
                          <td
                            className={`py-2 px-3 border border-slate-800 text-right font-semibold font-mono ${
                              (tx.outstanding_balance ?? tx.balance ?? 0) < 0 ? 'text-rose-400' : 'text-slate-100'
                            }`}
                          >
                            {formatReportCurrency(tx.outstanding_balance ?? tx.balance ?? 0)}
                          </td>
                          <td className="py-2 px-3 border border-slate-800 text-slate-300 font-sans">{tx.approved_by || '—'}</td>
                          <td className="py-2 px-3 border border-slate-800 text-slate-300 font-sans">{tx.requested_by || '—'}</td>
                          <td className="py-2 px-3 border border-slate-800 text-slate-400 font-sans text-[11px] truncate" title={tx.category}>
                            {tx.category || '—'}
                          </td>
                          <td className="py-2 px-3 border border-slate-800 text-slate-200 font-medium font-sans text-[11px] truncate" title={tx.project}>
                            {tx.project || '—'}
                          </td>
                          <td className="py-2 px-3 border border-slate-800 font-sans">
                            {tx.all_supportings && tx.all_supportings.length > 0 ? (
                              <button
                                type="button"
                                onClick={() => handleDownloadSupporting(tx.all_supportings[0])}
                                disabled={downloadingFileId === tx.all_supportings[0].id}
                                className="text-emerald-400 hover:text-emerald-300 flex items-center gap-1 cursor-pointer font-medium disabled:opacity-50"
                                title={tx.all_supportings[0].original_filename}
                              >
                                <FileText className="w-3.5 h-3.5" />
                                {downloadingFileId === tx.all_supportings[0].id ? 'Loading...' : 'Voucher'}
                              </button>
                            ) : tx.supportings ? (
                              <span className="text-slate-300 text-[10px]">{tx.supportings}</span>
                            ) : (
                              <span className="text-slate-600">—</span>
                            )}
                          </td>
                          <td className="py-2 px-3 border border-slate-800 text-slate-400 font-sans max-w-xs truncate" title={tx.notes}>
                            {tx.notes || '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="bg-slate-950 font-bold border-t-2 border-slate-800 text-[11px]">
                        <td colSpan={3} className="py-2 px-3 border border-slate-800 text-slate-100 text-right font-sans">
                          Subtotals:
                        </td>
                        <td className="py-2 px-3 border border-slate-800 text-right font-mono text-emerald-400">
                          {formatReportCurrency(reportDrilldownData.rows.reduce((acc, t) => acc + (Number(t.receipt) || 0), 0))}
                        </td>
                        <td className="py-2 px-3 border border-slate-800 text-right font-mono text-amber-400">
                          {formatReportCurrency(reportDrilldownData.rows.reduce((acc, t) => acc + (Number(t.payment) || 0), 0))}
                        </td>
                        <td colSpan={7} className="py-2 px-3 border border-slate-800"></td>
                      </tr>
                    </tfoot>
                  </table>
                  <TablePagination
                    currentPage={drilldownPage}
                    totalItems={(reportDrilldownData.rows || []).length}
                    pageSize={drilldownPageSize}
                    onPageChange={setDrilldownPage}
                    onPageSizeChange={setDrilldownPageSize}
                    pageSizeOptions={[5, 10, 20]}
                  />
                </div>
                <div className="px-6 py-3 border-t border-slate-800 bg-slate-950 flex items-center justify-end">
                  <button
                    type="button"
                    onClick={() => setReportDrilldownData(null)}
                    className="px-4 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium rounded-md text-xs transition cursor-pointer"
                  >
                    Close
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── View: Operations & Monitoring */}
      {currentView === 'admin_operations' && (
        <div className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 border-b border-slate-800 pb-3">
            <div>
              <h1 className="text-lg font-bold text-slate-100">Production Operations & Observability</h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Health probes, metrics tracking, automated backups, and production alert rules.
              </p>
            </div>
            <button
              type="button"
              disabled={isSubmitting}
              onClick={handleTriggerBackup}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-bold cursor-pointer"
            >
              <Database className="w-3.5 h-3.5" /> Trigger Online Backup
            </button>
          </div>

          {/* Active Alert Rules Evaluation */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg p-5 shadow-sm space-y-3">
            <h2 className="text-sm font-semibold text-slate-200">Production Alert Rules</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {alerts.map((alt) => (
                <div
                  key={alt.rule_id}
                  className={`p-3.5 rounded-lg border text-xs space-y-1.5 ${
                    alt.status === 'FIRING'
                      ? 'bg-rose-950/40 border-rose-800 text-rose-200'
                      : 'bg-slate-950 border-slate-800 text-slate-300'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-100">{alt.name}</span>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      alt.status === 'FIRING' ? 'bg-rose-950 text-rose-400 border border-rose-800' : 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                    }`}>
                      {alt.status}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400">{alt.message}</p>
                  <div className="pt-1 flex items-center justify-between text-[10px]">
                    <span className="text-slate-500">Rule: {alt.rule_id}</span>
                    <div className="flex items-center gap-2">
                      {alt.status === 'FIRING' && (
                        <button
                          type="button"
                          onClick={() => handleAcknowledgeAlert(alt.rule_id)}
                          className="px-2 py-0.5 rounded bg-rose-900/60 hover:bg-rose-800 text-rose-200 border border-rose-700 font-semibold cursor-pointer transition-colors"
                        >
                          Acknowledge / Clear
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => handleTestAlert(alt.rule_id)}
                        className="text-emerald-400 hover:underline font-semibold cursor-pointer"
                      >
                        Test / Simulate
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Database Backups List */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-sm">
            <div className="px-4 py-3 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-xs font-semibold text-slate-200">
                  Available Database Snapshots ({backups.length} Saved)
                </span>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Transactional snapshots manually initiated by administrators. Backups do not run on an automated timer.
                </p>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-200">
                <thead className="bg-slate-950/80 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                  <tr>
                    <th className="p-3">Backup File</th>
                    <th className="p-3">Storage Engine</th>
                    <th className="p-3">Created At</th>
                    <th className="p-3">Size</th>
                    <th className="p-3">SHA256 Checksum</th>
                    <th className="p-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                  {backups.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="p-6 text-center text-slate-500 font-sans">
                        No backups generated yet.
                      </td>
                    </tr>
                  ) : (
                    paginatedBackups.map((bk) => (
                      <tr key={bk.backup_id} className="hover:bg-slate-800/40">
                        <td className="p-3 font-semibold text-slate-100">{bk.filename || bk.backup_id}</td>
                        <td className="p-3 font-sans">
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
                            Supabase Storage
                          </span>
                        </td>
                        <td className="p-3 text-slate-400">{bk.created_at?.split('.')[0]?.replace('T', ' ')}</td>
                        <td className="p-3 text-slate-300">{(bk.size_bytes / 1024).toFixed(1)} KB</td>
                        <td className="p-3 text-slate-500 truncate max-w-[140px]">{bk.checksum_sha256}</td>
                        <td className="p-3 text-right font-sans space-x-2">
                          <button
                            type="button"
                            onClick={() => handleDownloadBackup(bk.backup_id)}
                            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-sky-400 text-[10px] font-semibold cursor-pointer"
                          >
                            Download
                          </button>
                          <button
                            type="button"
                            onClick={() => handleVerifyBackup(bk.backup_id)}
                            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-emerald-400 text-[10px] font-semibold cursor-pointer"
                          >
                            Verify PRAGMA
                          </button>
                          <button
                            type="button"
                            disabled={isSubmitting}
                            onClick={() => handleRestoreBackup(bk.backup_id)}
                            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-amber-400 text-[10px] font-semibold cursor-pointer disabled:opacity-50"
                          >
                            Restore
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <TablePagination
              currentPage={backupsPage}
              totalItems={backups.length}
              pageSize={backupsPageSize}
              onPageChange={setBackupsPage}
              onPageSizeChange={setBackupsPageSize}
              pageSizeOptions={[5, 10, 20]}
            />
          </div>

          {/* Diagnostic Error Logs Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-sm">
            <div className="px-4 py-3 bg-slate-950 border-b border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-xs font-semibold text-slate-200">
                  Recent Production Errors & Diagnostics ({recentErrors.length})
                </span>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Real-time telemetry capturing failed requests, unhandled exceptions, and API status codes.
                </p>
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-200">
              <thead className="bg-slate-950/80 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                <tr>
                  <th className="p-3">Timestamp</th>
                  <th className="p-3">Status</th>
                  <th className="p-3">Method & Path</th>
                  <th className="p-3">Error Type</th>
                  <th className="p-3">Message</th>
                  <th className="p-3 text-right">Correlation ID</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                {recentErrors.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-6 text-center text-slate-500 font-sans">
                      No production errors recorded. All systems healthy.
                    </td>
                  </tr>
                ) : (
                  paginatedErrors.map((err, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/40">
                      <td className="p-3 text-slate-400 whitespace-nowrap">{err.timestamp?.split('.')[0]?.replace('T', ' ')}</td>
                      <td className="p-3 font-sans">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                          err.status_code >= 500
                            ? 'bg-rose-950 text-rose-300 border-rose-800'
                            : 'bg-amber-950 text-amber-300 border-amber-800'
                        }`}>
                          HTTP {err.status_code}
                        </span>
                      </td>
                      <td className="p-3 text-slate-200 font-semibold">{err.method} {err.path}</td>
                      <td className="p-3 text-rose-400 font-semibold">{err.error_type}</td>
                      <td className="p-3 text-slate-300 font-sans max-w-xs truncate" title={err.message}>{err.message}</td>
                      <td className="p-3 text-right text-slate-500 text-[10px]">{err.correlation_id || '—'}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
            </div>
            <TablePagination
              currentPage={errorsPage}
              totalItems={recentErrors.length}
              pageSize={errorsPageSize}
              onPageChange={setErrorsPage}
              onPageSizeChange={setErrorsPageSize}
              pageSizeOptions={[5, 10, 25]}
            />
          </div>
        </div>
      )}

      {/* ── View: Audit Log */}
      {currentView === 'admin_audit' && (
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-3">
            <div>
              <h1 className="text-lg font-bold text-slate-100">Immutable Audit Trail</h1>
              <p className="text-xs text-slate-400 mt-0.5">
                Comprehensive append-only security and financial governance event log with user identity, correlation IDs, and state diffs.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={loadData}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold border border-slate-700 cursor-pointer"
                title="Refresh audit feed"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Refresh
              </button>
            </div>
          </div>

          {/* Search & Category Filter Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-slate-900/60 p-3 rounded-lg border border-slate-800">
            <div className="flex flex-wrap items-center gap-1.5">
              {[
                { id: 'ALL', label: 'All Events' },
                { id: 'REQUESTS', label: 'Requests & Approvals' },
                { id: 'CATALOG', label: 'Projects & Ledgers' },
                { id: 'USERS', label: 'Users & Roles' },
                { id: 'FINANCE', label: 'Finance & Periods' },
                { id: 'EXPORTS', label: 'Reports & Exports' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setAuditFilter(tab.id)}
                  className={`px-2.5 py-1 rounded text-xs font-medium transition-colors cursor-pointer ${
                    auditFilter === tab.id
                      ? 'bg-emerald-600 text-slate-950 font-bold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div className="relative min-w-[220px]">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={auditSearch}
                onChange={(e) => setAuditSearch(e.target.value)}
                placeholder="Search actor, action, ID..."
                className="w-full pl-8 pr-3 py-1.5 bg-slate-950 border border-slate-700 rounded-md text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
              />
            </div>
          </div>

          {/* Audit Events Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-sm">
            <div className="px-4 py-2.5 bg-slate-950 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400">
              <span>
                Displaying <strong>{filteredAuditEvents.length}</strong> of {auditEvents.length} recorded audit events
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-200">
              <thead className="bg-slate-950 text-slate-400 uppercase tracking-wider text-[10px] border-b border-slate-800">
                <tr>
                  <th className="p-3">Timestamp</th>
                  <th className="p-3">Action</th>
                  <th className="p-3">Actor</th>
                  <th className="p-3">Entity Type</th>
                  <th className="p-3">Correlation / Details</th>
                  <th className="p-3 text-right">State Diff</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {filteredAuditEvents.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-6 text-center text-slate-500">
                      No audit events match the selected criteria.
                    </td>
                  </tr>
                ) : (
                  paginatedAuditEvents.map((evt) => {
                    const isErrorOrReject = evt.action.includes('REJECT') || evt.action.includes('FAIL');
                    const isSuccess = evt.action.includes('APPROV') || evt.action.includes('POST') || evt.action.includes('SUCCESS');
                    const isCreateOrAdd = evt.action.includes('CREATE') || evt.action.includes('PROVISION');
                    const isReversalOrChange = evt.action.includes('REVERS') || evt.action.includes('CHANGE');

                    return (
                      <tr key={evt.id} className="hover:bg-slate-800/40">
                        <td className="p-3 font-mono text-[11px] text-slate-400 whitespace-nowrap">
                          {evt.created_at?.split('.')[0]?.replace('T', ' ')}
                        </td>
                        <td className="p-3">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                              isErrorOrReject
                                ? 'bg-rose-950 text-rose-300 border-rose-800'
                                : isSuccess
                                ? 'bg-emerald-950 text-emerald-300 border-emerald-800'
                                : isReversalOrChange
                                ? 'bg-amber-950 text-amber-300 border-amber-800'
                                : isCreateOrAdd
                                ? 'bg-cyan-950 text-cyan-300 border-cyan-800'
                                : 'bg-slate-800 text-slate-300 border-slate-700'
                            }`}
                          >
                            {evt.action.replace(/_/g, ' ')}
                          </span>
                        </td>
                        <td className="p-3 text-slate-200">
                          <div className="font-semibold text-xs">
                            {evt.actor_username || 'System'}
                          </div>
                          {evt.actor_user_id && (
                            <div className="text-[10px] font-mono text-slate-500">
                              {evt.actor_user_id}
                            </div>
                          )}
                        </td>
                        <td className="p-3 text-slate-400 font-mono text-[11px]">
                          {evt.entity_type}
                        </td>
                        <td className="p-3 font-mono text-[11px] text-slate-400">
                          <span className="text-slate-500 truncate max-w-[180px] block" title={evt.correlation_id}>
                            {evt.correlation_id || evt.entity_id || '—'}
                          </span>
                        </td>
                        <td className="p-3 text-right">
                          <button
                            type="button"
                            onClick={() => {
                              setDetailItem(evt);
                              setDetailModalOpen(true);
                            }}
                            className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white text-[11px] font-medium border border-slate-700 cursor-pointer inline-flex items-center gap-1"
                            title="Inspect before/after state"
                          >
                            <Eye className="w-3.5 h-3.5" /> View Diff
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
            </div>
            <TablePagination
              currentPage={auditPage}
              totalItems={filteredAuditEvents.length}
              pageSize={auditPageSize}
              onPageChange={setAuditPage}
              onPageSizeChange={setAuditPageSize}
              pageSizeOptions={[15, 25, 50, 100]}
            />
          </div>
        </div>
      )}

      {/* ── Provision User Modal */}
      <Modal
        isOpen={provisionModalOpen}
        onClose={() => setProvisionModalOpen(false)}
        title="Provision Organization User"
      >
        {onboardingTokenResult ? (
          <div className="space-y-4 text-xs">
            <div className="p-4 bg-emerald-950/60 border border-emerald-800 rounded-lg space-y-3">
              <div className="font-bold text-emerald-300 text-sm">User Setup Token Ready!</div>
              <p className="text-slate-300">
                Share this one-time onboarding setup token with the user so they can set their password:
              </p>
              <div className="flex items-center gap-2">
                <div className="flex-1 p-2.5 bg-slate-950 rounded font-mono text-xs text-amber-300 select-all border border-slate-800 break-all">
                  {onboardingTokenResult}
                </div>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(onboardingTokenResult);
                    addToast({ type: 'success', message: 'Token copied to clipboard!' });
                  }}
                  className="px-3 py-2 rounded bg-emerald-600 hover:bg-emerald-500 text-white font-medium cursor-pointer shrink-0 transition-colors"
                >
                  Copy
                </button>
              </div>
              <div className="p-2.5 bg-slate-900/90 rounded border border-slate-800 text-[11px] text-slate-300 space-y-1">
                <p className="font-semibold text-emerald-400">How the user logs in:</p>
                <ol className="list-decimal list-inside space-y-0.5 text-slate-400">
                  <li>Go to the PettyCash login page.</li>
                  <li>Click the <span className="text-slate-200 font-medium">Invite / Set Password</span> tab.</li>
                  <li>Paste this token and set their password.</li>
                </ol>
              </div>
            </div>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => {
                  setProvisionModalOpen(false);
                  setOnboardingTokenResult('');
                  setNewUsername('');
                  setNewUserEmail('');
                }}
                className="px-4 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 cursor-pointer"
              >
                Done
              </button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleProvisionUser} className="space-y-4 text-xs">
            <div>
              <label className="block text-slate-300 font-medium mb-1">Username *</label>
              <input
                type="text"
                required
                value={newUsername}
                onChange={(e) => setNewUsername(e.target.value)}
                placeholder="e.g. jdoe"
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-slate-300 font-medium mb-1">Email Address *</label>
              <input
                type="email"
                required
                value={newUserEmail}
                onChange={(e) => setNewUserEmail(e.target.value)}
                placeholder="jdoe@example.com"
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-slate-300 font-medium mb-1">Role *</label>
              <select
                value={newUserRole}
                onChange={(e) => setNewUserRole(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              >
                <option value="Employee">Employee (Submit Requests)</option>
                <option value="Manager">Manager (Approve Submissions)</option>
                <option value="Admin">Admin (Post to Ledger & Manage)</option>
              </select>
            </div>
            <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setProvisionModalOpen(false)}
                className="px-3.5 py-1.5 rounded bg-slate-800 text-slate-300"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="px-4 py-1.5 rounded bg-emerald-600 text-slate-950 font-bold hover:bg-emerald-500"
              >
                {isSubmitting ? 'Provisioning...' : 'Provision User'}
              </button>
            </div>
          </form>
        )}
      </Modal>

      {/* ── Assign Employee Modal */}
      <Modal
        isOpen={assignmentModalOpen}
        onClose={() => setAssignmentModalOpen(false)}
        title="Assign Employee to Manager"
      >
        <form onSubmit={handleCreateAssignment} className="space-y-4 text-xs">
          <div>
            <label className="block text-slate-300 font-medium mb-1">Select Manager *</label>
            <select
              value={assignManagerId}
              onChange={(e) => setAssignManagerId(e.target.value)}
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              required
            >
              <option value="">-- Choose Manager --</option>
              {usersList
                .filter((u) => u.role === 'Manager')
                .map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.username} ({m.email})
                  </option>
                ))}
            </select>
          </div>
          <div>
            <label className="block text-slate-300 font-medium mb-1">Select Employee *</label>
            <select
              value={assignEmployeeId}
              onChange={(e) => setAssignEmployeeId(e.target.value)}
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              required
            >
              <option value="">-- Choose Employee --</option>
              {usersList
                .filter((u) => u.role === 'Employee')
                .map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.username} ({e.email})
                  </option>
                ))}
            </select>
          </div>
          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setAssignmentModalOpen(false)}
              className="px-3.5 py-1.5 rounded bg-slate-800 text-slate-300"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-1.5 rounded bg-emerald-600 text-slate-950 font-bold hover:bg-emerald-500"
            >
              Save Assignment
            </button>
          </div>
        </form>
      </Modal>

      {/* ── Project Modal */}
      <Modal
        isOpen={projectModalOpen}
        onClose={() => setProjectModalOpen(false)}
        title="Add Project"
      >
        <form onSubmit={handleCreateProject} className="space-y-4 text-xs">
          <div>
            <label className="block text-slate-300 font-medium mb-1">Project Name *</label>
            <input
              type="text"
              required
              value={newProjectName}
              onChange={(e) => setNewProjectName(e.target.value)}
              placeholder="e.g. Project Phoenix"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
            />
          </div>
          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setProjectModalOpen(false)}
              className="px-3.5 py-1.5 rounded bg-slate-800 text-slate-300"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-1.5 rounded bg-emerald-600 text-slate-950 font-bold hover:bg-emerald-500"
            >
              Add Project
            </button>
          </div>
        </form>
      </Modal>

      {/* ── Ledger Modal */}
      <Modal
        isOpen={ledgerModalOpen}
        onClose={() => setLedgerModalOpen(false)}
        title="Add Ledger Head"
      >
        <form onSubmit={handleCreateLedger} className="space-y-4 text-xs">
          <div>
            <label className="block text-slate-300 font-medium mb-1">Ledger Head Name *</label>
            <input
              type="text"
              required
              value={newLedgerName}
              onChange={(e) => setNewLedgerName(e.target.value)}
              placeholder="e.g. Office Operations"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
            />
          </div>
          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setLedgerModalOpen(false)}
              className="px-3.5 py-1.5 rounded bg-slate-800 text-slate-300"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-1.5 rounded bg-emerald-600 text-slate-950 font-bold hover:bg-emerald-500"
            >
              Add Ledger Head
            </button>
          </div>
        </form>
      </Modal>

      {/* ── Configure Vault Balance Modal */}
      <Modal
        isOpen={balanceModalOpen}
        onClose={() => setBalanceModalOpen(false)}
        title="Configure Petty Cash Vault Balance"
      >
        <form onSubmit={handleUpdateVaultBalance} className="space-y-4 text-xs">
          <div>
            <label className="block text-slate-300 font-medium mb-1">
              Opening / Outstanding Balance (₹) *
            </label>
            <input
              type="number"
              step="0.01"
              min="0"
              required
              value={newOpeningBalance}
              onChange={(e) => setNewOpeningBalance(e.target.value)}
              placeholder="50000.00"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
            />
          </div>
          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setBalanceModalOpen(false)}
              className="px-3.5 py-1.5 rounded bg-slate-800 text-slate-300"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-1.5 rounded bg-emerald-600 text-slate-950 font-bold hover:bg-emerald-500"
            >
              Save Balance
            </button>
          </div>
        </form>
      </Modal>

      {/* ── Balance Adjustment Modal */}
      <Modal
        isOpen={adjustmentModalOpen}
        onClose={() => setAdjustmentModalOpen(false)}
        title="Record Vault Balance Adjustment"
      >
        <form onSubmit={handleCreateAdjustment} className="space-y-4 text-xs">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-300 font-medium mb-1">Direction *</label>
              <select
                value={adjDirection}
                onChange={(e) => setAdjDirection(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm"
              >
                <option value="INFLOW">INFLOW (+)</option>
                <option value="OUTFLOW">OUTFLOW (-)</option>
              </select>
            </div>
            <div>
              <label className="block text-slate-300 font-medium mb-1">Amount (₹) *</label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                required
                value={adjAmount}
                onChange={(e) => setAdjAmount(e.target.value)}
                placeholder="100.00"
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm"
              />
            </div>
          </div>
          <div>
            <label className="block text-slate-300 font-medium mb-1">Effective Date *</label>
            <input
              type="date"
              required
              value={adjDate}
              onChange={(e) => setAdjDate(e.target.value)}
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm"
            />
          </div>
          <div>
            <label className="block text-slate-300 font-medium mb-1">Audit Reason *</label>
            <input
              type="text"
              required
              value={adjReason}
              onChange={(e) => setAdjReason(e.target.value)}
              placeholder="e.g. Bank interest credit, cash count reconciliation variance"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm"
            />
          </div>
          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setAdjustmentModalOpen(false)}
              className="px-3.5 py-1.5 rounded bg-slate-800 text-slate-300"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-1.5 rounded bg-emerald-600 text-slate-950 font-bold hover:bg-emerald-500"
            >
              Record Adjustment
            </button>
          </div>
        </form>
      </Modal>

      {/* ── Financial Period Modal */}
      <Modal
        isOpen={periodModalOpen}
        onClose={() => setPeriodModalOpen(false)}
        title="Create Financial Accounting Period"
      >
        <form onSubmit={handleCreatePeriod} className="space-y-4 text-xs">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-300 font-medium mb-1">Period Start *</label>
              <input
                type="date"
                required
                value={periodStart}
                onChange={(e) => setPeriodStart(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm"
              />
            </div>
            <div>
              <label className="block text-slate-300 font-medium mb-1">Period End *</label>
              <input
                type="date"
                required
                value={periodEnd}
                onChange={(e) => setPeriodEnd(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm"
              />
            </div>
          </div>
          <p className="text-[11px] text-slate-400">
            A newly created period starts in OPEN status. You can lock/close it once the month is finalized to prevent any retroactive modifications.
          </p>
          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setPeriodModalOpen(false)}
              className="px-3.5 py-1.5 rounded bg-slate-800 text-slate-300"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-1.5 rounded bg-emerald-600 text-slate-950 font-bold hover:bg-emerald-500"
            >
              Create Period
            </button>
          </div>
        </form>
      </Modal>

      {/* ── Record Company Receipt Modal */}
      <Modal
        isOpen={receiptModalOpen}
        onClose={() => setReceiptModalOpen(false)}
        title="Record Direct Company Receipt"
      >
        <form onSubmit={handleCreateReceipt} className="space-y-4 text-xs">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-slate-300 font-medium mb-1">Receipt (Amount) ₹ *</label>
              <input
                type="number"
                step="0.01"
                min="0.01"
                required
                value={receiptAmount}
                onChange={(e) => setReceiptAmount(e.target.value)}
                placeholder="5000.00"
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-slate-300 font-medium mb-1">Date *</label>
              <input
                type="date"
                required
                value={receiptDate}
                onChange={(e) => setReceiptDate(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="block text-slate-300 font-medium mb-1">Description / Memo *</label>
            <input
              type="text"
              required
              value={receiptDesc}
              onChange={(e) => setReceiptDesc(e.target.value)}
              placeholder="e.g. Petty cash replenishment from main bank account"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-slate-300 font-medium mb-1">Category *</label>
            <input
              type="text"
              required
              list="receipt-category-options"
              value={receiptCategory}
              onChange={(e) => setReceiptCategory(e.target.value)}
              placeholder="e.g. Cash replenishment"
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm focus:ring-2 focus:ring-emerald-500 focus:outline-none"
            />
            <datalist id="receipt-category-options">
              <option value="Cash replenishment" />
              <option value="Direct Deposit" />
              <option value="Bank Withdrawal" />
              <option value="Company Capital Top-up" />
              <option value="Partner Contribution" />
            </datalist>
          </div>

          <div className="grid grid-cols-2 gap-3 pt-1">
            <div>
              <label className="block text-slate-300 font-medium mb-1">Default Ledger</label>
              <select
                value={receiptLedgerId}
                onChange={(e) => setReceiptLedgerId(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-xs focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              >
                {ledgers.map((l) => (
                  <option key={l.id} value={l.id}>{l.name}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-slate-300 font-medium mb-1">Default Project</label>
              <select
                value={receiptProjectId}
                onChange={(e) => setReceiptProjectId(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-xs focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              >
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="p-3 bg-slate-950 rounded border border-slate-800 text-[11px] text-slate-400">
            ℹ️ Direct company receipts post immediately into the petty cash balance and canonical ledger without default notes.
          </div>
          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setReceiptModalOpen(false)}
              className="px-3.5 py-1.5 rounded bg-slate-800 text-slate-300"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-4 py-1.5 rounded bg-emerald-600 text-slate-950 font-bold hover:bg-emerald-500"
            >
              Post Receipt
            </button>
          </div>
        </form>
      </Modal>

      {/* ── Post to Ledger Modal */}
      <Modal
        isOpen={postModalOpen}
        onClose={() => setPostModalOpen(false)}
        title="Post Voucher to Canonical Ledger"
      >
        {targetPostRequest && (
          <div className="space-y-4 text-xs">
            <div className="p-3 bg-slate-950 rounded border border-slate-800 space-y-1">
              <div className="flex justify-between">
                <span className="text-slate-400">Purpose:</span>
                <span className="font-semibold text-slate-100">{targetPostRequest.purpose}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Deduction Amount:</span>
                <span className="font-bold text-amber-400">₹{parseFloat(targetPostRequest.amount).toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Employee:</span>
                <span className="text-slate-200">{targetPostRequest.requester_username || targetPostRequest.requester_id}</span>
              </div>
            </div>

            <div>
              <label className="block text-slate-300 font-medium mb-1">
                Effective Posting Date *
              </label>
              <input
                type="date"
                required
                value={postEffectiveDate}
                onChange={(e) => setPostEffectiveDate(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm"
              />
            </div>

            <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={() => setPostModalOpen(false)}
                className="px-3.5 py-1.5 rounded bg-slate-800 text-slate-300"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={isSubmitting}
                onClick={handlePostRequest}
                className="px-4 py-1.5 rounded bg-emerald-600 text-slate-950 font-bold hover:bg-emerald-500 cursor-pointer"
              >
                {isSubmitting ? 'Posting...' : 'Confirm Atomic Post'}
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* ── Return for Correction Modal */}
      <Modal
        isOpen={returnModalOpen}
        onClose={() => setReturnModalOpen(false)}
        title="Return Request for Correction"
      >
        <div className="space-y-4 text-xs">
          <div>
            <label className="block text-slate-300 font-medium mb-1">
              Reason / Feedback for Employee *
            </label>
            <textarea
              rows={3}
              required
              value={returnReason}
              onChange={(e) => setReturnReason(e.target.value)}
              placeholder="State what needs revision or missing receipt vouchers..."
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm"
            />
          </div>
          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setReturnModalOpen(false)}
              className="px-3.5 py-1.5 rounded bg-slate-800 text-slate-300"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={isSubmitting}
              onClick={handleReturnForCorrection}
              className="px-4 py-1.5 rounded bg-amber-500 text-slate-950 font-bold hover:bg-amber-400"
            >
              Return for Correction
            </button>
          </div>
        </div>
      </Modal>

      {/* ── Reversal Confirmation Modal */}
      <Modal
        isOpen={reversalModalOpen}
        onClose={() => setReversalModalOpen(false)}
        title="Confirm Audited Transaction Reversal"
      >
        <div className="space-y-4 text-xs">
          <div className="p-3 bg-rose-950/40 border border-rose-800 rounded text-rose-200">
            ⚠️ This will reverse the transaction and atomically restore the vault balance. An audited two-way reversal entry will be recorded.
          </div>
          <div>
            <label className="block text-slate-300 font-medium mb-1">Reversal Reason *</label>
            <textarea
              rows={2}
              required
              value={reversalReason}
              onChange={(e) => setReversalReason(e.target.value)}
              placeholder="Justification for reversing this entry..."
              className="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded-md text-slate-100 text-sm"
            />
          </div>
          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <button
              type="button"
              onClick={() => setReversalModalOpen(false)}
              className="px-3.5 py-1.5 rounded bg-slate-800 text-slate-300"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={isSubmitting}
              onClick={handleExecuteReversal}
              className="px-4 py-1.5 rounded bg-rose-600 text-white font-bold hover:bg-rose-500"
            >
              Execute Reversal
            </button>
          </div>
        </div>
      </Modal>

      {/* ── Audit Event Detail Modal */}
      <Modal
        isOpen={detailModalOpen}
        onClose={() => setDetailModalOpen(false)}
        title="Audit Event State Inspection"
      >
        {detailItem && (
          <div className="space-y-4 text-xs font-mono">
            <div className="p-3 bg-slate-950 rounded-lg border border-slate-800 space-y-1.5">
              <div><span className="text-slate-400 font-sans">Action:</span> <span className="font-bold text-emerald-400">{detailItem.action}</span></div>
              <div><span className="text-slate-400 font-sans">Actor:</span> <span className="text-slate-200 font-semibold">{detailItem.actor_username || 'System'}</span> {detailItem.actor_user_id && <span className="text-slate-500">({detailItem.actor_user_id})</span>}</div>
              <div><span className="text-slate-400 font-sans">Entity:</span> <span className="text-slate-300">{detailItem.entity_type} {detailItem.entity_id ? `[${detailItem.entity_id}]` : ''}</span></div>
              <div><span className="text-slate-400 font-sans">Correlation ID:</span> <span className="text-slate-400">{detailItem.correlation_id}</span></div>
              <div><span className="text-slate-400 font-sans">Recorded At:</span> <span className="text-slate-400">{detailItem.created_at}</span></div>
            </div>

            {detailItem.before_json && (
              <div>
                <span className="font-sans font-semibold text-rose-300 block mb-1">Before State:</span>
                <pre className="p-3 bg-slate-950 rounded border border-rose-950/60 text-[11px] overflow-x-auto text-rose-200/90 max-h-48">
                  {JSON.stringify(JSON.parse(detailItem.before_json || '{}'), null, 2)}
                </pre>
              </div>
            )}

            {detailItem.after_json && (
              <div>
                <span className="font-sans font-semibold text-emerald-300 block mb-1">After State / Payload:</span>
                <pre className="p-3 bg-slate-950 rounded border border-emerald-950/60 text-[11px] overflow-x-auto text-emerald-200/90 max-h-48">
                  {JSON.stringify(JSON.parse(detailItem.after_json || '{}'), null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
