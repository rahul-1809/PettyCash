import React, { useState, useEffect } from 'react';
import { User, Mail, Shield, Bell, Check, Save } from 'lucide-react';
import { api } from '../api';

export default function ProfileView({ user, addToast }) {
  const [inAppEnabled, setInAppEnabled] = useState(true);
  const [emailEnabled, setEmailEnabled] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    async function loadPrefs() {
      try {
        setLoading(true);
        const prefs = await api.getNotificationPreferences();
        if (prefs) {
          setInAppEnabled(Boolean(prefs.in_app_enabled));
          setEmailEnabled(Boolean(prefs.email_enabled));
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    loadPrefs();
  }, []);

  const handleSave = async (e) => {
    e.preventDefault();
    try {
      setSaving(true);
      await api.updateNotificationPreferences(inAppEnabled, emailEnabled);
      addToast({
        type: 'success',
        title: 'Preferences Updated',
        message: 'Notification settings saved successfully.',
      });
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Update Failed',
        message: err.message,
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-xl font-bold text-slate-100">User Profile & Settings</h1>
        <p className="text-xs text-slate-400 mt-1">
          Manage your account profile, role authorization, and notification delivery options.
        </p>
      </div>

      {/* Profile Overview Card */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-6 shadow-sm space-y-4">
        <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider text-xs flex items-center gap-2">
          <User className="w-4 h-4 text-emerald-400" /> Account Identity
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
          <div className="p-3 bg-slate-950 rounded-md border border-slate-800">
            <span className="text-[11px] text-slate-400 block mb-1">Username</span>
            <span className="text-sm font-semibold text-slate-100">{user?.username}</span>
          </div>

          <div className="p-3 bg-slate-950 rounded-md border border-slate-800">
            <span className="text-[11px] text-slate-400 block mb-1">Email Address</span>
            <span className="text-sm font-semibold text-slate-100">{user?.email}</span>
          </div>

          <div className="p-3 bg-slate-950 rounded-md border border-slate-800">
            <span className="text-[11px] text-slate-400 block mb-1">System Role</span>
            <span className="text-sm font-semibold text-emerald-400">{user?.role}</span>
          </div>

          <div className="p-3 bg-slate-950 rounded-md border border-slate-800">
            <span className="text-[11px] text-slate-400 block mb-1">Account Status</span>
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-400">
              <span className="w-2 h-2 rounded-full bg-emerald-500" /> Active
            </span>
          </div>
        </div>
      </div>

      {/* Notification Preferences Card */}
      <div className="bg-slate-900 border border-slate-800 rounded-lg p-6 shadow-sm space-y-4">
        <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider text-xs flex items-center gap-2">
          <Bell className="w-4 h-4 text-emerald-400" /> Notification Delivery Preferences
        </h2>

        <form onSubmit={handleSave} className="space-y-4 pt-2">
          <div className="flex items-center justify-between p-3.5 bg-slate-950 rounded-md border border-slate-800">
            <div>
              <div className="text-sm font-medium text-slate-200">In-App Notifications</div>
              <div className="text-xs text-slate-400">
                Receive notifications inside the top navigation bar for workflow state transitions.
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={inAppEnabled}
                onChange={(e) => setInAppEnabled(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
            </label>
          </div>

          <div className="flex items-center justify-between p-3.5 bg-slate-950 rounded-md border border-slate-800">
            <div>
              <div className="text-sm font-medium text-slate-200">Email Notifications</div>
              <div className="text-xs text-slate-400">
                Dispatch transactional email alerts for approvals, postings, and returned vouchers.
              </div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input
                type="checkbox"
                checked={emailEnabled}
                onChange={(e) => setEmailEnabled(e.target.checked)}
                className="sr-only peer"
              />
              <div className="w-11 h-6 bg-slate-800 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-emerald-600"></div>
            </label>
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={saving || loading}
              className="flex items-center gap-2 px-4 py-2 rounded-md bg-emerald-600 hover:bg-emerald-500 text-slate-950 text-xs font-semibold focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-50 transition-colors cursor-pointer"
            >
              <Save className="w-4 h-4" />
              {saving ? 'Saving Preferences...' : 'Save Preferences'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
