import { useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import { LogOut, User, Search } from 'lucide-react';

export default function TopBar({ title }: { title?: string }) {
  const { user, logout } = useAuth();
  const nav = useNavigate();

  function openCommandPalette() {
    document.dispatchEvent(new CustomEvent('open-command-palette'));
  }

  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6 shrink-0">
      <div className="text-sm font-semibold text-slate-700">{title || 'Odum ERP Suite'}</div>
      <div className="flex items-center gap-3">
        {/* Cmd+K command palette button */}
        <button
          onClick={openCommandPalette}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 border border-gray-200 rounded-md px-2.5 py-1.5 hover:bg-gray-50 transition"
          title="Open command palette (⌘K)"
        >
          <Search size={12} />
          <span>Search</span>
          <kbd className="ml-1 font-mono text-slate-400 bg-gray-100 px-1 py-0.5 rounded text-[10px]">⌘K</kbd>
        </button>

        {/* Profile link */}
        <button
          onClick={() => nav('/profile')}
          className="flex items-center gap-2 text-sm text-slate-600 hover:text-slate-900 transition"
        >
          <User size={15} />
          {user?.first_name} {user?.last_name}
        </button>

        <button
          onClick={logout}
          className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-red-600 transition"
        >
          <LogOut size={13} />
          Sign out
        </button>
      </div>
    </header>
  );
}
