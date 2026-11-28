import React, { useState, useEffect } from 'react';
import { Lock, Mail, Key, Shield, ArrowRight, UserPlus, CheckCircle2 } from 'lucide-react';
import { api } from '../api';
import { LogoIcon } from '../components/Logo';

export default function LoginView({ onLoginSuccess, addToast }) {
  const [tab, setTab] = useState('login'); // 'login' | 'bootstrap' | 'token'
  const [adminExists, setAdminExists] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Check if initial admin bootstrap is required on mount
  useEffect(() => {
    let isMounted = true;
    api.getBootstrapStatus()
      .then((res) => {
        if (!isMounted) return;
        const exists = Boolean(res && res.admin_exists);
        setAdminExists(exists);
        if (!exists) {
          setTab('bootstrap');
        }
      })
      .catch(() => {});
    return () => { isMounted = false; };
  }, []);

  // Login form
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');

  // Bootstrap form
  const [bootUsername, setBootUsername] = useState('admin');
  const [bootEmail, setBootEmail] = useState('admin@example.com');
  const [bootPassword, setBootPassword] = useState('');

  // Set password form
  const [tokenInput, setTokenInput] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const handleLogin = async (e) => {
    e.preventDefault();
    setError('');
    if (!loginEmail.trim() || !loginPassword.trim()) {
      setError('Please provide both email and password.');
      return;
    }

    try {
      setLoading(true);
      const res = await api.login(loginEmail.trim(), loginPassword);
      addToast({
        type: 'success',
        title: 'Logged In',
        message: `Welcome back, ${res.user.username}!`,
      });
      onLoginSuccess(res.user);
    } catch (err) {
      setError(err.message || 'Login failed. Please verify your credentials.');
    } finally {
      setLoading(false);
    }
  };

  const handleBootstrap = async (e) => {
    e.preventDefault();
    setError('');
    if (!bootUsername.trim() || !bootEmail.trim() || !bootPassword.trim()) {
      setError('Please fill in all fields.');
      return;
    }

    try {
      setLoading(true);
      await api.bootstrapAdmin(bootUsername.trim(), bootEmail.trim(), bootPassword);
      addToast({
        type: 'success',
        title: 'Director Created',
        message: 'Director account provisioned. You can now log in.',
      });
      setLoginEmail(bootEmail);
      setAdminExists(true);
      setTab('login');
    } catch (err) {
      setError(err.message || 'Bootstrap admin creation failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleSetPassword = async (e) => {
    e.preventDefault();
    setError('');
    if (!tokenInput.trim() || !newPassword.trim()) {
      setError('Token and new password are required.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    try {
      setLoading(true);
      const res = await api.setPassword(tokenInput.trim(), newPassword);
      addToast({
        type: 'success',
        title: 'Password Configured',
        message: 'Your password has been set. You can now log in.',
      });
      setTab('login');
      if (res.email) setLoginEmail(res.email);
    } catch (err) {
      setError(err.message || 'Failed to set password with the token.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col justify-center py-12 sm:px-6 lg:px-8 text-slate-100">
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        <div className="flex justify-center">
          <LogoIcon size={56} className="drop-shadow-[0_4px_12px_rgba(16,185,129,0.3)]" />
        </div>
        <h1 className="mt-4 text-center text-2xl font-bold tracking-tight text-slate-100">
          PettyCash Management
        </h1>
        <p className="mt-1 text-center text-sm text-slate-400">
          Production enterprise petty cash, vouchers & ledger accounting
        </p>

        {/* Tab selection */}
        <div className="mt-6 flex rounded-lg bg-slate-900 p-1 border border-slate-800">
          <button
            type="button"
            onClick={() => { setTab('login'); setError(''); }}
            className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-colors ${
              tab === 'login'
                ? 'bg-slate-800 text-emerald-400 shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Sign In
          </button>
          <button
            type="button"
            onClick={() => { setTab('token'); setError(''); }}
            className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-colors ${
              tab === 'token'
                ? 'bg-slate-800 text-emerald-400 shadow'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Invite / Set Password
          </button>
          {!adminExists && (
            <button
              type="button"
              onClick={() => { setTab('bootstrap'); setError(''); }}
              className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition-colors ${
                tab === 'bootstrap'
                  ? 'bg-slate-800 text-emerald-400 shadow'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Init Director
            </button>
          )}
        </div>
      </div>

      <div className="mt-4 sm:mx-auto sm:w-full sm:max-w-md">
        <div className="bg-slate-900 py-8 px-4 shadow-xl border border-slate-800 rounded-lg sm:px-10">
          {error && (
            <div className="mb-5 p-3 rounded bg-rose-950/80 border border-rose-800 text-rose-200 text-xs font-medium">
              {error}
            </div>
          )}

          {tab === 'login' && (
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Email address
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-500">
                    <Mail className="w-4 h-4" />
                  </div>
                  <input
                    type="email"
                    required
                    value={loginEmail}
                    onChange={(e) => setLoginEmail(e.target.value)}
                    placeholder="user@example.com"
                    className="block w-full pl-9 pr-3 py-2 text-sm bg-slate-950 border border-slate-700 rounded-md text-slate-100 placeholder-slate-500 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Password
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-500">
                    <Lock className="w-4 h-4" />
                  </div>
                  <input
                    type="password"
                    required
                    value={loginPassword}
                    onChange={(e) => setLoginPassword(e.target.value)}
                    placeholder="••••••••"
                    className="block w-full pl-9 pr-3 py-2 text-sm bg-slate-950 border border-slate-700 rounded-md text-slate-100 placeholder-slate-500 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full flex justify-center items-center gap-2 py-2.5 px-4 border border-transparent rounded-md shadow-sm text-sm font-semibold text-slate-950 bg-emerald-500 hover:bg-emerald-400 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500 disabled:opacity-50 transition-colors cursor-pointer"
              >
                {loading ? 'Signing in...' : 'Sign In'}
                {!loading && <ArrowRight className="w-4 h-4" />}
              </button>
            </form>
          )}

          {tab === 'token' && (
            <form onSubmit={handleSetPassword} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Onboarding Token
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-slate-500">
                    <Key className="w-4 h-4" />
                  </div>
                  <input
                    type="text"
                    required
                    value={tokenInput}
                    onChange={(e) => setTokenInput(e.target.value)}
                    placeholder="Enter setup token from email/admin"
                    className="block w-full pl-9 pr-3 py-2 text-sm bg-slate-950 border border-slate-700 rounded-md text-slate-100 placeholder-slate-500 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  New Password
                </label>
                <input
                  type="password"
                  required
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="At least 8 characters"
                  className="block w-full px-3 py-2 text-sm bg-slate-950 border border-slate-700 rounded-md text-slate-100 placeholder-slate-500 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Confirm Password
                </label>
                <input
                  type="password"
                  required
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Repeat new password"
                  className="block w-full px-3 py-2 text-sm bg-slate-950 border border-slate-700 rounded-md text-slate-100 placeholder-slate-500 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full flex justify-center items-center gap-2 py-2.5 px-4 border border-transparent rounded-md shadow-sm text-sm font-semibold text-slate-950 bg-emerald-500 hover:bg-emerald-400 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500 disabled:opacity-50 transition-colors cursor-pointer"
              >
                {loading ? 'Updating...' : 'Set Password and Continue'}
              </button>
            </form>
          )}

          {!adminExists && tab === 'bootstrap' && (
            <form onSubmit={handleBootstrap} className="space-y-4">
              <div className="p-2.5 rounded bg-amber-950/40 border border-amber-800 text-amber-200 text-xs">
                Creates initial super-admin if no administrator exists yet.
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Username
                </label>
                <input
                  type="text"
                  required
                  value={bootUsername}
                  onChange={(e) => setBootUsername(e.target.value)}
                  className="block w-full px-3 py-2 text-sm bg-slate-950 border border-slate-700 rounded-md text-slate-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Email
                </label>
                <input
                  type="email"
                  required
                  value={bootEmail}
                  onChange={(e) => setBootEmail(e.target.value)}
                  className="block w-full px-3 py-2 text-sm bg-slate-950 border border-slate-700 rounded-md text-slate-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Master Password
                </label>
                <input
                  type="password"
                  required
                  value={bootPassword}
                  onChange={(e) => setBootPassword(e.target.value)}
                  placeholder="Strong administrator password"
                  className="block w-full px-3 py-2 text-sm bg-slate-950 border border-slate-700 rounded-md text-slate-100 focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                />
              </div>

              <button
                type="submit"
                disabled={loading}
                className="w-full flex justify-center items-center gap-2 py-2.5 px-4 border border-transparent rounded-md shadow-sm text-sm font-semibold text-slate-950 bg-amber-400 hover:bg-amber-300 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-amber-400 disabled:opacity-50 transition-colors cursor-pointer"
              >
                {loading ? 'Initializing...' : 'Bootstrap Director'}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
