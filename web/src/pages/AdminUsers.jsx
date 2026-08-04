import { Users as UsersIcon, UserCog, UserPlus } from 'lucide-react';
import Tabs from '../components/Tabs';
import Users from './Users';
import AdminStaff from './AdminStaff';
import RegistrationRequests from './RegistrationRequests';

/**
 * Single admin screen for everything user-related.
 * Replaces the former separate sidebar entries: Users, Сотрудники, Заявки.
 */
export default function AdminUsers() {
  return (
    <Tabs
      tabs={[
        { key: 'users', label: 'Пользователи', icon: UsersIcon, render: () => <Users /> },
        { key: 'staff', label: 'Сотрудники', icon: UserCog, render: () => <AdminStaff /> },
        { key: 'requests', label: 'Заявки', icon: UserPlus, render: () => <RegistrationRequests /> },
      ]}
    />
  );
}
