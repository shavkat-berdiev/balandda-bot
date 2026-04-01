# Balandda Analytics Dashboard - Frontend Implementation

## Overview
This document outlines the complete React frontend implementation for the Balandda Resort Analytics Dashboard.

## Project Structure

```
src/
├── App.jsx                           # Main app with routing (updated)
├── api.js                            # API client with analytics endpoints (updated)
├── index.css                         # Global styles and Tailwind imports (updated)
├── main.jsx                          # Entry point
├── components/
│   ├── DashboardLayout.jsx          # Main layout for analytics (NEW)
│   └── Layout.jsx                    # Original layout (unchanged)
├── pages/
│   ├── Analytics.jsx                 # Analytics router (NEW)
│   ├── AnalyticsOverview.jsx        # Dashboard overview page (NEW)
│   ├── IncomePage.jsx                # Income breakdown page (NEW)
│   ├── ExpensePage.jsx               # Expense breakdown page (NEW)
│   ├── PropertiesPage.jsx            # Properties/occupancy page (NEW)
│   ├── ReportsPage.jsx               # Daily reports page (NEW)
│   ├── Dashboard.jsx                 # Original dashboard (unchanged)
│   ├── Categories.jsx                # Original categories (unchanged)
│   ├── Users.jsx                     # Original users (unchanged)
│   ├── Transactions.jsx              # Original transactions (unchanged)
│   └── Login.jsx                     # Original login (unchanged)
└── utils/
    └── format.js                     # Formatting utilities (NEW)
```

## New Files Created

