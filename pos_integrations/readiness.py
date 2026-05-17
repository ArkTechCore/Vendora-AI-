PROVIDER_REQUIREMENTS = {
    "clover": {
        "title": "Clover",
        "ask_for": [
            "Clover Developer account and app access",
            "Merchant ID for each restaurant/store",
            "OAuth client ID and client secret for production app flow",
            "Access token and refresh token after merchant authorizes the app",
            "Order read permission and payment/tender read permission",
            "Webhook signing secret if using webhooks",
        ],
        "vendoraops_needs": [
            "Merchant ID -> external merchant ID",
            "Store/location identifier if multiple Clover locations exist",
            "OAuth tokens stored per store connection",
            "Orders/items/tenders mapped into ImportedSale and ImportedSaleItem",
        ],
    },
    "square": {
        "title": "Square",
        "ask_for": [
            "Square Developer account and application",
            "OAuth application ID and secret",
            "Seller location ID for each store",
            "OAuth token with ORDERS_READ and MERCHANT_PROFILE_READ",
            "PAYMENTS_READ if cash/card/tender split must come from payments",
            "Webhook signature key if using webhooks",
        ],
        "vendoraops_needs": [
            "Location ID -> external location ID",
            "OAuth access/refresh tokens per seller/store",
            "Search Orders response mapped into sales, line items, tax, tip, discounts",
            "Payment/tender data mapped into cash/card totals",
        ],
    },
    "toast": {
        "title": "Toast",
        "ask_for": [
            "Toast Standard API access, Custom Integration, or Partner Integration approval",
            "Client ID and client secret",
            "Restaurant GUID for each Toast location",
            "orders:read, menus:read, restaurants:read, and cashmgmt:read if available",
            "Production API host/environment details",
        ],
        "vendoraops_needs": [
            "Restaurant GUID -> external location ID",
            "Client credentials stored per client or connection",
            "Access token refresh using Toast client-credentials flow",
            "Orders/checks/selections/payments mapped into normalized sales",
        ],
    },
}


OPEN_SOURCE_UPGRADE_STACK = [
    ("Meilisearch", "MIT", "Fast search for menu items, vendors, ingredients, invoices, and reports."),
    ("Tesseract OCR", "Apache 2.0", "OCR engine for invoice images and scanned PDFs."),
    ("Gotenberg", "MIT", "HTML-to-PDF/document rendering service for polished downloadable reports."),
    ("GlitchTip", "open-source", "Self-hosted error tracking so production issues are visible."),
]
