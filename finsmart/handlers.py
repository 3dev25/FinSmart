from decimal import Decimal
from aiogram import Router,F
from aiogram.filters import Command
from aiogram.types import Message,ReplyKeyboardMarkup,KeyboardButton,Document
from aiogram.fsm.state import State,StatesGroup
from aiogram.fsm.context import FSMContext
from sqlalchemy import select,delete
from finsmart.db import Session,User,UserData
from finsmart.calculators import Loan,compare_prepayment,compare_refinance
from finsmart.cashback import parse_expenses_csv,Expense,CashbackRule,compare_rules
router=Router()
menu=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="💸 Досрочное погашение"),KeyboardButton(text="🔁 Рефинансирование")],[KeyboardButton(text="🎁 Оптимизатор кэшбэка"),KeyboardButton(text="ℹ️ Помощь")]],resize_keyboard=True)
def dec(s):
    try:return Decimal(str(s).replace(" ","").replace(",","."))
    except Exception:raise ValueError("Введите число, например 125000 или 12,5.")
async def save_data(uid,kind,payload):
    async with Session() as db:
        if await db.get(User,uid) is None:db.add(User(telegram_id=uid))
        db.add(UserData(telegram_id=uid,kind=kind,payload=payload));await db.commit()
class Prepay(StatesGroup): principal=State();rate=State();months=State();extra=State()
class Refi(StatesGroup): balance=State();old_rate=State();old_months=State();new_rate=State();new_months=State();fees=State();insurance=State()
class Cash(StatesGroup): csv=State();rules=State()
@router.message(Command("start"))
async def start(m:Message,s:FSMContext):
    await s.clear();await m.answer("FinSmart — расчёты по кредитам и кэшбэку. Все ставки и условия вводите самостоятельно.\\n\\nВыберите инструмент.",reply_markup=menu)
@router.message(Command("privacy"))
async def privacy(m:Message):await m.answer("Храним Telegram ID и введённые вами параметры расчётов. Не отправляйте номера карт, CVV, пароли или банковские выписки с реквизитами.",reply_markup=menu)
@router.message(Command("delete_me"))
async def delete_me(m:Message):
    async with Session() as db:await db.execute(delete(UserData).where(UserData.telegram_id==m.from_user.id));await db.execute(delete(User).where(User.telegram_id==m.from_user.id));await db.commit()
    await m.answer("Ваши сохранённые данные удалены.",reply_markup=menu)
@router.message(Command("prepay"))
@router.message(F.text=="💸 Досрочное погашение")
async def prepay(m:Message,s:FSMContext):await s.clear();await s.set_state(Prepay.principal);await m.answer("Остаток долга в ₽:")
@router.message(Prepay.principal)
async def p1(m:Message,s:FSMContext):
    try:v=dec(m.text);assert v>0
    except Exception:return await m.answer("Введите сумму больше нуля.")
    await s.update_data(principal=str(v));await s.set_state(Prepay.rate);await m.answer("Годовая ставка в %:")
@router.message(Prepay.rate)
async def p2(m:Message,s:FSMContext):
    try:v=dec(m.text);assert 0<=v<=1000
    except Exception:return await m.answer("Введите корректную ставку.")
    await s.update_data(rate=str(v));await s.set_state(Prepay.months);await m.answer("Сколько месяцев осталось (1–600)?")
@router.message(Prepay.months)
async def p3(m:Message,s:FSMContext):
    try:v=int(m.text);assert 1<=v<=600
    except Exception:return await m.answer("Введите целое число от 1 до 600.")
    await s.update_data(months=v);await s.set_state(Prepay.extra);await m.answer("Сколько дополнительно вносить каждый месяц (₽)?")
@router.message(Prepay.extra)
async def p4(m:Message,s:FSMContext):
    try:v=dec(m.text);assert v>=0
    except Exception:return await m.answer("Введите неотрицательную сумму.")
    d=await s.get_data();await s.clear();r=compare_prepayment(Loan(Decimal(d['principal']),Decimal(d['rate']),d['months']),v);fmt=lambda x:f"{x:,.2f} ₽".replace(","," ")
    await save_data(m.from_user.id,"prepayment",d|{"extra":str(v)})
    await m.answer(f"Сравнение досрочного погашения\\nБез досрочных: проценты {fmt(r.baseline.total_interest)}, срок {r.baseline.final_month} мес.\\n\\nСократить срок: проценты {fmt(r.reduce_term.total_interest)}, срок {r.reduce_term.final_month} мес., экономия {fmt(r.interest_saved_term)}\\nУменьшать платёж: проценты {fmt(r.reduce_payment.total_interest)}, срок {r.reduce_payment.final_month} мес., экономия {fmt(r.interest_saved_payment)}\\n\\nОценка по аннуитетной модели; правила банка могут отличаться.",reply_markup=menu)
