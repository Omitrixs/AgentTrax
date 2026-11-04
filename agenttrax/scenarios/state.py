"""Deterministic in-memory state for the order support scenario."""

from agenttrax.scenarios.models import (
    CaseStatus,
    OrderStatus,
    PaymentStatus,
    ScenarioObjective,
    ScenarioSnapshot,
    SimulatedOrder,
    SupportCase,
)

SCENARIO_ID = "order_refund_support_v1"
DEMO_ORDER_ID = "ord_demo_001"
DEMO_CASE_ID = "case_demo_001"


class OrderSupportScenarioState:
    """Own and expose the isolated state of one order support scenario."""

    def __init__(self) -> None:
        self._order: SimulatedOrder
        self._support_case: SupportCase
        self._objective: ScenarioObjective
        self.reset()

    @property
    def order(self) -> SimulatedOrder:
        """Return the current immutable simulated order."""

        return self._order

    @property
    def support_case(self) -> SupportCase:
        """Return the current immutable support case."""

        return self._support_case

    @property
    def objective(self) -> ScenarioObjective:
        """Return the scenario's immutable objective."""

        return self._objective

    def reset(self) -> ScenarioSnapshot:
        """Restore the deterministic initial scenario state."""

        order = SimulatedOrder(
            order_id=DEMO_ORDER_ID,
            status=OrderStatus.DELIVERED,
            payment_status=PaymentStatus.PAID,
            currency="USD",
            total_minor_units=12_999,
            refunded_minor_units=0,
        )
        support_case = SupportCase(
            case_id=DEMO_CASE_ID,
            order_id=DEMO_ORDER_ID,
            status=CaseStatus.OPEN,
            notes=(),
        )
        objective = ScenarioObjective(
            refund_minor_units=2_500,
            expected_remaining_minor_units=10_499,
            require_case_note=True,
            require_case_closed=True,
        )

        # Assign only after every initial record has validated.
        self._order = order
        self._support_case = support_case
        self._objective = objective

        return self.snapshot()

    def snapshot(self) -> ScenarioSnapshot:
        """Return a validated immutable snapshot of the current state."""

        return ScenarioSnapshot(
            scenario_id=SCENARIO_ID,
            order=self._order,
            support_case=self._support_case,
            objective=self._objective,
        )

    def replace_order(self, order: SimulatedOrder) -> None:
        """Replace the order with a validated record for the same order."""

        if not isinstance(order, SimulatedOrder):
            raise TypeError("order must be a SimulatedOrder.")

        if order.order_id != self._order.order_id:
            raise ValueError("Cannot replace the scenario with another order.")

        self._order = order

    def replace_support_case(self, support_case: SupportCase) -> None:
        """Replace the case with a validated record for the same scenario."""

        if not isinstance(support_case, SupportCase):
            raise TypeError("support_case must be a SupportCase.")

        if support_case.case_id != self._support_case.case_id:
            raise ValueError("Cannot replace the scenario with another case.")

        if support_case.order_id != self._order.order_id:
            raise ValueError("Support case must reference the scenario order.")

        self._support_case = support_case
