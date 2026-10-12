# AVON JEWELER

A responsive Django jewellery storefront with a premium, editorial-style customer experience and a staff-protected commerce dashboard. The application uses Django's authentication and ORM, MySQL in configured deployments (SQLite for a quick local smoke test), Decimal-based server-side pricing, and Razorpay for real payment processing.

## Included

- Product catalogue, category/metal filters, search, sort, product details, inventory, wishlists, and customer carts.
- Customer registration/sign-in, editable profile details, verified phone numbers, saved delivery addresses, checkout, customer-specific order history, and shipment tracking.
- Fixed-price and weight-based products. Weight prices use the latest configured metal/purity rate, gram weight, and making charge; discounts and configurable store or product tax rates are calculated on the server using `Decimal`.
- Razorpay online payment and cash-on-delivery orders.
- Staff-only Django administration for products and image uploads, categories, metal rates, store tax settings, customer/user records, addresses, coupons, orders, payments, and shipping/tracking details.
- Razorpay server-side order creation, payment signature verification plus server-side captured-payment checks, and an HMAC-verified webhook endpoint.
- Branded AVON JEWELER order-confirmation email templates. In development emails are printed to the console; production can use SMTP settings in `.env`.
- A repeatable `seed_products` command for a starter catalogue.

## Requirements

- Windows 10/11 (instructions below), Python 3.10+, and pip.
- MySQL 8+ for a normal local/deployed database. MySQL Server must be running, and the database/user must exist before Django starts.
- Razorpay account and API keys for actual checkout. Test keys are appropriate for development. A public HTTPS deployment URL is required for Razorpay webhooks.

## Windows setup

Open PowerShell in the project directory:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and set a unique, private `DJANGO_SECRET_KEY`; keep `DJANGO_DEBUG=True` only on a local development machine. Do not commit `.env`.

### MySQL

Create the database using MySQL (for example, from MySQL Workbench or the MySQL command line):

```sql
CREATE DATABASE avon_jeweler CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'avon_app'@'localhost' IDENTIFIED BY 'use-a-unique-local-password';
GRANT ALL PRIVILEGES ON avon_jeweler.* TO 'avon_app'@'localhost';
FLUSH PRIVILEGES;
```

Set `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT` in `.env` to match the database and account. The included PyMySQL adapter avoids a separate native MySQL client build on Windows. Alternatively, set `DATABASE_URL` to a PostgreSQL connection URL. If no database is configured, the project uses local SQLite only for local development and automated tests.

### Migrate, seed, and start

```powershell
python manage.py check
python manage.py makemigrations store
python manage.py migrate
python manage.py seed_products
python manage.py createsuperuser
python manage.py runserver
```

Visit `http://127.0.0.1:8000/` for the AVON JEWELER storefront and `http://127.0.0.1:8000/admin/` for staff administration. Uploaded product images are stored below `media/`; serve media from private/object storage or a correctly configured web server in production.

### Admin product workflow

Sign in at `/admin/` using a Django superuser/staff account. Add a category if needed, then add a product with a unique SKU, active status, inventory, tax, and either:

- **Fixed price**: set `Fixed price` to the product's pre-tax base amount.
- **Weight-based**: set metal, purity, weight in grams, and making charge; add a matching `MetalRate` for the current metal price per gram. The latest effective rate at checkout is used.

Add one or more images in the product's inline image section. Upload a local image or provide a trusted image URL. Never use untrusted image upload hosting. Update the order's status and the inline shipping record to manage fulfillment and share tracking details. Register customers in the standard Django Users administration.

## Phone verification and order notifications

Configure a Twilio Verify service and set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, and `TWILIO_VERIFY_SERVICE_SID` in `.env`. Customers enter their phone number in international E.164 format (for example, `+919876543210`) on their account page and request an SMS code. Phone verification is required before checkout. Twilio credentials are required for live SMS.

Set `ORDER_NOTIFICATION_EMAIL` to the store administrator's email address. Each successfully placed order (Razorpay or cash on delivery) sends an order summary to this address. In local development, the configured email backend prints the message to the console; production requires working SMTP settings.

## Razorpay configuration

1. Create a Razorpay account and copy **test** API key ID and key secret into `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` in the server's `.env`.
2. Restart Django. Checkout creates a real Razorpay test order on the server; the browser receives only the public key ID and order details. A payment is marked captured only after signature verification and a server-side Razorpay payment fetch reports the expected order, amount, INR currency, and `captured` status.
3. In the Razorpay dashboard, configure a webhook endpoint at `https://your-domain.example/payments/razorpay/webhook/`, subscribe to `payment.captured` and `payment.failed`, and put its webhook secret in `RAZORPAY_WEBHOOK_SECRET`.
4. Never use live keys in development, put secrets in source control, or treat a browser redirect/payment callback by itself as proof of payment. The checkout deliberately does not simulate or bypass payments when credentials are absent.

The checkout creates an order and reserves inventory before redirecting to Razorpay. Unpaid online orders remain `pending` for staff review; cash-on-delivery orders enter `processing` with payment marked pending collection. Configure an operational process to cancel expired online orders and reconcile/refund payments in the Razorpay dashboard. Razorpay credentials and a publicly reachable HTTPS webhook are external setup requirements, not bundled services.

## Tax settings

In Django admin, open **Store settings** to edit the default tax percentage applied to products without a product-specific tax override. A product can optionally set its own tax rate in the product's Metal & pricing section.

## Vercel deployment

Import the private GitHub repository into Vercel. In Project Settings, enable access to System Environment Variables. Configure `DJANGO_SECRET_KEY` as a new secret and configure either `DATABASE_URL` for hosted PostgreSQL or all `DB_*` variables for hosted MySQL in the Vercel project settings. Vercel deployments force `DEBUG=False`, use their deployment hostnames (including `jeweler-web-site.vercel.app`), enable HTTPS proxy handling, and reject SQLite because serverless local storage is not persistent. `VERCEL_URL` and project deployment hosts are automatically trusted when system environment variables are enabled.

After adding database credentials, run migrations against the Vercel database from a trusted local shell with the Vercel CLI linked to this project:

```powershell
vercel env run -- python manage.py migrate
vercel env run -- python manage.py seed_products
```

Add the deployed URL to `DJANGO_CSRF_TRUSTED_ORIGINS` only if using a custom domain or if the Vercel system host variables are unavailable. Do not put database URLs or secret keys in GitHub.

### Production security and email

Set `DJANGO_DEBUG=False`, a strong random `DJANGO_SECRET_KEY`, exact `DJANGO_ALLOWED_HOSTS`, database credentials, HTTPS, and `DJANGO_SECURE_SSL_REDIRECT=True` behind a correctly configured TLS-terminating server. Set secure proxy/forwarded-protocol settings appropriate to the deployment platform, use a production WSGI server, configure static/media delivery, backups, monitoring, and a production SMTP service. Set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` (or SSL as appropriate), and `DEFAULT_FROM_EMAIL` for confirmation emails. Do not expose `.env`, debug pages, or user-uploaded media from an unsafe location.

## Tests

Run the automated tests against Django's isolated test database (SQLite by default):

```powershell
python manage.py test store
```

The suite covers Decimal fixed/weight pricing, store tax settings, catalogue/search/detail pages, customer registration/profile/address/phone verification, customer isolation for orders, stock reservation, COD and admin order email, missing-credential behavior, Razorpay signature/capture checks, and webhook HMAC validation. External SMS and payment gateway calls are mocked in tests; for end-to-end flows, configure Twilio Verify and Razorpay **test** keys. A live webhook needs the external dashboard and public HTTPS setup above.
