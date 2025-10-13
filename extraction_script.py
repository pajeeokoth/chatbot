# === Date-first extraction using dateparser (prefer these spans) ===
# Improved date and budget entity extraction using dateparser + heuristics
import dateparser
import re

MONTH_WORDS = r'\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|march|april|may|june|july|august|september|october|november|december)\b'


# === date spans extraction ===
def find_date_spans(text):
    """
    Return list of (start, end, matched_text, parsed_dt) found by dateparser.search.search_dates.
    Fall back to a few explicit regexes (ISO) if needed.
    """
    spans = []
    # === try dateparser search first ===
    if dateparser is not None:
        try:
            res = dateparser.search.search_dates(text, settings={'PREFER_DATES_FROM': 'future', 'RETURN_AS_TIMEZONE_AWARE': False})
        except Exception:
            res = None
        if res:
            for match_text, dt in res:
                # === find first occurrence of match_text (case-insensitive) and use it ===
                m = re.search(re.escape(match_text), text, flags=re.IGNORECASE)
                if m:
                    spans.append((m.start(), m.end()-1, match_text, dt))
    # === fallback: explicit ISO-ish regex spans not caught by dateparser ===
    for m in re.finditer(r'\b20\d{2}[/-]\d{1,2}[/-]\d{1,2}\b', text):
        spans.append((m.start(), m.end()-1, text[m.start():m.end()], None))
    return spans

# === Improved numeric-as-budget decision (use date spans + context cues + year heuristics) ===
CURRENCY_CUES = ['$', 'usd', 'dollars', 'eur', '€', '£', 'budget', 'price', 'cost', 'fare', 'ticket', 'pay']

def is_token_overlapping_spans(start, end, spans):
    return any(s <= start <= e or s <= end <= e for (s,e, *_ ) in spans)

def is_likely_budget_token(text, start, end, date_spans):
    """
    Return True if numeric token at (start,end) is likely a budget, False otherwise.
    Uses date_spans to avoid classifying date tokens.
    """
    # don't label if overlaps an already-detected date
    if is_token_overlapping_spans(start, end, date_spans):
        return False

    window = text[max(0, start-30):min(len(text), end+30)].lower()

    # strong currency cues -> budget
    if any(cue in window for cue in CURRENCY_CUES):
        return True
    # currency symbol immediately before e.g. $1900
    if start > 0 and text[start-1] in ['$', '€', '£']:
        return True

    token = text[start:end+1]
    # numeric-only value
    try:
        val = int(re.sub(r'[^0-9]', '', token))
    except Exception:
        return False

    # heuristic rules for years vs price:
    # if token is a 4-digit year within typical year range and there's a month word nearby -> treat as date
    if len(token) == 4 and 1900 <= val <= 2035:
        month_nearby = re.search(MONTH_WORDS, window, flags=re.IGNORECASE)
        if month_nearby:
            return False  # likely a year in date context
        # if sentence contains explicit date tokens (24, Aug etc) treat as Date
        if re.search(r'\b\d{1,2}\b', window) and re.search(MONTH_WORDS, window, flags=re.IGNORECASE):
            return False

    # numeric-value heuristics: consider values >=100 as plausible budgets (tunable)
    if val >= 100 and val <= 1000000:
        # If text contains words like 'on' before token plus month words, that might be a date: be conservative
        before = text[max(0, start-10):start].lower()
        if re.search(r'\bon\b', before) and re.search(MONTH_WORDS, text, flags=re.IGNORECASE):
            return False
        return True

    return False

    # Using spaCy NER extraction of LUIS utterances from frames.json
# - Uses spaCy NER when available (fallback to rule-based regex and heuristics)
# - Adds more entity patterns (airport codes, times, currencies, passenger counts)

import json
import re
import sys
from pathlib import Path

# === Configuration, Reuse existing notebook constants if available, else fall back ===
INPUT_FILE = globals().get('INPUT_FILE', '../data/frames_dataset/frames.json')
OUTPUT_FILE = globals().get('OUTPUT_FILE', '../data/frames_dataset/luis_flight_booking.json')

