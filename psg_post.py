import json
import argparse
import re
from pathlib import Path
from copy import deepcopy


# ── Skema (identisk med SCHEMA i psg_extract_pipeline.py) ────────────────────

SCHEMA = {
    "metadata": {"filnavn": None, "udfyldt_af": None},
    "patient": {
        "navn": None, "cpr-nummer": None, "vaegt": None,
        "hoejde": None, "BMI": None, "ESS": None,
    },
    "test_oplysninger": {
        "dato": None, "henviser": None, "henvisningsdiagnose": None,
        "starttid": None, "sluttid": None, "total_optagetid": None,
        "optaget_af": None, "neurofysiologi_assisstent": None, "montage": None,
    },
    "klinisk_information": {
        "klinisk_resume": None, "kommentar": None,
        "patient_oplysninger_ved_optagelse": None, "medicin": None,
    },
    "soevn_opsummering": {
        "scoringens_navn": None, "analyse_start_lights_out": None,
        "analyse_afslutning_lights_on": None, "tid_i_seng_trt_min": None,
        "total_soevntid_tst_min": None, "soveperiode_min": None,
        "soevneffektivitet_procent": None, "soevnlatens_min": None,
        "rem_latens_min": None, "antal_opvaagninger": None,
        "arousals": {"total": None, "indeks": None},
    },
    "soevnstadier": {
        s: {"latens_min": None, "varighed_min": None, "procent_af_tst": None}
        for s in ("vaagen", "n1", "n2", "n3", "rem", "total")
    },
    "oget_muskelaktivitet_rem": {"chin": None, "tib": None, "fds": None},
    "respirations_analyse": {
        "ahi_total": None, "ahi_rygleje": None, "ahi_ikke_rygleje": None,
        "andel_natten_i_rygleje_procent": None,
        "obstruktiv_apnoe_indeks": None, "mixed_apnoe_indeks": None,
        "central_apnoe_indeks": None, "hypopnoe_indeks": None,
        "oxygen_desaturationer": {"total": None, "indeks": None},
    },
    "spo2_oversigt": {
        "baseline": None,
        "minimum_procent":  {"vaagen": None, "nrem": None, "rem": None, "total": None},
        "middel_procent":   {"vaagen": None, "nrem": None, "rem": None, "total": None},
        "maksimum_procent": {"vaagen": None, "nrem": None, "rem": None, "total": None},
        "spo2_under_90_procent": {
            "akkumuleret_varighed": None, "akkumuleret_procent": None,
        },
        "co2_vaerdier": {"etco2_max": None, "tcpco2_max": None},
    },
    "benbevaegelser": {
        "lm_indeks":   {"vaagen": None, "nrem": None, "rem": None, "total": None},
        "plms_indeks": {"vaagen": None, "nrem": None, "rem": None, "total": None},
        "lms_efterfulgt_af_arousals": None,
    },
    "hjerte": {"middel_hjertefrekvens": None, "ekg_bemaerkninger": None},
    "sammenfatning": {
        "soevnmoenster": None, "soevn_dagtid": None, "anfald": None,
        "beskrivelse": None, "paroksystisk_aktivitet": None, "fokal": None,
    },
    "konklusion_og_plan": {
        "bedoemt_af": None, "dato_for_bedoemmelse": None,
        "konklusion_tekst": None, "plan": None,
        "a_diagnose": {"kode": None, "tekst": None},
        "b_diagnose": {"kode": None, "tekst": None},
    },
}


# ── 1. Stavefejl-mapping ──────────────────────────────────────────────────────
# Format: (sektion, forkert_nøgle, korrekt_nøgle)
# Kun ét niveau ad gangen — dybe stier håndteres via sektion-nøgle-par.

STAVEFEJL: list[tuple[str, str, str]] = [
    # patient
    ("patient",               "cpr_nummer",              "cpr-nummer"),
    # respirationsanalyse
    ("respirations_analyse",  "ahi_ikke_erygleje",        "ahi_ikke_rygleje"),
    ("respirations_analyse",  "ahi_ikke_rielje",          "ahi_ikke_rygleje"),
    ("respirations_analyse",  "ahi_ikke_rygeje",          "ahi_ikke_rygleje"),
    # sammenfatning
    ("sammenfatning",         "paroksystisk_aktvitet",    "paroksystisk_aktivitet"),
    ("sammenfatning",         "paroksystisk_akti_vitet",  "paroksystisk_aktivitet"),
    ("sammenfatning",         "paroksystisk_aglebivelse", "paroksystisk_aktivitet"),
    ("sammenfatning",         "beskrivere",               "beskrivelse"),
    # benbevaegelser
    ("benbevaegelser",        "lms_efterfuldt_af_arousals", "lms_efterfulgt_af_arousals"),
]

