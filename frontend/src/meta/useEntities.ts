import { useQuery } from '@tanstack/react-query';
import api from '../api/client';
import type { EntityMeta } from './types';

export function useEntities() {
  return useQuery<EntityMeta[]>({
    queryKey: ['meta', 'entities'],
    queryFn: () => api.get('/meta/entities/').then(r => r.data),
    staleTime: Infinity,
  });
}

export function useEntityMeta(app: string, entity: string) {
  return useQuery<EntityMeta>({
    queryKey: ['meta', 'entities', app, entity],
    queryFn: () => api.get(`/meta/entities/${app}/${entity}/`).then(r => r.data),
    staleTime: Infinity,
    enabled: Boolean(app && entity),
  });
}
