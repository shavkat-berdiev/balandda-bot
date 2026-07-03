"""Keep the bookings calendar in sync with prepayments.

Every prepayment logged in analytics (by an agent) automatically creates or
updates a linked reservation, so the calendar always reflects real bookings
without any manual import. Idempotent and overlap-safe.
"""

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from db.enums import PrepaymentStatus, ReservationSource, ReservationStatus
from db.models import Prepayment, Reservation, ReservationEvent

logger = logging.getLogger(__name__)


def _res_status(prep_status: PrepaymentStatus) -> ReservationStatus:
    if prep_status == PrepaymentStatus.CANCELLED:
        return ReservationStatus.CANCELLED
    if prep_status in (PrepaymentStatus.CONFIRMED, PrepaymentStatus.SETTLED):
        return ReservationStatus.CONFIRMED
    return ReservationStatus.HOLD


async def sync_reservation_for_prepayment(session: AsyncSession, prepayment: Prepayment) -> None:
    """Create or update the calendar reservation linked to this prepayment."""
    # Snapshot all needed values BEFORE any commit/rollback (a rollback expires
    # the ORM object, and a later attribute access would raise MissingGreenlet).
    pid = prepayment.id
    # Prepayments created FROM the bookings calendar already have their reservation
    # (they mirror a payment on it) — never spawn a duplicate booking for those.
    if getattr(prepayment, "reservation_id", None):
        return
    p_property_id = prepayment.property_id
    p_check_in = prepayment.check_in_date
    p_check_out = prepayment.check_out_date
    p_guest = prepayment.guest_name
    p_amount = prepayment.amount
    status = _res_status(prepayment.status)

    if not p_check_in or not p_check_out or p_check_out <= p_check_in:
        return

    existing = (
        await session.execute(
            select(Reservation).where(Reservation.prepayment_id == pid)
        )
    ).scalar_one_or_none()

    if existing:
        existing.check_in = p_check_in
        existing.check_out = p_check_out
        existing.guest_name = p_guest
        existing.deposit_amount = p_amount
        existing.status = status
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            logger.warning("reservation sync overlap for prepayment %s", pid)
            return
        session.add(ReservationEvent(
            reservation_id=existing.id, actor_name="Авто (предоплата)", action="auto",
            detail=f"Обновлено из предоплаты (статус: {status.value})",
        ))
        await session.commit()
        return

    if status == ReservationStatus.CANCELLED:
        return  # nothing to create for a cancelled prepayment

    res = Reservation(
        property_id=p_property_id,
        check_in=p_check_in,
        check_out=p_check_out,
        guest_name=p_guest,
        status=status,
        source=ReservationSource.MANUAL,
        deposit_amount=p_amount,
        prepayment_id=pid,
        note="Авто из предоплаты",
    )
    session.add(res)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.warning("reservation create overlap for prepayment %s", pid)
        return
    session.add(ReservationEvent(
        reservation_id=res.id, actor_name="Авто (предоплата)", action="auto",
        detail=f"Создано из предоплаты: депозит {p_amount}",
    ))
    await session.commit()
