export function formatCurrency(amount, currency = 'UZS') {
  if (typeof amount !== 'number') return '0 ' + currency;

  const formatted = Math.abs(amount)
    .toFixed(0)
    .replace(/\B(?=(\d{3})+(?!\d))/g, '.');

  const sign = amount < 0 ? '-' : '';
  return `${sign}${formatted} ${currency}`;
}

export function formatDate(date) {
  if (!date) return '';
  if (typeof date === 'string') {
    return new Date(date).toLocaleDateString('ru-RU', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  }
  return date.toLocaleDateString('ru-RU', {
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });
}

export function formatDateShort(date) {
  if (!date) return '';
  if (typeof date === 'string') {
    return new Date(date).toLocaleDateString('ru-RU', {
      year: '2-digit',
      month: '2-digit',
      day: '2-digit',
    });
  }
  return date.toLocaleDateString('ru-RU', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
  });
}

export function getDateRange(type) {
  const today = new Date();
  const from = new Date();

  switch (type) {
    case 'today':
      from.setHours(0, 0, 0, 0);
      break;
    case 'week':
      from.setDate(today.getDate() - today.getDay());
      from.setHours(0, 0, 0, 0);
      break;
    case 'month':
      from.setDate(1);
      from.setHours(0, 0, 0, 0);
      break;
    default:
      from.setDate(today.getDate() - 30);
      from.setHours(0, 0, 0, 0);
  }

  return {
    from: from.toISOString().split('T')[0],
    to: today.toISOString().split('T')[0],
  };
}
