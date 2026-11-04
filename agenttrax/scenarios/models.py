"""Strict domain models for deterministic AgentTrax scenarios."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import ConfigDict, Field, field_validator, model_validator

from agenttrax.contracts.models import StrictContractModel

NonBlankString = Annotated[str, Field(min_length=1)]
PositiveMinorUnits = Annotated[int, Field(gt=0)]
NonNegativeMinorUnits = Annotated[int, Field(ge=0)]


class OrderStatus(StrEnum):
    """Possible statuses for a simulated order."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class PaymentStatus(StrEnum):
    """Payment status for a simulated order."""

    UNPAID = "UNPAID"
    PAID = "PAID"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"


class CaseStatus(StrEnum):
    """Support case lifecycle states."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ScenarioModel(StrictContractModel):
    """Shared strict configuration for scenario domain models."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_default=True,
    )


class SimulatedOrder(ScenarioModel):
    """An order held entirely inside the simulator."""

    order_id: NonBlankString
    status: OrderStatus
    payment_status: PaymentStatus
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    total_minor_units: PositiveMinorUnits
    refunded_minor_units: NonNegativeMinorUnits = 0

    @field_validator("order_id")
    @classmethod
    def validate_order_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("order_id must not be blank.")
        return value

    @model_validator(mode="after")
    def validate_refund_balance(self) -> SimulatedOrder:
        if self.refunded_minor_units > self.total_minor_units:
            raise ValueError("Refunded amount cannot exceed order total.")

        if self.refunded_minor_units == self.total_minor_units:
            if self.payment_status != PaymentStatus.REFUNDED:
                raise ValueError(
                    "A fully refunded order must have REFUNDED payment status."
                )
        elif self.refunded_minor_units > 0:
            if self.payment_status != PaymentStatus.PARTIALLY_REFUNDED:
                raise ValueError(
                    "A partially refunded order must have "
                    "PARTIALLY_REFUNDED payment status."
                )
        elif self.payment_status in {
            PaymentStatus.PARTIALLY_REFUNDED,
            PaymentStatus.REFUNDED,
        }:
            raise ValueError(
                "Refund payment status requires a positive refunded amount."
            )

        return self

    @property
    def remaining_refundable_minor_units(self) -> int:
        """Return the remaining refundable amount in minor currency units."""

        return self.total_minor_units - self.refunded_minor_units


class CaseNote(ScenarioModel):
    """A deterministic note attached to a support case."""

    sequence: PositiveMinorUnits
    note: Annotated[str, Field(max_length=500)]

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Case note must not be empty or whitespace.")
        return value


class SupportCase(ScenarioModel):
    """A simulated customer-support case."""

    case_id: NonBlankString
    order_id: NonBlankString
    status: CaseStatus
    notes: tuple[CaseNote, ...] = ()

    @field_validator("case_id", "order_id")
    @classmethod
    def validate_identifiers(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Identifiers must not be blank.")
        return value

    @model_validator(mode="after")
    def validate_note_sequence(self) -> SupportCase:
        expected = tuple(range(1, len(self.notes) + 1))
        actual = tuple(note.sequence for note in self.notes)

        if actual != expected:
            raise ValueError("Case note sequences must be contiguous from 1.")

        return self


class ScenarioObjective(ScenarioModel):
    """Expected business outcome; not an independent verification result."""

    refund_minor_units: PositiveMinorUnits
    expected_remaining_minor_units: NonNegativeMinorUnits
    require_case_note: bool = True
    require_case_closed: bool = True


class ScenarioSnapshot(ScenarioModel):
    """Immutable, read-only view of the current simulator state."""

    scenario_id: NonBlankString
    order: SimulatedOrder
    support_case: SupportCase
    objective: ScenarioObjective

    @model_validator(mode="after")
    def validate_related_records(self) -> ScenarioSnapshot:
        if self.support_case.order_id != self.order.order_id:
            raise ValueError("Support case must reference the scenario order.")

        if self.objective.refund_minor_units > self.order.total_minor_units:
            raise ValueError("Objective refund cannot exceed the order total.")

        expected_remaining = (
            self.order.total_minor_units - self.objective.refund_minor_units
        )
        if self.objective.expected_remaining_minor_units != expected_remaining:
            raise ValueError(
                "Expected remaining balance does not match the objective refund."
            )
        return self
