import React from 'react';
import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

export default function Toast({ toasts, onDismiss }) {
  if (!toasts || toasts.length === 0) return null;

  return (
    <div
      role="region"
      aria-label="Notifications"
      className="fixed bottom-5 right-5 z-50 flex flex-col gap-2 max-w-md w-full px-4 pointer-events-none"
    >
      {toasts.map((toast) => {
        const isError = toast.type === 'error';
        const isSuccess = toast.type === 'success';

        return (
          <div
            key={toast.id}
            role="alert"
            className={`pointer-events-auto flex items-start gap-3 p-3.5 rounded-lg border shadow-lg transition-all transform translate-y-0 ${
              isError
                ? 'bg-rose-900/95 border-rose-700 text-rose-100'
                : isSuccess
                ? 'bg-emerald-900/95 border-emerald-700 text-emerald-100'
                : 'bg-slate-900/95 border-slate-700 text-slate-100'
            }`}
          >
            <div className="shrink-0 mt-0.5">
              {isError && <AlertCircle className="w-5 h-5 text-rose-400" aria-hidden="true" />}
              {isSuccess && <CheckCircle2 className="w-5 h-5 text-emerald-400" aria-hidden="true" />}
              {!isError && !isSuccess && <Info className="w-5 h-5 text-slate-400" aria-hidden="true" />}
            </div>
            <div className="flex-1 text-sm font-medium leading-snug">
              {toast.title && <div className="font-semibold mb-0.5">{toast.title}</div>}
              <div>{toast.message}</div>
            </div>
            <button
              type="button"
              onClick={() => onDismiss(toast.id)}
              className="shrink-0 text-slate-400 hover:text-white p-1 rounded transition-colors"
              aria-label="Dismiss alert"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