# Søvnstadier: gammel S-nomenklatur → ny N-nomenklatur
STADIE_MAP = {"s1": "n1", "s2": "n2", "s3": "n3", "s4": None}  # s4 ignoreres


def ret_stavefejl(obj: dict, log: list) -> dict:
    """Ret kendte feltnavn-varianter til kanoniske navne."""
    for sektion, forkert, korrekt in STAVEFEJL:
        sek = obj.get(sektion)
        if not isinstance(sek, dict):
            continue
        if forkert in sek and korrekt not in sek:
            sek[korrekt] = sek.pop(forkert)
            log.append(f"{sektion}.{forkert} → {korrekt}")
        elif forkert in sek and korrekt in sek:
            # Begge findes — bevar korrekt, slet forkert
            sek.pop(forkert)
            log.append(f"{sektion}.{forkert} fjernet (duplikat)")

    # Søvnstadier S1/S2/S3 → N1/N2/N3
    stadier = obj.get("soevnstadier")
    if isinstance(stadier, dict):
        for gammel, ny in STADIE_MAP.items():
            if gammel in stadier:
                if ny is not None and ny not in stadier:
                    stadier[ny] = stadier.pop(gammel)
                    log.append(f"soevnstadier.{gammel} → {ny}")
                else:
                    stadier.pop(gammel)
                    log.append(f"soevnstadier.{gammel} fjernet (s4 eller duplikat)")

    return obj


# ── 2. Checkbox-rettelse ──────────────────────────────────────────────────────

def _kollaps_checkbox(val) -> bool | None:
    if val is None or isinstance(val, bool):
        return val
    if not isinstance(val, dict):
        return val
    norm = {k.lower().strip(":"): v for k, v in val.items()}
    def _b(x):
        if isinstance(x, bool): return x
        if isinstance(x, (int, float)): return bool(x)
        return str(x).lower() in ("true", "1", "ja", "yes", "x")
    ja  = _b(norm.get("ja",  False))
    nej = _b(norm.get("nej", False))
    if ja and not nej:  return True
    if nej and not ja:  return False
    return None


def ret_checkboxes(obj: dict, log: list) -> dict:
    rem = obj.get("oget_muskelaktivitet_rem")
    if not isinstance(rem, dict):
        return obj
    for felt in ("chin", "tib", "fds"):
        if felt not in rem:
            continue
        gammel = rem[felt]
        if isinstance(gammel, dict):
            ny = _kollaps_checkbox(gammel)
            rem[felt] = ny
            log.append(f"oget_muskelaktivitet_rem.{felt}: dict → {ny}")
    return obj


# ── 3. Medicin-dict → streng ──────────────────────────────────────────────────

def ret_medicin(obj: dict, log: list) -> dict:
    """
    Hvis medicin er en dict med medicinnavn-nøgler eller en liste, kollaps til streng.
    fx {"Keppra": "200mg", "Topimax": "50mg"} → "Keppra: 200mg, Topimax: 50mg"
    eller ["Duloxetin 60 mg mod angst", "Amlodipin 10 mg for BT"] → samme (newline-adskilt)
    """
    ki = obj.get("klinisk_information")
    if not isinstance(ki, dict):
        return obj
    medicin = ki.get("medicin")
    if medicin is None:
        return obj
    
    # Skema siger medicin skal være string (eller null)
    dele = []
    
    if isinstance(medicin, dict):
        # Dict: "navn: dosis" per indgang
        for k, v in medicin.items():
            if v and str(v).strip():
                dele.append(f"{k}: {v}")
            else:
                dele.append(k)
        ki["medicin"] = "\n".join(dele) if dele else None
        log.append(f"klinisk_information.medicin: dict({len(medicin)} indgange) → streng")
    elif isinstance(medicin, list):
        # Liste: hver indgang som streng, join med newline
        dele = [str(item).strip() for item in medicin if item and str(item).strip()]
        ki["medicin"] = "\n".join(dele) if dele else None
        log.append(f"klinisk_information.medicin: liste({len(medicin)} indgange) → streng")
    
    return obj


