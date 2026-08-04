import { Home, Tag, CalendarOff } from 'lucide-react';
import Tabs from '../components/Tabs';
import AdminProperties from './AdminProperties';
import AdminTypeLabels from './AdminTypeLabels';
import AdminBlockedDates from './AdminBlockedDates';

/**
 * Single admin screen for the resort inventory.
 * Replaces the former separate sidebar entries: Объекты, Названия типов, Закрытые даты.
 */
export default function AdminPropertiesHub() {
  return (
    <Tabs
      tabs={[
        { key: 'properties', label: 'Объекты', icon: Home, render: () => <AdminProperties /> },
        { key: 'type-labels', label: 'Названия типов', icon: Tag, render: () => <AdminTypeLabels /> },
        { key: 'blocked-dates', label: 'Закрытые даты', icon: CalendarOff, render: () => <AdminBlockedDates /> },
      ]}
    />
  );
}
