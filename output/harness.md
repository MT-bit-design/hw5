# Campus Customs Agent Harness

## Data

- Original: `data/campus_customs.db` (read-only, never change it)
- Working copy: `data/campus_customs_new.db` (agents write here)
- "Today" for every agent is `desk.date_today`, not the system clock.

## Tables

Links marked *implied* are not declared foreign keys; agents must join on them by hand.

### desk (1 row)
- Fields: `date_today`, `notes`
- Why: The shop's current date; all due-date and overdue checks use it.

### tickets (3 rows)
- Fields: `id` (PK), `type`, `requester`, `subject`, `sku`, `size`, `qty`, `lease_id` (FK → leases), `invoice_id` (FK → invoices), `status`, `notes`, `created_at`
- Links: `sku` + `size` → inventory (*implied*), `sku` → pricing (*implied*)
- Why: The work queue; each ticket is a job an agent must resolve.

### inventory (10 rows)
- Fields: `sku` + `size` (composite PK), `name`, `qty`, `location`
- Links: `sku` → pricing (*implied*)
- Why: Stock on hand by size; decides if an order can ship now.

### pricing (4 rows)
- Fields: `sku` (PK), `unit_cost`, `list_price`
- Why: Cost and price per SKU; sets the floor for any discount.

### vendors (3 rows)
- Fields: `id` (PK), `name`, `specialty`, `lead_days`
- Why: Who can restock or deliver, and how long it takes.

### invoices (1 row)
- Fields: `id` (PK), `vendor_id` (FK → vendors), `amount`, `due_date`, `status`, `description`
- Why: Money the shop owes vendors; must be checked before paying.

### leases (1 row)
- Fields: `id` (PK), `space_name`, `landlord`, `monthly_rent`, `next_due`, `notes`
- Why: Rent the shop owes; the real amount and date to check a rent notice against.

### cash_accounts (1 row)
- Fields: `name` (PK), `balance`, `date`
- Why: Cash available; every payment must fit inside the balance.

### payments (0 rows)
- Fields: `id` (PK), `kind`, `ref_id`, `amount`, `account`, `paid_at`, `approved_by`
- Links: `ref_id` → invoices or leases depending on `kind` (*implied*), `account` → cash_accounts.name (*implied*)
- Why: The record of money paid out, with who approved it; empty at the start.