# ── 3b. Dato-normalisering ───────────────────────────────────────────────────

_DATE_PATHS: list[tuple[str, ...]] = [
    ("test_oplysninger", "dato"),
    ("konklusion_og_plan", "dato_for_bedoemmelse"),
]


def _normalize_date_str(val: str) -> str | None:
    """Normaliser forskellige dato-formater til 'dd-mm-yyyy'.

    Eksempler:
      - '22-23.09 2006' -> '22-09-2006'  (tager første dag i intervallet)
      - '22.09.2006'    -> '22-09-2006'
      - '22/09/2006'    -> '22-09-2006'
      - '2006-09-22'    -> '22-09-2006'
    Returnerer None hvis formatet ikke kan parses sikkert.
    """
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None

    # dd[-dd].mm yyyy  (tillad ., -, / og mellemrum)
    m = re.match(
        r"^\s*(?P<d1>\d{1,2})(?:\s*[-–]\s*(?P<d2>\d{1,2}))?\s*"
        r"[./-]\s*(?P<m>\d{1,2})\s*[./-]?\s*(?P<y>\d{2,4})\s*$",
        s,
    )
    if m:
        day = int(m.group("d1"))
        month = int(m.group("m"))
        year = int(m.group("y"))
        if year < 100:
            # konservativ antagelse: 00-79 -> 2000-2079, 80-99 -> 1980-1999
            year = 2000 + year if year <= 79 else 1900 + year
        if 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100:
            return f"{day:02d}-{month:02d}-{year:04d}"
        return None

    # yyyy-mm-dd (evt. med / eller .)
    m = re.match(
        r"^\s*(?P<y>\d{4})\s*[./-]\s*(?P<m>\d{1,2})\s*[./-]\s*(?P<d>\d{1,2})\s*$",
        s,
    )
    if m:
        year = int(m.group("y"))
        month = int(m.group("m"))
        day = int(m.group("d"))
        if 1 <= day <= 31 and 1 <= month <= 12 and 1900 <= year <= 2100:
            return f"{day:02d}-{month:02d}-{year:04d}"
        return None

    return None


def _get_in(obj: dict, path: tuple[str, ...]):
    cur = obj
    for key in path[:-1]:
        if not isinstance(cur, dict):
            return None, None
        cur = cur.get(key)
    if not isinstance(cur, dict):
        return None, None
    return cur, path[-1]


def ret_datoer(obj: dict, log: list) -> dict:
    for path in _DATE_PATHS:
        parent, leaf = _get_in(obj, path)
        if parent is None or leaf is None:
            continue
        old = parent.get(leaf)
        if old is None:
            continue
        if isinstance(old, dict):
            # Undgå at gætte hvis LLM har lavet en struktur.
            continue
        new = _normalize_date_str(old)
        if new and str(old).strip() != new:
            parent[leaf] = new
            log.append(f"{'.'.join(path)}: '{str(old).strip()}' → '{new}'")
    return obj


# ── 3c. Generel normalisering (a la compare_experiments) ────────────────────

TOMME = {
    "", "-", "\u2013", "\u2014", "n/a", "na", "none", "null", "ikke udfyldt",
    "mangler", "-/-", "./.", ".",
}
BOOL_SAND = {"true", "ja", "yes", "1", "sand", "positiv", "x"}
BOOL_FALSK = {"false", "nej", "no", "0", "falsk", "negativ", "intet", "ingen"}
ENHED = re.compile(
    r"\s*(cm|kg|%|/h|/t|timer|min\.|min|minutter|slag per minut|bpm|kg/m2|kpa|sek|sekunder|ml|l|mmhg|hz|mv)\s*$",
    flags=re.IGNORECASE,
)

KLOKKESLAET = {
    "test_oplysninger.starttid",
    "test_oplysninger.sluttid",
    "soevn_opsummering.analyse_start_lights_out",
    "soevn_opsummering.analyse_afslutning_lights_on",
}