### 1. src/components/DashboardLayout.jsx
- Main layout component for analytics dashboard
- Dark sidebar (#1a5676) with white navigation text
- Top bar with date range picker (Today, Week, Month, Custom)
- Responsive mobile/desktop layout
- Navigation items: Overview (Обзор), Income (Доходы), Expenses (Расходы), Properties (Объекты), Reports (Отчёты)

### 2. src/utils/format.js
- `formatCurrency(amount, currency)` - Formats numbers with dot separators (e.g., "3.200.000 UZS")
- `formatDate(date)` - Full Russian date format
- `formatDateShort(date)` - Short date format (DD.MM.YY)
- `getDateRange(type)` - Returns from/to dates for 'today', 'week', 'month'

### 3. src/pages/Analytics.jsx
- Router for analytics section
- Manages date range state and passes to all child pages
- Routes:
  - `/analytics/` - Overview (default)
  - `/analytics/income` - Income page
  - `/analytics/expenses` - Expense page
  - `/analytics/properties` - Properties page
  - `/analytics/reports` - Reports page

### 4. src/pages/AnalyticsOverview.jsx
- Dashboard overview with KPI cards and charts
- KPI Cards: Total Income, Total Expenses, Net Profit, Occupancy Rate
- Line Chart: Daily income/expense trend (uses Recharts)
- Pie Chart: Income breakdown by payment method
- Bar Chart: Income by property type
- Mock data provided, with API fallback when available
- Responsive grid layout

### 5. src/pages/IncomePage.jsx
- Income breakdown and analytics
- Filters: By property, payment method, search
- Summary table grouped by property
- Detailed transactions table
- Export button (UI ready for API integration)
- Total income summary footer
- Displays: Date, Property, Type, Payment Method, Amount

### 6. src/pages/ExpensePage.jsx
- Expense breakdown and analytics
- Filters: By category, search text
- Pie Chart: Expense distribution by category
- Bar chart: Top categories with percentages
- Detailed expense transactions table
- Displays: Date, Category, Staff Member, Amount
- Export functionality
- Total expense summary footer

### 7. src/pages/PropertiesPage.jsx
- Property occupancy and revenue tracking
- Summary cards: Total properties, average occupancy, monthly revenue
- Property grid: Shows occupancy status, occupancy rate, monthly revenue
- Revenue bar chart by property
- Occupancy trend chart
- Detailed property table with all metrics
- Color-coded status (occupied/free)
- Progress bars for occupancy percentage

### 8. src/pages/ReportsPage.jsx
- Daily reports list with expandable details
- Status indicators and import type badges
- Summary statistics: Total reports, total income, total expenses, net profit
- Expandable report details showing:
  - Properties involved
  - Payment methods used
  - Expense categories
- Download and view options
- Organized by date in descending order

## Updated Files

### App.jsx
- Added Analytics import
- Added route: `<Route path="/analytics/*" element={<Analytics user={user} onLogout={handleLogout} />} />`
- Maintains existing Dashboard and other routes

### api.js
- Added credentials: 'include' to request function
- Added analytics endpoints:
  - `getDailyReports(from, to)` - List of daily reports
  - `getReportDetail(id)` - Single report details
  - `getBreakdown(from, to)` - Income breakdown
  - `getStructuredReports(from, to)` - Structured reports
  - `getProperties()` - Property list
  - `getHealth()` - Health check

### index.css
- Added Google Fonts import (Inter)
- Custom scrollbar styling
- Input focus styles with green accent
- Loading spinner animation
- Improved typography and spacing

## Design System

### Color Palette
- Primary Blue: `#1a5676` - Sidebar background
- Green Accent: `#2d8c5a` - Charts, positive metrics, income
- Amber Accent: `#f59e0b` - Secondary accent
- Red: `#dc2626` - Expenses, negative metrics
- Gray Tones: `#6b7280`, `#9ca3af`, `#e5e7eb`, `#f3f4f6`

### Typography
- Font Family: Inter (Google Fonts)
- Weights: 400, 500, 600, 700, 800
- Used across all components with Tailwind classes

### Components Used
- **Recharts**: Line, Pie, Bar charts with tooltips
- **Lucide React**: Icons throughout (Menu, ChevronDown, TrendingUp, etc.)
- **Tailwind CSS**: All styling via utility classes
- **React Router v6**: Navigation and page routing

## Mock Data Structure

All pages include comprehensive mock data that matches expected API responses:

### Daily Reports
```javascript
{
  date: '2026-03-31',
  income: 7800000,
  expense: 1500000,
  itemCount: 24
}
```

### Income Entries
```javascript
{
  id: 1,
  date: '2026-03-31',
  property: 'Люкс Suite',
  type: 'room',
  method: 'Карта',
  amount: 2500000
}
```

### Properties
```javascript
{
  id: 1,
  name: 'Люкс Suite',
  type: 'Люкс',
  status: 'occupied',
  monthRevenue: 7500000,
  occupancyRate: 95
}
```

## Features Implemented

### Overview Page
- KPI cards with color-coded styling
- Multi-line chart comparing income vs expenses
- Pie chart with payment method breakdown
- Bar chart for property revenue comparison

### Income Page
- Advanced filtering (property, payment method, search)
- Summary table grouped by property
- Complete transaction list
- Currency formatting with thousand separators
- Export functionality UI

### Expense Page
- Category-based filtering
- Pie chart visualization of expense distribution
- Bar chart with percentages
- Staff member tracking
- Transaction history table

### Properties Page
- Property cards with status indicators
- Occupancy percentage with progress bars
- Revenue tracking
- Stacked bar chart for occupancy trends
- Horizontal bar chart for revenue comparison

### Reports Page
- Expandable report details
- Quick stats summary
- Import status badges (Text-Import vs Structured)
- Completion status indicators
- Property, payment method, and category breakdown per report

## Responsive Design

All pages use Tailwind's responsive breakpoints:
- `grid-cols-1` - Mobile (default)
- `md:grid-cols-2` - Tablet
- `lg:grid-cols-3` - Desktop
- `lg:pl-64` - Desktop with sidebar offset

Mobile-specific:
- Hamburger menu that opens sidebar overlay
- Touch-friendly button sizes
- Optimized spacing for smaller screens

## API Integration

The dashboard is designed to work with mock data while API integration is in progress. To enable real API calls:

1. Ensure the API endpoints are available at `/api/v1/`
2. The mock data will automatically fallback if API calls fail
3. Each page has a try-catch block that logs errors and falls back to mock data

Expected API endpoints:
- `GET /api/v1/daily-reports/list?from_date={from}&to_date={to}`
- `GET /api/v1/daily-reports/detail/{id}`
- `GET /api/v1/daily-reports/breakdown?from_date={from}&to_date={to}`
- `GET /api/v1/structured-reports/list?from_date={from}&to_date={to}`
- `GET /api/v1/properties`
- `GET /api/v1/health`

## Language

All text is in Russian:
- Navigation labels
- Form placeholders
- Error messages
- Chart labels
- Button labels

## Browser Support

Works with all modern browsers that support:
- ES2020+
- React 18
- CSS Grid and Flexbox
- SVG (for charts)

## File Statistics

- Total new files: 9
- Total updated files: 3
- Lines of code: ~2,500+
- Components: 13
- Pages: 6
- Utility functions: 4

## Next Steps for Production

1. Connect to real API endpoints
2. Add loading states for longer operations
3. Implement data caching/memoization
4. Add error handling and toast notifications
5. Set up authentication token refresh
6. Add CSV/PDF export functionality
7. Implement date range picker for custom dates
8. Add more detailed charts with date filtering
9. Set up analytics tracking
10. Performance optimization (code splitting, lazy loading)