# === Intent mapping from frame actions ===
INTENT_MAP = globals().get('INTENT_MAP', {
    'book': 'BookFlight',
    'inform': 'ProvideInfo',
    'offer': 'OfferFlight',
    'request': 'RequestInfo',
    'confirm': 'ConfirmBooking',
    'greet': 'Greet',
    'thankyou': 'ThankYou',
    'select': 'SelectOption',
    'deny': 'DenyRequest',
    'ack': 'Acknowledge'
})

# === IATA airport code mapping (3-letter codes) ===
# This is a small sample; in production, should use a comprehensive list or API lookup as needed ===
IATA_MAP = {
    "LON": "London",
    "NYC": "New York",
    "SFO": "San Francisco",
    "SEA": "Seattle",
    "CHI": "Chicago",
    "BOS": "Boston",
    "ATL": "Atlanta",
    "DFW": "Dallas",
    "DEN": "Denver",
    "MIA": "Miami",
    "LAX": "Los Angeles",
    "PAR": "Paris",
    "BER": "Berlin",
    "ROM": "Rome",
    "AMS": "Amsterdam",
    "BKK": "Bangkok",
    "HKG": "Hong Kong",
    "DEL": "Delhi",
    "DXB": "Dubai",
    "SYD": "Sydney"
}

# === Helper to position finder for IATA codes ===
def map_iata_to_city(value):
    if not value:
        return value
    val = str(value).strip().upper()
    return IATA_MAP.get(val, value)

# === Helper to find positions of value in text (case-insensitive) ===
def find_positions(text, value):
    if not value or not text:
        return None
    s = str(value).strip()
    if not s:
        return None
    m = re.search(re.escape(s), text, flags=re.IGNORECASE)
    if m:
        return m.start(), m.end() - 1
    norm_text = re.sub(r'\s+', ' ', text).lower()
    norm_value = re.sub(r'\s+', ' ', s).lower()
    idx = norm_text.find(norm_value)
    if idx != -1:
        words = norm_value.split()
        pattern = r'\\b' + r'\\s+'.join(map(re.escape, words)) + r'\\b'
        m2 = re.search(pattern, text, flags=re.IGNORECASE)
        if m2:
            return m2.start(), m2.end() - 1
    mapped = map_iata_to_city(s)
    if mapped and mapped.lower() != norm_value:
        norm_mapped = re.sub(r'\s+', ' ', mapped).lower()
        idx2 = norm_text.find(norm_mapped)
        if idx2 != -1:
            words = norm_mapped.split()
            pattern = r'\\b' + r'\\s+'.join(map(re.escape, words)) + r'\\b'
            m2 = re.search(pattern, text, flags=re.IGNORECASE)
            if m2:
                return m2.start(), m2.end() - 1
    from difflib import get_close_matches
    words = norm_text.split()
    cm = get_close_matches(norm_value, words, n=1, cutoff=0.8)
    if cm:
        word = cm[0]
        m3 = re.search(re.escape(word), text, flags=re.IGNORECASE)
        if m3:
            return m3.start(), m3.end() - 1
    return None

# === Entity normalization mapping ===
# ENTITY_MAP = globals().get('ENTITY_MAP', {})

# === Blocklist certain spaCy labels and unwanted entity names ===
BLOCKLIST =  globals().get('BLOCKLIST', {'EVENT', 'FAC', 'LAW', 'PRODUCT', 'NORP', 'PERCENT', 'PERSON', 'WORK_OF_ART'})
# add common unwanted entity names
BLOCKLIST.update({'Act', 'Action', 'Agent', 'Airline', 'Airlines', 'Class', 'Classes', 'Confirmation', 'Email'
                 , 'Emails', 'Flight', 'Flights', 'Meal', 'Meals', 'Name', 'Names'
                 , 'Preference', 'Preferences', 'Seat', 'Seats', 'Status', 'Statuses', 'Ticket', 'Tickets'
                 , 'Type', 'Types', 'Value', 'Values'})
# Ensure a lower-cased blocklist is available for case-insensitive checking
try:
    BLOCKLIST_LOWER = set([b.lower() for b in BLOCKLIST])