@router.message(Command("refinance"))
@router.message(F.text=="🔁 Рефинансирование")
async def refinance(m:Message,s:FSMContext):await s.clear();await s.set_state(Refi.balance);await m.answer("Остаток текущего долга (₽):")
async def next_refi(m,s,state,key,value,prompt):await s.update_data(**{key:str(value)});await s.set_state(state);await m.answer(prompt)
@router.message(Refi.balance)
async def r1(m:Message,s:FSMContext):
    try:v=dec(m.text);assert v>0
    except Exception:return await m.answer("Введите сумму больше нуля.")
    await next_refi(m,s,Refi.old_rate,"balance",v,"Ставка текущего кредита (%):")
@router.message(Refi.old_rate)
async def r2(m:Message,s:FSMContext):
    try:v=dec(m.text);assert v>=0
    except Exception:return await m.answer("Введите корректную ставку.")
    await next_refi(m,s,Refi.old_months,"old_rate",v,"Сколько месяцев осталось?")
@router.message(Refi.old_months)
async def r3(m:Message,s:FSMContext):
    try:v=int(m.text);assert 1<=v<=600
    except Exception:return await m.answer("Введите от 1 до 600.")
    await next_refi(m,s,Refi.new_rate,"old_months",v,"Ставка нового кредита (%):")
@router.message(Refi.new_rate)
async def r4(m:Message,s:FSMContext):
    try:v=dec(m.text);assert v>=0
    except Exception:return await m.answer("Введите корректную ставку.")
    await next_refi(m,s,Refi.new_months,"new_rate",v,"Срок нового кредита в месяцах:")
@router.message(Refi.new_months)
async def r5(m:Message,s:FSMContext):
    try:v=int(m.text);assert 1<=v<=600
    except Exception:return await m.answer("Введите от 1 до 600.")
    await next_refi(m,s,Refi.fees,"new_months",v,"Комиссии и расходы (₽, если нет — 0):")
@router.message(Refi.fees)
async def r6(m:Message,s:FSMContext):
    try:v=dec(m.text);assert v>=0
    except Exception:return await m.answer("Введите неотрицательную сумму.")
    await next_refi(m,s,Refi.insurance,"fees",v,"Страховка за весь срок (₽, если нет — 0):")
@router.message(Refi.insurance)
async def r7(m:Message,s:FSMContext):
    try:v=dec(m.text);assert v>=0
    except Exception:return await m.answer("Введите неотрицательную сумму.")
    d=await s.get_data();await s.clear();r=compare_refinance(Decimal(d['balance']),Decimal(d['old_rate']),int(d['old_months']),Decimal(d['new_rate']),int(d['new_months']),Decimal(d['fees']),v);fmt=lambda x:f"{x:,.2f} ₽".replace(","," ")
    await save_data(m.from_user.id,"refinance",d|{"insurance":str(v)})
    await m.answer(f"Текущий кредит: {fmt(r.current_total)}\\nНовый кредит и расходы: {fmt(r.new_total)}\\nЧистая выгода: {fmt(r.net_saving)}\\nОкупаемость расходов: {r.break_even_month or 'не достигнута'} мес.",reply_markup=menu)