# Felt-specifikke varighedsfelter som skal tolkes som H:MM:SS eller MM:SS
DURATION_FIELDS = {
    "spo2_oversigt.spo2_under_90_procent.akkumuleret_varighed",
}

# Felter vi IKKE skal forsøge at konvertere til tal/bool.
FRITEKST = {
    "klinisk_information.klinisk_resume",
    "klinisk_information.kommentar",
    "klinisk_information.patient_oplysninger_ved_optagelse",
    "klinisk_information.medicin",
    "test_oplysninger.henvisningsdiagnose",
    "test_oplysninger.henviser",
    "hjerte.ekg_bemaerkninger",
    "patient.navn",
    "sammenfatning.soevnmoenster",
    "sammenfatning.soevn_dagtid",
    "sammenfatning.anfald",
    "sammenfatning.beskrivelse",
    "sammenfatning.paroksystisk_aktivitet",
    "sammenfatning.fokal",
    "konklusion_og_plan.konklusion_tekst",
    "konklusion_og_plan.plan",
    "konklusion_og_plan.bedoemt_af",
}

NOMINALE = {
    "patient.cpr-nummer",
    "test_oplysninger.dato",
    "test_oplysninger.starttid",
    "test_oplysninger.sluttid",
    "test_oplysninger.montage",
    "konklusion_og_plan.dato_for_bedoemmelse",
    "konklusion_og_plan.a_diagnose.kode",
    "konklusion_og_plan.a_diagnose.tekst",
    "konklusion_og_plan.b_diagnose.kode",
    "konklusion_og_plan.b_diagnose.tekst",
}

# Kendte bool-felter i skemaet (udover checkbox-dicts som allerede håndteres).
BOOL_FIELDS = {
    "oget_muskelaktivitet_rem.chin",
    "oget_muskelaktivitet_rem.tib",
    "oget_muskelaktivitet_rem.fds",
    "benbevaegelser.lms_efterfulgt_af_arousals",
}


def _normalize_time_str(s: str) -> str | None:
    """Normaliser klokkeslæt til 'HH:MM:SS'.

    - Hvis input er 'H:MM' antages sekunder = 00.
    - Hvis input er 'H:MM:SS' bevares sekunder.
    - Returnerer None hvis det ikke ligner et klokkeslæt.
    """
    m = re.match(
        r"^\s*(\d{1,2})\s*[:.]\s*(\d{2})(?:\s*[:.]\s*(\d{2}))?\s*$",
        s,
    )
    if not m:
        return None
    h = int(m.group(1))
    mi = int(m.group(2))
    sec = int(m.group(3)) if m.group(3) is not None else 0
    if 0 <= h <= 47 and 0 <= mi <= 59 and 0 <= sec <= 59:
        return f"{h:02d}:{mi:02d}:{sec:02d}"
    return None


def _normalize_duration_to_minutes(s: str) -> float | None:
    """Konverter varighed skrevet som H:MM eller H:MM:SS til minutter."""
    m = re.match(r"^\s*(\d{1,3})\s*:\s*(\d{2})(?:\s*:\s*(\d{2}))?\s*$", s)
    if not m:
        return None
    first = int(m.group(1))
    second = int(m.group(2))
    third = int(m.group(3)) if m.group(3) else None
    # Hvis der er tre komponenter: H:MM:SS -> timer:minutter:sekunder
    if third is not None:
        h = first; mi = second; sec = third
        if not (0 <= mi <= 59 and 0 <= sec <= 59):
            return None
        return round(h * 60 + mi + sec / 60.0, 2)
    # To-komponent: tolkes som minutter:sekunder (mm:ss), ikke timer:minutter
    minutes = first; sec = second
    if not (0 <= sec <= 59):
        return None
    return round(minutes + sec / 60.0, 2)


