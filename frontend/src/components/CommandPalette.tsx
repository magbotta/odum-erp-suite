import { useState, useEffect, useMemo, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search } from 'lucide-react';
import { useEntities } from '../meta/useEntities';
import type { EntityMeta } from '../meta/types';

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [activeIndex, setActiveIndex] = useState(0);
  const nav = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const { data: entities = [] } = useEntities();

  const close = useCallback(() => {
    setOpen(false);
    setQuery('');
    setActiveIndex(0);
  }, []);

  // Listen for the custom event dispatched by TopBar
  useEffect(() => {
    function handleOpen() {
      setOpen(true);
    }
    document.addEventListener('open-command-palette', handleOpen);
    return () => document.removeEventListener('open-command-palette', handleOpen);
  }, []);

  // Keyboard shortcut Cmd+K / Ctrl+K
  useEffect(() => {
    function handleKeydown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setOpen(o => !o);
      }
      if (e.key === 'Escape' && open) {
        close();
      }
    }
    document.addEventListener('keydown', handleKeydown);
    return () => document.removeEventListener('keydown', handleKeydown);
  }, [open, close]);

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const filtered = useMemo<EntityMeta[]>(() => {
    const q = query.toLowerCase().trim();
    if (!q) return entities.slice(0, 20);
    return entities.filter(
      e =>
        e.label.toLowerCase().includes(q) ||
        e.label_plural.toLowerCase().includes(q) ||
        e.app.toLowerCase().includes(q) ||
        e.entity.toLowerCase().includes(q)
    );
  }, [query, entities]);

  // Reset active index when filtered list changes
  useEffect(() => {
    setActiveIndex(0);
  }, [filtered]);

  function select(e: EntityMeta) {
    nav(`/entities/${e.app}/${e.entity}`);
    close();
  }

  function handleKeydown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex(i => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex(i => Math.max(i - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const item = filtered[activeIndex];
      if (item) select(item);
    } else if (e.key === 'Escape') {
      close();
    }
  }

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-24 p-4"
      aria-modal="true"
      role="dialog"
      aria-label="Command palette"
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/40" onClick={close} />

      {/* Panel */}
      <div className="relative bg-white rounded-xl shadow-2xl border border-gray-200 w-full max-w-lg overflow-hidden">
        {/* Search input */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-100">
          <Search size={16} className="text-slate-400 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={handleKeydown}
            placeholder="Search entities…"
            className="flex-1 text-sm text-slate-900 placeholder-slate-400 outline-none bg-transparent"
          />
          <kbd className="text-xs text-slate-400 bg-gray-100 px-1.5 py-0.5 rounded font-mono">Esc</kbd>
        </div>

        {/* Results */}
        <ul className="max-h-72 overflow-y-auto py-1" role="listbox">
          {filtered.length === 0 && (
            <li className="px-4 py-6 text-center text-sm text-slate-400">No matches found</li>
          )}
          {filtered.map((e, i) => (
            <li
              key={e.key}
              role="option"
              aria-selected={i === activeIndex}
              onClick={() => select(e)}
              onMouseEnter={() => setActiveIndex(i)}
              className={`flex items-center justify-between px-4 py-2.5 cursor-pointer transition text-sm ${
                i === activeIndex ? 'bg-odum-50 text-odum-700' : 'text-slate-700 hover:bg-gray-50'
              }`}
            >
              <span className="font-medium">{e.label_plural}</span>
              <span className="text-xs text-slate-400 capitalize">{e.app.replace(/_/g, ' ')}</span>
            </li>
          ))}
        </ul>

        {filtered.length > 0 && (
          <div className="px-4 py-2 border-t border-gray-100 text-xs text-slate-400 flex gap-3">
            <span>↑↓ navigate</span>
            <span>↵ open</span>
            <span>Esc close</span>
          </div>
        )}
      </div>
    </div>
  );
}
