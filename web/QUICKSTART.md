# Balandda Analytics Dashboard - Quick Start Guide

## Installation & Setup

### Prerequisites
- Node.js 18+
- npm or yarn

### Installation Steps

```bash
# Navigate to web directory
cd /sessions/funny-cool-gauss/mnt/balandda-bot/web

# Install dependencies
npm install

# Start development server
npm run dev

# The app will be available at http://localhost:5173
```

## Accessing the Analytics Dashboard

Once the development server is running:

1. Login with your Telegram account (existing auth mechanism)
2. Navigate to the Analytics section or visit `/analytics`
3. You'll see the dashboard home page with:
   - KPI cards showing income, expenses, profit, and occupancy
   - Charts showing financial trends
   - Navigation to other analytics pages

## Dashboard Pages

### 1. Overview (Обзор) - Default Page
**Path:** `/analytics/`

Features:
- 4 KPI cards with key metrics
- Line chart: Daily income vs expenses trend
- Pie chart: Income breakdown by payment method
- Bar chart: Income by property type

### 2. Income (Доходы)
**Path:** `/analytics/income`

Features:
- Filter by property, payment method, or search
- Summary table grouped by property
- Detailed transaction list
- Export button
- Total income summary

### 3. Expenses (Расходы)
**Path:** `/analytics/expenses`

Features:
- Category filter and search
- Pie chart showing expense distribution
- Progress bars for each category
- Detailed expense transaction list
- Summary of expenses by category

### 4. Properties (Объекты)
**Path:** `/analytics/properties`

Features:
- Property cards showing status and metrics
- Summary statistics (count, occupancy, revenue)
- Revenue bar chart
- Occupancy trend line chart
- Detailed property table

### 5. Reports (Отчёты)
**Path:** `/analytics/reports`

Features:
- List of daily reports
- Expandable details per report
- Summary statistics
- Properties, payment methods, and categories involved
- Download and view options

## Date Range Selection

All pages support date range filtering via the top-right date picker:
- **Сегодня** (Today) - Current day
- **Неделя** (Week) - Last 7 days
- **Месяц** (Month) - Current month
- **Произвольный** (Custom) - For future implementation

Changing the date range will automatically reload the data for all pages.

## Mock Data

All pages include comprehensive mock data. The dashboard will:
1. Try to fetch data from the API (`/api/v1/...`)
2. Automatically fall back to mock data if API is unavailable
3. Display mock data professionally even while API is being developed

This allows you to see the full UI immediately without waiting for backend implementation.

## Using with API

To connect the dashboard to the real backend API:

1. Ensure your API server is running and accessible at `/api/v1/`
2. The following endpoints should return the expected data:

```
GET /api/v1/daily-reports/list?from_date=2026-03-01&to_date=2026-03-31
GET /api/v1/daily-reports/detail/{report_id}
GET /api/v1/daily-reports/breakdown?from_date=2026-03-01&to_date=2026-03-31
GET /api/v1/structured-reports/list?from_date=2026-03-01&to_date=2026-03-31
GET /api/v1/properties
GET /api/v1/health
```

3. The dashboard will automatically use real data when available

## Common Tasks

### Viewing Total Income for a Period
1. Go to Overview page
2. Select desired date range
3. View KPI card titled "Доход за период"
4. See income breakdown pie chart

### Finding Expense by Category
1. Go to Expenses page
2. Select category from filter dropdown
3. View pie chart and progress bars
4. Check detailed table below

### Checking Property Occupancy
1. Go to Properties page
2. View property cards with occupancy percentages
3. Check occupancy trend chart
4. Review detailed property table

### Exporting Data
1. Navigate to Income or Expense page
2. Apply filters as needed
3. Click "Экспорт" (Export) button
4. Data will be downloaded (when backend is ready)

## Customization

### Changing Colors
Edit colors in components:
- Sidebar: `#1a5676` (primary blue)
- Accents: `#2d8c5a` (green), `#f59e0b` (amber)
- Red: `#dc2626` (negative)

Colors are in Tailwind classes throughout components.

### Modifying Filters
Edit filter options in pages:
- Properties: `/src/pages/IncomePage.jsx` - `properties` array
- Categories: `/src/pages/ExpensePage.jsx` - `categories` array
- Payment Methods: `/src/pages/IncomePage.jsx` - `paymentMethods` array

### Adding New Charts
Use Recharts library (already installed):
```jsx
import { LineChart, Bar, PieChart, BarChart } from 'recharts';
```

See existing examples in AnalyticsOverview.jsx

## Troubleshooting

### Dashboard Not Loading
- Check that the development server is running: `npm run dev`
- Verify you're logged in
- Check browser console for errors (F12 → Console tab)

### Charts Not Displaying
- Ensure recharts is installed: `npm install recharts`
- Check that data is being loaded (inspect in browser DevTools)
- Verify component imports

### API Data Not Loading
- Check API is running and accessible at `/api/v1/`
- Check browser Network tab to see API requests
- Verify response format matches expected structure
- Check console for error messages

### Styling Issues
- Ensure Tailwind CSS is properly configured
- Clear browser cache and reload
- Run `npm run build` to verify CSS compilation

## Development Tips

### Adding a New Page
1. Create new file in `src/pages/NewPage.jsx`
2. Add route in `src/pages/Analytics.jsx`
3. Add navigation item in `src/components/DashboardLayout.jsx`
4. Import and use analytics utilities from `src/utils/format.js`

### Formatting Numbers
Use the formatting utilities:
```jsx
import { formatCurrency, formatDate } from '../utils/format';

formatCurrency(1000000)  // Returns "1.000.000 UZS"
formatDate('2026-03-31') // Returns "31 марта 2026"
```

### Responsive Design Testing
```bash
# Use browser DevTools (F12)
# Click device toggle to test mobile/tablet sizes
```

## Performance Optimization

For production deployment:
1. Run: `npm run build`
2. Build output in `/dist/`
3. Serve from `/dist/` directory
4. Consider code splitting for large page bundles

## Support & Documentation

- See `ANALYTICS_DASHBOARD.md` for complete technical documentation
- See `FILE_STRUCTURE.txt` for project structure overview
- Check component files for inline comments and examples

## Next Steps

1. Install dependencies: `npm install`
2. Start dev server: `npm run dev`
3. Visit http://localhost:5173
4. Login and navigate to `/analytics`
5. Explore each page and its features
6. Connect to backend API when ready

Enjoy! The dashboard is ready to use and customize.