def _normalize_scalar(felt: str, v):
    if v is None:
        return None
    if isinstance(v, (int, float, bool)):
        return v

    s = str(v).strip()
    if not s:
        return None
    sl = s.lower().strip()
    if sl in TOMME:
        return None

    # Datoer (kun whitelisted felter)
    if felt in {".".join(p) for p in _DATE_PATHS}:
        nd = _normalize_date_str(s)
        return nd if nd is not None else s

    # Klokkeslæt-felter: normaliser til HH:MM:SS (behold som string)
    if felt in KLOKKESLAET:
        nt = _normalize_time_str(s)
        return nt if nt is not None else s

    # Fritekst/nominale felter: behold som string (men nulstil tydelige TOMME ovenfor)
    if felt in FRITEKST or felt in NOMINALE:
        return s
    # Numeric: strip enhed, håndtér komma-decimal og parse FØR bool-konvertering
    s2 = ENHED.sub("", s).strip()
    if re.match(r"^-?\d+,\d+$", s2):
        s2 = s2.replace(",", ".")
    if re.match(r"^-?\d+(?:\.\d+)?$", s2):
        try:
            f = float(s2)
            if f.is_integer():
                return int(f)
            return f
        except ValueError:
            pass

    # Bool-normalisering (a la compare_experiments): ja/nej/true/false -> bool
    if sl in BOOL_SAND:
        return True
    if sl in BOOL_FALSK:
        return False

    # Kendte bool-felter kan stadig ligge som andre typer (fx 0/1) og bør bevares
    # som de er, hvis de ikke matcher kendte bool-strenge.
    if felt in BOOL_FIELDS:
        return v

    # Varigheder: hvis modellen har skrevet H:MM(:SS) i et *_min felt
    if felt in DURATION_FIELDS or felt.endswith("_min"):
        dur = _normalize_duration_to_minutes(s)
        if dur is not None:
            return dur

    return s


def ret_normaliser(obj: dict, log: list) -> dict:
    """Normaliser scalar-værdier på relevante felter (uden at røre struktur)."""

    def _walk(cur, prefix: str = ""):
        if not isinstance(cur, dict):
            return
        for k, v in list(cur.items()):
            felt = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                _walk(v, felt)
                continue
            if isinstance(v, list):
                # Skemaet bruger ikke lister; lad dem være og lad skema-tvang håndtere det.
                continue
            nv = _normalize_scalar(felt, v)
            if nv != v:
                cur[k] = nv
                log.append(f"{felt}: {v!r} → {nv!r}")

    _walk(obj)
    return obj


# ── 4. Skema-tvang ────────────────────────────────────────────────────────────

def _tving_sektion(
    output: dict | None,
    skema: dict,
    sti: str,
    log: list,
    keep_extra: bool = False,
) -> dict:
    """
    Returner en ny dict der præcist matcher skemaets struktur.
    - Manglende nøgler udfyldes med None
    - Ekstra nøgler fjernes (logges)
    - Nested dicts behandles rekursivt
    - Scalars der er dicts forsøges reddet (apnø-indeks.total → scalar)
    """
    if not isinstance(output, dict):
        if output is not None:
            log.append(f"{sti}: forventet dict, fik {type(output).__name__} → nulstiller")
        return {
            k: (
                _tving_sektion(None, v, f"{sti}.{k}", log, keep_extra=keep_extra)
                if isinstance(v, dict)
                else None
            )
            for k, v in skema.items()
        }

    rettet = {}
    for noegle, skema_val in skema.items():
        felt_sti = f"{sti}.{noegle}" if sti else noegle
        output_val = output.get(noegle)

        if isinstance(skema_val, dict):
            rettet[noegle] = _tving_sektion(
                output_val,
                skema_val,
                felt_sti,
                log,
                keep_extra=keep_extra,
            )
        else:
            # Forventet scalar
            if isinstance(output_val, dict):
                # Prøv at redde: tag .total hvis det findes, ellers None
                reddet = output_val.get("total", output_val.get("indeks"))
                if reddet is not None:
                    log.append(f"{felt_sti}: dict → .total={reddet}")
                else:
                    log.append(f"{felt_sti}: dict uden .total → null")
                    reddet = None
                rettet[noegle] = reddet
            else:
                rettet[noegle] = output_val

    # Ekstra nøgler: fjern (default) eller behold (keep_extra)
    extra = sorted(set(output.keys()) - set(skema.keys()))
    if extra:
        if keep_extra:
            for k in extra:
                rettet[k] = output[k]
            log.append(
                f"{sti}: bevarer {len(extra)} ekstra: {', '.join(extra[:6])}"
                + (" ..." if len(extra) > 6 else "")
            )
        else:
            log.append(
                f"{sti}: fjerner {len(extra)} ekstra: {', '.join(extra[:6])}"
                + (" ..." if len(extra) > 6 else "")
            )

    return rettet


