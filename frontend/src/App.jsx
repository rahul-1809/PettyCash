import React, { useState, useEffect, useCallback } from 'react';
import { api } from './api';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';
import Toast from './components/Toast';
import LoginView from './views/LoginView';
import ProfileView from './views/ProfileView';
import NotificationsView from './views/NotificationsView';
import AdminViews from './views/AdminViews';
import ManagerViews from './views/ManagerViews';
import EmployeeViews from './views/EmployeeViews';
import SpreadsheetTool from './components/SpreadsheetTool';
import { LogoIcon } from './components/Logo';

export default function App() {
  const [user, setUser] = useState(null);
  const [authChecking, setAuthChecking] = useState(true);
  const [currentView, setCurrentView] = useState('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [toasts, setToasts] = useState([]);
  const [badges, setBadges] = useState({
    pendingApprovals: 0,
    pendingAssignments: 0,
    pendingPostings: 0,
    draftsCount: 0,
    submittedCount: 0,
    unreadNotifications: 0,
  });

  const addToast = useCallback(({ title, message, type = 'info' }) => {
    const id = Date.now() + Math.random().toString(36).substring(2, 7);
    setToasts((prev) => [...prev, { id, title, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4500);
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Determine initial view based on role
  const getInitialViewForRole = (role) => {
    if (role === 'Admin') return 'admin_dashboard';
    if (role === 'Manager') return 'manager_dashboard';
    return 'employee_dashboard';
  };

  // Listen for unauthorized 401 events across all API calls
  useEffect(() => {
    const handleUnauthorized = () => {
      api.setAuthToken(null);
      api.setCurrentUser(null);
      setUser(null);
      setCurrentView('login');
      addToast({
        type: 'warning',
        title: 'Session Expired',
        message: 'Your session has expired or was reset. Please log in again.',
      });
    };
    window.addEventListener('pettycash:unauthorized', handleUnauthorized);
    return () => window.removeEventListener('pettycash:unauthorized', handleUnauthorized);
  }, [addToast]);

  // Check existing session on boot
  useEffect(() => {
    async function verifySession() {
      const token = api.getAuthToken();
      if (!token) {
        setAuthChecking(false);
        return;
      }
      try {
        const me = await api.getMe();
        if (me && me.id) {
          setUser(me);
          setCurrentView(getInitialViewForRole(me.role));
        } else {
          api.setAuthToken(null);
          setUser(null);
        }
      } catch (e) {
        api.setAuthToken(null);
        setUser(null);
      } finally {
        setAuthChecking(false);
      }
    }
    verifySession();
  }, []);

  // Poll badges for sidebar notifications
  const updateBadges = useCallback(async () => {
    if (!user) return;
    try {
      // Common: unread notifications count
      const unreadNotifs = await api.listNotifications(true).catch(() => []);
      const unreadCount = Array.isArray(unreadNotifs) ? unreadNotifs.length : 0;

      if (user.role === 'Admin') {
        const reqs = await api.listRequests().catch(() => []);
        const approvedCount = reqs.filter(
          (r) => r.status === 'SUPPORTING_UPLOADED' || (r.status === 'APPROVED' && r.supporting_files?.length > 0)
        ).length;
        setBadges((prev) => ({
          ...prev,
          pendingPostings: currentView === 'admin_postings' ? 0 : approvedCount,
          unreadNotifications: currentView === 'notifications' ? 0 : unreadCount,
        }));
      } else if (user.role === 'Manager') {
        const [reqs, assigns] = await Promise.all([
          api.listRequests().catch(() => []),
          api.listAssignments().catch(() => []),
        ]);
        const pendingQueue = reqs.filter(
          (r) => r.status === 'SUBMITTED' && r.approving_manager_id === user.id
        ).length;
        const pendingAssign = assigns.filter(
          (a) => a.manager_id === user.id && a.status === 'PENDING'
        ).length;
        setBadges((prev) => ({
          ...prev,
          pendingApprovals: currentView === 'manager_approvals' ? 0 : pendingQueue,
          pendingAssignments: currentView === 'manager_assignments' ? 0 : pendingAssign,
          unreadNotifications: currentView === 'notifications' ? 0 : unreadCount,
        }));
      } else if (user.role === 'Employee') {
        const reqs = await api.listRequests().catch(() => []);
        const draftsCount = reqs.filter(
          (r) => r.requester_id === user.id && (r.status === 'DRAFT' || r.status === 'RETURNED_FOR_CORRECTION')
        ).length;
        // Urgent badge on submitted is for manager-approved requests awaiting employee voucher upload
        const awaitingVouchers = reqs.filter(
          (r) => r.requester_id === user.id && r.status === 'APPROVED'
        ).length;
        setBadges((prev) => ({
          ...prev,
          draftsCount: currentView === 'employee_drafts' ? 0 : draftsCount,
          submittedCount: currentView === 'employee_submitted' ? 0 : awaitingVouchers,
          unreadNotifications: currentView === 'notifications' ? 0 : unreadCount,
        }));
      }
    } catch (_) {}
  }, [user, currentView]);

  useEffect(() => {
    if (!user) return;
    updateBadges();

    const handleVisibility = () => {
      if (!document.hidden) {
        updateBadges();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);

    const interval = setInterval(() => {
      if (!document.hidden) {
        updateBadges();
      }
    }, 45000);

    return () => {
      clearInterval(interval);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [user, updateBadges]);

  const handleLoginSuccess = (authenticatedUser) => {
    setUser(authenticatedUser);
    setCurrentView(getInitialViewForRole(authenticatedUser.role));
  };

  const handleLogout = async () => {
    await api.logout();
    setUser(null);
    setCurrentView('login');
    addToast({
      type: 'info',
      title: 'Logged Out',
      message: 'You have been safely signed out.',
    });
  };

  if (authChecking) {
    return (
      <div className="min-h-screen bg-slate-950 flex flex-col items-center justify-center text-slate-100">
        <LogoIcon size={48} className="animate-pulse drop-shadow-[0_4px_16px_rgba(16,185,129,0.35)]" />
        <div className="mt-4 text-xs font-semibold text-slate-300 tracking-wide">
          Loading PettyCash workspace...
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <>
        <LoginView onLoginSuccess={handleLoginSuccess} addToast={addToast} />
        <Toast toasts={toasts} onDismiss={dismissToast} />
      </>
    );
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      {/* Top Header Navbar */}
      <Navbar
        user={user}
        unreadCount={badges.unreadNotifications}
        onLogout={handleLogout}
        onOpenProfile={() => setCurrentView('profile')}
        onOpenNotifications={() => setCurrentView('notifications')}
        onNotificationChanged={updateBadges}
        onToggleSidebar={() => setSidebarOpen((prev) => !prev)}
        sidebarOpen={sidebarOpen}
      />

      <div className="flex-1 flex overflow-hidden">
        {/* Role-Based Sidebar Navigation */}
        <Sidebar
          role={user.role}
          currentView={currentView}
          onSelectView={(viewId) => {
            // Immediately clear badge for the clicked section
            if (viewId === 'employee_submitted') setBadges((b) => ({ ...b, submittedCount: 0 }));
            if (viewId === 'employee_drafts') setBadges((b) => ({ ...b, draftsCount: 0 }));
            if (viewId === 'manager_approvals') setBadges((b) => ({ ...b, pendingApprovals: 0 }));
            if (viewId === 'manager_assignments') setBadges((b) => ({ ...b, pendingAssignments: 0 }));
            if (viewId === 'admin_postings') setBadges((b) => ({ ...b, pendingPostings: 0 }));
            if (viewId === 'notifications') setBadges((b) => ({ ...b, unreadNotifications: 0 }));

            // Guard: Restrict spreadsheet utility to Admin & Manager only
            if (viewId === 'spreadsheet_tool' && user.role === 'Employee') {
              setCurrentView('employee_dashboard');
            } else {
              setCurrentView(viewId);
            }
            setSidebarOpen(false);
          }}
          isOpen={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          badges={badges}
        />

        {/* Main Workspace Area */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 lg:p-8 bg-slate-950">
          <div className="max-w-7xl mx-auto">
            {/* Shared Profile & Settings View */}
            {currentView === 'profile' && (
              <ProfileView user={user} addToast={addToast} />
            )}

            {/* Shared Full Notifications & Alerts View */}
            {currentView === 'notifications' && (
              <NotificationsView
                user={user}
                addToast={addToast}
                onNavigate={setCurrentView}
                onNotificationChanged={updateBadges}
              />
            )}

            {/* Controlled Spreadsheet Migration / Import Utility (Admin & Manager Only) */}
            {currentView === 'spreadsheet_tool' &&
              (user.role === 'Admin' || user.role === 'Manager') && (
                <div className="space-y-4">
                  <div className="p-4 bg-slate-900 border border-slate-800 rounded-lg flex items-center justify-between">
                    <div>
                      <h2 className="text-sm font-semibold text-slate-200">
                        Spreadsheet Migration & Analysis Tool
                      </h2>
                      <p className="text-xs text-slate-400">
                        Controlled utility for parsing raw spreadsheets, interactive recalculation, and legacy exports.
                      </p>
                    </div>
                    <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-amber-950 text-amber-300 border border-amber-800">
                      Restricted Utility
                    </span>
                  </div>
                  <div className="bg-slate-900 border border-slate-800 rounded-lg p-2 overflow-hidden">
                    <SpreadsheetTool />
                  </div>
                </div>
              )}

            {/* Admin Views */}
            {user.role === 'Admin' &&
              currentView !== 'profile' &&
              currentView !== 'notifications' &&
              currentView !== 'spreadsheet_tool' && (
                <AdminViews
                  currentView={currentView}
                  onNavigate={setCurrentView}
                  addToast={addToast}
                  user={user}
                />
              )}

            {/* Manager Views */}
            {user.role === 'Manager' &&
              currentView !== 'profile' &&
              currentView !== 'notifications' &&
              currentView !== 'spreadsheet_tool' && (
                <ManagerViews
                  currentView={currentView}
                  onNavigate={setCurrentView}
                  addToast={addToast}
                  user={user}
                />
              )}

            {/* Employee Views */}
            {user.role === 'Employee' &&
              currentView !== 'profile' &&
              currentView !== 'notifications' &&
              currentView !== 'spreadsheet_tool' && (
                <EmployeeViews
                  currentView={currentView}
                  onNavigate={setCurrentView}
                  addToast={addToast}
                  user={user}
                />
              )}
          </div>
        </main>
      </div>

      {/* Global Toast Notifications */}
      <Toast toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}
