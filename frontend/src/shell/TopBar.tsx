import { useAuth } from '../auth/AuthContext';
import { LogOut, User } from 'lucide-react';

export default function TopBar({ title }: { title?: string }) {
  const { user, logout } = useAuth();

  return (
    <header className="h-14 bg-white border-b border-gray-200 flex items-center justify-between px-6 shrink-0">
      <div className="text-sm font-semibold text-slate-700">{title || 'Odum ERP Suite'}</div>
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <User size={15} />
          {user?.first_name} {user?.last_name}
        </div>
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
