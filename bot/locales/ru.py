messages = {
    # Start & welcome
    "welcome": (
        "Добро пожаловать в Balandda Analytics!\n\n"
        "Я помогу вам вести учёт наличных поступлений и расходов.\n"
        "Выберите раздел для начала работы."
    ),
    "welcome_back": "С возвращением, {name}!",
    "not_authorized": "У вас нет доступа к этому боту. Обратитесь к администратору.",

    # Sections
    "select_section": "Выберите раздел:",
    "section_resort": "Курорт",
    "section_restaurant": "Ресторан",
    "switched_to": "Вы переключились на: {section}",

    # Main menu
    "main_menu": "Главное меню — {section}",
    "btn_new_report": "Новый отчёт",
    "btn_cash_in": "Приход",
    "btn_cash_out": "Расход",
    "btn_history": "История",
    "btn_report": "Отчёт",
    "btn_settings": "Настройки",

    # Cash flow
    "enter_amount": "Введите сумму (UZS):",
    "select_category": "Выберите категорию:",
    "enter_note": "Добавьте комментарий (или /skip):",
    "confirm_transaction": (
        "Подтвердите запись:\n\n"
        "{type}: {amount:,.0f} UZS\n"
        "Категория: {category}\n"
        "Комментарий: {note}\n\n"
        "Всё верно?"
    ),
    "transaction_saved": "Записано!",
    "transaction_cancelled": "Отменено.",
    "invalid_amount": "Введите корректную сумму (только цифры).",

    # History
    "history_empty": "Нет записей за выбранный период.",
    "history_header": "Последние {count} записей:",

    # Reports
    "report_today": "Отчёт за сегодня — {section}",
    "report_total_in": "Приход: {amount:,.0f} UZS",
    "report_total_out": "Расход: {amount:,.0f} UZS",
    "report_net": "Итого: {amount:,.0f} UZS",

    # Daily auto report
    "daily_report_header": "Ежедневный отчёт — {date}",

    # Settings
    "settings_menu": "Настройки",
    "language_changed": "Язык изменён на русский.",

    # Common
    "btn_confirm": "Подтвердить",
    "btn_cancel": "Отмена",
    "btn_back": "Назад",
    "btn_skip": "Пропустить",
    "error": "Произошла ошибка. Попробуйте ещё раз.",
}
