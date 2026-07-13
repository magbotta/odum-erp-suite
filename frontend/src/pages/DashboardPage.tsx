import { useEntities } from '../meta/useEntities';
import { useAuth } from '../auth/AuthContext';
import {
  DollarSign, Users, Package, TrendingUp, UserCheck,
  Database, Layers
} from 'lucide-react';

export default function DashboardPage() {
  const { user } = useAuth();
  const { data: entities = [] } = useEntities();

  const appCount = new Set(entities.map(e => e.app)).size;

  const highlights = [
    { label: 'Total Entities', value: entities.length, icon: Database, color: 'bg-blue-50 text-blue-600' },
    { label: 'Installed Apps', value: appCount, icon: Layers, color: 'bg-odum-50 text-odum-600' },
  ];

  const quickLinks = [
    { label: 'Customers', app: 'accounting', entity: 'Customer', icon: Users },
    { label: 'Sales Invoices', app: 'accounting', entity: 'SalesInvoice', icon: DollarSign },
    { label: 'CRM Leads', app: 'crm', entity: 'Lead', icon: TrendingUp },
    { label: 'Employees', app: 'hrm', entity: 'Employee', icon: UserCheck },
    { label: 'Items', app: 'warehouse', entity: 'Item', icon: Package },
    { label: 'Sales Orders', app: 'sales', entity: 'SalesOrder', icon: TrendingUp },
  ];

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">
          Welcome back{user?.first_name ? `, ${user.first_name}` : ''}
        </h1>
        <p className="text-slate-500 text-sm mt-1">
          Odum ERP Suite · {new Date().toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {highlights.map(h => (
          <div key={h.label} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm flex items-center gap-3">
            <div className={`rounded-lg p-2.5 ${h.color}`}>
              <h.icon size={18} />
            </div>
            <div>
              <div className="text-2xl font-bold text-slate-900">{h.value}</div>
              <div className="text-xs text-slate-500">{h.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Quick links */}
      <div className="mb-2 text-xs font-semibold text-slate-500 uppercase tracking-wider">Quick Access</div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-8">
        {quickLinks.map(link => (
          <a
            key={`${link.app}.${link.entity}`}
            href={`/entities/${link.app}/${link.entity}`}
            className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm hover:border-odum-300 hover:shadow-md transition flex items-center gap-3"
          >
            <div className="rounded-lg p-2 bg-slate-50">
              <link.icon size={16} className="text-slate-600" />
            </div>
            <span className="text-sm font-medium text-slate-700">{link.label}</span>
          </a>
        ))}
      </div>

      {/* All apps grid */}
      <div className="mb-2 text-xs font-semibold text-slate-500 uppercase tracking-wider">All Apps</div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[...new Set(entities.map(e => e.app))].map(app => {
          const appEntities = entities.filter(e => e.app === app);
          return (
            <div key={app} className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
              <div className="text-sm font-semibold text-slate-700 capitalize mb-1">
                {app.replace(/_/g, ' ')}
              </div>
              <div className="text-xs text-slate-400">{appEntities.length} entit{appEntities.length === 1 ? 'y' : 'ies'}</div>
              <div className="mt-2 flex flex-wrap gap-1">
                {appEntities.slice(0, 3).map(e => (
                  <a
                    key={e.entity}
                    href={`/entities/${e.app}/${e.entity}`}
                    className="text-xs text-odum-700 hover:underline"
                  >
                    {e.label}
                  </a>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
