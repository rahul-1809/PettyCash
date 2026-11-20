import React, { useState, useEffect, useRef } from 'react';
import {
  Bell,
  User,
  LogOut,
  Menu,
  Shield,
  Briefcase,
  UserCheck,
  Check,
  CheckCircle2,
  ExternalLink,
} from 'lucide-react';
import { api } from '../api';
import Logo from './Logo';

export default function Navbar({
  user,
  unreadCount: propUnreadCount,
  onLogout,
  onOpenProfile,
  onOpenNotifications,
  onNotificationChanged,
  onToggleSidebar,
  sidebarOpen,
}) {
  const [notifications, setNotifications] = useState([]);
  const [showNotifications, setShowNotifications] = useState(false);
  const [loadingNotifications, setLoadingNotifications] = useState(false);
  const notificationRef = useRef(null);

  const fetchNotifications = async () => {
    try {
      setLoadingNotifications(true);
      const data = await api.listNotifications(false, 15);
      setNotifications(Array.isArray(data) ? data : []);
    } catch (e) {
      console.error('Failed to load notifications', e);
    } finally {
      setLoadingNotifications(false);
    }
  };

  useEffect(() => {
    fetchNotifications();
  }, [propUnreadCount]);

  // Re-fetch when popover opens
  useEffect(() => {
    if (showNotifications) {
      fetchNotifications();
    }
  }, [showNotifications]);

  useEffect(() => {
    function handleClickOutside(e) {
      if (
        notificationRef.current &&
        !notificationRef.current.contains(e.target)
      ) {
        setShowNotifications(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleMarkRead = async (id, e) => {
    e.stopPropagation();
    try {
      await api.markNotificationRead(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n))
      );
      if (onNotificationChanged) onNotificationChanged();
    } catch (err) {
      console.error(err);
    }
  };

  const localUnreadCount = notifications.filter((n) => !n.read_at).length;
  const unreadCount = propUnreadCount !== undefined ? propUnreadCount : localUnreadCount;

  const roleBadge = () => {
    if (user?.role === 'Admin') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-950/80 text-amber-300 border border-amber-800/80">
          <Shield className="w-3 h-3" /> Admin
        </span>
      );
    }
    if (user?.role === 'Manager') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-purple-950/80 text-purple-300 border border-purple-800/80">
          <Briefcase className="w-3 h-3" /> Manager
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-950/80 text-emerald-300 border border-emerald-800/80">
        <UserCheck className="w-3 h-3" /> Employee
      </span>
    );
  };

  return (
    <header className="sticky top-0 z-40 bg-slate-900 border-b border-slate-800 shadow-sm text-slate-100">
      <div className="flex items-center justify-between px-4 sm:px-6 h-16">
        {/* Left: Mobile hamburger & Brand */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onToggleSidebar}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-md lg:hidden focus:ring-2 focus:ring-emerald-500 focus:outline-none"
            aria-label="Toggle navigation menu"
          >
            <Menu className="w-5 h-5" />
          </button>

          <Logo size={32} />
        </div>

        {/* Right: Notifications, User Chip & Profile */}
        <div className="flex items-center gap-3 sm:gap-4">
          {/* Notifications Popover */}
          <div className="relative" ref={notificationRef}>
            <button
              type="button"
              onClick={() => setShowNotifications((prev) => !prev)}
              className="relative p-2 text-slate-300 hover:text-white hover:bg-slate-800 rounded-md transition-colors focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              aria-label={`Notifications ${unreadCount > 0 ? `(${unreadCount} unread)` : ''}`}
            >
              <Bell className="w-5 h-5" />
              {unreadCount > 0 && (
                <span className="absolute top-1 right-1 w-4 h-4 bg-emerald-500 text-slate-950 text-[10px] font-extrabold rounded-full flex items-center justify-center shadow">
                  {unreadCount > 9 ? '9+' : unreadCount}
                </span>
              )}
            </button>

            {showNotifications && (
              <div className="absolute right-0 mt-2 w-80 sm:w-96 bg-slate-900 border border-slate-700 rounded-lg shadow-2xl py-2 z-50 text-slate-100">
                <div className="flex items-center justify-between px-4 py-2 border-b border-slate-800">
                  <div className="font-semibold text-sm text-slate-200">Notifications</div>
                  <span className="text-xs text-slate-400">
                    {unreadCount} unread
                  </span>
                </div>

                <div className="max-h-80 overflow-y-auto divide-y divide-slate-800/60">
                  {notifications.length === 0 ? (
                    <div className="p-6 text-center text-sm text-slate-400">
                      No notifications yet
                    </div>
                  ) : (
                    notifications.map((n) => (
                      <div
                        key={n.id}
                        className={`p-3 text-xs flex items-start justify-between gap-2 hover:bg-slate-800/60 transition-colors ${
                          !n.read_at ? 'bg-slate-800/40' : ''
                        }`}
                      >
                        <div className="flex-1 pr-2">
                          <div className="font-medium text-slate-200 mb-0.5">
                            {n.message}
                          </div>
                          <div className="text-[10px] text-slate-400">
                            {new Date(n.created_at).toLocaleString()}
                          </div>
                        </div>
                        {!n.read_at && (
                          <button
                            type="button"
                            onClick={(e) => handleMarkRead(n.id, e)}
                            className="shrink-0 p-1 text-slate-400 hover:text-emerald-400 rounded hover:bg-slate-700 transition-colors"
                            title="Mark as read"
                          >
                            <Check className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    ))
                  )}
                </div>

                <div className="p-2 border-t border-slate-800 bg-slate-950/60 flex items-center justify-between text-xs">
                  <button
                    type="button"
                    onClick={() => {
                      setShowNotifications(false);
                      if (onOpenNotifications) onOpenNotifications();
                    }}
                    className="w-full text-center py-1 text-emerald-400 hover:text-emerald-300 font-semibold cursor-pointer"
                  >
                    View all notifications & history →
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* User profile & Role */}
          <div className="flex items-center gap-2 pl-2 border-l border-slate-800">
            <button
              type="button"
              onClick={onOpenProfile}
              className="flex items-center gap-2.5 p-1.5 rounded-md hover:bg-slate-800 transition-colors text-left focus:ring-2 focus:ring-emerald-500 focus:outline-none"
              title="Account settings"
            >
              <div className="w-7 h-7 rounded-full bg-slate-700 text-slate-200 font-semibold text-xs flex items-center justify-center border border-slate-600">
                {user?.username ? user.username.substring(0, 2).toUpperCase() : 'U'}
              </div>
              <div className="hidden md:block">
                <div className="text-xs font-semibold text-slate-200 truncate max-w-[120px]">
                  {user?.username || 'User'}
                </div>
                <div className="text-[10px] text-slate-400 truncate max-w-[120px]">
                  {user?.email}
                </div>
              </div>
            </button>
            <div className="hidden sm:block">{roleBadge()}</div>
          </div>

          {/* Logout */}
          <button
            type="button"
            onClick={onLogout}
            className="p-2 text-slate-400 hover:text-rose-400 hover:bg-slate-800 rounded-md transition-colors focus:ring-2 focus:ring-rose-500 focus:outline-none"
            title="Log out"
            aria-label="Log out"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>
  );
}