except Exception:
    BLOCKLIST_LOWER = set()

# === entity patterns for regex-based extraction ===
ENTITY_PATTERNS = [
    ("DepartureDate", re.compile(r"\b(20\d{2}[\/-]\d{1,2}[\/-]\d{1,2})\b")),
    ("DepartureDate", re.compile(r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+20\d{2})\b", re.IGNORECASE)),
    ("Time", re.compile(r"\b(\d{1,2}:(?:\d{2})(?:\s?[APMapm]{2})?)\b")),
    ("Budget", re.compile(r"\b\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\b")),
    ("Budget", re.compile(r"\b(?:usd|dollars|eur|€|£)\s?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\b", re.IGNORECASE)),
    ("AirportCode", re.compile(r"\b[A-Z]{3}\b")),
    ("NumPassengers", re.compile(r"\b(\d+)\s*(?:passengers|people|persons|pax)\b", re.IGNORECASE)),
]

# === Try to enable spaCy (dependency parsing + NER) and sklearn for optional classifier ===
USE_SPACY = False
try:
    import spacy
    nlp = spacy.load('en_core_web_sm')
    USE_SPACY = True
except Exception:
    USE_SPACY = False

# === Try to import sklearn for optional intent classifier ===
HAVE_SKLEARN = False
clf = None
vectorizer = None
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from collections import Counter
    import joblib, os
    HAVE_SKLEARN = True
except Exception:
    HAVE_SKLEARN = False

# If True, force training and persisting the intent classifier even if training counts are small
FORCE_TRAIN = True

# === Helper for entity extraction ===
def extract_entities_from_text(text):
    date_spans = find_date_spans(text)
    entities = []
    for s, e, match, dt in date_spans:
        entities.append({'category': 'Date', 'offset': s, 'endPos': e, 'text': match})
    for etype, pattern in ENTITY_PATTERNS:
        try:
            for m in pattern.finditer(text):
                s, e = m.start(), m.end()-1
                if is_token_overlapping_spans(s, e, [(ds, de) for ds, de, _, _ in date_spans]):
                    continue
                if any(ent['offset'] <= s <= ent['endPos'] or ent['offset'] <= e <= ent['endPos'] for ent in entities):
                    continue
                entities.append({'category': etype, 'offset': s, 'endPos': e, 'text': text[s:e+1]})
        except re.error:
            continue
    for m in re.finditer(r"\b\d{3,6}\b", text):
        s, e = m.start(), m.end()-1
        if is_token_overlapping_spans(s, e, [(ds, de) for ds, de, _, _ in date_spans]):
            continue
        if any(ent['offset'] <= s <= ent['endPos'] or ent['offset'] <= e <= ent['endPos'] for ent in entities):
            continue
        if is_likely_budget_token(text, s, e, date_spans):
            span_text = text[s:e+1]
            entities.append({'category': 'Budget', 'offset': s, 'endPos': e, 'text': span_text})
    if USE_SPACY:
        doc = nlp(text)
        for ent in doc.ents:
            label = ent.label_
            if label in ('GPE', 'LOC', 'ORG'):
                et = 'Location'
            elif label in ('DATE',):
                et = 'Date'
            elif label in ('TIME',):
                et = 'Time'
            elif label in ('MONEY',):
                et = 'Budget'
            else:
                et = label
            start, end = ent.start_char, ent.end_char-1
            if any(existing['offset'] <= start <= existing['endPos'] or existing['offset'] <= end <= existing['endPos'] for existing in entities):
                continue
            # use case-insensitive blocklist
            if et.lower() in BLOCKLIST_LOWER:
                continue
            entities.append({'category': et, 'offset': start, 'endPos': end, 'text': ent.text})
        # dependency-based heuristics: look for numeric tokens attached to budget/price words
        try:
            for token in doc:
                if token.like_num or token.ent_type_ == 'MONEY':
                    head = token.head.lemma_.lower() if token.head is not None else ''
                    left = token.nbor(-1).lemma_.lower() if token.i > 0 else ''
                    right = token.nbor(1).lemma_.lower() if token.i < len(doc)-1 else ''
                    cues = {'budget', 'price', 'cost', 'fare', 'costs', 'budgeted', 'pay', 'paying', 'expense', 'amount'}
                    if head in cues or left in cues or right in cues or token.ent_type_ == 'MONEY':
                        s = token.idx
                        e = token.idx + len(token.text) - 1
                        if not is_token_overlapping_spans(s, e, [(ds, de) for ds, de, _, _ in date_spans]):
                            if not any(existing['offset'] == s and existing['endPos'] == e for existing in entities):
                                entities.append({'category': 'Budget', 'offset': s, 'endPos': e, 'text': token.text})
        except Exception:
            pass
    for m in re.finditer(r"\b([A-Z]{3})\b", text):
        ctx = text[max(0, m.start()-20):m.end()+20].lower()
        if 'airport' in ctx or 'from' in ctx or 'to' in ctx or 'arriv' in ctx or 'depart' in ctx:
            start, end = m.start(), m.end()-1
            if not any(s['offset'] <= start <= s['endPos'] for s in entities):
                entities.append({'category': 'AirportCode', 'offset': start, 'endPos': end, 'text': m.group(1)})
    for e in entities:
        lab = e['category']
        if lab.lower() in ('location', 'gpe', 'loc'):
            e['category'] = 'Location'
    return entities

# === Helper to convert our internal entity form to the requested final form ===
def to_final_entities(entity_list):
    out = []
    for ent in entity_list:
        cat = ent.get('category') or ent.get('entity')
        # use case-insensitive blocklist check
        if not cat or cat.lower() in BLOCKLIST_LOWER:
            continue
        start = ent.get('offset')
        end = ent.get('endPos')
        if start is None or end is None:
            continue
        length = end - start + 1
        if length <= 0:
            continue
        out.append({'category': cat, 'offset': start, 'length': length})
    return out

# === Gazetteer matcher to supplement spaCy/regex ===
# Usage: before dedupe_entities, call `utter_entities.extend(gazetteer_match(text))` to add matches

GAZETTEER = set([
    'new york', 'los angeles', 'san francisco', 'paris', 'london', 'berlin', 'rome', 'amsterdam',
    'miami', 'chicago', 'seattle', 'boston', 'sydney', 'bangkok', 'hong kong', 'delhi', 'dubai'
])

def gazetteer_match(text):
    """Return list of Location-like entity dicts found in text using a small gazetteer.
    This is a fallback when spaCy is not available or misses multi-word cities.
    """
    text_lower = text.lower()
    found = []
    for name in sorted(GAZETTEER, key=lambda s: -len(s)):
        idx = text_lower.find(name)
        if idx != -1:
            s = idx
            e = idx + len(name) - 1
            found.append({'category': 'Location', 'offset': s, 'endPos': e, 'text': text[s:e+1]})
    return found


# === Helper to Dedupe the found entities ===
def dedupe_entities(entities):
    """Remove exact duplicates and resolve overlapping spans using a priority order.
    Priority (higher first): Date > Budget > Time > Location > AirportCode > NumPassengers > others
    """
    if not entities:
        return []
    
    # === normalize keys first ===
    items = []
    for e in entities:
        items.append({
            'category': e.get('category'),
            'start': int(e.get('offset')),
            'end': int(e.get('endPos')),
            'text': e.get('text')
        })
    # === remove exact duplicates first ===
    uniq = []
    seen = set()
    for it in items:
        key = (it['category'], it['start'], it['end'])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(it)

    # === resolve overlaps using priority ===
    priority = {'Date': 6, 'Budget': 5, 'Time': 4, 'Location': 3, 'AirportCode': 2, 'NumPassengers': 1}

    # === sort by start then by priority desc then by length desc ===
    uniq.sort(key=lambda x: (x['start'], -priority.get(x['category'], 0), -(x['end']-x['start'])))

    result = []
    for cand in uniq:
        overlap = False
        for kept in result:
            if not (cand['end'] < kept['start'] or cand['start'] > kept['end']):

                # overlapping spans: keep the one with higher priority or longer span if same priority
                p_c = priority.get(cand['category'], 0)
                p_k = priority.get(kept['category'], 0)
                if p_c > p_k:
                    # replace kept with cand
                    result.remove(kept)
                    result.append(cand)
                elif p_c == p_k:
                    # same priority: keep longer span
                    len_c = cand['end'] - cand['start']
                    len_k = kept['end'] - kept['start']
                    if len_c > len_k:
                        result.remove(kept)
                        result.append(cand)
                overlap = True
                break
        if not overlap:
            result.append(cand)

    # === convert back to output format ===
    out = []
    for r in result:
        out.append({
            'category': r['category'],
            'offset': r['start'],
            'endPos': r['end'],
            'text': r.get('text')
        })
    return out

# === Load dataset robustly (file may be a dict with 'conversations' or a list of conversations) ===
with open(INPUT_FILE, 'r', encoding='utf-8') as f:
    dataset = json.load(f)

conversations = dataset.get('conversations') if isinstance(dataset, dict) and 'conversations' in dataset else dataset


# === If sklearn is available, attempt to load a persisted classifier + vectorizer if present. ===
# DO NOT train or persist models from the notebook; only load existing artifacts.
clf = None
vectorizer = None
if HAVE_SKLEARN:
    try:
        model_dir = Path(OUTPUT_FILE).parent / 'models'
        clf_file = model_dir / 'intent_clf.joblib'
        vect_file = model_dir / 'intent_vect.joblib'
        if clf_file.exists() and vect_file.exists():
            clf = joblib.load(clf_file)
            vectorizer = joblib.load(vect_file)
            print('✅ Loaded persisted intent classifier from', clf_file)
        else:
            print('ℹ️ sklearn available but no persisted classifier found; skipping training as requested')
    except Exception as e:
        print('⚠️ Failed to load persisted classifier:', e)
        clf = None

output = []


# === Iterate conversations and turns ===
for convo in (conversations or []):
    turns = convo.get('turns') if isinstance(convo, dict) else []
    for turn in (turns or []):
        speaker = (turn.get('speaker') or turn.get('author') or '').lower()
        if speaker != 'user':
            continue
        text = (turn.get('text') or '').strip()
        if not text:
            continue

        # === determine intent: prefer frame/actions ===
        intent = None
        found = False
        for fr in (turn.get('frames') or []):
            for act in (fr.get('actions') or []):
                act_type = (act.get('act') or act.get('type') or act.get('name') or '').lower().strip()
                if not act_type:
                    continue
                if act_type in INTENT_MAP:
                    intent = INTENT_MAP[act_type]
                    found = True
                    break
                base = act_type.split('_')[0]
                if base in INTENT_MAP:
                    intent = INTENT_MAP[base]
                    found = True
                    break
            if found:
                break

        # === classifier fallback ===
        if not intent and clf is not None and vectorizer is not None:
            try:
                pred = clf.predict(vectorizer.transform([text]))
                intent = pred[0]
            except Exception:
                intent = None

        # === heuristic fallback on text if still unknown ===
        if not intent:
            txt = text.lower()
            if any(k in txt for k in ['book', 'reserve', 'purchase', 'buy', 'ticket']):
                intent = 'BookFlight'
            elif any(k in txt for k in ['price', 'cost', 'fare', 'quote', 'how much', 'budget', '$']):
                intent = 'RequestInfo'
            elif any(k in txt for k in ['hello', 'hi', 'good morning', 'hey']):
                intent = 'Greet'
            elif any(k in txt for k in ['thanks', 'thank you']):
                intent = 'ThankYou'
            else:
                intent = 'BookFlight'

        # === entity extraction ===
        utter_entities = []


        # === prefer authoritative frame values when available ===
        for fr in (turn.get('frames') or []):
            candidates = []
            if isinstance(fr.get('info'), list):
                candidates = fr.get('info')
            elif isinstance(fr.get('slots'), list):
                candidates = fr.get('slots')
            elif isinstance(fr.get('attributes'), list):
                candidates = fr.get('attributes')
            for info in (candidates or []):
                slot = info.get('slot') or info.get('name') or info.get('key') or info.get('label')
                value = info.get('value') or info.get('text') or info.get('values') or info.get('valueText')
                if isinstance(value, list) and len(value) > 0:
                    value = value[0]
                if not slot or value is None:
                    continue
                # cat = ENTITY_MAP.get(slot.lower(), slot)
                cat = (slot and slot.lower()) or slot
                pos = None
                try:
                    pos = find_positions(text, value)
                except Exception:
                    pos = None
                if pos:
                    s, e = pos
                    utter_entities.append({'category': cat, 'offset': s, 'endPos': e, 'text': str(value)})

        # === supplement with text-based extraction ===
        try:
            extracted = extract_entities_from_text(text)
        except Exception:
            extracted = []
        for e in (extracted or []):
            category = e.get('category') or e.get('entity')
            start = e.get('offset') if 'offset' in e else e.get('startPos')
            end = e.get('endPos') if 'endPos' in e else e.get('end')
            # case-insensitive blocklist check
            if not category or category.lower() in BLOCKLIST_LOWER:
                continue
            if start is None or end is None:
                continue
            dup = any(d['category'] == category and d['offset'] == start and d['endPos'] == end for d in utter_entities)
            if not dup:
                utter_entities.append({'category': category, 'offset': start, 'endPos': end, 'text': e.get('text')})

        # === add gazetteer matches as fallback (avoid duplicates) ===
        try:
            for g in gazetteer_match(text):
                if not any(d['category'] == g['category'] and d['offset'] == g['offset'] and d['endPos'] == g['endPos'] for d in utter_entities):
                    utter_entities.append(g)
        except Exception:
            pass

        # === spaCy dependency-based budget heuristics ===
        if USE_SPACY:
            try:
                doc = nlp(text)
                for ent in doc.ents:
                    if ent.label_.upper() == 'MONEY':
                        s, e = ent.start_char, ent.end_char - 1
                        if not any(existing['offset'] <= s <= existing['endPos'] or existing['offset'] <= e <= existing['endPos'] for existing in utter_entities):
                            utter_entities.append({'category': 'Budget', 'offset': s, 'endPos': e, 'text': ent.text})
                for token in doc:
                    if token.like_num or token.ent_type_ == 'MONEY':
                        head = token.head.lemma_.lower() if token.head is not None else ''
                        left = token.nbor(-1).lemma_.lower() if token.i > 0 else ''
                        right = token.nbor(1).lemma_.lower() if token.i < len(doc)-1 else ''
                        cues = {'budget', 'price', 'cost', 'fare', 'costs', 'budgeted', 'pay', 'paying', 'expense', 'amount'}
                        if head in cues or left in cues or right in cues or token.ent_type_ == 'MONEY':
                            s = token.idx
                            e = token.idx + len(token.text) - 1
                            if not is_token_overlapping_spans(s, e, find_date_spans(text)):
                                if not any(existing['offset'] == s and existing['endPos'] == e for existing in utter_entities):
                                    utter_entities.append({'category': 'Budget', 'offset': s, 'endPos': e, 'text': token.text})
            except Exception:
                pass
        # === dedupe and finalize entities ===
        utter_entities.extend(gazetteer_match(text))
        deduped = dedupe_entities(utter_entities)
        final_entities = to_final_entities(deduped)
        output.append({
            'intent': intent,
            'language': 'en-us',
            'text': text,
            'entities': final_entities
        })

# === save the simple array format ===
Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)
def normalize_utterance_text(t):
    if not t:
        return ''
    import re
    s = re.sub(r'\s+', ' ', t).strip().lower()
    return s
# === dedupe utterances by (normalized_text, intent) preserving first occurrence ===
seen_utts = set()
deduped_output = []
removed = 0
for item in output:
    key = (normalize_utterance_text(item.get('text', '')), item.get('intent'))
    if key in seen_utts:
        removed += 1
        continue
    seen_utts.add(key)
    deduped_output.append(item)

# === Save output (LUIS JSON) ===
with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
    json.dump(deduped_output, f, indent=2, ensure_ascii=False)

print(f'✅ Wrote {len(deduped_output)} utterances to: {OUTPUT_FILE} (removed {removed} duplicates)')
print("✅ LUIS JSON created successfully!")