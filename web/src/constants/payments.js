// Single source of truth for payment methods across every screen that records money
// (accommodation calendar, SPA schedule, reports). Mirrors PaymentMethod +
// PAYMENT_METHOD_LABELS in db/enums.py — keep the two in sync.
//
// PREPAYMENT is deliberately absent: it is produced by the prepayment flow, never
// chosen by hand, and offering it here would let staff record income that no
// wallet or prepayment record backs.
export const PAYMENT_METHODS = [
  { value: 'CASH', label: 'Наличные' },
  { value: 'CARD_TRANSFER', label: 'Перевод на карту' },
  { value: 'WIRE_TRANSFER', label: 'Перечисление' },
  { value: 'TERMINAL_VISA', label: 'Терминал Visa' },
  { value: 'TERMINAL_UZCARD', label: 'Терминал UzCard' },
  { value: 'PAYME', label: 'PayMe' },
];

export const PAYMENT_METHOD_LABELS = Object.fromEntries(
  PAYMENT_METHODS.map((m) => [m.value, m.label]),
);
