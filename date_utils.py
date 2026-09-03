"""
Flexible Arabic/English date & time parsing for the voice agent.

The LLM does the heavy lifting of understanding caller intent ("أبغى أغير
الموعد" -> reschedule); this module only needs to turn a spoken date/DOB
into a Python `date` so Python code (not the LLM) can do the actual
verification/matching - per spec Rule 2 "never invent... use API data for
all facts" applies equally to identity verification: the comparison must be
a deterministic equality check, not an LLM judgment call.

Unlike a fixed set of regex templates, this parses ANY order/format a
caller might actually say a date in, by breaking the transcript into a
sequence of (month-name | numeric-value) tokens - handling digits, spoken
English number words, and mixed forms uniformly - then resolving day/month/
year from that sequence using magnitude and position heuristics. This
covers, among others:
  "12 February 1988"              day-month-year, month as a word
  "1988-02-12" / "12/2/1988"      ISO / slash-numeric
  "26 02 1982"                    space-separated, no separator
  "12826"                          glued digit run: day=12,month=8,year=26
  "twelve eight twenty six"        spoken equivalent of the above
  "twenty twenty six eight twelve" spoken year-month-day
  "August eight twenty six"        month-day-year, day/year as words
  "August eight twenty twenty six" same, with a full 4-digit spoken year

If nothing in the transcript can be confidently resolved into day+month+
year, this returns None - callers must treat that as "ask the caller to
repeat/clarify," never as a license to guess.
"""

import re
from datetime import date
from typing import List, Optional, Tuple

_AR_MONTHS = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "ابريل": 4,
    "مايو": 5, "يونيو": 6, "يوليو": 7, "أغسطس": 8, "اغسطس": 8,
    "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12,
}

_EN_MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}

_EN_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19,
}
_EN_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_Item = Tuple[str, int]  # ('month', 1-12) or ('num', value)


def _normalize_digits(text: str) -> str:
    return text.translate(_ARABIC_DIGITS)


def _tokenize(text: str) -> List[_Item]:
    """
    Breaks the transcript into an ordered sequence of ('month', 1-12) and
    ('num', value) items, discarding filler words. Handles raw digit tokens
    and spoken English number words (including tens+ones compounds like
    "twenty six" -> 26) uniformly in one pass, so callers don't need to
    pre-guess whether a caller spoke digits or words.
    """
    words = re.findall(r"[A-Za-z\u0600-\u06FF]+|\d+", text)
    items: List[_Item] = []
    i = 0
    while i < len(words):
        w = words[i]
        wl = w.lower()

        if w.isdigit():
            items.append(("num", int(w)))
            i += 1
            continue

        if wl in _EN_MONTHS:
            items.append(("month", _EN_MONTHS[wl]))
            i += 1
            continue
        if w in _AR_MONTHS:
            items.append(("month", _AR_MONTHS[w]))
            i += 1
            continue

        if wl in _EN_TENS:
            val = _EN_TENS[wl]
            if i + 1 < len(words) and words[i + 1].lower() in _EN_ONES and _EN_ONES[words[i + 1].lower()] < 10:
                val += _EN_ONES[words[i + 1].lower()]
                i += 1
            items.append(("num", val))
            i += 1
            continue

        if wl in _EN_ONES:
            items.append(("num", _EN_ONES[wl]))
            i += 1
            continue

        i += 1  # filler word (e.g. "the", "of", "على", "في") - discard

    return items


def _merge_year_pairs(items: List[_Item]) -> List[_Item]:
    """
    Merges adjacent ('num', X) ('num', Y) pairs, both in 10-99, into a
    single ('num', X*100+Y) IF the result is a plausible year (1900-2099).
    Handles a 4-digit year spoken as two 2-digit chunks: "twenty twenty six"
    -> 2026, "nineteen eighty two" -> 1982. Values below 10 never combine
    this way, so "twelve eight twenty six" stays as three separate numbers
    (day=12, month=8, year=26) rather than being mis-merged.
    """
    merged: List[_Item] = []
    i = 0
    while i < len(items):
        if (i + 1 < len(items) and items[i][0] == "num" and items[i + 1][0] == "num"
                and 10 <= items[i][1] <= 99 and 10 <= items[i + 1][1] <= 99):
            candidate = items[i][1] * 100 + items[i + 1][1]
            if 1900 <= candidate <= 2099:
                merged.append(("num", candidate))
                i += 2
                continue
        merged.append(items[i])
        i += 1
    return merged


