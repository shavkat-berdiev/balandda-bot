"""One-off import of existing pool (Бассейн) bookings from the July/August 2026
Google Sheet into the reservations calendar. Idempotent: skips any unit+date that
already has an active booking, so it will not double-book or duplicate on re-run.

Run inside the bot container:
    docker compose exec bot python scripts/import_pool_2026.py
"""

import asyncio
import json
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select
from db.database import async_session
from db.models import Property, Reservation
from db.enums import ReservationStatus, ReservationSource

INACTIVE = (ReservationStatus.CANCELLED, ReservationStatus.EXPIRED)

DATA = json.loads(r'''[
{
"unit": "\u0422\u0435\u0440\u0430\u0441\u0441\u0430 \u041c\u041a1",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u0422\u0435\u0440\u0430\u0441\u0441\u0430 \u041c\u041a2",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u0422\u0435\u0440\u0430\u0441\u0441\u0430 \u041c\u041a3",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u0422\u0435\u0440\u0430\u0441\u0441\u0430 \u041c\u041a4",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u0422\u0435\u0440\u0430\u0441\u0441\u0430 \u041c\u041a5",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u0422\u0435\u0440\u0430\u0441\u0441\u0430 \u041c\u041a6",
"check_in": "2026-07-04",
"nights": 1,
"guest": "\u0418\u0440\u0438\u043d\u0430",
"phone": "330036030",
"note": "\u0418\u0440\u0438\u043d\u0430 330036030"
},
{
"unit": "\u0422\u0435\u0440\u0430\u0441\u0441\u0430 \u041c\u041a6",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 1",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 2",
"check_in": "2026-07-01",
"nights": 1,
"guest": "\u041c\u0430\u043b\u0438\u043a\u0430",
"phone": "901885950",
"note": "\u041c\u0430\u043b\u0438\u043a\u0430 90 188 59 50"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 2",
"check_in": "2026-07-07",
"nights": 1,
"guest": "\u0412\u0435\u0440\u043e\u043d\u0438\u043a\u0430",
"phone": "974014117",
"note": "\u0412\u0435\u0440\u043e\u043d\u0438\u043a\u0430 97 401 41 17"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 2",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 3",
"check_in": "2026-07-01",
"nights": 1,
"guest": "\u0425\u0443\u0440\u0448\u0438\u0434",
"phone": "999761120",
"note": "\u0425\u0443\u0440\u0448\u0438\u0434 99 976 11 20"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 3",
"check_in": "2026-07-03",
"nights": 1,
"guest": "\u0412\u0438\u043b\u043e\u043b\u0430",
"phone": "917773347",
"note": "\u0412\u0438\u043b\u043e\u043b\u0430 917773347"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 3",
"check_in": "2026-07-09",
"nights": 1,
"guest": "\u0421\u0430\u0444\u0438\u044f \u0445\u0443\u0448",
"phone": null,
"note": "\u0421\u0430\u0444\u0438\u044f \u0445\u0443\u0448"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 3",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 4",
"check_in": "2026-07-01",
"nights": 1,
"guest": "\u041d\u0438\u043c",
"phone": "990393797",
"note": "\u041d\u0438\u043c 990393797"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 4",
"check_in": "2026-07-03",
"nights": 1,
"guest": "\u0412\u0438\u043a\u0442\u043e\u0440\u0438\u044f",
"phone": "998642570",
"note": "\u0412\u0438\u043a\u0442\u043e\u0440\u0438\u044f 99 864 25 70"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 4",
"check_in": "2026-07-04",
"nights": 1,
"guest": "\u0420\u0443\u0441\u043b\u0430\u043d",
"phone": "974641817",
"note": "\u0420\u0443\u0441\u043b\u0430\u043d 97 464 18 17"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 4",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 5",
"check_in": "2026-07-01",
"nights": 1,
"guest": "\u0421\u0435\u0432\u0430\u0440\u0430",
"phone": "909051388",
"note": "\u0421\u0435\u0432\u0430\u0440\u0430 90 905 13 88"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 5",
"check_in": "2026-07-03",
"nights": 1,
"guest": "\u042e\u043b\u0434\u0443\u0437",
"phone": "505011100",
"note": "\u042e\u043b\u0434\u0443\u0437 505011100"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 5",
"check_in": "2026-07-04",
"nights": 1,
"guest": "\u0424\u0430\u0440\u0445\u0430\u0434",
"phone": "770967777",
"note": "\u0424\u0430\u0440\u0445\u0430\u0434 77 096 77 77"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 5",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 5",
"check_in": "2026-07-28",
"nights": 1,
"guest": "..998632331",
"phone": "998632331",
"note": "..998632331"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 6",
"check_in": "2026-07-01",
"nights": 1,
"guest": "\u0428\u0430\u0445\u0440\u0438\u0437\u043e\u0434\u0430",
"phone": "909147885",
"note": "\u0428\u0430\u0445\u0440\u0438\u0437\u043e\u0434\u0430 909147885"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 6",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 7",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 8",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437 \u0448\u0430\u043b\u0435",
"phone": null,
"note": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437 \u0448\u0430\u043b\u0435"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 9",
"check_in": "2026-07-01",
"nights": 1,
"guest": "\u041a\u0430\u043c\u0438\u043b\u0430",
"phone": "977680812",
"note": "\u041a\u0430\u043c\u0438\u043b\u0430 97 768 08 12"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 9",
"check_in": "2026-07-10",
"nights": 1,
"guest": "\u0412\u0438\u043e\u043b\u0435\u0442\u0442\u0430",
"phone": "920018889",
"note": "\u0412\u0438\u043e\u043b\u0435\u0442\u0442\u0430 920018889"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 9",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437 \u0448\u0430\u043b\u0435",
"phone": null,
"note": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437 \u0448\u0430\u043b\u0435"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 10",
"check_in": "2026-07-01",
"nights": 1,
"guest": "\u0424\u0430\u0440\u0445\u0430\u0434",
"phone": "974808067",
"note": "\u0424\u0430\u0440\u0445\u0430\u0434 97 480 80 67"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 10",
"check_in": "2026-07-03",
"nights": 1,
"guest": "\u0425\u0430\u0444\u0438\u0437\u0430",
"phone": "771119202",
"note": "\u0425\u0430\u0444\u0438\u0437\u0430 77 111 92 02"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 10",
"check_in": "2026-07-11",
"nights": 1,
"guest": "\u042e\u0440\u044f \u0441\u0435\u0440\u0442\u0438\u0444\u0438\u043a\u0430\u0442",
"phone": null,
"note": "\u042e\u0440\u044f \u0441\u0435\u0440\u0442\u0438\u0444\u0438\u043a\u0430\u0442"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 10",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437 \u0448\u0430\u043b\u0435",
"phone": null,
"note": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437 \u0448\u0430\u043b\u0435"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 11",
"check_in": "2026-07-03",
"nights": 1,
"guest": "\u041a\u0438\u0442\u0430\u0439",
"phone": "971324214",
"note": "\u041a\u0438\u0442\u0430\u0439 97 1324214"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 11",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u041a\u0430\u0431\u0438\u043d\u043a\u0430 12",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 1",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 2",
"check_in": "2026-07-01",
"nights": 1,
"guest": "\u0416\u0430\u0432\u043e\u0445\u0438\u0440",
"phone": "946534649",
"note": "\u0416\u0430\u0432\u043e\u0445\u0438\u0440 94 653 46 49"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 2",
"check_in": "2026-07-03",
"nights": 1,
"guest": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437",
"phone": null,
"note": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437 6 \u0448\u0430\u043b\u0435"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 2",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 3",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 3",
"check_in": "2026-07-25",
"nights": 1,
"guest": "\u0417\u0438\u044f\u043a\u043e\u0432\u0430 \u041c\u0430\u0444\u0442\u0443\u043d\u0430 \u0438\u0437 \u0448\u0430\u043b\u0435",
"phone": null,
"note": "\u0417\u0438\u044f\u043a\u043e\u0432\u0430 \u041c\u0430\u0444\u0442\u0443\u043d\u0430 \u0438\u0437 \u0448\u0430\u043b\u0435"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 4",
"check_in": "2026-07-02",
"nights": 1,
"guest": "\u041d\u043e\u0434\u0438\u0440\u0430",
"phone": "997275566",
"note": "\u041d\u043e\u0434\u0438\u0440\u0430 99 727 55 66"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 4",
"check_in": "2026-07-03",
"nights": 1,
"guest": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437",
"phone": null,
"note": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437 12 \u0434\u043e\u043c\u0438\u043a\u0430"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 4",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437 \u0448\u0430\u043b\u0435",
"phone": null,
"note": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437 \u0448\u0430\u043b\u0435"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 5",
"check_in": "2026-07-01",
"nights": 1,
"guest": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437",
"phone": null,
"note": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437 2 \u0448\u0430\u043b\u0435"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 5",
"check_in": "2026-07-02",
"nights": 1,
"guest": "\u041c\u0443\u0445\u0430\u043c\u043c\u0430\u0434",
"phone": "944080700",
"note": "\u041c\u0443\u0445\u0430\u043c\u043c\u0430\u0434 94 408 07 00"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 5",
"check_in": "2026-07-03",
"nights": 1,
"guest": "\u0420\u0435\u0433\u0438\u043d\u0430",
"phone": "909553165",
"note": "\u0420\u0435\u0433\u0438\u043d\u0430 90 955 31 65"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 5",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437 \u0448\u0430\u043b\u0435",
"phone": null,
"note": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437 \u0448\u0430\u043b\u0435"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 6",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437 \u0448\u0430\u043b\u0435",
"phone": null,
"note": "\u0413\u043e\u0441\u0442\u0438 \u0438\u0437 \u0448\u0430\u043b\u0435"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 6",
"check_in": "2026-07-24",
"nights": 1,
"guest": "\u0425\u0430\u0439\u0438\u0442\u043e\u0432 \u0410\u0445\u043c\u0435\u0434",
"phone": "903150159",
"note": "\u0425\u0430\u0439\u0438\u0442\u043e\u0432 \u0410\u0445\u043c\u0435\u0434 903150159 (4 \u0447\u0435\u043b)"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 6",
"check_in": "2026-07-25",
"nights": 1,
"guest": "\u0415\u043b\u0435\u043d\u0430",
"phone": "770013924",
"note": "\u0415\u043b\u0435\u043d\u0430 770013924 (4 \u0447\u0435\u043b)"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 7",
"check_in": "2026-07-18",
"nights": 1,
"guest": "\u0427\u0438\u043b\u043b\u0430",
"phone": null,
"note": "\u0427\u0438\u043b\u043b\u0430"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 7",
"check_in": "2026-07-24",
"nights": 1,
"guest": "\u041a\u0430\u043c\u0438\u043b\u0430",
"phone": null,
"note": "\u041a\u0430\u043c\u0438\u043b\u0430"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 7",
"check_in": "2026-07-25",
"nights": 1,
"guest": "\u0410\u043d\u0430\u0441\u0442\u0430\u0441\u0438\u044f +",
"phone": "998909604484",
"note": "\u0410\u043d\u0430\u0441\u0442\u0430\u0441\u0438\u044f +998909604484 (6 \u0447\u0435\u043b)"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 6",
"check_in": "2026-08-24",
"nights": 1,
"guest": "\u0425\u0430\u0439\u0438\u0442\u043e\u0432 \u0410\u0445\u043c\u0435\u0434",
"phone": "903150159",
"note": "\u0425\u0430\u0439\u0438\u0442\u043e\u0432 \u0410\u0445\u043c\u0435\u0434 903150159 (4 \u0447\u0435\u043b)"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 6",
"check_in": "2026-08-25",
"nights": 1,
"guest": "\u0415\u043b\u0435\u043d\u0430",
"phone": "770013924",
"note": "\u0415\u043b\u0435\u043d\u0430 770013924 (4 \u0447\u0435\u043b)"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 7",
"check_in": "2026-08-24",
"nights": 1,
"guest": "\u041a\u0430\u043c\u0438\u043b\u0430",
"phone": null,
"note": "\u041a\u0430\u043c\u0438\u043b\u0430"
},
{
"unit": "\u0428\u0430\u0442\u0435\u0440 7",
"check_in": "2026-08-25",
"nights": 1,
"guest": "\u0410\u043d\u0430\u0441\u0442\u0430\u0441\u0438\u044f +",
"phone": "998909604484",
"note": "\u0410\u043d\u0430\u0441\u0442\u0430\u0441\u0438\u044f +998909604484 (6 \u0447\u0435\u043b)"
}
]''')


