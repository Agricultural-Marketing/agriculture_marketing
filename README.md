## Agricultural Marketing

Custom Frappe app for tracking agricultural marketing operations (invoices, collections, trial balances, and related reports).

### Features
- Invoice workflow with items and commission handling
- Collection forms and statement pages
- Trial balance sections (cash, customer, supplier, income, expense, share capital, tax)
- Aggregated reporting and detailed report pages
- Arabic translations via `translations/ar.csv`

### Prerequisites
- Frappe/Bench installed and a working site
- Python 3.10+ (per your Frappe stack)

### Install
From your bench directory:

```bash
# get app (local path or git)
bench get-app /home/salama/benches/bench-15/apps/agricultural_marketing

# or via git if hosted
# bench get-app agricultural_marketing https://your.git.repo/agricultural_marketing.git

# install on a site
bench --site <your-site> install-app agricultural_marketing
```

### Usage
After installation, log in and use:
- Pages: `Collection Form`, `Detailed Report`, `Statement Forms`
- Doctypes: `Invoice Form` (+ items and commissions), trial balance section doctypes

### Development
Common commands:
```bash
# start services and auto-build assets
bench start

# apply changes
bench --site <your-site> migrate
bench --site <your-site> clear-cache

# watch JS/CSS changes
bench watch
```

### Tests
```bash
bench --site <your-site> run-tests --app agricultural_marketing
```

### Translations
Update `translations/ar.csv` and rebuild:
```bash
bench build
bench --site <your-site> clear-cache
```

### License
MIT