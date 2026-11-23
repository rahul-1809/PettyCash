import React, { useState, useEffect } from 'react';
import { User, Mail, Shield, Bell, Check, Save, Send, Loader2 } from 'lucide-react';
import { api } from '../api';

export default function ProfileView({ user, addToast }) {
  const getCachedPref = (key, fallback) => {
    try {
      const uId = user?.id || 'anon';
      const val = localStorage.getItem(`pettycash_pref_${uId}_${key}`);
      return val !== null ? JSON.parse(val) : fallback;
    } catch {
      return fallback;
    }
  };

  const [inAppEnabled, setInAppEnabled] = useState(() => getCachedPref('in_app', true));
  const [emailEnabled, setEmailEnabled] = useState(() => getCachedPref('email', true));
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingEmail, setTestingEmail] = useState(false);

  useEffect(() => {
    async function loadPrefs() {
      try {
        setLoading(true);
        const prefs = await api.getNotificationPreferences();
        if (prefs) {
          const inApp = Boolean(prefs.in_app_enabled);
          const email = Boolean(prefs.email_enabled);
          setInAppEnabled(inApp);
          setEmailEnabled(email);
          try {
            const uId = user?.id || 'anon';
            localStorage.setItem(`pettycash_pref_${uId}_in_app`, JSON.stringify(inApp));
            localStorage.setItem(`pettycash_pref_${uId}_email`, JSON.stringify(email));
          } catch (_) {}
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    if (user?.id) {
      loadPrefs();
    }
  }, [user?.id]);

  const handleToggleInApp = async (checked) => {
    setInAppEnabled(checked);
    try {
      const uId = user?.id || 'anon';
      localStorage.setItem(`pettycash_pref_${uId}_in_app`, JSON.stringify(checked));
    } catch (_) {}
    try {
      setSaving(true);
      await api.updateNotificationPreferences(checked, emailEnabled);
      addToast({
        type: 'success',
        title: 'Preference Updated',
        message: `In-app notifications ${checked ? 'enabled' : 'disabled'}.`,
      });
    } catch (err) {
      setInAppEnabled(!checked);
      addToast({ type: 'error', message: err.message });
    } finally {
      setSaving(false);
    }
  };

  const handleToggleEmail = async (checked) => {
    setEmailEnabled(checked);
    try {
      const uId = user?.id || 'anon';
      localStorage.setItem(`pettycash_pref_${uId}_email`, JSON.stringify(checked));
    } catch (_) {}
    try {
      setSaving(true);
      await api.updateNotificationPreferences(inAppEnabled, checked);
      addToast({
        type: 'success',
        title: 'Preference Updated',
        message: `Email alerts ${checked ? 'enabled' : 'disabled'}.`,
      });
    } catch (err) {
      setEmailEnabled(!checked);
      addToast({ type: 'error', message: err.message });
    } finally {
      setSaving(false);
    }
  };

  const handleSendTestEmail = async () => {
    try {
      setTestingEmail(true);
      const res = await api.sendTestEmail();
      addToast({
        type: 'success',
        title: 'Test Email Dispatched',
        message: `A test email has been sent to ${res.recipient || user?.email}. Please check your inbox.`,
      });
    } catch (err) {
      addToast({
        type: 'error',
        title: 'Email Delivery Failed',
        message: err.message || 'Could not dispatch test email. Please check server SMTP configuration.',
      });
    } finally {
      setTestingEmail(false);
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
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider text-xs flex items-center gap-2">
            <Bell className="w-4 h-4 text-emerald-400" /> Notification Delivery Preferences
          </h2>
          {saving && (
            <span className="text-[11px] text-emerald-400 animate-pulse font-medium">Saving...</span>
          )}
        </div>

        {loading ? (
          <div className="py-8 flex flex-col items-center justify-center gap-2 text-xs text-slate-500">
            <Loader2 className="w-5 h-5 animate-spin text-emerald-400" />
            <span>Loading delivery channels...</span>
          </div>
        ) : (
          <div className="space-y-4 pt-2">
            <div className="flex items-center justify-between p-3.5 bg-slate-950 rounded-md border border-slate-800 gap-4">
              <div>
                <div className="text-sm font-medium text-slate-200">In-App Notifications</div>
                <div className="text-xs text-slate-400">
                  Receive notifications inside the top navigation bar for workflow state transitions.
                </div>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={inAppEnabled}
                onClick={() => handleToggleInApp(!inAppEnabled)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  inAppEnabled ? 'bg-emerald-600' : 'bg-slate-700'
                }`}
              >
                <span
                  aria-hidden="true"
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition duration-200 ease-in-out ${
                    inAppEnabled ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>

            <div className="flex items-center justify-between p-3.5 bg-slate-950 rounded-md border border-slate-800 gap-4">
              <div>
                <div className="text-sm font-medium text-slate-200">Email Notifications</div>
                <div className="text-xs text-slate-400">
                  Dispatch transactional email alerts for approvals, postings, and returned vouchers.
                </div>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={emailEnabled}
                onClick={() => handleToggleEmail(!emailEnabled)}
                className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                  emailEnabled ? 'bg-emerald-600' : 'bg-slate-700'
                }`}
              >
                <span
                  aria-hidden="true"
                  className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-md transition duration-200 ease-in-out ${
                    emailEnabled ? 'translate-x-5' : 'translate-x-0'
                  }`}
                />
              </button>
            </div>

            {/* Test Email Action Row */}
            <div className="mt-4 pt-3 border-t border-slate-800/80 space-y-2">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <div className="text-xs font-medium text-slate-300">Verify Email Delivery</div>
                  <div className="text-[11px] text-slate-500">
                    Send a test email to <span className="text-slate-300 font-mono">{user?.email}</span> to verify delivery routing.
                  </div>
                </div>
                <button
                  type="button"
                  disabled={testingEmail || !emailEnabled}
                  onClick={handleSendTestEmail}
                  className="inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-medium text-slate-200 disabled:opacity-50 disabled:cursor-not-allowed transition"
                >
                  {testingEmail ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-emerald-400" />
                      <span>Sending...</span>
                    </>
                  ) : (
                    <>
                      <Send className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Send Test Email</span>
                    </>
                  )}
                </button>
              </div>
              <p className="text-[10px] text-slate-500">
                Tip: Cloud hosting platforms (like Render Free tier) block outbound SMTP ports (587/465). For guaranteed delivery on Render, configure <code className="text-emerald-400 bg-slate-950 px-1 py-0.5 rounded">RESEND_API_KEY</code> in environment variables to send over HTTPS (Port 443).
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