def ret_skema(obj: dict, log: list, keep_extra: bool = False) -> dict:
    return _tving_sektion(obj, SCHEMA, "", log, keep_extra=keep_extra)


# ── Samlet pipeline ───────────────────────────────────────────────────────────

def ret_json(obj: dict, keep_extra: bool = False) -> tuple[dict, list[str]]:
    """
    Kør alle rettelsestrin i rækkefølge.
    Returnerer (rettet_obj, log).
    """
    obj = deepcopy(obj)
    log: list[str] = []

    ret_stavefejl(obj, log)   # 1. stavefejl
    ret_checkboxes(obj, log)  # 2. checkboxes
    ret_medicin(obj, log)     # 3. medicin-dict
    ret_datoer(obj, log)      # 3b. dato-normalisering
    ret_normaliser(obj, log)  # 3c. generel normalisering
    obj = ret_skema(obj, log, keep_extra=keep_extra) # 4. skema-tvang

    return obj, log


# ── Fil-behandling ────────────────────────────────────────────────────────────

def behandl_fil(
    input_sti: Path,
    output_sti: Path,
    dry_run: bool = False,
    verbose: bool = False,
    keep_extra: bool = False,
) -> int:
    try:
        raw = input_sti.read_text(encoding="utf-8")
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  ✗ {input_sti.name}: ugyldig JSON — {e}")
        return 0

    rettet, log = ret_json(obj, keep_extra=keep_extra)

    # Tæl kun substantielle ændringer (ignorer "fjerner 0 ekstra")
    antal = len([l for l in log if l])

    if verbose and log:
        print(f"  {input_sti.name} ({antal} ændringer):")
        for l in log:
            print(f"    {l}")

    if not dry_run:
        output_sti.parent.mkdir(parents=True, exist_ok=True)
        output_sti.write_text(
            json.dumps(rettet, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    return antal


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Post-processer og skema-standardiser LLM PSG JSON-output"
    )
    parser.add_argument("--input",   "-i", required=True,
                        help="Mappe med JSON-filer (én run-mappe ad gangen)")
    parser.add_argument("--output",  "-o", default=None,
                        help="Output-mappe (standard: <input>_fixed/)")
    parser.add_argument("--inplace", action="store_true",
                        help="Overskriv input-filerne direkte")
    parser.add_argument("--dry-run", action="store_true",
                        help="Vis hvad der ville ske, skriv ingenting")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print alle ændringer per fil")
    parser.add_argument("--keep-extra", action="store_true",
                        help="Bevar ekstra felter udenfor skemaet (default fjerner dem)")
    args = parser.parse_args()

    input_mappe = Path(args.input)
    if not input_mappe.exists():
        print(f"Fejl: '{input_mappe}' findes ikke.")
        return

    if args.inplace:
        output_mappe = input_mappe
    elif args.output:
        output_mappe = Path(args.output)
    else:
        output_mappe = input_mappe.parent / (input_mappe.name + "_fixed")

    # Ignorer run_meta.json og config.json
    json_filer = sorted([
        f for f in input_mappe.glob("*.json")
        if f.name not in ("run_meta.json", "config.json")
    ])

    if not json_filer:
        print(f"Ingen JSON-filer fundet i '{input_mappe}'.")
        return

    print(f"Behandler {len(json_filer)} filer"
          + (" [dry-run]" if args.dry_run else "")
          + f" → {output_mappe if not args.inplace else 'in-place'}")

    total_aendringer = 0
    filer_aendret    = 0

    for json_sti in json_filer:
        output_sti = output_mappe / json_sti.name
        antal = behandl_fil(
            json_sti, output_sti,
            dry_run=args.dry_run,
            verbose=args.verbose,
            keep_extra=bool(args.keep_extra),
        )
        if antal:
            total_aendringer += antal
            filer_aendret    += 1
        elif args.verbose:
            print(f"  {json_sti.name}: ingen ændringer")

    print(f"\nFærdig:")
    print(f"  Filer ændret:     {filer_aendret}/{len(json_filer)}")
    print(f"  Totale ændringer: {total_aendringer}")
    if not args.dry_run and not args.inplace:
        print(f"  Gemt i:           {output_mappe}")


if __name__ == "__main__":
    main()