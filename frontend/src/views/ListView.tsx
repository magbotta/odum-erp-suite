import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { Plus, RefreshCw, ChevronLeft, ChevronRight } from 'lucide-react';
import api from '../api/client';
import type { EntityMeta } from '../meta/types';

interface Props { meta: EntityMeta }

export default function ListView({ meta }: Props) {
  const nav = useNavigate();
  const [page, setPage] = useState(1);
  const pageSize = 25;

  const { data: rows = [], isLoading, refetch } = useQuery<Record<string, unknown>[]>({
    queryKey: ['entity', meta.api_path, page],
    queryFn: () => api.get(`${meta.api_path}`, { params: { page, page_size: pageSize } }).then(r => r.data),
  });

  const visibleFields = meta.fields.filter(f => !f.hidden && f.type !== 'table').slice(0, 6);

  function displayValue(val: unknown, type: string): string {
    if (val == null) return '—';
    if (type === 'boolean') return val ? 'Yes' : 'No';
    if (type === 'currency') return `${Number(val).toFixed(2)}`;
    return String(val).slice(0, 80);
  }

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-slate-900">{meta.label_plural}</h1>
          <p className="text-sm text-slate-500 mt-0.5">{rows.length} records loaded</p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => refetch()}
            className="flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900 border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50 transition"
          >
            <RefreshCw size={13} />
            Refresh
          </button>
          <Link
            to={`/entities/${meta.app}/${meta.entity}/new`}
            className="flex items-center gap-1.5 bg-ochre-600 hover:bg-ochre-700 text-white text-sm font-medium rounded-lg px-3 py-1.5 transition"
          >
            <Plus size={14} />
            New {meta.label}
          </Link>
        </div>
      </div>

      {/* Workflow status pills */}
      {meta.workflow && (
        <div className="flex gap-2 mb-4 flex-wrap">
          {meta.workflow.states.map(state => (
            <span key={state} className="text-xs bg-slate-100 text-slate-600 rounded-full px-2.5 py-0.5 border border-slate-200">
              {state}
            </span>
          ))}
        </div>
      )}

      {/* Table */}
      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        {isLoading ? (
          <div className="p-10 text-center text-slate-400 text-sm animate-pulse">Loading…</div>
        ) : rows.length === 0 ? (
          <div className="p-10 text-center">
            <div className="text-slate-400 text-sm">No records found</div>
            <Link
              to={`/entities/${meta.app}/${meta.entity}/new`}
              className="mt-3 inline-block text-ochre-600 hover:text-ochre-700 text-sm font-medium"
            >
              Create the first {meta.label}
            </Link>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  {visibleFields.map(f => (
                    <th key={f.name} className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                      {f.label}
                    </th>
                  ))}
                  {meta.workflow && (
                    <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                      Status
                    </th>
                  )}
                  <th className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider">
                    Created
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-50">
                {rows.map((row) => (
                  <tr
                    key={String(row.id)}
                    onClick={() => nav(`/entities/${meta.app}/${meta.entity}/${row.id}`)}
                    className="hover:bg-ochre-50 cursor-pointer transition"
                  >
                    {visibleFields.map(f => (
                      <td key={f.name} className="px-4 py-3 text-slate-700">
                        {displayValue(row[f.name], f.type)}
                      </td>
                    ))}
                    {meta.workflow && (
                      <td className="px-4 py-3">
                        <span className="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium bg-slate-100 text-slate-700">
                          {String(row.status ?? '—')}
                        </span>
                      </td>
                    )}
                    <td className="px-4 py-3 text-slate-400 text-xs">
                      {row.created_at ? String(row.created_at).slice(0, 10) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination */}
        {rows.length >= pageSize && (
          <div className="px-4 py-3 border-t border-gray-100 flex items-center justify-between text-sm text-slate-500">
            <span>Page {page}</span>
            <div className="flex gap-2">
              <button
                onClick={() => setPage(p => Math.max(1, p - 1))}
                disabled={page === 1}
                className="flex items-center gap-1 px-2.5 py-1 rounded border border-gray-200 hover:bg-gray-50 disabled:opacity-40 transition"
              >
                <ChevronLeft size={13} /> Prev
              </button>
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={rows.length < pageSize}
                className="flex items-center gap-1 px-2.5 py-1 rounded border border-gray-200 hover:bg-gray-50 disabled:opacity-40 transition"
              >
                Next <ChevronRight size={13} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
