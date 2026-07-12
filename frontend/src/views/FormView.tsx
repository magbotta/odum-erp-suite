import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Save } from 'lucide-react';
import api from '../api/client';
import type { EntityMeta } from '../meta/types';
import FieldRenderer from './fields/FieldRenderer';

interface Props {
  meta: EntityMeta;
  initialData?: Record<string, unknown>;
  recordId?: string;
}

export default function FormView({ meta, initialData, recordId }: Props) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [formData, setFormData] = useState<Record<string, unknown>>(initialData ?? {});
  const isEdit = Boolean(recordId);

  useEffect(() => {
    if (initialData) setFormData(initialData);
  }, [initialData]);

  const mutation = useMutation({
    mutationFn: (data: Record<string, unknown>) =>
      isEdit
        ? api.patch(`${meta.api_path}/${recordId}`, data).then(r => r.data)
        : api.post(meta.api_path, data).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['entity', meta.api_path] });
      nav(`/entities/${meta.app}/${meta.entity}`);
    },
  });

  const editableFields = meta.fields.filter(f => !f.read_only && f.type !== 'table');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    mutation.mutate(formData);
  }

  return (
    <div>
      <div className="flex items-center gap-3 mb-6">
        <button
          onClick={() => nav(-1)}
          className="text-slate-500 hover:text-slate-700 transition"
        >
          <ArrowLeft size={18} />
        </button>
        <div>
          <h1 className="text-xl font-bold text-slate-900">
            {isEdit ? `Edit ${meta.label}` : `New ${meta.label}`}
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">{meta.app} / {meta.entity}</p>
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            {editableFields.map(field => (
              <div
                key={field.name}
                className={field.type === 'text' || field.type === 'json' ? 'md:col-span-2' : ''}
              >
                <label className="block text-xs font-semibold text-slate-600 mb-1.5">
                  {field.label}
                  {field.required && <span className="text-red-500 ml-0.5">*</span>}
                </label>
                <FieldRenderer
                  field={field}
                  value={formData[field.name]}
                  onChange={val => setFormData(prev => ({ ...prev, [field.name]: val }))}
                />
              </div>
            ))}
          </div>

          {mutation.isError && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {String((mutation.error as Error)?.message ?? 'An error occurred.')}
            </div>
          )}
        </div>

        <div className="mt-4 flex justify-end gap-3">
          <button
            type="button"
            onClick={() => nav(-1)}
            className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 transition"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={mutation.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-ochre-600 hover:bg-ochre-700 text-white text-sm font-semibold rounded-lg transition disabled:opacity-50"
          >
            <Save size={14} />
            {mutation.isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Create'}
          </button>
        </div>
      </form>
    </div>
  );
}
