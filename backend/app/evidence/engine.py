"""Evidence engine.

Turns retrieved records into structured evidence items. Every item
carries a source reference (table, row id, field) so nothing in a
generated response can exist without a pointer back into our own data -
this is the grounding contract that prevents hallucinated evidence.

`supports` is claim-relative: a confirmed delivery contradicts a
"product not received" claim (supports the merchant), while a failed
delivery corroborates it (supports the customer). The same fact can
support different sides under different claims.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..models.entities import Chargeback, Customer, Delivery, Order, Transaction

REASON_PNR = "product_not_received"
REASON_UNAUTH = "unauthorized_transaction"
REASON_NAD = "product_not_as_described"


@dataclass
class Evidence:
    key: str
    statement: str
    value: str
    source_table: str
    source_id: str
    source_field: str
    supports: str    # merchant | customer | neutral | missing
    strength: str    # strong | moderate | weak

    def dict(self) -> dict:
        return asdict(self)


def _fmt_ts(ts) -> str:
    return ts.strftime("%d %b %Y, %H:%M") if ts else "not recorded"


def collect_evidence(case: Chargeback, customer: Customer, txn: Transaction,
                     order: Order, delivery: Delivery | None) -> list[Evidence]:
    items: list[Evidence] = []
    add = items.append

    # ---- payment ---------------------------------------------------------
    add(Evidence(
        key="payment_status",
        statement=f"Payment of ₹{txn.amount:,.0f} was "
                  f"{'successfully captured' if txn.payment_status == 'captured' else txn.payment_status}"
                  f" via {txn.payment_method.replace('_', ' ')}.",
        value=txn.payment_status,
        source_table="transactions", source_id=txn.id,
        source_field="payment_status",
        supports="merchant" if txn.payment_status == "captured" else "neutral",
        strength="moderate"))

    # ---- delivery --------------------------------------------------------
    if delivery is None:
        add(Evidence(
            key="delivery_record",
            statement="No delivery record exists for this order.",
            value="missing",
            source_table="deliveries", source_id=order.id,
            source_field="delivery_status",
            supports="customer" if case.reason == REASON_PNR else "missing",
            strength="strong" if case.reason == REASON_PNR else "moderate"))
    else:
        status = delivery.delivery_status
        conf = delivery.delivery_confirmation
        confirmed = conf in ("signed", "otp", "photo")

        if status == "delivered":
            if case.reason == REASON_PNR:
                if confirmed:
                    add(Evidence(
                        key="delivery_confirmed",
                        statement=f"Carrier {delivery.carrier} recorded the "
                                  f"package as delivered on "
                                  f"{_fmt_ts(delivery.delivered_ts)} with "
                                  f"{conf} confirmation, contradicting the "
                                  f"non-receipt claim.",
                        value=f"delivered/{conf}",
                        source_table="deliveries", source_id=str(delivery.id),
                        source_field="delivery_confirmation",
                        supports="merchant", strength="strong"))
                else:
                    add(Evidence(
                        key="delivery_unconfirmed",
                        statement="The package is marked delivered, but no "
                                  "delivery confirmation (signature/OTP/photo)"
                                  " is on file - a mis-delivery cannot be "
                                  "ruled out.",
                        value="delivered/none",
                        source_table="deliveries", source_id=str(delivery.id),
                        source_field="delivery_confirmation",
                        supports="missing", strength="moderate"))
            else:
                add(Evidence(
                    key="delivery_completed",
                    statement=f"The order was delivered on "
                              f"{_fmt_ts(delivery.delivered_ts)}"
                              f"{' with ' + conf + ' confirmation' if confirmed else ''}.",
                    value=f"delivered/{conf}",
                    source_table="deliveries", source_id=str(delivery.id),
                    source_field="delivery_status",
                    supports="merchant" if confirmed else "neutral",
                    strength="moderate"))
        else:
            add(Evidence(
                key="delivery_incomplete",
                statement=f"Carrier records show delivery status "
                          f"'{status.replace('_', ' ')}' - the package was "
                          f"never confirmed delivered.",
                value=status,
                source_table="deliveries", source_id=str(delivery.id),
                source_field="delivery_status",
                supports="customer" if case.reason == REASON_PNR else "neutral",
                strength="strong" if case.reason == REASON_PNR else "weak"))

        if not delivery.has_tracking:
            add(Evidence(
                key="tracking_missing",
                statement="No tracking number is on file for this shipment.",
                value="missing",
                source_table="deliveries", source_id=str(delivery.id),
                source_field="tracking_number",
                supports="missing", strength="moderate"))

    # ---- device & session (decisive for unauthorized claims) -------------
    if case.reason == REASON_UNAUTH:
        if txn.device_seen_before:
            add(Evidence(
                key="known_device",
                statement="The transaction came from a device previously "
                          "used by this customer's account, which is "
                          "inconsistent with a stolen-card claim.",
                value="device_seen_before=true",
                source_table="transactions", source_id=txn.id,
                source_field="device_seen_before",
                supports="merchant", strength="strong"))
        else:
            add(Evidence(
                key="unknown_device",
                statement="The transaction came from a device never seen on "
                          "this account before, consistent with third-party "
                          "fraud.",
                value="device_seen_before=false",
                source_table="transactions", source_id=txn.id,
                source_field="device_seen_before",
                supports="customer", strength="strong"))
        if txn.txns_last_24h >= 3:
            add(Evidence(
                key="high_velocity",
                statement=f"{txn.txns_last_24h} transactions were attempted "
                          f"on this account in 24 hours - a pattern typical "
                          f"of account takeover.",
                value=str(txn.txns_last_24h),
                source_table="transactions", source_id=txn.id,
                source_field="txns_last_24h",
                supports="customer", strength="moderate"))
        if txn.ip_geo_distance_km > 500:
            add(Evidence(
                key="geo_anomaly",
                statement=f"The order IP was ~{txn.ip_geo_distance_km:,.0f} km"
                          f" from the customer's usual location.",
                value=f"{txn.ip_geo_distance_km:,.0f} km",
                source_table="transactions", source_id=txn.id,
                source_field="ip_geo_distance_km",
                supports="customer", strength="moderate"))

    # ---- addresses --------------------------------------------------------
    add(Evidence(
        key="address_match",
        statement=("Shipping and billing addresses match "
                   f"({order.shipping_city})." if order.shipping_billing_match
                   else f"Shipping address ({order.shipping_city}) differs "
                        f"from billing address ({order.billing_city})."),
        value="match" if order.shipping_billing_match else "mismatch",
        source_table="orders", source_id=order.id,
        source_field="shipping_billing_match",
        supports="merchant" if order.shipping_billing_match else "neutral",
        strength="weak"))

    # ---- customer history --------------------------------------------------
    add(Evidence(
        key="order_history",
        statement=f"The customer has completed {customer.previous_orders} "
                  f"previous orders over "
                  f"{customer.account_age_days / 30:.0f} months.",
        value=str(customer.previous_orders),
        source_table="customers", source_id=customer.id,
        source_field="previous_orders",
        supports="neutral", strength="weak"))
    if customer.previous_chargebacks == 0:
        add(Evidence(
            key="no_prior_disputes",
            statement="The customer has never filed a chargeback before.",
            value="0",
            source_table="customers", source_id=customer.id,
            source_field="previous_chargebacks",
            supports="customer", strength="moderate"))
    else:
        add(Evidence(
            key="prior_disputes",
            statement=f"The customer has filed "
                      f"{customer.previous_chargebacks} previous "
                      f"chargeback(s).",
            value=str(customer.previous_chargebacks),
            source_table="customers", source_id=customer.id,
            source_field="previous_chargebacks",
            supports="merchant",
            strength="moderate" if customer.previous_chargebacks > 1 else "weak"))

    # ---- claim timing -------------------------------------------------------
    if case.claim_delay_days is not None:
        if case.claim_delay_days >= 10:
            add(Evidence(
                key="late_claim",
                statement=f"The claim was filed {case.claim_delay_days:.0f} "
                          f"days after the delivery/shipment event.",
                value=f"{case.claim_delay_days:.0f} days",
                source_table="chargebacks", source_id=case.id,
                source_field="claim_delay_days",
                supports="merchant", strength="weak"))
        elif case.claim_delay_days <= 3:
            add(Evidence(
                key="prompt_claim",
                statement=f"The claim was filed promptly "
                          f"({case.claim_delay_days:.1f} days after the "
                          f"delivery/shipment event).",
                value=f"{case.claim_delay_days:.1f} days",
                source_table="chargebacks", source_id=case.id,
                source_field="claim_delay_days",
                supports="customer", strength="weak"))

    return items


def missing_evidence(items: list[Evidence]) -> list[str]:
    return [i.statement for i in items if i.supports == "missing"]


def merchant_strength(items: list[Evidence]) -> str:
    """Overall strength of the merchant's evidence position."""
    strong = sum(1 for i in items
                 if i.supports == "merchant" and i.strength == "strong")
    moderate = sum(1 for i in items
                   if i.supports == "merchant" and i.strength == "moderate")
    if strong >= 1:
        return "strong"
    if moderate >= 2:
        return "moderate"
    return "weak"
