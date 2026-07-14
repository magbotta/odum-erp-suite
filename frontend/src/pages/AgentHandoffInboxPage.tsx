import { useEffect, useMemo, useState } from 'react';
import {
  Bot, CheckCircle2, XCircle, PenLine, UserCog, Inbox as InboxIcon,
  AlertTriangle, Clock, Ban, HelpCircle, Gauge, ListChecks,
} from 'lucide-react';
import {
  useHandoffs, useHandoff, isSuspending,
  useApproveHandoff, useEditApproveHandoff, useRejectHandoff,
  useTakeOverHandoff, useAcknowledgeHandoff,
  type AgentHandoff, type HandoffTriggerReason,
} from '../api/agentHandoffs';
import { SkeletonTable } from '../components/Skeleton';
import ConfirmModal from '../components/ConfirmModal';
import { useToast } from '../components/Toast';

const TRIGGER_LABEL: Record<HandoffTriggerReason, string> = {
  low_confidence: 'Low Confidence',
  policy_boundary: 'Policy Boundary',
  missing_data: 'Missing Data',
  execution_error: 'Execution Error',
  stop_condition: 'Stop Condition',
  requires_approval: 'Requires Approval',
  max_steps: 'Max Steps Reached',
  kill_requested: 'Kill Switch',
  review_queue: 'Review Queue',
};

const TRIGGER_STYLE: Record<HandoffTriggerReason, string> = {
  low_confidence: 'bg-amber-50 text-amber-700 border-amber-200',
  policy_boundary: 'bg-red-50 text-red-700 border-red-200',
  missing_data: 'bg-amber-50 text-amber-700 border-amber-200',
  execution_error: 'bg-red-50 text-red-700 border-red-200',
  stop_condition: 'bg-slate-50 text-slate-600 border-slate-200',
  requires_approval: 'bg-blue-50 text-blue-700 border-blue-200',
  max_steps: 'bg-slate-50 text-slate-600 border-slate-200',
  kill_requested: 'bg-red-50 text-red-700 border-red-200',
  review_queue: 'bg-violet-50 text-violet-700 border-violet-200',
};

const TRIGGER_ICON: Record<HandoffTriggerReason, typeof AlertTriangle> = {
  low_confidence: Gauge,
  policy_boundary: Ban,
  missing_data: HelpCircle,
  execution_error: AlertTriangle,
  stop_condition: Clock,
  requires_approval: HelpCircle,
  max_steps: Clock,
  kill_requested: Ban,
  review_queue: ListChecks,
};

const STATUS_TABS = [
  { key: 'pending', label: 'Needs Action' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'expired', label: 'Expired' },
] as const;

