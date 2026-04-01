"""Database seeding functions for initial data population."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.enums import PropertyType, ServiceType
from db.models import Property, ServiceItem, MinibarItem, StaffMember


async def seed_database(async_session: AsyncSession) -> None:
    """Populate initial data if tables are empty."""

    # Seed properties
    await _seed_properties(async_session)

    # Seed service items
    await _seed_service_items(async_session)

    # Seed minibar items
    await _seed_minibar_items(async_session)

    # Seed staff members
    await _seed_staff_members(async_session)


async def _seed_properties(async_session: AsyncSession) -> None:
    """Seed the properties table if empty."""
    # Check if table is empty
    result = await async_session.execute(select(Property))
    if result.scalars().first():
        return

    properties = [
        # Домики с сауной (3-8)
        Property(
            code="domik_1",
            name_ru="Домик 1",
            name_uz="Domik 1",
            property_type=PropertyType.CHALET_WITH_SAUNA,
            unit_number="1",
            capacity=6,
            has_sauna=True,
            price_weekday=3900000,
            price_weekend=4700000,
            emoji="🏠",
            sort_order=1,
        ),
        Property(
            code="domik_2",
            name_ru="Домик 2",
            name_uz="Domik 2",
            property_type=PropertyType.CHALET_WITH_SAUNA,
            unit_number="2",
            capacity=6,
            has_sauna=True,
            price_weekday=3900000,
            price_weekend=4700000,
            emoji="🏠",
            sort_order=2,
        ),
        # Домики без сауны
        Property(
            code="domik_3",
            name_ru="Домик 3",
            name_uz="Domik 3",
            property_type=PropertyType.CHALET_WITHOUT_SAUNA,
            unit_number="3",
            capacity=6,
            has_sauna=False,
            price_weekday=3500000,
            price_weekend=4200000,
            emoji="🏠",
            sort_order=3,
        ),
        Property(
            code="domik_4",
            name_ru="Домик 4",
            name_uz="Domik 4",
            property_type=PropertyType.CHALET_WITHOUT_SAUNA,
            unit_number="4",
            capacity=6,
            has_sauna=False,
            price_weekday=3500000,
            price_weekend=4200000,
            emoji="🏠",
            sort_order=4,
        ),
        # Домики с сауной (продолжение)
        Property(
            code="domik_5",
            name_ru="Домик 5",
            name_uz="Domik 5",
            property_type=PropertyType.CHALET_WITH_SAUNA,
            unit_number="5",
            capacity=6,
            has_sauna=True,
            price_weekday=3900000,
            price_weekend=4700000,
            emoji="🏠",
            sort_order=5,
        ),
        Property(
            code="domik_6",
            name_ru="Домик 6",
            name_uz="Domik 6",
            property_type=PropertyType.CHALET_WITH_SAUNA,
            unit_number="6",
            capacity=6,
            has_sauna=True,
            price_weekday=3900000,
            price_weekend=4700000,
            emoji="🏠",
            sort_order=6,
        ),
        Property(
            code="domik_7",
            name_ru="Домик 7",
            name_uz="Domik 7",
            property_type=PropertyType.CHALET_WITH_SAUNA,
            unit_number="7",
            capacity=6,
            has_sauna=True,
            price_weekday=3900000,
            price_weekend=4700000,
            emoji="🏠",
            sort_order=7,
        ),
        Property(
            code="domik_8",
            name_ru="Домик 8",
            name_uz="Domik 8",
            property_type=PropertyType.CHALET_WITHOUT_SAUNA,
            unit_number="8",
            capacity=6,
            has_sauna=False,
            price_weekday=3500000,
            price_weekend=4200000,
            emoji="🏠",
            sort_order=8,
        ),
        # Белое Шале
        Property(
            code="white_chalet",
            name_ru="10-Белое Шале",
            name_uz="10-Oq Chalet",
            property_type=PropertyType.WHITE_CHALET,
            unit_number="10",
            capacity=4,
            has_sauna=False,
            price_weekday=2900000,
            price_weekend=3900000,
            emoji="🏡",
            sort_order=9,
        ),
        # Апартаменты
        Property(
            code="apartment_1",
            name_ru="Апартамент 1",
            name_uz="Kvartira 1",
            property_type=PropertyType.APARTMENT,
            unit_number="1",
            capacity=6,
            has_sauna=False,
            price_weekday=2900000,
            price_weekend=3900000,
            emoji="🏢",
            sort_order=10,
        ),
        Property(
            code="apartment_2",
            name_ru="Апартамент 2",
            name_uz="Kvartira 2",
            property_type=PropertyType.APARTMENT,
            unit_number="2",
            capacity=6,
            has_sauna=False,
            price_weekday=2900000,
            price_weekend=3900000,
            emoji="🏢",
            sort_order=11,
        ),
        # Пентхаус
        Property(
            code="penthouse",
            name_ru="Пентхаус",
            name_uz="Penthouse",
            property_type=PropertyType.PENTHOUSE,
            unit_number=None,
            capacity=10,
            has_sauna=False,
            price_weekday=4500000,
            price_weekend=5700000,
            emoji="🏰",
            sort_order=12,
        ),
        # Вилла
        Property(
            code="villa_infinity",
            name_ru="Вилла Infinity",
            name_uz="Villa Infinity",
            property_type=PropertyType.VILLA,
            unit_number=None,
            capacity=25,
            has_sauna=False,
            price_weekday=8500000,
            price_weekend=11000000,
            emoji="🏛",
            sort_order=13,
        ),
        # SPA Сьюты
        Property(
            code="spa_suite_1",
            name_ru="SPA Сьют 1",
            name_uz="SPA Suite 1",
            property_type=PropertyType.SPA_SUITE,
            unit_number="1",
            capacity=2,
            has_sauna=False,
            price_weekday=2700000,
            price_weekend=3300000,
            emoji="🧖",
            sort_order=14,
        ),
        Property(
            code="spa_suite_2",
            name_ru="SPA Сьют 2",
            name_uz="SPA Suite 2",
            property_type=PropertyType.SPA_SUITE,
            unit_number="2",
            capacity=2,
            has_sauna=False,
            price_weekday=2700000,
            price_weekend=3300000,
            emoji="🧖",
            sort_order=15,
        ),
        Property(
            code="spa_suite_3",
            name_ru="SPA Сьют 3",
            name_uz="SPA Suite 3",
            property_type=PropertyType.SPA_SUITE,
            unit_number="3",
            capacity=2,
            has_sauna=False,
            price_weekday=2700000,
            price_weekend=3300000,
            emoji="🧖",
            sort_order=16,
        ),
    ]

    async_session.add_all(properties)
    await async_session.commit()


async def _seed_service_items(async_session: AsyncSession) -> None:
    """Seed the service_items table if empty."""
    # Check if table is empty
    result = await async_session.execute(select(ServiceItem))
    if result.scalars().first():
        return

    services = [
        ServiceItem(
            service_type=ServiceType.CLASSIC_AROMA_45,
            name_ru="Классический аромамассаж 45мин",
            name_uz="Klassik aroma massage 45 min",
            duration_minutes=45,
            price=500000,
            sort_order=1,
        ),
        ServiceItem(
            service_type=ServiceType.CLASSIC_AROMA_60,
            name_ru="Классический аромамассаж 60мин",
            name_uz="Klassik aroma massage 60 min",
            duration_minutes=60,
            price=600000,
            sort_order=2,
        ),
        ServiceItem(
            service_type=ServiceType.DETOX_60,
            name_ru="Детокс терапия 60мин",
            name_uz="Detoks terapiya 60 min",
            duration_minutes=60,
            price=500000,
            sort_order=3,
        ),
        ServiceItem(
            service_type=ServiceType.DETOX_95,
            name_ru="Детокс терапия 95мин",
            name_uz="Detoks terapiya 95 min",
            duration_minutes=95,
            price=850000,
            sort_order=4,
        ),
        ServiceItem(
            service_type=ServiceType.FOOT_MASSAGE_30,
            name_ru="Массаж для ног 30мин",
            name_uz="Oyoq massazhi 30 min",
            duration_minutes=30,
            price=350000,
            sort_order=5,
        ),
        ServiceItem(
            service_type=ServiceType.BACK_MASSAGE_30,
            name_ru="Массаж спины 30мин",
            name_uz="Orqa massazhi 30 min",
            duration_minutes=30,
            price=350000,
            sort_order=6,
        ),
        ServiceItem(
            service_type=ServiceType.HAMMAM,
            name_ru="Хаммам",
            name_uz="Hammam",
            duration_minutes=60,
            price=500000,
            sort_order=7,
        ),
        ServiceItem(
            service_type=ServiceType.OTHER_SERVICE,
            name_ru="Другое",
            name_uz="Boshqa",
            duration_minutes=0,
            price=0,
            sort_order=8,
        ),
    ]

    async_session.add_all(services)
    await async_session.commit()


async def _seed_minibar_items(async_session: AsyncSession) -> None:
    """Seed the minibar_items table if empty."""
    # Check if table is empty
    result = await async_session.execute(select(MinibarItem))
    if result.scalars().first():
        return

    items = [
        MinibarItem(
            name_ru="Пепси",
            name_uz="Pepsi",
            price=20000,
            sort_order=1,
        ),
        MinibarItem(
            name_ru="Фанта",
            name_uz="Fanta",
            price=20000,
            sort_order=2,
        ),
        MinibarItem(
            name_ru="Кока-кола",
            name_uz="Koka-Kola",
            price=20000,
            sort_order=3,
        ),
        MinibarItem(
            name_ru="Вода",
            name_uz="Suv",
            price=15000,
            sort_order=4,
        ),
        MinibarItem(
            name_ru="Сок",
            name_uz="Sho'rva",
            price=25000,
            sort_order=5,
        ),
        MinibarItem(
            name_ru="Снеки",
            name_uz="Sneklar",
            price=30000,
            sort_order=6,
        ),
    ]

    async_session.add_all(items)
    await async_session.commit()


async def _seed_staff_members(async_session: AsyncSession) -> None:
    """Seed the staff_members table if empty."""
    # Check if table is empty
    result = await async_session.execute(select(StaffMember))
    if result.scalars().first():
        return

    staff = [
        StaffMember(
            name="Акбар",
            role_description="Инкассация",
        ),
        StaffMember(
            name="Дилшод",
            role_description="Кухня/доставка",
        ),
        StaffMember(
            name="Шамшод",
            role_description="Кухня",
        ),
        StaffMember(
            name="Илес",
            role_description="Хозяйственные",
        ),
        StaffMember(
            name="Наргиса",
            role_description="Персонал",
        ),
    ]

    async_session.add_all(staff)
    await async_session.commit()
