import { Sparkles, Tag, Layers, MapPin, Contact } from 'lucide-react';
import Tabs from '../components/Tabs';
import AdminServices from './AdminServices';
import AdminServiceTypes from './AdminServiceTypes';
import AdminServiceCategories from './AdminServiceCategories';
import AdminSpaLocations from './AdminSpaLocations';
import AdminSpaMasters from './AdminSpaMasters';

/**
 * Single admin screen for the whole SPA catalogue.
 * Replaces the former separate sidebar entries:
 * Услуги, Типы услуг, SPA категории, SPA кабинеты, SPA мастера.
 */
export default function AdminSpaCatalog() {
  return (
    <Tabs
      tabs={[
        { key: 'services', label: 'Услуги', icon: Sparkles, render: () => <AdminServices /> },
        { key: 'types', label: 'Типы услуг', icon: Tag, render: () => <AdminServiceTypes /> },
        { key: 'categories', label: 'Категории', icon: Layers, render: () => <AdminServiceCategories /> },
        { key: 'locations', label: 'Кабинеты', icon: MapPin, render: () => <AdminSpaLocations /> },
        { key: 'masters', label: 'Мастера', icon: Contact, render: () => <AdminSpaMasters /> },
      ]}
    />
  );
}
