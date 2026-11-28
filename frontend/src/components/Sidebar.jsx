import React from 'react';
import {
  LayoutDashboard,
  Users,
  FolderTree,
  Receipt,
  FileCheck2,
  FileSpreadsheet,
  Activity,
  History,
  Archive,
  PlusCircle,
  FileClock,
  Send,
  UserCheck,
  UserCog,
  FileText,
  Bell,
  X,
} from 'lucide-react';

export default function Sidebar({
  role,
  currentView,
  onSelectView,
  isOpen,
  onClose,
  badges = {},
}) {
  const directorNav = [
    { id: 'admin_dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'admin_reports', label: 'Reports & ZIP Exports', icon: FileSpreadsheet },
    { id: 'admin_users', label: 'Users & Access', icon: Users },
    { id: 'admin_operations', label: 'Operations & Monitoring', icon: Activity },
    { id: 'admin_audit', label: 'Audit Trail', icon: History },
    { id: 'notifications', label: 'Notifications', icon: Bell, badge: badges.unreadNotifications },
    { id: 'profile', label: 'Profile & Security', icon: UserCog },
  ];

  const financeNav = [
    { id: 'admin_dashboard', label: 'Dashboard & Analytics', icon: LayoutDashboard },
    {
      id: 'admin_postings',
      label: 'Requests for Posting',
      icon: FileCheck2,
      badge: badges.pendingPostings,
    },
    { id: 'finance_direct_expense', label: 'Direct Company Expense', icon: PlusCircle },
    { id: 'admin_receipts', label: 'Company Receipts', icon: Receipt },
    { id: 'admin_reports', label: 'Reports & ZIP Exports', icon: FileSpreadsheet },
    {
      id: 'admin_catalog',
      label: 'Projects, Ledgers & Vault',
      icon: FolderTree,
    },
    { id: 'finance_assignments', label: 'Hierarchy Assignments', icon: Users },
    { id: 'notifications', label: 'Notifications', icon: Bell, badge: badges.unreadNotifications },
    { id: 'profile', label: 'Profile & Security', icon: UserCog },
    { id: 'spreadsheet_tool', label: 'Spreadsheet Utility', icon: FileText },
  ];

  const managerNav = [
    { id: 'manager_dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'manager_new_request', label: 'New Request', icon: PlusCircle },
    { id: 'manager_my_requests', label: 'My Requests', icon: Send },
    {
      id: 'manager_approvals',
      label: 'Approval Queue',
      icon: FileCheck2,
      badge: badges.pendingApprovals,
    },
    { id: 'manager_reports', label: 'Reports & ZIP Exports', icon: FileSpreadsheet },
    {
      id: 'manager_assignments',
      label: 'Assignments',
      icon: Users,
      badge: badges.pendingAssignments,
    },
    { id: 'manager_history', label: 'Decision History', icon: History },
    { id: 'notifications', label: 'Notifications', icon: Bell, badge: badges.unreadNotifications },
    { id: 'profile', label: 'Profile & Security', icon: UserCheck },
    { id: 'spreadsheet_tool', label: 'Spreadsheet Utility', icon: FileText },
  ];

  const employeeNav = [
    { id: 'employee_dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'employee_new_request', label: 'New Request', icon: PlusCircle },
    {
      id: 'employee_submitted',
      label: 'Submitted Requests',
      icon: Send,
      badge: badges.submittedCount,
    },
    {
      id: 'employee_drafts',
      label: 'Drafts & Returned',
      icon: FileClock,
      badge: badges.draftsCount,
    },
    { id: 'employee_history', label: 'Request History', icon: History },
    { id: 'employee_managers', label: 'Assigned Managers', icon: UserCheck },
    { id: 'notifications', label: 'Notifications', icon: Bell, badge: badges.unreadNotifications },
    { id: 'profile', label: 'Profile & Security', icon: UserCog },
  ];

  const items =
    role === 'Director' || role === 'Admin'
      ? directorNav
      : role === 'Finance'
      ? financeNav
      : role === 'Manager'
      ? managerNav
      : employeeNav;

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-slate-950/70 backdrop-blur-sm z-40 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Sidebar container */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 w-64 bg-slate-900 border-r border-slate-800 transition-transform duration-200 ease-in-out lg:translate-x-0 lg:static lg:z-auto flex flex-col ${
          isOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
        aria-label="Sidebar Navigation"
      >
        <div className="flex items-center justify-between p-4 border-b border-slate-800 lg:hidden">
          <span className="font-semibold text-sm text-slate-200">Menu</span>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-white rounded-md hover:bg-slate-800 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
            aria-label="Close navigation sidebar"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Navigation links */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {items.map((item) => {
            const Icon = item.icon;
            const active = currentView === item.id;

            return (
              <button
                key={item.id}
                type="button"
                onClick={() => {
                  onSelectView(item.id);
                  if (onClose) onClose();
                }}
                className={`w-full flex items-center justify-between px-3 py-2.5 rounded-lg text-sm font-medium transition-colors focus:ring-2 focus:ring-emerald-500 focus:outline-none text-left ${
                  active
                    ? 'bg-slate-800 text-emerald-400 font-semibold border-l-4 border-emerald-500 shadow-sm'
                    : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
                }`}
              >
                <div className="flex items-center gap-3 min-w-0">
                  <Icon
                    className={`w-4 h-4 shrink-0 ${
                      active ? 'text-emerald-400' : 'text-slate-400'
                    }`}
                  />
                  <span className="truncate">{item.label}</span>
                </div>
                {item.badge > 0 && (
                  <span
                    className={`shrink-0 ml-2 px-2 py-0.5 text-xs font-bold rounded-full ${
                      active
                        ? 'bg-emerald-500 text-slate-950'
                        : 'bg-slate-800 text-emerald-400 border border-emerald-700/50'
                    }`}
                  >
                    {item.badge}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        {/* Role footer indicator */}
        <div className="p-3 border-t border-slate-800/80 bg-slate-950/40 text-[11px] text-slate-400 flex items-center justify-between">
          <span>Active Role</span>
          <span className="font-semibold text-slate-200">{role}</span>
        </div>
      </aside>
    </>
  );
}
