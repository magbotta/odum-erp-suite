import type { FieldDef } from '../../meta/types';

interface Props {
  field: FieldDef;
  value?: unknown;
  onChange?: (val: unknown) => void;
  readOnly?: boolean;
}

export default function FieldRenderer({ field, value, onChange, readOnly }: Props) {
  const base =
    'w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-odum-500 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-500';
  const disabled = readOnly || field.read_only;
  const strVal = value == null ? '' : String(value);

  if (field.type === 'boolean') {
    return (
      <input
        type="checkbox"
        checked={Boolean(value)}
        disabled={disabled}
        onChange={e => onChange?.(e.target.checked)}
        className="h-4 w-4 rounded border-gray-300 text-odum-600 focus:ring-odum-500"
      />
    );
  }

  if (field.type === 'text' || field.type === 'json') {
    return (
      <textarea
        rows={3}
        value={strVal}
        disabled={disabled}
        onChange={e => onChange?.(e.target.value)}
        className={base}
      />
    );
  }

  if ((field.type === 'select' || field.type === 'multiselect') && field.options?.length) {
    return (
      <select
        value={strVal}
        disabled={disabled}
        onChange={e => onChange?.(e.target.value)}
        className={base}
      >
        <option value="">— Select —</option>
        {field.options.map(opt => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
    );
  }

  if (field.type === 'date') {
    return (
      <input
        type="date"
        value={strVal}
        disabled={disabled}
        onChange={e => onChange?.(e.target.value)}
        className={base}
      />
    );
  }

  if (field.type === 'datetime') {
    return (
      <input
        type="datetime-local"
        value={strVal}
        disabled={disabled}
        onChange={e => onChange?.(e.target.value)}
        className={base}
      />
    );
  }

  if (field.type === 'integer' || field.type === 'float' || field.type === 'currency') {
    return (
      <input
        type="number"
        step={field.type === 'integer' ? '1' : '0.01'}
        value={strVal}
        disabled={disabled}
        onChange={e => onChange?.(e.target.value)}
        className={base}
      />
    );
  }

  if (field.type === 'email') {
    return (
      <input
        type="email"
        value={strVal}
        disabled={disabled}
        onChange={e => onChange?.(e.target.value)}
        className={base}
      />
    );
  }

  if (field.type === 'url') {
    return (
      <input
        type="url"
        value={strVal}
        disabled={disabled}
        onChange={e => onChange?.(e.target.value)}
        className={base}
      />
    );
  }

  // Default: string / phone / link / geopoint / geofence / route
  return (
    <input
      type="text"
      value={strVal}
      disabled={disabled}
      onChange={e => onChange?.(e.target.value)}
      className={base}
      placeholder={field.type === 'link' ? 'UUID' : undefined}
    />
  );
}
