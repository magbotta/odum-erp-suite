import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Edit, Trash2, ChevronRight } from 'lucide-react';
import api from '../api/client';
import type { EntityMeta } from '../meta/types';
import FieldRenderer from './fields/FieldRenderer';
import ConfirmModal from '../components/ConfirmModal';
import { Skeleton } from '../components/Skeleton';
import { useToast } from '../components/Toast';
import { useWorkflowActions } from '../hooks/useWorkflowActions';

interface Props { meta: EntityMeta; recordId: string }

export default function DetailView({ meta, recordId }: Props) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [deleteOpen, setDeleteOpen] = useState(false);

  const { data: record, isLoading } = useQuery<Record<string, unknown>>({
    queryKey: ['entity', meta.api_path, recordId],
    queryFn: () => api.get(`${meta.api_path}/${recordId}`).then(r => r.data),
  });

  const deleteMutation = useMutation({
    mutationFn: () => api.delete(`${meta.api_path}/${recordId}`),
    onSuccess: () => {
      toast.success(`${meta.label} deleted.`);
      qc.invalidateQueries({ queryKey: ['entity', meta.api_path] });
      nav(`/entities/${meta.app}/${meta.entity}`);
    },
    onError: () => {
      toast.error(`Failed to delete ${meta.label}.`);
    },
  });

  const { availableTransitions, loading: actionLoading, trigger } = useWorkflowActions(meta, record);

  async function handleAction(action: string, toState: string) {
    try {
      await trigger(action);
      await qc.invalidateQueries({ queryKey: ['entity', meta.api_path, recordId] });
      toast.success(`Status updated to ${toState}.`);
    } catch {
      toast.error(`Action failed. Please try again.`);
    }
  }

  if (isLoading) {
    return (
      <div>
        <div className="flex items-center gap-3 mb-6">
          <Skeleton className="h-6 w-6" />
          <div className="space-y-2">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-3 w-64" />
          </div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="space-y-2">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-9 w-full" />
              </div>
            ))}
          </div>
        </div>
      </div>
    );
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
            <span className="ml-2 inline-flex items-center rounded-full px-3 py-1 text-xs font-medium bg-odum-100 text-odum-800 border border-odum-200">
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
            onClick={() => setDeleteOpen(true)}
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
          <div className="flex gap-2 flex-wrap mb-3">
            {meta.workflow.states.map(state => (
              <span
                key={state}
                className={`text-xs rounded-full px-3 py-1 border ${
                  record.status === state
                    ? 'bg-odum-500 text-white border-odum-500 font-semibold'
                    : 'bg-gray-50 text-slate-500 border-gray-200'
                }`}
              >
                {state}
              </span>
            ))}
          </div>
          {availableTransitions.length > 0 && (
            <div className="flex gap-2 flex-wrap pt-3 border-t border-gray-100">
              <span className="text-xs text-slate-400 self-center mr-1">Actions:</span>
              {availableTransitions.map(t => (
                <button
                  key={t.action}
                  disabled={actionLoading}
                  onClick={() => t.action && handleAction(t.action, t.to)}
                  className="flex items-center gap-1.5 text-xs font-semibold border border-odum-300 text-odum-700 bg-odum-50 hover:bg-odum-100 px-3 py-1.5 rounded-lg transition disabled:opacity-50"
                >
                  {t.action}
                  <ChevronRight size={12} />
                  <span className="font-normal text-odum-500">{t.to}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Delete confirmation modal */}
      <ConfirmModal
        open={deleteOpen}
        title={`Delete ${meta.label}`}
        message={`Are you sure you want to delete this ${meta.label}? This action cannot be undone.`}
        confirmLabel="Delete"
        danger
        onConfirm={() => {
          setDeleteOpen(false);
          deleteMutation.mutate();
        }}
        onCancel={() => setDeleteOpen(false)}
      />
    </div>
  );
}