function timeAgo(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

export default function AgentHandoffInboxPage() {
  const [statusTab, setStatusTab] = useState<string>('pending');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: handoffs = [], isLoading } = useHandoffs(statusTab);

  useEffect(() => {
    // Keep selection valid as the list refetches/filters change
    if (selectedId && !handoffs.some(h => h.id === selectedId)) {
      setSelectedId(handoffs[0]?.id ?? null);
    } else if (!selectedId && handoffs.length > 0) {
      setSelectedId(handoffs[0].id);
    }
  }, [handoffs, selectedId]);

  const reviewQueueCount = handoffs.filter(h => h.trigger_reason === 'review_queue').length;
  const actionCount = handoffs.length - reviewQueueCount;

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
          <Bot size={22} className="text-odum-600" />
          Agent Handoff Inbox
        </h1>
        <p className="text-slate-500 text-sm mt-1">
          Review and resolve human checkpoints raised by AI agents (ADR-0001).
        </p>
      </div>

      {/* Status tabs */}
      <div className="flex items-center gap-1 border-b border-gray-200 mb-4">
        {STATUS_TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => setStatusTab(tab.key)}
            className={`px-3 py-2 text-sm font-medium border-b-2 -mb-px transition ${
              statusTab === tab.key
                ? 'border-odum-600 text-odum-700'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            {tab.label}
            {tab.key === 'pending' && actionCount > 0 && (
              <span className="ml-1.5 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-red-600 text-white text-[10px] font-semibold">
                {actionCount}
              </span>
            )}
          </button>
        ))}
        {statusTab === 'pending' && reviewQueueCount > 0 && (
          <span className="ml-auto mr-2 text-xs text-violet-600 flex items-center gap-1">
            <ListChecks size={12} />
            {reviewQueueCount} in review queue (post-hoc, run already continued)
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-4">
        <HandoffList
          handoffs={handoffs}
          loading={isLoading}
          selectedId={selectedId}
          onSelect={setSelectedId}
        />
        <HandoffDetail
          id={selectedId}
          onResolved={() => {
            /* selection auto-advances via the effect above once the list refetches */
          }}
        />
      </div>
    </div>
  );
}

function HandoffList({
  handoffs, loading, selectedId, onSelect,
}: {
  handoffs: AgentHandoff[];
  loading: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  if (loading) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-3">
        <SkeletonTable rows={5} cols={1} />
      </div>
    );
  }

  if (handoffs.length === 0) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-8 text-center">
        <InboxIcon size={28} className="mx-auto text-slate-300 mb-2" />
        <div className="text-sm text-slate-500">Nothing here.</div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100 overflow-hidden max-h-[70vh] overflow-y-auto">
      {handoffs.map(h => {
        const Icon = TRIGGER_ICON[h.trigger_reason];
        const active = h.id === selectedId;
        return (
          <button
            key={h.id}
            onClick={() => onSelect(h.id)}
            className={`w-full text-left px-4 py-3 transition ${
              active ? 'bg-odum-50' : 'hover:bg-gray-50'
            }`}
          >
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="text-sm font-semibold text-slate-800 truncate">{h.agent_name}</span>
              <span className="text-[11px] text-slate-400 shrink-0">{timeAgo(h.created_at)}</span>
            </div>
            <div className={`inline-flex items-center gap-1 text-[11px] font-medium border rounded-full px-2 py-0.5 mb-1.5 ${TRIGGER_STYLE[h.trigger_reason]}`}>
              <Icon size={11} />
              {TRIGGER_LABEL[h.trigger_reason]}
            </div>
            <p className="text-xs text-slate-500 line-clamp-2">{h.trigger_detail}</p>
          </button>
        );
      })}
    </div>
  );
}

function HandoffDetail({ id, onResolved }: { id: string | null; onResolved: () => void }) {
  const { data: h, isLoading } = useHandoff(id);
  const toast = useToast();

  const approve = useApproveHandoff();
  const editApprove = useEditApproveHandoff();
  const reject = useRejectHandoff();
  const takeOver = useTakeOverHandoff();
  const acknowledge = useAcknowledgeHandoff();

  const [notes, setNotes] = useState('');
  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectReason, setRejectReason] = useState('');
  const [takeOverConfirmOpen, setTakeOverConfirmOpen] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editedJson, setEditedJson] = useState('');
  const [editError, setEditError] = useState('');

  useEffect(() => {
    setNotes('');
    setRejectReason('');
    setEditMode(false);
    setEditError('');
    setEditedJson(h?.proposed_action ? JSON.stringify(h.proposed_action, null, 2) : '{}');
  }, [id, h?.proposed_action]);

  if (!id) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-12 text-center text-sm text-slate-400">
        Select a handoff to review.
      </div>
    );
  }

  if (isLoading || !h) {
    return (
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <SkeletonTable rows={4} cols={1} />
      </div>
    );
  }

  const isReviewQueue = h.trigger_reason === 'review_queue';
  const resolved = h.status !== 'pending';
  const busy = approve.isPending || editApprove.isPending || reject.isPending
    || takeOver.isPending || acknowledge.isPending;

  async function handleApprove() {
    if (!h) return;
    try {
      const res = await approve.mutateAsync({ id: h.id, notes });
      toast.success(res.message);
      onResolved();
    } catch {
      toast.error('Failed to approve handoff.');
    }
  }

  async function handleEditApprove() {
    if (!h) return;
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(editedJson);
    } catch {
      setEditError('Not valid JSON — fix the payload before submitting.');
      return;
    }
    setEditError('');
    try {
      const res = await editApprove.mutateAsync({ id: h.id, editedPayload: parsed, notes });
      toast.success(res.message);
      setEditMode(false);
      onResolved();
    } catch {
      toast.error('Failed to submit edited action.');
    }
  }

  async function handleReject() {
    if (!h || !rejectReason.trim()) return;
    try {
      const res = await reject.mutateAsync({ id: h.id, reason: rejectReason.trim() });
      toast.success(res.message);
      setRejectOpen(false);
      onResolved();
    } catch {
      toast.error('Failed to reject handoff.');
    }
  }

  async function handleTakeOver() {
    if (!h) return;
    try {
      const res = await takeOver.mutateAsync({ id: h.id, notes });
      toast.success(res.message);
      setTakeOverConfirmOpen(false);
      onResolved();
    } catch {
      toast.error('Failed to take over run.');
    }
  }

  async function handleAcknowledge() {
    if (!h) return;
    try {
      const res = await acknowledge.mutateAsync({ id: h.id, notes });
      toast.success(res.message);
      onResolved();
    } catch {
      toast.error('Failed to acknowledge entry.');
    }
  }

  const Icon = TRIGGER_ICON[h.trigger_reason];

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-6 min-w-0">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <Bot size={16} className="text-odum-600" />
            <span className="text-sm font-semibold text-slate-800">{h.agent_name}</span>
            <span className="text-xs text-slate-400">· run {h.run_id.slice(0, 8)}</span>
          </div>
          <div className={`inline-flex items-center gap-1.5 text-xs font-medium border rounded-full px-2.5 py-1 ${TRIGGER_STYLE[h.trigger_reason]}`}>
            <Icon size={13} />
            {TRIGGER_LABEL[h.trigger_reason]}
          </div>
        </div>
        <div className="text-right shrink-0">
          {h.confidence != null && (
            <div className="text-xs text-slate-500 mb-1">
              Confidence: <span className="font-semibold text-slate-700">{Math.round(h.confidence * 100)}%</span>
            </div>
          )}
          <div className="text-[11px] text-slate-400">{timeAgo(h.created_at)}</div>
        </div>
      </div>

      {resolved && (
        <div className="mb-4 rounded-lg bg-slate-50 border border-slate-200 px-3 py-2 text-xs text-slate-600">
          Resolved as <span className="font-semibold">{h.status}</span>
          {h.resolution_notes && <> — “{h.resolution_notes}”</>}
        </div>
      )}

      <p className="text-sm text-slate-700 mb-4">{h.trigger_detail}</p>

      {h.proposed_reasoning && (
        <div className="mb-4">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Agent's Reasoning</div>
          <p className="text-sm text-slate-600 bg-gray-50 rounded-lg border border-gray-100 p-3">{h.proposed_reasoning}</p>
        </div>
      )}

      {h.proposed_action && (
        <div className="mb-4">
          <div className="flex items-center justify-between mb-1">
            <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Proposed Action</div>
            {!resolved && !isReviewQueue && (
              <button
                onClick={() => setEditMode(m => !m)}
                className="text-xs text-odum-700 hover:underline flex items-center gap-1"
              >
                <PenLine size={12} />
                {editMode ? 'Cancel edit' : 'Edit before approving'}
              </button>
            )}
          </div>
          {editMode ? (
            <div>
              <textarea
                value={editedJson}
                onChange={e => setEditedJson(e.target.value)}
                rows={8}
                className="w-full font-mono text-xs bg-slate-900 text-slate-100 rounded-lg p-3 border border-slate-700 focus:outline-none focus:ring-2 focus:ring-odum-500"
                spellCheck={false}
              />
              {editError && <p className="text-xs text-red-600 mt-1">{editError}</p>}
            </div>
          ) : (
            <pre className="text-xs bg-slate-900 text-slate-100 rounded-lg p-3 overflow-x-auto">
              {JSON.stringify(h.proposed_action, null, 2)}
            </pre>
          )}
        </div>
      )}

      {h.data_gathered && Object.keys(h.data_gathered).length > 0 && (
        <details className="mb-4 group">
          <summary className="text-xs font-semibold text-slate-500 uppercase tracking-wide cursor-pointer select-none">
            Data Gathered So Far ({Object.keys(h.data_gathered).length})
          </summary>
          <pre className="text-xs bg-gray-50 border border-gray-100 rounded-lg p-3 mt-1 overflow-x-auto max-h-64 overflow-y-auto">
            {JSON.stringify(h.data_gathered, null, 2)}
          </pre>
        </details>
      )}

      {h.record_links.length > 0 && (
        <div className="mb-4">
          <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-1">Related Records</div>
          <div className="flex flex-wrap gap-2">
            {h.record_links.map(link => (
              <a
                key={`${link.entity}-${link.id}`}
                href={link.api_url || undefined}
                className="text-xs px-2 py-1 rounded-md bg-gray-50 border border-gray-200 text-slate-600 hover:text-odum-700 hover:border-odum-300"
              >
                {link.entity}: {link.label}
              </a>
            ))}
          </div>
        </div>
      )}

      {!resolved && (
        <>
          <div className="border-t border-gray-100 pt-4 mt-4">
            <label className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Notes (optional)</label>
            <textarea
              value={notes}
              onChange={e => setNotes(e.target.value)}
              rows={2}
              placeholder="Add context for the audit trail…"
              className="w-full mt-1 text-sm rounded-lg border border-gray-200 p-2 focus:outline-none focus:ring-2 focus:ring-odum-500"
            />
          </div>

          {isReviewQueue ? (
            <div className="flex justify-end mt-3">
              <button
                onClick={handleAcknowledge}
                disabled={busy}
                className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg bg-violet-600 hover:bg-violet-700 text-white transition disabled:opacity-50"
              >
                <ListChecks size={14} />
                Acknowledge
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap justify-end gap-2 mt-3">
              <button
                onClick={() => setTakeOverConfirmOpen(true)}
                disabled={busy}
                className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-gray-200 text-slate-600 hover:bg-gray-50 transition disabled:opacity-50"
              >
                <UserCog size={14} />
                Take Over
              </button>
              <button
                onClick={() => setRejectOpen(true)}
                disabled={busy}
                className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium rounded-lg border border-red-200 text-red-600 hover:bg-red-50 transition disabled:opacity-50"
              >
                <XCircle size={14} />
                Reject
              </button>
              {editMode ? (
                <button
                  onClick={handleEditApprove}
                  disabled={busy}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg bg-odum-600 hover:bg-odum-700 text-white transition disabled:opacity-50"
                >
                  <PenLine size={14} />
                  Approve With Edits
                </button>
              ) : (
                <button
                  onClick={handleApprove}
                  disabled={busy}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm font-semibold rounded-lg bg-odum-600 hover:bg-odum-700 text-white transition disabled:opacity-50"
                >
                  <CheckCircle2 size={14} />
                  Approve
                </button>
              )}
            </div>
          )}
        </>
      )}

      {/* Reject reason modal */}
      {rejectOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/40" onClick={() => setRejectOpen(false)} />
          <div className="relative bg-white rounded-xl shadow-xl border border-gray-200 w-full max-w-sm p-6">
            <h2 className="text-base font-bold text-slate-900 mb-2">Reject this action</h2>
            <p className="text-sm text-slate-600 mb-3">
              A reason is required — it's sent back to the agent as a learning signal.
            </p>
            <textarea
              value={rejectReason}
              onChange={e => setRejectReason(e.target.value)}
              rows={3}
              autoFocus
              placeholder="Why is this being rejected?"
              className="w-full text-sm rounded-lg border border-gray-200 p-2 mb-4 focus:outline-none focus:ring-2 focus:ring-red-400"
            />
            <div className="flex justify-end gap-3">
              <button
                onClick={() => setRejectOpen(false)}
                className="px-4 py-2 text-sm border border-gray-200 rounded-lg hover:bg-gray-50 transition text-slate-700"
              >
                Cancel
              </button>
              <button
                onClick={handleReject}
                disabled={!rejectReason.trim() || busy}
                className="px-4 py-2 text-sm font-semibold rounded-lg bg-red-600 hover:bg-red-700 text-white transition disabled:opacity-50"
              >
                Reject
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmModal
        open={takeOverConfirmOpen}
        title="Take over this run?"
        message="The agent run will be stopped permanently (status: killed). You'll need to complete the remaining work yourself."
        confirmLabel="Take Over"
        danger
        onConfirm={handleTakeOver}
        onCancel={() => setTakeOverConfirmOpen(false)}
      />
    </div>
  );
}
