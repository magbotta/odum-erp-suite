import { useState, useMemo, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { Plus, RefreshCw, ChevronLeft, ChevronRight, ChevronUp, ChevronDown, Search } from 'lucide-react';
import api from '../api/client';
import type { EntityMeta } from '../meta/types';
import { SkeletonTable } from '../components/Skeleton';
import { useToast } from '../components/Toast';

interface Props { meta: EntityMeta }

type SortDir = 'asc' | 'desc';

export default function ListView({ meta }: Props) {
  const nav = useNavigate();
  const toast = useToast();
  const [page, setPage] = useState(1);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortField, setSortField] = useState<string | null>(null);
  const [sortDir, setSortDir] = useState<SortDir>('asc');
  const pageSize = 25;

  const { data: rows = [], isLoading, refetch, error } = useQuery<Record<string, unknown>[]>({
    queryKey: ['entity', meta.api_path, page],
    queryFn: () => api.get(`${meta.api_path}`, { params: { page, page_size: pageSize } }).then(r => r.data),
  });

  useEffect(() => {
    if (error) toast.error(`Failed to load ${meta.label_plural}.`);
  }, [error]); // eslint-disable-line react-hooks/exhaustive-deps

  const visibleFields = meta.fields.filter(f => !f.hidden && f.type !== 'table').slice(0, 6);

  // Client-side search across all string fields
  const filteredRows = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return rows;
    return rows.filter(row =>
      visibleFields.some(f => {
        const val = row[f.name];
        return val != null && String(val).toLowerCase().includes(q);
      })
    );
  }, [rows, searchQuery, visibleFields]);

  // Client-side sort
  const sortedRows = useMemo(() => {
    if (!sortField) return filteredRows;
    return [...filteredRows].sort((a, b) => {
      const av = a[sortField];
      const bv = b[sortField];
      const aStr = av == null ? '' : String(av);
      const bStr = bv == null ? '' : String(bv);
      const cmp = aStr.localeCompare(bStr, undefined, { numeric: true });
      return sortDir === 'asc' ? cmp : -cmp;
    });
  }, [filteredRows, sortField, sortDir]);

  function handleSort(fieldName: string) {
    if (sortField === fieldName) {
      setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(fieldName);
      setSortDir('asc');
    }
  }

  function displayValue(val: unknown, type: string): string {
    if (val == null) return '—';
    if (type === 'boolean') return val ? 'Yes' : 'No';
    if (type === 'currency') return `${Number(val).toFixed(2)}`;
    return String(val).slice(0, 80);
  }

  const totalCount = rows.length;
  const filteredCount = filteredRows.length;
  const isFiltered = searchQuery.trim().length > 0;

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-5">
        <div>
          <h1 className="text-xl font-bold text-slate-900">{meta.label_plural}</h1>
          <p className="text-sm text-slate-500 mt-0.5">
            {isFiltered
              ? `${filteredCount} of ${totalCount} records`
              : `${totalCount} record${totalCount !== 1 ? 's' : ''}`}
          </p>
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
            className="flex items-center gap-1.5 bg-odum-600 hover:bg-odum-700 text-white text-sm font-medium rounded-lg px-3 py-1.5 transition"
          >
            <Plus size={14} />
            New {meta.label}
          </Link>
        </div>
      </div>

      {/* Search box */}
      <div className="relative mb-4">
        <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
        <input
          type="text"
          placeholder={`Search ${meta.label_plural.toLowerCase()}…`}
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          className="w-full max-w-sm pl-8 pr-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-odum-500 focus:border-transparent bg-white"
        />
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
          <SkeletonTable rows={6} cols={visibleFields.length + 2} />
        ) : sortedRows.length === 0 ? (
          <div className="p-10 text-center">
            <div className="text-slate-400 text-sm">
              {isFiltered ? `No records match "${searchQuery}"` : 'No records found'}
            </div>
            {!isFiltered && (
              <Link
                to={`/entities/${meta.app}/${meta.entity}/new`}
                className="mt-3 inline-block text-odum-600 hover:text-odum-700 text-sm font-medium"
              >
                Create the first {meta.label}
              </Link>
            )}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50">
                  {visibleFields.map(f => (
                    <th
                      key={f.name}
                      onClick={() => handleSort(f.name)}
                      className="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wider cursor-pointer select-none hover:text-slate-700 hover:bg-gray-100 transition"
                    >
                      <span className="inline-flex items-center gap-1">
                        {f.label}
                        {sortField === f.name ? (
                          sortDir === 'asc' ? (
                            <ChevronUp size={12} className="text-odum-600" />
                          ) : (
                            <ChevronDown size={12} className="text-odum-600" />
                          )
                        ) : (
                          <ChevronUp size={12} className="opacity-0 group-hover:opacity-30" />
                        )}
                      </span>
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
                {sortedRows.map((row) => (
                  <tr
                    key={String(row.id)}
                    onClick={() => nav(`/entities/${meta.app}/${meta.entity}/${row.id}`)}
                    className="hover:bg-odum-50 cursor-pointer transition"
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
