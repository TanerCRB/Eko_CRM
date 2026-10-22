/** Prototype handoff contracts, not an accepted database schema or API. */
export type UserId = string;
export type VisitState = 'planned' | 'held' | 'cancelled' | 'decision';
export type ActionStatus = 'todo' | 'progress' | 'done' | 'cancelled';
export interface User { id: UserId; name: string; initials: string; role: 'rep' | 'manager'; region: string }
export interface Contact { kind: 'phone' | 'email'; value: string; label: string; primary: boolean }
export interface Customer {
  id: string; name: string; country: string; street: string; town: string; postcode: string;
  nip: string; contacts: Contact[]; owner: UserId; archived: boolean;
}
export interface Visit {
  id: string; customerId: string; owner: UserId; start: string; end: string;
  /** Held is derived from end time and is never stored. */
  status: Exclude<VisitState, 'held'>;
  moved: boolean; unsynced: boolean; purpose: string; location: string;
}
export interface Note { id: string; customerId: string; visitId: string | null; author: UserId; body: string; created: string }
export interface FollowUp {
  id: string; customerId: string; noteId: string; owner: UserId; author: UserId;
  title: string; due: string; status: ActionStatus; changedBy: UserId;
}
export interface DemoState {
  version: 1; users: User[]; customers: Customer[]; visits: Visit[]; notes: Note[]; actions: FollowUp[];
  connections: Record<UserId, 'connected' | 'expired'>;
}
export interface VisitMetrics { planned: number; held: number; moved: number; cancelled: number; decision: number }
export interface StatusBadgeProps { state: VisitState | ActionStatus | 'moved' | 'unsynced'; label?: string }
export interface VisitCardProps { visit: Visit; customer: Customer; onOpen: (visitId: string) => void }
export interface CustomerSheetProps { customer: Customer; visits: Visit[]; notes: Note[]; onClose: () => void }
export interface FollowUpCardProps { action: FollowUp; allowedTransitions: ActionStatus[]; onStatusChange: (id: string, next: ActionStatus) => void }