@router.message(Command("cashback"))
@router.message(F.text=="🎁 Оптимизатор кэшбэка")
async def cash_start(m:Message,s:FSMContext):await s.clear();await s.set_state(Cash.csv);await m.answer("Пришлите CSV расходов. Нужны столбцы суммы и категории. Удалите банковские реквизиты.")
@router.message(Cash.csv,F.document)
async def cash_file(m:Message,s:FSMContext):
    if m.document.file_size and m.document.file_size>5_000_000:
        return await m.answer("Максимальный размер CSV — 5 МБ.")
    f=await m.bot.get_file(m.document.file_id)
    stream=await m.bot.download_file(f.file_path)
    try:
        rows=parse_expenses_csv(stream.read())
    except Exception as e:
        return await m.answer(f"Ошибка CSV: {e}")
    if not rows:
        return await m.answer("В CSV не найдены расходы.")
    categories=sorted({x.category for x in rows})
    await s.update_data(
        expenses=[{"amount":str(x.amount),"category":x.category,
                   "description":x.description,"date":x.date} for x in rows],
        rules=[]
    )
    await s.set_state(Cash.rules)
    await m.answer(
        "Категории в файле:\\n"+"\\n".join(categories)+
        "\\n\\nДобавляйте правила по одному сообщению в формате:\\n"
        "Категория; ставка%; месячный лимит ₽\\n"
        "Пример: Супермаркеты; 5; 1500\\n"
        "Лимит 0 означает без лимита. Напишите ГОТОВО, когда внесёте все правила."
    )


@router.message(Cash.csv)
async def cash_wrong(m:Message):
    await m.answer("Прикрепите CSV-файл документом.")


@router.message(Cash.rules)
async def cash_rules(m:Message,s:FSMContext):
    if not m.text:
        return await m.answer("Отправьте правило текстом или напишите ГОТОВО.")
    if m.text.strip().casefold() in {"готово","готов"}:
        data=await s.get_data()
        if not data.get("rules"):
            return await m.answer("Добавьте хотя бы одно правило перед завершением.")
        rows=[Expense(Decimal(x["amount"]),x["category"],x["description"],x["date"])
              for x in data["expenses"]]
        results=compare_rules(rows,[
            CashbackRule(
                name=rule["name"],category=rule["category"],
                rate_percent=Decimal(rule["rate_percent"]),
                monthly_cap=Decimal(rule["monthly_cap"]) if rule["monthly_cap"] is not None else None
            ) for rule in data["rules"]
        ])
        await s.clear()
        await save_data(
            m.from_user.id,"cashback",
            {"rules":data["rules"],"rows":len(rows)}
        )
        lines=["Сравнение введённых условий кэшбэка:"]
        for item,rule in zip(results,data["rules"]):
            lines.append(
                f"{rule['name']} ({item.category}, {rule['rate_percent']}%): {item.cashback:,.2f} ₽; "
                f"подходящие расходы {item.eligible_spend:,.2f} ₽; "
                f"упущено относительно лучшего правила этой категории "
                f"{item.lost_cashback:,.2f} ₽"
            )
        lines.append(
            "\\nРасчёт ориентировочный: без MCC и полных банковских условий "
            "нельзя проверить исключения, округление и дополнительные ограничения."
        )
        return await m.answer("\\n".join(lines),reply_markup=menu)

    parts=[part.strip() for part in m.text.split(";")]
    if len(parts)!=3:
        return await m.answer("Нужен формат: Категория; ставка%; месячный лимит ₽")
    data=await s.get_data()
    categories={x["category"].casefold():x["category"] for x in data["expenses"]}
    category=categories.get(parts[0].casefold())
    if not category:
        return await m.answer("Категория должна точно совпадать с одной из категорий CSV.")
    try:
        rate=dec(parts[1])
        cap=dec(parts[2])
        if not Decimal("0")<=rate<=Decimal("100") or cap<0:
            raise ValueError()
    except Exception:
        return await m.answer("Ставка должна быть 0–100%, лимит — неотрицательным числом.")
    rules=data.get("rules",[])
        rules.append({
        "name":f"Условие {len(rules)+1}",
        "category":category,
        "rate_percent":str(rate),
        "monthly_cap":None if cap==0 else str(cap),
    })
    await s.update_data(rules=rules)
    await m.answer(
        f"Добавлено: {category}, {rate}%"
        +(f", лимит {cap:,.2f} ₽" if cap else ", без лимита")
        +". Добавьте следующее правило или напишите ГОТОВО."
    )

@router.message(Command("help"))
@router.message(F.text=="ℹ️ Помощь")
async def help_msg(m:Message):await m.answer("/prepay — досрочное погашение\\n/refinance — рефинансирование\\n/cashback — кэшбэк по CSV\\n/privacy — данные\\n/delete_me — удалить данные",reply_markup=menu)
@router.message()
async def fallback(m:Message):await m.answer("Выберите инструмент в меню или используйте /help.",reply_markup=menu)
