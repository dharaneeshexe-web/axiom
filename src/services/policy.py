"""Policy Engine — embeds the buyer's budget, approval, and preference rules.

The single most important idea: the agent does NOT just buy. It evaluates every
purchase against explicit, explainable, human-set policies BEFORE any money
moves, and surfaces the reasoning (budget, approval, preferred payment, merchant
rules) in the reply and trace.
"""
from dataclasses import dataclass, field
from typing import List, Optional
from ..models.schemas import PaymentMethod


@dataclass
class PolicyDecision:
    approved: bool
    requires_approval: bool
    over_budget: bool
    reason: Optional[str] = None
    remaining_budget: Optional[int] = None      # paise remaining this month
    price: Optional[int] = None                 # paise
    suggested_actions: List[str] = field(default_factory=list)
    merchant_rule: Optional[str] = None
    decisions: List[str] = field(default_factory=list)   # decision-graph steps


class PolicyEngine:
    """Evaluates a purchase against the buyer's profile and merchant rules."""

    def __init__(
        self,
        preferred_payment: PaymentMethod = PaymentMethod.CARD,
        monthly_budget: int = 10_000_000,       # paise = Rs 1,00,000
        approval_threshold: int = 5_000_000,    # paise = Rs 50,000
        max_discount: Optional[int] = None,     # paise, merchant rule example
    ):
        self.preferred_payment = preferred_payment
        self.monthly_budget = monthly_budget
        self.approval_threshold = approval_threshold
        self.max_discount = max_discount
        self.spent_this_month = 0

    def record_spend(self, amount_paise: int) -> None:
        self.spent_this_month += amount_paise

    @property
    def remaining_budget(self) -> int:
        return self.monthly_budget - self.spent_this_month

    def evaluate(
        self,
        price_paise: int,
        payment_method: Optional[PaymentMethod] = None,
        merchant_rule_hint: Optional[str] = None,
    ) -> PolicyDecision:
        d = PolicyDecision(
            approved=True,
            requires_approval=False,
            over_budget=False,
            price=price_paise,
            remaining_budget=self.remaining_budget,
            suggested_actions=[],
            decisions=[],
        )

        # 1. Budget check
        if price_paise > self.remaining_budget:
            d.over_budget = True
            d.approved = False
            d.reason = (
                f"This is over your remaining monthly budget of "
                f"Rs {self._rupees(self.remaining_budget):,}."
            )
            d.decisions.append("budget: OVER")
        else:
            d.decisions.append("budget: OK")

        # 2. Approval threshold
        if price_paise >= self.approval_threshold and d.approved:
            d.requires_approval = True
            d.reason = (
                f"This exceeds your auto-approval limit of "
                f"Rs {self._rupees(self.approval_threshold):,} and needs your approval."
            )
            d.decisions.append("approval: REQUIRED")
        elif d.approved:
            d.decisions.append("approval: AUTO")

        # 3. Payment preference
        method = payment_method or self.preferred_payment
        if method != self.preferred_payment:
            d.suggested_actions.append(
                f"You usually pay with {self.preferred_payment.value.upper()}."
            )
        d.decisions.append(f"preference: {method.value}")

        # 4. Merchant rule (example: discount/price guard)
        if merchant_rule_hint:
            d.merchant_rule = merchant_rule_hint
            d.decisions.append("merchant: APPLIED")

        return d

    @staticmethod
    def _rupees(paise: int) -> int:
        return paise // 100
