import { useParams } from 'react-router-dom';
import { useEntityMeta } from '../meta/useEntities';
import ListView from '../views/ListView';
import FormView from '../views/FormView';
import DetailView from '../views/DetailView';
import { useQuery } from '@tanstack/react-query';
import api from '../api/client';

export default function EntityPage({ mode }: { mode: 'list' | 'new' | 'detail' | 'edit' }) {
  const { app, entity, id } = useParams<Record<string, string>>();
  const { data: meta, isLoading } = useEntityMeta(app!, entity!);

  const { data: record } = useQuery<Record<string, unknown>>({
    queryKey: ['entity', meta?.api_path, id],
    queryFn: () => api.get(`${meta!.api_path}/${id}`).then(r => r.data),
    enabled: Boolean(meta && id && (mode === 'detail' || mode === 'edit')),
  });

  if (isLoading || !meta) {
    return (
      <div className="p-10 text-center text-slate-400 text-sm animate-pulse">
        Loading entity definition…
      </div>
    );
  }

  if (mode === 'list') return <ListView meta={meta} />;
  if (mode === 'new') return <FormView meta={meta} />;
  if (mode === 'edit') return <FormView meta={meta} initialData={record} recordId={id} />;
  if (mode === 'detail') return <DetailView meta={meta} recordId={id!} />;
  return null;
}