def _expand_year(y: int) -> int:
    """A 2-digit year always means 2000+y in this deployment's context."""
    return 2000 + y if y < 100 else y


def _safe_date(year: int, month: int, day: int) -> Optional[date]:
    try:
        return date(year, month, day)
    except (ValueError, TypeError):
        return None


def _resolve_date_from_items(items: List[_Item]) -> Optional[date]:
    months = [v for k, v in items if k == "month"]
    nums = [v for k, v in items if k == "num"]

    if months:
        # A month name anchors the parse - the two numbers are day and
        # year, in whichever order they appear (day-month-year or
        # month-day-year both reduce to the same two leftover numbers).
        if len(nums) < 2:
            return None
        day, year = nums[0], nums[1]
        return _safe_date(_expand_year(year), months[0], day)

    # No month word - purely numeric/word-numbers. Need exactly three
    # components: day, month, year (in some order).
    if len(nums) < 3:
        return None
    a, b, c = nums[0], nums[1], nums[2]

    if a >= 1900:
        # Leading 4-digit year -> year-month-day (ISO-style / "twenty
        # twenty six eight twelve").
        return _safe_date(a, b, c)

    if c >= 1900:
        # Trailing 4-digit year -> day-month-year ("26 02 1982",
        # "12/2/1988").
        return _safe_date(c, b, a)

    # Neither number is an obvious 4-digit year - default to day-month-year
    # (KSA convention) with the trailing number as a 2-digit year.
    return _safe_date(_expand_year(c), b, a)


def _try_digit_run_split(digits: str) -> Optional[date]:
    """
    Handles a single unbroken run of digits with no separators at all, e.g.
    "12826" meaning day=12, month=8, year=26 (->2026) - spoken as "twelve
    eight twenty six" but transcribed as one glued number. Tries
    day/month/year length splits (day-month-year, KSA convention) across
    plausible digit-length combinations, returning the first valid date.
    """
    n = len(digits)
    if n < 4 or n > 8:
        return None
    for day_len in (1, 2):
        for month_len in (1, 2):
            year_len = n - day_len - month_len
            if year_len not in (2, 4):
                continue
            day = int(digits[:day_len])
            month = int(digits[day_len:day_len + month_len])
            year = _expand_year(int(digits[day_len + month_len:]))
            result = _safe_date(year, month, day)
            if result:
                return result
    return None


def parse_spoken_date(text: str) -> Optional[date]:
    """
    Parses a spoken/transcribed date string - in Arabic or English, in
    essentially any digit/word/order combination a caller might actually
    use - into a Python date. Returns None if it can't confidently parse;
    callers (agent tools) must treat None as "ask the caller to repeat/
    clarify," never as a fallback guess.
    """
    if not text:
        return None
    text = _normalize_digits(text.strip())

    if text.isdigit():
        result = _try_digit_run_split(text)
        if result:
            return result
        # Falls through to the general path below too (e.g. a bare 4-digit
        # year alone wouldn't satisfy the digit-run split's length bounds).

    items = _merge_year_pairs(_tokenize(text))
    return _resolve_date_from_items(items)


def format_date_arabic(d: date) -> str:
    """Formats a date as a natural Arabic phrase, e.g. 'الثلاثاء 18 أغسطس'."""
    ar_months_rev = {
        1: "يناير", 2: "فبراير", 3: "مارس", 4: "أبريل", 5: "مايو", 6: "يونيو",
        7: "يوليو", 8: "أغسطس", 9: "سبتمبر", 10: "أكتوبر", 11: "نوفمبر", 12: "ديسمبر",
    }
    ar_weekdays = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    return f"{ar_weekdays[d.weekday()]} {d.day} {ar_months_rev[d.month]}"


def format_date_english(d: date) -> str:
    return d.strftime("%A %d %B")