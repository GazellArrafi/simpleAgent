"""LangChain tools milik Data Agent. Dipakai oleh node data_agent (dipanggil langsung)
dan oleh agent ReAct 'Tanya Data Agent' (dipanggil oleh LLM)."""

from collections import defaultdict

from langchain_core.tools import tool

from bank_data.repository import get_repo


def _customer_or_error(customer_id: str):
    c = get_repo().get_customer(customer_id.strip().upper())
    if not c:
        raise ValueError(f"Nasabah {customer_id} tidak ditemukan")
    return c


@tool
def get_customer_overview(customer_id: str) -> dict:
    """Ringkasan produk yang dimiliki nasabah (punya kartu kredit? pinjaman? consent marketing?)."""
    _customer_or_error(customer_id)
    return get_repo().overview(customer_id.strip().upper())


@tool
def get_customer_profile(customer_id: str) -> dict:
    """Profil nasabah: nama, usia, kota, pekerjaan, penghasilan bulanan, segmen, kanal favorit."""
    c = dict(_customer_or_error(customer_id))
    c.pop("demo_persona", None)  # label generator, bukan data bank
    return c


@tool
def get_savings_summary(customer_id: str, days: int = 90) -> dict:
    """Rekening tabungan nasabah + mutasi N hari terakhir."""
    cid = _customer_or_error(customer_id)["customer_id"]
    repo = get_repo()
    return {"accounts": repo.get_savings_accounts(cid),
            "transactions": repo.get_savings_transactions(cid, days=days)}


@tool
def get_credit_cards(customer_id: str) -> list[dict]:
    """Daftar kartu kredit nasabah: limit, saldo terpakai, sisa limit, tanggal cetak tagihan, autodebet."""
    return get_repo().get_credit_cards(_customer_or_error(customer_id)["customer_id"])


@tool
def get_cc_statements(customer_id: str) -> list[dict]:
    """Riwayat lembar tagihan kartu kredit bulanan (total tagihan, minimum, jatuh tempo, status bayar)."""
    return get_repo().get_cc_statements(_customer_or_error(customer_id)["customer_id"])


@tool
def get_cc_transactions(customer_id: str, days: int = 30, category: str | None = None) -> list[dict]:
    """Transaksi kartu kredit N hari terakhir. category opsional: groceries, dining, ecommerce, transport,
    travel, entertainment, bills, health, electronics, fashion, education."""
    return get_repo().get_cc_transactions(_customer_or_error(customer_id)["customer_id"], days=days, category=category)


@tool
def get_spending_by_category(customer_id: str, days: int = 30) -> dict:
    """Total belanja kartu kredit (approved) per kategori untuk N hari terakhir, dalam Rupiah."""
    totals = defaultdict(int)
    for t in get_repo().get_cc_transactions(_customer_or_error(customer_id)["customer_id"], days=days):
        if t["type"] == "purchase" and t["status"] == "approved":
            totals[t["category"]] += t["amount"]
    return dict(sorted(totals.items(), key=lambda kv: -kv[1]))


@tool
def get_loans(customer_id: str) -> list[dict]:
    """Pinjaman nasabah (KPR/KKB/KTA): cicilan bulanan, jatuh tempo berikutnya, autodebet, hari tunggakan."""
    return get_repo().get_loans(_customer_or_error(customer_id)["customer_id"])


@tool
def get_offer_catalog() -> list[dict]:
    """Katalog penawaran/promo bank yang bisa direkomendasikan."""
    return get_repo().offers


@tool
def search_customers(query: str) -> list[dict]:
    """Cari nasabah berdasarkan nama, kota, atau segmen. Mengembalikan maks 10 hasil (id, nama, kota, segmen)."""
    q = query.lower()
    hits = [c for c in get_repo().list_customers()
            if q in c["full_name"].lower() or q in c["city"].lower() or q == c["segment"].lower()]
    return [{k: c[k] for k in ("customer_id", "full_name", "city", "segment")} for c in hits[:10]]


ALL_TOOLS = [get_customer_overview, get_customer_profile, get_savings_summary, get_credit_cards,
             get_cc_statements, get_cc_transactions, get_spending_by_category, get_loans,
             get_offer_catalog, search_customers]
