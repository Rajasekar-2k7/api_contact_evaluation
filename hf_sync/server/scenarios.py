# server/scenarios.py — All 5 scenarios for the environment
# DOMAIN 1: Payment Service API (scenarios 1, 2, 3)
# DOMAIN 2: Auth & Gateway API (scenarios 4, 5)

SCENARIOS = {

    # ─── SCENARIO 1: EASY ──────────────────────────────────────────────
    1: {
        "id": 1,
        "name": "Add Optional Field",
        "difficulty": "easy",
        "domain": "Payment Service",
        "description": (
            "Payment Service v2 adds an optional 'description' field to "
            "POST /payments. No existing required fields changed."
        ),
        "spec_v1": {
            "service": "Payment Service",
            "version": "v1",
            "endpoint": "POST /v1/payments",
            "required_fields": ["amount", "currency"],
            "optional_fields": [],
            "response": {
                "success": {"id": "string", "status": "string"},
                "error_codes": ["insufficient_funds", "card_expired"]
            }
        },
        "spec_v2": {
            "service": "Payment Service",
            "version": "v2",
            "endpoint": "POST /v2/payments",
            "required_fields": ["amount", "currency"],
            "optional_fields": ["description"],
            "response": {
                "success": {"id": "string", "status": "string"},
                "error_codes": ["insufficient_funds", "card_expired"]
            }
        },
        "client_code": {
            "mobile_app": (
                "def pay(amount, currency):\n"
                "    r = api.post('/v1/payments', {'amount': amount, 'currency': currency})\n"
                "    if r['status'] == 'succeeded': return True\n"
                "    return False"
            ),
            "web_dashboard": (
                "async function pay(amount, currency) {\n"
                "    const r = await fetch('/v1/payments', {method:'POST',\n"
                "        body: JSON.stringify({amount, currency})});\n"
                "    return r.json();\n"
                "}"
            ),
            "partner_api": (
                "def charge(amount, currency):\n"
                "    return requests.post('/v1/payments',\n"
                "        json={'amount': amount, 'currency': currency})"
            )
        },
        "client_personas": {
            "mobile_app": {"update_cycle_days": 90, "tolerance": "zero"},
            "web_dashboard": {"update_cycle_days": 1, "tolerance": "high"},
            "partner_api": {"update_cycle_days": 30, "tolerance": "medium"}
        },
        "dependency_graph": {
            "payment_service": ["fraud_service", "notification_service"],
            "api_gateway": ["payment_service"],
            "clients": ["api_gateway"]
        },
        "ground_truth": {
            "changed_fields": ["optional_fields"],
            "change_category": "field_added",
            "is_breaking": False,
            "affected_clients": [],
            "severity": 0.0,
            "reason": (
                "Adding an optional field is backwards compatible. "
                "All existing clients that do not send 'description' "
                "will continue to work without any changes."
            ),
            "required_change_keywords": ["optional", "backwards compatible", "no action"],
            "required_migration_keywords": ["no migration needed", "optional", "non-breaking"]
        }
    },

    # ─── SCENARIO 2: MEDIUM ────────────────────────────────────────────
    2: {
        "id": 2,
        "name": "Error Code Breaking Change",
        "difficulty": "medium",
        "domain": "Payment Service",
        "description": (
            "Payment Service v2 renames error code 'insufficient_funds' "
            "to 'payment_declined'. Two clients hardcode the old string. "
            "Based on a real 2019 Stripe incident."
        ),
        "spec_v1": {
            "service": "Payment Service",
            "version": "v1",
            "endpoint": "POST /v1/payments",
            "required_fields": ["amount", "currency"],
            "optional_fields": ["description"],
            "response": {
                "success": {"id": "string", "status": "string"},
                "error_codes": ["insufficient_funds", "card_expired"]
            }
        },
        "spec_v2": {
            "service": "Payment Service",
            "version": "v2",
            "endpoint": "POST /v2/payments",
            "required_fields": ["amount", "currency"],
            "optional_fields": ["description"],
            "response": {
                "success": {"id": "string", "status": "string"},
                "error_codes": ["payment_declined", "card_expired"]
            }
        },
        "client_code": {
            "mobile_app": (
                "def pay(amount, currency):\n"
                "    r = api.post('/v1/payments', {'amount': amount, 'currency': currency})\n"
                "    if r.status_code == 400:\n"
                "        err = r.json()['error']\n"
                "        if err['code'] == 'insufficient_funds':\n"
                "            raise InsufficientFundsError()\n"
                "        raise PaymentError(err['message'])\n"
                "    return r.json()"
            ),
            "web_dashboard": (
                "async function pay(amount, currency) {\n"
                "    const r = await fetch('/v1/payments', {\n"
                "        method: 'POST', body: JSON.stringify({amount, currency})});\n"
                "    if (!r.ok) {\n"
                "        const err = await r.json();\n"
                "        throw new Error(err.message);\n"
                "    }\n"
                "    return r.json();\n"
                "}"
            ),
            "partner_api": (
                "def charge(amount, currency):\n"
                "    r = requests.post('/v1/payments',\n"
                "        json={'amount': amount, 'currency': currency})\n"
                "    data = r.json()\n"
                "    if data.get('error', {}).get('code') == 'insufficient_funds':\n"
                "        log_insufficient_funds()\n"
                "        return False\n"
                "    return True"
            )
        },
        "client_personas": {
            "mobile_app": {"update_cycle_days": 90, "tolerance": "zero"},
            "web_dashboard": {"update_cycle_days": 1, "tolerance": "high"},
            "partner_api": {"update_cycle_days": 30, "tolerance": "medium", "sla_notice_days": 90}
        },
        "dependency_graph": {
            "payment_service": ["fraud_service", "notification_service"],
            "api_gateway": ["payment_service"],
            "clients": ["api_gateway"]
        },
        "ground_truth": {
            "changed_fields": ["error_codes"],
            "change_category": "error_code_changed",
            "is_breaking": True,
            "affected_clients": ["mobile_app", "partner_api"],
            "severity": 0.8,
            "reason": (
                "mobile_app hardcodes string 'insufficient_funds' in error handler. "
                "partner_api hardcodes string 'insufficient_funds' in reconciliation logic. "
                "web_dashboard uses generic error.message — NOT affected."
            ),
            "required_change_keywords": ["hardcoded", "insufficient_funds", "renamed"],
            "required_migration_keywords": ["parallel", "support both", "transition", "notify partner"]
        }
    },

    # ─── SCENARIO 3: HARD ──────────────────────────────────────────────
    3: {
        "id": 3,
        "name": "The Fix That Breaks (Paradox)",
        "difficulty": "hard",
        "domain": "Payment Service",
        "description": (
            "Payment Service fixes a bug: v1 returned amount in cents, "
            "v2 returns amount in dollars (correct). BUT all clients "
            "built display logic around the bug. This 'fix' will show "
            "wrong prices everywhere. All clients affected differently."
        ),
        "spec_v1": {
            "service": "Payment Service",
            "version": "v1",
            "endpoint": "GET /v1/payments/:id",
            "response": {
                "id": "string",
                "amount": "integer",
                "currency": "string",
                "status": "string"
            },
            "note": "amount is in CENTS (e.g. $10.00 = 1000)"
        },
        "spec_v2": {
            "service": "Payment Service",
            "version": "v2",
            "endpoint": "GET /v2/payments/:id",
            "response": {
                "id": "string",
                "amount": "float",
                "currency": "string",
                "status": "string"
            },
            "note": "amount is in DOLLARS (e.g. $10.00 = 10.00)"
        },
        "client_code": {
            "mobile_app": (
                "def display_payment(payment_id):\n"
                "    r = api.get(f'/v1/payments/{payment_id}')\n"
                "    raw = r['amount']\n"
                "    display = raw / 100\n"
                "    show_on_screen(f'${display:.2f}')"
            ),
            "web_dashboard": (
                "async function showPayment(id) {\n"
                "    const p = await fetch(`/v1/payments/${id}`).then(r => r.json());\n"
                "    const display = (p.amount / 100).toFixed(2);\n"
                "    document.getElementById('amount').textContent = `$${display}`;\n"
                "}"
            ),
            "partner_api": (
                "def get_payment_amount(payment_id):\n"
                "    r = requests.get(f'/v1/payments/{payment_id}')\n"
                "    raw = r.json()['amount']\n"
                "    self.db.store_raw_amount(raw)\n"
                "    return raw"
            )
        },
        "client_personas": {
            "mobile_app": {
                "update_cycle_days": 90,
                "tolerance": "zero",
                "impact": "Shows 1/100 of correct price (e.g. $0.10 instead of $10.00)"
            },
            "web_dashboard": {
                "update_cycle_days": 1,
                "tolerance": "high",
                "impact": "Shows 1/100 of correct price"
            },
            "partner_api": {
                "update_cycle_days": 30,
                "tolerance": "medium",
                "impact": "Stores wrong values in DB — reconciliation failure"
            }
        },
        "dependency_graph": {
            "payment_service": ["reporting_service", "fraud_service"],
            "reporting_service": ["dashboard"],
            "clients": ["api_gateway", "reporting_service"]
        },
        "ground_truth": {
            "changed_fields": ["amount", "amount_unit"],
            "change_category": "behavior_changed",
            "is_breaking": True,
            "affected_clients": ["mobile_app", "web_dashboard", "partner_api"],
            "severity": 1.0,
            "reason": (
                "All clients built around buggy cents behavior. "
                "mobile_app and web_dashboard divide by 100 — will show cents-value as dollars. "
                "partner_api stores raw — will record 100x smaller values in DB."
            ),
            "required_change_keywords": ["cents", "dollars", "divide by 100", "behavior", "all clients"],
            "required_migration_keywords": [
                "migrate clients first", "versioned rollout", "parallel",
                "update mobile first", "partner notice", "db migration"
            ]
        }
    },

    # ─── SCENARIO 4: MEDIUM ────────────────────────────────────────────
    4: {
        "id": 4,
        "name": "Auth Token Format Change",
        "difficulty": "medium",
        "domain": "Auth Service",
        "description": (
            "Auth Service v2 changes token format from opaque string "
            "to JWT. The token is longer, has a different structure, "
            "and requires a new validation endpoint. Some clients parse "
            "the token directly, others just pass it through."
        ),
        "spec_v1": {
            "service": "Auth Service",
            "version": "v1",
            "endpoint": "POST /v1/auth/token",
            "response": {
                "token": "string (opaque, 32 chars)",
                "expires_in": "integer (seconds)",
                "token_type": "Bearer"
            },
            "validation": "GET /v1/auth/validate?token={token}"
        },
        "spec_v2": {
            "service": "Auth Service",
            "version": "v2",
            "endpoint": "POST /v2/auth/token",
            "response": {
                "token": "string (JWT, 3 parts separated by .)",
                "expires_in": "integer (seconds)",
                "token_type": "Bearer",
                "refresh_token": "string (new in v2)"
            },
            "validation": "JWT signature verification (no endpoint needed)"
        },
        "client_code": {
            "mobile_app": (
                "def login(user, password):\n"
                "    r = api.post('/v1/auth/token', {'user': user, 'pass': password})\n"
                "    token = r['token']\n"
                "    # Stores token as-is, passes in Authorization header\n"
                "    self.token = token\n"
                "    self.headers = {'Authorization': f'Bearer {token}'}\n"
                "    return True"
            ),
            "web_dashboard": (
                "async function login(user, pass) {\n"
                "    const r = await fetch('/v1/auth/token', {\n"
                "        method: 'POST', body: JSON.stringify({user, pass})});\n"
                "    const data = await r.json();\n"
                "    // PARSES token to extract user_id from position 0-8\n"
                "    const user_id = data.token.substring(0, 8);\n"
                "    localStorage.setItem('user_id', user_id);\n"
                "    localStorage.setItem('token', data.token);\n"
                "}"
            ),
            "partner_api": (
                "def authenticate(user, password):\n"
                "    r = requests.post('/v1/auth/token',\n"
                "        json={'user': user, 'pass': password})\n"
                "    token = r.json()['token']\n"
                "    # Validates by calling validate endpoint\n"
                "    valid = requests.get(f'/v1/auth/validate?token={token}')\n"
                "    return valid.status_code == 200"
            )
        },
        "client_personas": {
            "mobile_app": {"update_cycle_days": 90, "tolerance": "low"},
            "web_dashboard": {"update_cycle_days": 1, "tolerance": "high"},
            "partner_api": {"update_cycle_days": 30, "tolerance": "medium"}
        },
        "dependency_graph": {
            "auth_service": ["user_service", "session_store"],
            "api_gateway": ["auth_service"],
            "clients": ["api_gateway"]
        },
        "ground_truth": {
            "changed_fields": ["token_format", "validation_method"],
            "change_category": "type_changed",
            "is_breaking": True,
            "affected_clients": ["web_dashboard", "partner_api"],
            "severity": 0.7,
            "reason": (
                "web_dashboard extracts user_id from token position 0-8 — JWT format breaks this. "
                "partner_api calls /v1/auth/validate which is removed in v2. "
                "mobile_app just passes token in header — NOT affected."
            ),
            "required_change_keywords": ["jwt", "opaque", "parse", "validate endpoint", "position"],
            "required_migration_keywords": ["versioned endpoint", "parallel support", "migrate validation"]
        }
    },

    # ─── SCENARIO 5: HARD ──────────────────────────────────────────────
    5: {
        "id": 5,
        "name": "Silent Rate Limit Semantic Change",
        "difficulty": "hard",
        "domain": "API Gateway",
        "description": (
            "API Gateway v2 changes rate limiting from per-IP to per-user. "
            "The response format looks identical. No error codes changed. "
            "But shared infrastructure clients (CDNs, proxies) that route "
            "traffic from thousands of users through ONE IP will now hit "
            "rate limits 1000x more aggressively. The change is invisible "
            "in the spec but catastrophic in production."
        ),
        "spec_v1": {
            "service": "API Gateway",
            "version": "v1",
            "rate_limiting": {
                "strategy": "per_ip",
                "limit": 1000,
                "window": "1 hour",
                "error_response": {"status": 429, "error": "rate_limit_exceeded"}
            }
        },
        "spec_v2": {
            "service": "API Gateway",
            "version": "v2",
            "rate_limiting": {
                "strategy": "per_user",
                "limit": 1000,
                "window": "1 hour",
                "error_response": {"status": 429, "error": "rate_limit_exceeded"}
            }
        },
        "client_code": {
            "mobile_app": (
                "class APIClient:\n"
                "    # Each user has their own mobile install\n"
                "    # Each makes ~50 requests/hour\n"
                "    # 1 user = 1 IP on mobile network\n"
                "    def make_request(self, endpoint):\n"
                "        return api.get(endpoint, headers=self.auth_headers)"
            ),
            "cdn_proxy": (
                "class CDNProxy:\n"
                "    # Routes ALL user traffic through 3 CDN IPs\n"
                "    # 50,000 users x 50 requests/hour = 2.5M requests/hour\n"
                "    # Under v1: spreads across 50k user IPs — well under limit\n"
                "    # Under v2: each user gets own limit — still fine\n"
                "    # BUT: proxy cannot inject per-user auth headers\n"
                "    # Unauthenticated proxied requests = 1 shared 'anonymous' user\n"
                "    def proxy_request(self, request):\n"
                "        return forward(request, remove_auth=True)"
            ),
            "partner_api": (
                "class PartnerIntegration:\n"
                "    # Runs batch jobs from 1 server IP\n"
                "    # Uses service account (1 user_id)\n"
                "    # Makes 800 requests/hour in batch\n"
                "    # Under v1: 800/1000 per-IP — under limit\n"
                "    # Under v2: 800/1000 per-user — still under limit\n"
                "    def run_batch(self):\n"
                "        for item in self.batch:\n"
                "            api.post('/v1/process', item)"
            )
        },
        "client_personas": {
            "mobile_app": {"users": "direct", "ip_sharing": False, "impact": "none"},
            "cdn_proxy": {"users": 50000, "ip_sharing": True, "anonymous_routing": True},
            "partner_api": {"users": 1, "ip_sharing": False, "impact": "none"}
        },
        "dependency_graph": {
            "api_gateway": ["payment_service", "auth_service", "data_service"],
            "cdn_proxy": ["api_gateway"],
            "mobile_app": ["api_gateway"],
            "partner_api": ["api_gateway"]
        },
        "ground_truth": {
            "changed_fields": ["rate_limiting.strategy"],
            "change_category": "behavior_changed",
            "is_breaking": True,
            "affected_clients": ["cdn_proxy"],
            "severity": 0.9,
            "reason": (
                "cdn_proxy routes anonymous traffic as 1 shared user. "
                "All 50k users share 1 rate limit (1000/hour). "
                "mobile_app: each user = own rate limit — NOT affected. "
                "partner_api: 1 user service account, 800 req/hr — NOT affected."
            ),
            "required_change_keywords": [
                "per_user", "per_ip", "shared", "anonymous", "cdn", "proxy"
            ],
            "required_migration_keywords": [
                "inject user_id", "cdn configuration", "exempt service accounts",
                "monitor anonymous traffic", "gradual rollout"
            ]
        }
    }
}
