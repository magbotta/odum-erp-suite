import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import Sidebar from './Sidebar';
import TopBar from './TopBar';

export default function AppShell() {
  const { user, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="text-slate-400 text-sm animate-pulse">Loading…</div>
      </div>
    );
  }

  if (!user) return <Navigate to="/login" replace />;

  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
