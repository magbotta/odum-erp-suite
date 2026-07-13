import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Save } from 'lucide-react';
import api from '../api/client';
import type { EntityMeta } from '../meta/types';
import FieldRenderer from './fields/FieldRenderer';
import { useToast } from '../components/Toast';

interface Props {
  meta: EntityMeta;
  initialData?: Record<string, unknown>;
  recordId?: string;
}

interface FieldErrors {
  [fieldName: string]: string[];
}

function parseApiError(err: unknown): { general: string; fields: FieldErrors } {
  const axiosErr = err as {
    response?: {
      data?: {
        detail?: unknown;
        message?: string;
      };
      status?: number;
    };
    message?: string;
  };

  const data = axiosErr?.response?.data;
  if (!data) {
    return { general: axiosErr?.message ?? 'An error occurred.', fields: {} };
  }

  // Django Ninja validation errors: { detail: [ { loc: [..., fieldName], msg: "..." } ] }
  if (Array.isArray(data.detail)) {
    const fields: FieldErrors = {};
    const generalMessages: string[] = [];
    for (const item of data.detail as { loc?: string[]; msg?: string }[]) {
      const loc = item.loc ?? [];
      const fieldName = loc.length >= 2 ? loc[loc.length - 1] : null;
      const msg = item.msg ?? 'Invalid value';
      if (fieldName && fieldName !== 'body' && fieldName !== '__root__') {
        fields[fieldName] = [...(fields[fieldName] ?? []), msg];
      } else {
        generalMessages.push(msg);
      }
    }
    const general = generalMessages.join(', ') || (Object.keys(fields).length > 0 ? 'Please fix the errors below.' : 'Validation failed.');
    return { general, fields };
  }

  // Django Ninja string detail
  if (typeof data.detail === 'string') {
    return { general: data.detail, fields: {} };
  }

  // Django Ninja object detail (field: [msg] map)
  if (data.detail && typeof data.detail === 'object' && !Array.isArray(data.detail)) {
    const fields: FieldErrors = {};
    for (const [key, val] of Object.entries(data.detail as Record<string, unknown>)) {
      fields[key] = Array.isArray(val) ? val.map(String) : [String(val)];
    }
    return { general: 'Please fix the errors below.', fields };
  }

  return { general: data.message ?? 'An error occurred.', fields: {} };
}

export default function FormView({ meta, initialData, recordId }: Props) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const toast = useToast();
  const [formData, setFormData] = useState<Record<string, unknown>>(initialData ?? {});
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
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
      toast.success(isEdit ? `${meta.label} saved.` : `${meta.label} created.`);
      nav(`/entities/${meta.app}/${meta.entity}`);
    },
    onError: (err: unknown) => {
      const { general, fields } = parseApiError(err);
      setFieldErrors(fields);
      toast.error(general);
    },
  });

  const editableFields = meta.fields.filter(f => !f.read_only && f.type !== 'table');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});
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
            {editableFields.map(field => {
              const errs = fieldErrors[field.name];
              return (
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
                    onChange={val => {
                      setFormData(prev => ({ ...prev, [field.name]: val }));
                      // Clear field error on change
                      if (fieldErrors[field.name]) {
                        setFieldErrors(prev => {
                          const next = { ...prev };
                          delete next[field.name];
                          return next;
                        });
                      }
                    }}
                  />
                  {errs && errs.length > 0 && (
                    <div className="mt-1 space-y-0.5">
                      {errs.map((msg, i) => (
                        <p key={i} className="text-xs text-red-600">{msg}</p>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {mutation.isError && Object.keys(fieldErrors).length === 0 && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
              {parseApiError(mutation.error).general}
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
            className="flex items-center gap-2 px-4 py-2 bg-odum-600 hover:bg-odum-700 text-white text-sm font-semibold rounded-lg transition disabled:opacity-50"
          >
            <Save size={14} />
            {mutation.isPending ? 'Saving…' : isEdit ? 'Save changes' : 'Create'}
          </button>
        </div>
      </form>
    </div>
  );
}
