import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Edit, Trash2 } from 'lucide-react';
import api from '../api/client';
import type { EntityMeta } from '../meta/types';
import FieldRenderer from './fields/FieldRenderer';

interface Props { meta: EntityMeta; recordId: string }

export default function DetailView({ meta, recordId }: Props) {
  const nav = useNavigate();
  const qc = useQueryClient();

  const { data: record, isLoading } = useQuery<Record<string, unknown>>({
    queryKey: ['entity', meta.api_path, recordId],
    queryFn: () => api.get(`${meta.api_path}/${recordId}`).then(r => r.data),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`${meta.api_path}/${recordId}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['entity', meta.api_path] });
      nav(`/entities/${meta.app}/${meta.entity}`);
    },
  });

  if (isLoading) {
    return <div className="p-10 text-center text-slate-400 animate-pulse">Loading…</div>;
  }

  if (!record) {
    return <div className="p-10 text-center text-slate-400">Record not found.</div>;
  }

  const visibleFields = meta.fields.filter(f => !f.hidden && f.type !== 'table');

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <button onClick={() => nav(-1)} className="text-slate-500 hover:text-slate-700 transition">
            <ArrowLeft size={18} />
          </button>
          <div>
            <h1 className="text-xl font-bold text-slate-900">{meta.label}</h1>
            <p className="text-xs text-slate-400 mt-0.5 font-mono">{recordId}</p>
          </div>
          {record.status != null && (
            <span className="ml-2 inline-flex items-center rounded-full px-3 py-1 text-xs font-medium bg-ochre-100 text-ochre-800 border border-ochre-200">
              {String(record.status)}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => nav(`/entities/${meta.app}/${meta.entity}/${recordId}/edit`)}
            className="flex items-center gap-1.5 text-sm border border-gray-200 rounded-lg px-3 py-1.5 hover:bg-gray-50 transition"
          >
            <Edit size={13} /> Edit
          </button>
          <button
            onClick={() => { if (confirm('Delete this record?')) deleteMutation.mutate(); }}
            className="flex items-center gap-1.5 text-sm border border-red-200 text-red-600 rounded-lg px-3 py-1.5 hover:bg-red-50 transition"
          >
            <Trash2 size={13} /> Delete
          </button>
        </div>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {visibleFields.map(field => (
            <div
              key={field.name}
              className={field.type === 'text' || field.type === 'json' ? 'md:col-span-2' : ''}
            >
              <label className="block text-xs font-semibold text-slate-500 mb-1.5 uppercase tracking-wide">
                {field.label}
              </label>
              <FieldRenderer field={field} value={record[field.name]} readOnly />
            </div>
          ))}
        </div>
        <div className="mt-6 pt-4 border-t border-gray-100 grid grid-cols-2 gap-4 text-xs text-slate-400">
          <div><span className="font-medium">Created:</span> {String(record.created_at ?? '—').slice(0, 19).replace('T', ' ')}</div>
          <div><span className="font-medium">Updated:</span> {String(record.updated_at ?? '—').slice(0, 19).replace('T', ' ')}</div>
        </div>
      </div>

      {/* Workflow transitions */}
      {meta.workflow && (
        <div className="mt-4 bg-white rounded-xl border border-gray-200 shadow-sm p-4">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">Workflow</div>
          <div className="flex gap-2 flex-wrap">
            {meta.workflow.states.map(state => (
              <span
                key={state}
                className={`text-xs rounded-full px-3 py-1 border ${
                  record.status === state
                    ? 'bg-ochre-500 text-white border-ochre-500 font-semibold'
                    : 'bg-gray-50 text-slate-500 border-gray-200'
                }`}
              >
                {state}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
