import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useEntities } from '../meta/useEntities';
import {
  DollarSign, Users, UserCheck, CreditCard, Kanban,
  ShoppingCart, TrendingUp, Package, Building2, Globe,
  Factory, Receipt, GraduationCap, Heart, Leaf,
  HeartHandshake, Radio, Landmark, Coins, Scale,
  LayoutDashboard, ChevronDown, ChevronRight,
  type LucideIcon,
} from 'lucide-react';

const APP_CONFIG: Record<string, { label: string; Icon: LucideIcon; group: string }> = {
  accounting: { label: 'Accounting', Icon: DollarSign, group: 'Core' },
  crm: { label: 'CRM', Icon: Users, group: 'Core' },
  hrm: { label: 'HR', Icon: UserCheck, group: 'Core' },
  payroll: { label: 'Payroll', Icon: CreditCard, group: 'Core' },
  project: { label: 'Projects', Icon: Kanban, group: 'Core' },
  purchasing: { label: 'Purchasing', Icon: ShoppingCart, group: 'Core' },
  sales: { label: 'Sales', Icon: TrendingUp, group: 'Core' },
  warehouse: { label: 'Warehouse', Icon: Package, group: 'Core' },
  asset_management: { label: 'Assets', Icon: Building2, group: 'Core' },
  website: { label: 'Website', Icon: Globe, group: 'Core' },
  manufacturing: { label: 'Manufacturing', Icon: Factory, group: 'Industry' },
  pos: { label: 'POS', Icon: Receipt, group: 'Industry' },
  education_sis: { label: 'Education', Icon: GraduationCap, group: 'Industry' },
  healthcare_his: { label: 'Healthcare', Icon: Heart, group: 'Industry' },
  agriculture: { label: 'Agriculture', Icon: Leaf, group: 'Industry' },
  nonprofit: { label: 'Nonprofit', Icon: HeartHandshake, group: 'Industry' },
  telecom: { label: 'Telecom', Icon: Radio, group: 'Industry' },
  government: { label: 'Government', Icon: Landmark, group: 'Industry' },
  microfinance: { label: 'Microfinance', Icon: Coins, group: 'Industry' },
  legal_services: { label: 'Legal', Icon: Scale, group: 'Industry' },
};

function AppSection({ appKey, entities }: { appKey: string; entities: { entity: string; label: string }[] }) {
  const cfg = APP_CONFIG[appKey];
  const [open, setOpen] = useState(appKey === 'crm' || appKey === 'accounting');
  if (!cfg) return null;
  const { label, Icon } = cfg;

  return (
    <div>
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-slate-300 hover:text-white hover:bg-slate-700 transition text-sm font-medium"
      >
        <Icon size={15} className="shrink-0 text-ochre-400" />
        <span className="flex-1 text-left">{label}</span>
        {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
      </button>
      {open && (
        <div className="ml-4 pl-3 border-l border-slate-700 mt-0.5 space-y-0.5">
          {entities.map(e => (
            <NavLink
              key={e.entity}
              to={`/entities/${appKey}/${e.entity}`}
              className={({ isActive }) =>
                `block px-2 py-1.5 rounded text-xs transition ${
                  isActive
                    ? 'bg-ochre-600 text-white font-semibold'
                    : 'text-slate-400 hover:text-white hover:bg-slate-700'
                }`
              }
            >
              {e.label}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Sidebar() {
  const { data: entities = [] } = useEntities();

  const byApp = entities.reduce<Record<string, typeof entities>>((acc, e) => {
    if (!acc[e.app]) acc[e.app] = [];
    acc[e.app].push(e);
    return acc;
  }, {});

  const coreApps = Object.keys(byApp).filter(a => APP_CONFIG[a]?.group === 'Core');
  const industryApps = Object.keys(byApp).filter(a => APP_CONFIG[a]?.group === 'Industry');

  return (
    <aside className="w-56 bg-slate-900 flex flex-col h-full overflow-y-auto shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-2.5 px-4 py-4 border-b border-slate-700">
        <span className="text-2xl">🟠</span>
        <div>
          <div className="text-white font-bold text-sm leading-tight">Odum ERP Suite</div>
          <div className="text-slate-400 text-xs">Open Source</div>
        </div>
      </div>

      <nav className="flex-1 p-3 space-y-1">
        {/* Dashboard */}
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            `flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition ${
              isActive
                ? 'bg-ochre-600 text-white'
                : 'text-slate-300 hover:text-white hover:bg-slate-700'
            }`
          }
        >
          <LayoutDashboard size={15} />
          Dashboard
        </NavLink>

        {/* Core apps */}
        {coreApps.length > 0 && (
          <>
            <div className="pt-3 pb-1 px-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Core
            </div>
            {coreApps.map(appKey => (
              <AppSection
                key={appKey}
                appKey={appKey}
                entities={byApp[appKey].map(e => ({ entity: e.entity, label: e.label }))}
              />
            ))}
          </>
        )}

        {/* Industry apps */}
        {industryApps.length > 0 && (
          <>
            <div className="pt-3 pb-1 px-3 text-xs font-semibold text-slate-500 uppercase tracking-wider">
              Industry
            </div>
            {industryApps.map(appKey => (
              <AppSection
                key={appKey}
                appKey={appKey}
                entities={byApp[appKey].map(e => ({ entity: e.entity, label: e.label }))}
              />
            ))}
          </>
        )}
      </nav>

      <div className="p-3 border-t border-slate-700">
        <div className="text-xs text-slate-500 text-center">
          {entities.length} entities · {Object.keys(byApp).length} apps
        </div>
      </div>
    </aside>
  );
}