async def main():
    created = skipped_overlap = skipped_nounit = 0
    async with async_session() as session:
        props = {p.name_ru: p for p in (await session.execute(select(Property))).scalars().all()}
        for b in DATA:
            prop = props.get(b["unit"])
            if not prop:
                skipped_nounit += 1
                print("  NO UNIT:", b["unit"])
                continue
            ci = date.fromisoformat(b["check_in"])
            co = ci + timedelta(days=int(b.get("nights", 1)))
            overlap = (
                await session.execute(
                    select(Reservation).where(
                        Reservation.property_id == prop.id,
                        Reservation.check_in < co,
                        Reservation.check_out > ci,
                        Reservation.status.notin_(INACTIVE),
                    )
                )
            ).scalars().first()
            if overlap:
                skipped_overlap += 1
                continue
            session.add(Reservation(
                property_id=prop.id,
                check_in=ci,
                check_out=co,
                guest_name=(b.get("guest") or None),
                guest_phone=(b.get("phone") or None),
                status=ReservationStatus.CONFIRMED,
                source=ReservationSource.MANUAL,
                note="[импорт бассейн] " + (b.get("note") or ""),
            ))
            await session.commit()
            created += 1
    print(f"\nDONE  created={created}  skipped_overlap={skipped_overlap}  skipped_nounit={skipped_nounit}  total={len(DATA)}")


if __name__ == "__main__":
    asyncio.run(main())
