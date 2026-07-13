import { useState } from 'react';
import { useAuth } from '../auth/AuthContext';
import { useToast } from '../components/Toast';
import api from '../api/client';
import { Save, User } from 'lucide-react';

export default function ProfilePage() {
  const { user } = useAuth();
  const toast = useToast();

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);

  async function handleChangePassword(e: React.FormEvent) {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      toast.error('New passwords do not match.');
      return;
    }
    if (newPassword.length < 8) {
      toast.error('New password must be at least 8 characters.');
      return;
    }
    setLoading(true);
    try {
      await api.post('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      });
      toast.success('Password changed successfully.');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      const msg =
        axiosErr?.response?.data?.detail ?? 'Failed to change password. Please try again.';
      toast.error(typeof msg === 'string' ? msg : 'Failed to change password.');
    } finally {
      setLoading(false);
    }
  }

  const inputBase =
    'w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-odum-500 focus:border-transparent';

  return (
    <div className="max-w-lg">
      <h1 className="text-xl font-bold text-slate-900 mb-6">My Profile</h1>

      {/* Profile info */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-6">
        <div className="flex items-center gap-4 mb-5">
          <div className="h-12 w-12 rounded-full bg-odum-100 flex items-center justify-center">
            <User size={22} className="text-odum-600" />
          </div>
          <div>
            <div className="font-semibold text-slate-900">
              {user?.first_name} {user?.last_name}
            </div>
            <div className="text-sm text-slate-500">{user?.email}</div>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">First name</div>
            <div className="text-slate-800">{user?.first_name || '—'}</div>
          </div>
          <div>
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Last name</div>
            <div className="text-slate-800">{user?.last_name || '—'}</div>
          </div>
          <div className="col-span-2">
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Email</div>
            <div className="text-slate-800">{user?.email || '—'}</div>
          </div>
        </div>
      </div>

      {/* Change password */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
        <h2 className="text-sm font-bold text-slate-900 mb-4">Change Password</h2>
        <form onSubmit={handleChangePassword} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">
              Current password <span className="text-red-500">*</span>
            </label>
            <input
              type="password"
              value={currentPassword}
              onChange={e => setCurrentPassword(e.target.value)}
              required
              autoComplete="current-password"
              className={inputBase}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">
              New password <span className="text-red-500">*</span>
            </label>
            <input
              type="password"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              required
              autoComplete="new-password"
              minLength={8}
              className={inputBase}
            />
          </div>
          <div>
            <label className="block text-xs font-semibold text-slate-600 mb-1.5">
              Confirm new password <span className="text-red-500">*</span>
            </label>
            <input
              type="password"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              required
              autoComplete="new-password"
              className={inputBase}
            />
          </div>
          <div className="pt-1">
            <button
              type="submit"
              disabled={loading}
              className="flex items-center gap-2 bg-odum-600 hover:bg-odum-700 text-white text-sm font-semibold px-4 py-2 rounded-lg transition disabled:opacity-50"
            >
              <Save size={14} />
              {loading ? 'Saving…' : 'Update password'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
