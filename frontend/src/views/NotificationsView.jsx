import React, { useState, useEffect, useCallback } from 'react';
import {
  Bell,
  CheckCheck,
  Check,
  RotateCcw,
  RefreshCw,
  SlidersHorizontal,
  Mail,
  ShieldAlert,
  Info,
} from 'lucide-react';
import { api } from '../api';

export default function NotificationsView({ user, addToast, onNavigate, onNotificationChanged }) {
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all'); // 'all' | 'unread' | 'read'
  const [processingId, setProcessingId] = useState(null);

  const loadNotifications = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.listNotifications(false);
      setNotifications(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error(err);
      addToast({
        type: 'error',
        title: 'Error',
        message: 'Could not load notifications.',
      });
    } finally {
      setLoading(false);
    }
  }, [addToast]);

  useEffect(() => {
    loadNotifications();
  }, [loadNotifications]);

  const handleMarkRead = async (id) => {
    try {
      setProcessingId(id);
      await api.markNotificationRead(id);
      setNotifications((prev) =>
        prev.map((n) =>
          n.id === id ? { ...n, read_at: new Date().toISOString() } : n
        )
      );
      if (onNotificationChanged) onNotificationChanged();
      addToast({
        type: 'success',
        title: 'Notification Read',
        message: 'Marked as read.',
      });
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Error',
        message: err.message || 'Could not update notification status.',
      });
    } finally {
      setProcessingId(null);
    }
  };

  const handleMarkUnread = async (id) => {
    try {
      setProcessingId(id);
      await api.markNotificationUnread(id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, read_at: null } : n))
      );
      if (onNotificationChanged) onNotificationChanged();
      addToast({
        type: 'info',
        title: 'Notification Unread',
        message: 'Marked as unread.',
      });
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Error',
        message: err.message || 'Could not update notification status.',
      });
    } finally {
      setProcessingId(null);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      setLoading(true);
      await api.markAllNotificationsRead();
      setNotifications((prev) =>
        prev.map((n) => ({
          ...n,
          read_at: n.read_at || new Date().toISOString(),
        }))
      );
      if (onNotificationChanged) onNotificationChanged();
      addToast({
        type: 'success',
        title: 'All Read',
        message: 'All notifications marked as read.',
      });
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Error',
        message: err.message || 'Could not mark all notifications as read.',
      });
    } finally {
      setLoading(false);
    }
  };

  const filteredNotifications = notifications.filter((n) => {
    if (filter === 'unread') return !n.read_at;
    if (filter === 'read') return !!n.read_at;
    return true;
  });

  const unreadCount = notifications.filter((n) => !n.read_at).length;
  const readCount = notifications.filter((n) => !!n.read_at).length;

  const getEventBadge = (eventType, isRead) => {
    const label = (eventType || 'ALERT')
      .replace(/^PETTY_CASH_/, '')
      .replace(/_/g, ' ');

    // When read, all event badges share the exact same clean, muted badge styling
    if (isRead) {
      return (
        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-400 border border-slate-700/80">
          {label}
        </span>
      );
    }

    // For unread items:
    if (eventType?.includes('REJECTED')) {
      return (
        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-950 text-rose-300 border border-rose-800">
          {label}
        </span>
      );
    }

    return (
      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950 text-emerald-300 border border-emerald-800">
        {label}
      </span>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <h1 className="text-lg font-bold text-slate-100 flex items-center gap-2">
            <Bell className="w-5 h-5 text-emerald-400" />
            Notifications & System Alerts
          </h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Real-time notifications for expense submissions, approval decisions, assignments, and postings.
          </p>
        </div>

        <div className="flex items-center gap-2">
          {unreadCount > 0 && (
            <button
              type="button"
              onClick={handleMarkAllRead}
              disabled={loading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold border border-slate-700 cursor-pointer disabled:opacity-50"
            >
              <CheckCheck className="w-4 h-4 text-emerald-400" /> Mark All as Read
            </button>
          )}

          <button
            type="button"
            onClick={loadNotifications}
            disabled={loading}
            className="p-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 cursor-pointer"
            title="Refresh Notifications"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>

          {onNavigate && (
            <button
              type="button"
              onClick={() => onNavigate('profile')}
              className="flex items-center gap-1 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-medium border border-slate-700 cursor-pointer"
              title="Notification Channel Preferences"
            >
              <SlidersHorizontal className="w-3.5 h-3.5 text-slate-400" /> Channels
            </button>
          )}
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-800/80 pb-2 overflow-x-auto">
        <button
          type="button"
          onClick={() => setFilter('all')}
          className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
            filter === 'all'
              ? 'bg-emerald-600 text-slate-950 font-bold'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          }`}
        >
          All ({notifications.length})
        </button>
        <button
          type="button"
          onClick={() => setFilter('unread')}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
            filter === 'unread'
              ? 'bg-emerald-600 text-slate-950 font-bold'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          }`}
        >
          Unread
          {unreadCount > 0 && (
            <span
              className={`px-1.5 py-0.2 rounded-full text-[10px] font-bold ${
                filter === 'unread'
                  ? 'bg-slate-950 text-emerald-400'
                  : 'bg-emerald-500 text-slate-950'
              }`}
            >
              {unreadCount}
            </span>
          )}
        </button>
        <button
          type="button"
          onClick={() => setFilter('read')}
          className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors cursor-pointer ${
            filter === 'read'
              ? 'bg-emerald-600 text-slate-950 font-bold'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
          }`}
        >
          Read ({readCount})
        </button>
      </div>

      {/* Notification List */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden shadow-sm">
        {loading && notifications.length === 0 ? (
          <div className="p-8 text-center text-xs text-slate-400">
            <RefreshCw className="w-5 h-5 mx-auto mb-2 animate-spin text-emerald-400" />
            Loading your notification feed...
          </div>
        ) : filteredNotifications.length === 0 ? (
          <div className="p-12 text-center text-slate-400">
            <Info className="w-8 h-8 mx-auto mb-2 text-slate-600" />
            <div className="text-sm font-semibold text-slate-300">No notifications found</div>
            <p className="text-xs text-slate-500 mt-1">
              {filter === 'unread'
                ? "You're all caught up! No unread notifications."
                : filter === 'read'
                ? 'No archived notifications yet.'
                : 'No notification records present for your account.'}
            </p>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/80">
            {filteredNotifications.map((n) => {
              const isUnread = !n.read_at;
              return (
                <div
                  key={n.id}
                  className={`p-4 flex flex-col sm:flex-row sm:items-start justify-between gap-3 transition-colors ${
                    isUnread ? 'bg-slate-800/30 hover:bg-slate-800/50' : 'hover:bg-slate-800/20'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-1 shrink-0">
                      {isUnread ? (
                        <div
                          className="w-2.5 h-2.5 rounded-full bg-emerald-400 ring-4 ring-emerald-500/20"
                          title="Unread notification"
                        />
                      ) : (
                        <div
                          className="w-2.5 h-2.5 rounded-full bg-slate-600"
                          title="Read notification"
                        />
                      )}
                    </div>

                    <div className="space-y-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-semibold text-sm text-slate-100">
                          {n.title || 'System Notification'}
                        </span>
                        {getEventBadge(n.event_type, !isUnread)}
                      </div>

                      <p className="text-xs text-slate-300 leading-relaxed max-w-2xl">
                        {n.message}
                      </p>

                      <div className="flex items-center gap-3 text-[11px] text-slate-400 pt-1 font-mono">
                        <span>{new Date(n.created_at).toLocaleString()}</span>
                        {n.read_at && (
                          <span className="text-slate-500">
                            • Read {new Date(n.read_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Actions: Mark read / unread */}
                  <div className="flex items-center gap-2 self-end sm:self-center shrink-0">
                    {isUnread ? (
                      <button
                        type="button"
                        disabled={processingId === n.id}
                        onClick={() => handleMarkRead(n.id)}
                        className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-emerald-400 hover:text-emerald-300 text-xs font-semibold border border-slate-700 cursor-pointer disabled:opacity-50"
                        title="Mark as read"
                      >
                        <Check className="w-3.5 h-3.5" />
                        <span>Mark read</span>
                      </button>
                    ) : (
                      <button
                        type="button"
                        disabled={processingId === n.id}
                        onClick={() => handleMarkUnread(n.id)}
                        className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800/80 hover:bg-slate-700 text-slate-400 hover:text-slate-200 text-xs font-medium border border-slate-700/80 cursor-pointer disabled:opacity-50"
                        title="Mark as unread"
                      >
                        <RotateCcw className="w-3.5 h-3.5" />
                        <span>Mark unread</span>
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
