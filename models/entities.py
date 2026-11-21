"""Core domain entities and enums for Track & Field Manager."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple


class CompetitionTier(str, Enum):
    """League tiers from local to international level."""

    PROVINCIALE = "Provinciale"
    REGIONALE = "Regionale"
    NAZIONALE = "Nazionale"
    INTERNAZIONALE = "Internazionale"

    @property
    def display_name(self) -> str:
        """Nome mostrato in interfaccia (il `value` resta quello salvato nel DB e usato come chiave)."""
        return TIER_DISPLAY_NAMES[self]

    @property
    def order(self) -> int:
        return TIER_ORDER.index(self)

    @property
    def next_tier(self) -> Optional["CompetitionTier"]:
        idx = self.order
        if idx + 1 < len(TIER_ORDER):
            return TIER_ORDER[idx + 1]
        return None

    @property
    def previous_tier(self) -> Optional["CompetitionTier"]:
        idx = self.order
        return TIER_ORDER[idx - 1] if idx > 0 else None


TIER_ORDER: List[CompetitionTier] = [
    CompetitionTier.PROVINCIALE,
    CompetitionTier.REGIONALE,
    CompetitionTier.NAZIONALE,
    CompetitionTier.INTERNAZIONALE,
]

# Nomi dei livelli come gli vede il giocatore (Q18: slot dei Campionati di Società). Solo testo: il `value`
# dell'enum NON si cambia, perché è scritto nei salvataggi e usato come chiave (es. TICKET_PRICE).
TIER_DISPLAY_NAMES: Dict[CompetitionTier, str] = {
    CompetitionTier.PROVINCIALE: "Fase regionale CdS",
    CompetitionTier.REGIONALE: "Finale Bronzo",
    CompetitionTier.NAZIONALE: "Finale Argento",
    CompetitionTier.INTERNAZIONALE: "Finale Oro / Coppa Europa",
}

# Economia (PIANOLAVORO A.1, 2026-11-20). Sponsor società +40% e montepremi +25% rispetto ai valori precedenti
# (600/1250/2500/4800 e 1200/2800/6000/12500). I rimborsi spese degli atleti sono scesi del 45% (non del 20% del
# piano: con -20% il flusso restava a -3.237 €/sett.): vedi WAGE_* sotto e docs/BALANCE.md §A.
TIER_CONFIG: Dict[CompetitionTier, Dict[str, int]] = {
    CompetitionTier.PROVINCIALE: {
        "weekly_sponsor": 840,
        "prize_base": 1500,
        "opponent_skill": 42,
        "travel_cost": 350,
    },
    CompetitionTier.REGIONALE: {
        "weekly_sponsor": 1750,
        "prize_base": 3500,
        "opponent_skill": 56,
        "travel_cost": 750,
    },
    CompetitionTier.NAZIONALE: {
        "weekly_sponsor": 3500,
        "prize_base": 7500,
        "opponent_skill": 70,
        "travel_cost": 1500,
    },
    CompetitionTier.INTERNAZIONALE: {
        "weekly_sponsor": 6720,
        "prize_base": 15625,
        "opponent_skill": 84,
        "travel_cost": 3000,
    },
}


class SeasonPhase(str, Enum):
    """Real athletics seasonal cycle."""

    # Pre-stagione senza gare: apre ogni ciclo delle partite di Carriera nuove (`GameState.prep_weeks` > 0).
    PREPARAZIONE = "Preparazione (Pre-stagione)"
    OUTDOOR = "Outdoor (Primavera/Estate)"
    CROSS = "Cross (Autunno)"
    INDOOR = "Indoor (Inverno)"


class Specialty(str, Enum):
    """Athlete primary track & field discipline group."""

    SPRINTS = "Velocità"
    MIDDLE_DISTANCE = "Mezzofondo"
    JUMPS = "Salti"
    THROWS = "Lanci"

    @property
    def peak_age_range(self) -> Tuple[int, int]:
        """Typical peak age window per discipline."""
        if self == Specialty.SPRINTS:
            return (20, 27)
        if self == Specialty.JUMPS:
            return (20, 28)
        if self == Specialty.MIDDLE_DISTANCE:
            return (21, 30)
        return (23, 32)  # Throws peak later


class TrainingFocus(str, Enum):
    """Weekly training regimens assignable per athlete."""

    ENDURANCE = "Resistenza"
    EXPLOSIVE_POWER = "Potenza Esplosiva"
    TECHNIQUE = "Tecnica"
    REST = "Riposo & Recupero"


class PeriodizationPhase(str, Enum):
    """Training periodization block for load & tapering strategy."""

    PREP_GENERALE = "Prep. Generale"
    PREP_SPECIFICA = "Prep. Specifica"
    GARA = "Gara (Picco)"
    SCARICO = "Scarico (Tapering)"


class Personality(str, Enum):
    """Athlete psychological profile affecting load response and consistency."""

    PERFEZIONISTA = "Perfezionista"
    IMPULSIVO = "Impulsivo"
    LEADER = "Leader"
    RESILIENTE = "Resiliente"


class WeatherCondition(str, Enum):
    """Meet weather conditions affecting wind and performance."""

    SERENO = "Sereno"
    VENTOSO = "Ventoso"
    PIOGGIA = "Pioggia"
    CALDO = "Caldo"


class RaceAttitude(str, Enum):
    """How hard an athlete pushes in a race: trades performance for fatigue & injury risk."""

    PRUDENTE = "Prudente"
    NORMALE = "Normale"
    AGGRESSIVO = "Aggressivo"


# score bonus, post-race fatigue, base in-race injury chance, extra result variance (std dev)
ATTITUDE_EFFECTS: Dict[RaceAttitude, Dict[str, float]] = {
    RaceAttitude.PRUDENTE: {"score": -2.0, "fatigue": 4, "injury": 0.005, "sigma": 0.0},
    RaceAttitude.NORMALE: {"score": 0.0, "fatigue": 7, "injury": 0.02, "sigma": 0.0},
    RaceAttitude.AGGRESSIVO: {"score": 2.5, "fatigue": 11, "injury": 0.05, "sigma": 2.0},
}

# Piano gara di 800m e 1500m (B.1): ritmo iniziale e scatto finale, scelti prima della gara e applicati dal modello
# (non sono comandi in gara). Si sommano all'atteggiamento. I bonus positivi (Veloce, scatti) valgono per intero solo a
# un atleta con molta resistenza e si riducono, fino a diventare un crollo, se ne ha poco; il costo in fatica è fisso.
# Cifre misurate e confermate dall'utente il 2026-11-20 (Q23, docs/BALANCE.md sezione C).
class RacePace(str, Enum):
    LENTO = "Lento"
    MEDIO = "Medio"
    VELOCE = "Veloce"


class RaceKick(str, Enum):
    NESSUNO = "Nessuno"
    ULTIMI_200 = "Ultimi 200m"
    ULTIMO_GIRO = "Ultimo giro"


STRATEGY_EVENTS: Tuple[str, ...] = ("800m", "1500m")
# punteggio (× fattore di resistenza) e fatica post-gara
PACE_EFFECTS: Dict[RacePace, Tuple[float, int]] = {
    RacePace.LENTO: (-2.0, -4),
    RacePace.MEDIO: (0.0, 0),
    RacePace.VELOCE: (3.0, 10),
}
KICK_EFFECTS: Dict[RaceKick, Tuple[float, int]] = {
    RaceKick.NESSUNO: (0.0, 0),
    RaceKick.ULTIMI_200: (2.0, 8),
    RaceKick.ULTIMO_GIRO: (4.0, 15),
}
# Fattore di resistenza f = (stamina − (REF − SPAN/2)) / SPAN, tra FLOOR e 1, rispetto alla resistenza tipica della categoria
# (media dei mezzofondisti generati: la resistenza sale con la categoria): f = 0,5 per un atleta nella media, 1 per uno
# molto resistente, < 0 per uno che non ha fondo. Veloce e scatti rendono punteggio × f; Lento rende punteggio × f
# (perde per chi ha fondo, guadagna per chi non ne ha). La fatica non dipende da f.
STRATEGY_STAMINA_REF: Dict[CompetitionTier, int] = {
    CompetitionTier.PROVINCIALE: 47,
    CompetitionTier.REGIONALE: 59,
    CompetitionTier.NAZIONALE: 72,
    CompetitionTier.INTERNAZIONALE: 84,
}
STRATEGY_STAMINA_SPAN = 30
STRATEGY_FACTOR_FLOOR = -0.5

# Rischio nei concorsi (B.2): lungo e peso. Il modello non simula i singoli tentativi (la vista li ricava dal risultato),
# quindi il «rischio» è una scelta per evento: un bonus di tecnica (punti di tecnica × peso della tecnica nell'evento)
# contro una probabilità di tentativo nullo. Un nullo fa perdere il tentativo migliore: la misura scende di una quota
# fissa (si ripiega sul successivo). Una sola estrazione RNG, e solo se il rischio non è «Sicuro».
# CIFRE PROVVISORIE: il bonus e le probabilità sono del piano; FIELD_FOUL_LOSS è mia, da misurare e confermare (Q24).
class FieldRisk(str, Enum):
    SICURO = "Sicuro"
    BILANCIATO = "Bilanciato"
    AGGRESSIVO = "Aggressivo"


FIELD_STRATEGY_EVENTS: Tuple[str, ...] = ("Salto in Lungo", "Getto del Peso")
# punti di tecnica, probabilità di nullo
FIELD_RISK_EFFECTS: Dict[FieldRisk, Tuple[int, float]] = {
    FieldRisk.SICURO: (0, 0.0),
    FieldRisk.BILANCIATO: (1, 0.05),
    FieldRisk.AGGRESSIVO: (3, 0.15),
}
FIELD_FOUL_LOSS = 0.03  # quota della misura persa con un nullo (migliore → secondo tentativo)

# Bonus al bersaglio di forma per la fase «Gara (Picco)», solo nel tick che precede una settimana di gara
# (la forma usata in gara è quella calcolata nel tick precedente). Minore del +9 dello Scarico: il picco
# non toglie la fatica, quindi è più debole del tapering vero e proprio.
PEAK_FORM_BONUS = 6

# Club facilities & youth academy tuning
YOUTH_SQUAD_MAX = 8
YOUTH_TRAINING_MULT = 1.5
WEEKLY_SCOUTING_POINTS = 8
SCOUTING_SEARCH_POINTS = 2
# Cumulative weekly scouting fee by total points used (each search pays the difference)
SCOUTING_FEES: Dict[int, int] = {0: 0, 1: 0, 2: 150, 3: 350, 4: 600, 5: 1000, 6: 1500, 7: 2200, 8: 3000}
GYM_MAX_LEVEL = 5
GYM_TRAINING_BONUS_PER_LEVEL = 0.06
GYM_UPKEEP_PER_LEVEL = 40
# Impianti avanzati (PIANOLAVORO E.2): acquisto una tantum, nessuna manutenzione (il piano non ne indica: aperta, Q34).
# Chiave → (nome, costo €, effetto in una riga). Senza l'impianto ogni effetto vale come prima di E.2.
FACILITY_MEDICAL = "centro_medico"
FACILITY_VIDEO = "analisi_video"
FACILITY_WEIGHTS = "palestra_pesi"
FACILITY_ALTITUDE = "campo_altura"
FACILITY_ORDER: List[str] = [FACILITY_MEDICAL, FACILITY_VIDEO, FACILITY_WEIGHTS, FACILITY_ALTITUDE]
FACILITY_LABELS: Dict[str, str] = {
    FACILITY_MEDICAL: "Centro medico",
    FACILITY_VIDEO: "Centro analisi video",
    FACILITY_WEIGHTS: "Palestra pesi",
    FACILITY_ALTITUDE: "Campo altura",
}
FACILITY_COSTS: Dict[str, int] = {
    FACILITY_MEDICAL: 15000,
    FACILITY_VIDEO: 10000,
    FACILITY_WEIGHTS: 12000,
    FACILITY_ALTITUDE: 20000,
}
# Centro medico: taglia del 15% i tempi di infortunio (allenamento e gare, non la squalifica per doping). Su 1-3 settimane
# intere si arrotonda a caso (una sola estrazione dell'RNG, solo con l'impianto) e non si scende sotto 1 settimana.
MEDICAL_CENTER_INJURY_CUT = 0.15
INJURY_MIN_WEEKS = 1
# Gli altri tre moltiplicano la probabilità settimanale di miglioramento della qualità indicata (come la Palestra).
VIDEO_CENTER_TECHNIQUE_BONUS = 0.05
WEIGHTS_ROOM_STRENGTH_BONUS = 0.10
ALTITUDE_CAMP_STAMINA_BONUS = 0.10  # solo atleti di Mezzofondo

# Giovanili avanzate (PIANOLAVORO E.3). CIFRE DI COSTO PROVVISORIE (il piano non le indica, Q35); gli effetti sono del piano.
# Academy a stelle 0-5 (0 = il vivaio di prima): ogni stella +10% di crescita ai ragazzi del vivaio, quindi 5 stelle = +50%.
ACADEMY_MAX_LEVEL = 5
ACADEMY_GROWTH_BONUS_PER_LEVEL = 0.10
ACADEMY_UPGRADE_COST_STEP = 4000  # salire alla stella N costa N × passo: 4.000, 8.000, 12.000, 16.000, 20.000
# Scout (un solo osservatore capo, attributi 1-20 come lo staff): restringe la fascia d'incertezza con cui si vedono i ragazzi
# segnalati. Senza scout la fascia del potenziale è quella di sempre (±8, `potential_band_display`) e la qualità attuale
# (OVR) si vede come fascia di ±5. Con l'attributo 20 la fascia si stringe a ±SCOUT_*_BAND_MIN (OVR: esatto).
SCOUT_ATTRIBUTES: Tuple[Tuple[str, str], ...] = (("potenziale", "Giudizio potenziale"), ("attuale", "Giudizio attuale"))
SCOUT_POTENTIAL_BAND = 8
SCOUT_POTENTIAL_BAND_MIN = 2
SCOUT_CURRENT_BAND = 5
SCOUT_CURRENT_BAND_MIN = 0
SCOUT_BAND_OFFSET = 3  # scarto deterministico del centro della fascia (come `potential_band_display`)
# Rete scouting globale: una regione è un filtro in più della ricerca (+1 punto e una quota fissa). Chiave → (nome,
# disciplina, qualità, nazionalità). Ogni ragazzo segnalato ha REGION_STAR_CHANCE di avere quella qualità tra i due estremi.
SCOUT_REGIONS: Dict[str, Tuple[str, Specialty, str, str]] = {
    "giamaica": ("Giamaica", Specialty.SPRINTS, "speed", "Giamaica"),
    "kenya": ("Kenya", Specialty.MIDDLE_DISTANCE, "stamina", "Kenya"),
    "nigeria": ("Nigeria", Specialty.THROWS, "strength", "Nigeria"),
}
SCOUT_REGION_STAR_CHANCE = 0.20
SCOUT_REGION_STAR_STAT_MIN = 81
SCOUT_REGION_STAR_STAT_MAX = 90
SCOUT_REGION_EXTRA_POINTS = 1
SCOUT_REGION_FEE = 800

# Notizie dinamiche (PIANOLAVORO F.1): a ogni chiusura di mese (`MONTH_WEEKS`) il generatore di `models/narrative.py` scrive al
# più una riga per tipo, senza RNG. Soglia sotto la quale la relazione con l'agente è «insoddisfazione» (la neutra è 50).
NARRATIVE_TENSION_RELATION = 30

# Conferenza stampa dopo la gara (PIANOLAVORO F.2). CIFRE PROVVISORIE (Q37). La prestazione del club nel meeting è «good» se è tra
# i primi PRESS_GOOD_MAX_PLACEMENT, «bad» se è tra gli ultimi PRESS_BAD_FROM_BOTTOM (con almeno PRESS_MIN_TEAMS squadre), altrimenti
# «average». La risposta alla domanda sulla prestazione sposta la reputazione; quella sul miglior atleta del meeting sposta
# la relazione con il suo agente (D.1). Chiudere la conferenza senza rispondere non ha alcun effetto.
PRESS_GOOD_MAX_PLACEMENT = 2
PRESS_BAD_FROM_BOTTOM = 2
PRESS_MIN_TEAMS = 4
PRESS_REPUTATION: Dict[str, Dict[str, int]] = {
    "good": {"soddisfatto": 2, "cauto": 1, "critico": -2},
    "average": {"soddisfatto": 0, "cauto": 1, "critico": 0},
    "bad": {"soddisfatto": -2, "cauto": 0, "critico": 1},
}
PRESS_RELATION: Dict[str, int] = {"punto": 3, "valuto": 0, "dubbio": -3}

# Relazioni tra atleti (PIANOLAVORO F.3). CIFRE PROVVISORIE (Q38). Ogni coppia della Prima Squadra ha, in modo deterministico
# (crc32 degli id, nessun RNG), nessuna relazione, un'amicizia (valore +40..+90) o una rivalità (−40..−90); il valore sta in
# `Athlete.relationships` (id dell'altro atleta → −100..+100, simmetrico). Da ≥ RELATION_FRIEND_MIN è amicizia, da ≤ RELATION_RIVAL_MAX
# rivalità. Una staffetta con un'amicizia tra le sue frazioni ha +RELAY_FRIEND_HARMONY di affiatamento in gara, con una rivalità
# RELAY_RIVAL_HARMONY (le due cose si sommano). La chimica di squadra (amicizie meno rivalità nella Prima Squadra) sposta il
# bersaglio di forma di tutti di CHEMISTRY_FORM_PER_NET_PAIR per coppia netta, al più ±CHEMISTRY_FORM_MAX. Correre insieme in
# staffetta avvicina: +RELATION_BOND_PER_RELAY a ogni coppia della staffetta a ogni meeting.
RELATION_FRIEND_MIN = 30
RELATION_RIVAL_MAX = -30
RELATION_FRIEND_PCT = 12  # % di coppie che nascono amiche
RELATION_RIVAL_PCT = 6  # % di coppie che nascono rivali
RELATION_STRENGTH_MIN = 40
RELATION_STRENGTH_MAX = 90
RELAY_FRIEND_HARMONY = 10
RELAY_RIVAL_HARMONY = -10
CHEMISTRY_FORM_PER_NET_PAIR = 0.25
CHEMISTRY_FORM_MAX = 3
RELATION_BOND_PER_RELAY = 2
# Storico per atleta (PIANOLAVORO G.1/G.2, solo per i grafici: nessun effetto sul gioco, nessun RNG). A fine di ogni tick si salva
# (forma, fatica, infortunato) di ogni atleta, al più le ultime HISTORY_WEEKS settimane; a ogni gara individuale si salva il
# risultato, al più gli ultimi HISTORY_RESULTS. Vedi `models/history.py`.
HISTORY_WEEKS = 12
# Heat map della Dashboard (G.1): il punteggio atteso di un atleta in una gara (`expected_event_score`, stessa scala dei rivali: 42
# provinciale, 56 regionale, 70 nazionale, 84 internazionale) si colora tra HEATMAP_SCORE_LOW (freddo) e HEATMAP_SCORE_HIGH (caldo).
# Righe: i migliori HEATMAP_ATHLETES della Prima Squadra per valore complessivo.
HEATMAP_SCORE_LOW = 40.0
HEATMAP_SCORE_HIGH = 80.0
HEATMAP_ATHLETES = 8
# Scheda atleta (G.2, solo presentazione): soglie dei livelli di una caratteristica 0-100 (stesse del badge a colori di prima: 80 / 65 / 45).
# Il livello decide il colore della barra: `great` verde, `good` giallo, `mid` arancione, `low` rosso. Per la fatica (meno è meglio) si inverte.
STAT_LEVEL_GREAT = 80
STAT_LEVEL_GOOD = 65
STAT_LEVEL_MID = 45
HISTORY_RESULTS = 10
# Rimborso spese settimanale di un atleta di Prima Squadra: base + overall × WAGE_PER_OVERALL, tra WAGE_MIN e WAGE_MAX.
# (prima 100|80 + overall × 4,2, tra 95 e 950: -45%). Vale per gli atleti creati o promossi da ora: i salvataggi
# esistenti tengono i rimborsi già scritti (mai rivisti dopo la creazione, vedi AUDIT R14).
WAGE_BASE_ADULT = 55
WAGE_BASE_PROSPECT = 45  # giovani promettenti (`is_youth_prospect`)
WAGE_PER_OVERALL = 2.3
WAGE_MIN = 52
WAGE_MAX = 520
# Bonus una tantum per la promozione di categoria, a fine stagione (PIANOLAVORO A.1).
PROMOTION_BONUS = 5000
STAND_EXPANSION_SEATS = 500
STAND_MAX_SEATS = 20000
TICKET_PRICE: Dict[str, int] = {
    "Provinciale": 4,
    "Regionale": 6,
    "Nazionale": 9,
    "Internazionale": 14,
}
DEBT_WEEKLY_INTEREST = 0.05
BANKRUPTCY_THRESHOLD = -20000
# Team points per finishing place (1st..8th) for the club league table
TEAM_POINTS: Dict[int, int] = {1: 8, 2: 7, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 1}
# Spareggio in classifica (A.2): a pari punti vince chi ha più 1° posti, poi più 2°, ... (un contatore per ogni
# piazzamento che dà punti); se è ancora parità, un sorteggio deterministico (stagione + posizione del club, non il nome).
LEAGUE_PLACE_SLOTS = len(TEAM_POINTS)
TIEBREAK_DRAW_TAG = "spareggio"
# Etichetta del seed di ripiego per un salvataggio senza stato dell'RNG (vedi `models/rng_state.py`).
RNG_SEED_TAG = "rng"

# Ranking individuale e di società (PIANOLAVORO C.1). CIFRE PROVVISORIE: vedi docs/BALANCE.md e QUESTIONS Q26.
# Punti per piazzamento (1°..8°; oltre l'8° nessuno), moltiplicati per il livello della gara: lo stesso 1° vale
# molto di più in Finale Oro che in Fase regionale. A ogni meeting i punti già posseduti si moltiplicano per
# `RANKING_DECAY` (a ~9 meeting l'anno, il peso di un risultato si dimezza dopo ~6 meeting, circa sei mesi).
RANKING_PLACE_POINTS: Tuple[int, ...] = (100, 80, 65, 52, 42, 34, 28, 22)
RANKING_TIER_MULT: Dict[CompetitionTier, float] = {
    CompetitionTier.PROVINCIALE: 0.10,
    CompetitionTier.REGIONALE: 0.25,
    CompetitionTier.NAZIONALE: 0.50,
    CompetitionTier.INTERNAZIONALE: 1.00,
}
RANKING_DECAY = 0.9
RANKING_WORLD_SIZE = 100  # «Top 100 mondiale»: anche il campo sintetico ha questa dimensione per evento e sesso
RANKING_NATIONAL_SIZE = 50  # «Top 50 nazionale»: solo atleti di nazionalità `RANKING_HOME_NATION`
RANKING_HOME_NATION = "Italia"
# Campo sintetico (atleti di fantasia che riempiono la classifica mondiale e non gareggiano col club).
RANKING_SYNTH_ITALIAN_SHARE = 0.25  # quota di italiani tra i sintetici (gli altri vengono dalle altre nazioni)
RANKING_SYNTH_SKILL_TOP = 94.0  # livello (scala del punteggio di gara) del 1° sintetico di ogni evento
RANKING_SYNTH_SKILL_BOTTOM = 58.0  # e del 100°
RANKING_SYNTH_SKILL_JITTER = 2.0  # scarto iniziale casuale attorno alla retta fra i due estremi
RANKING_SYNTH_DRIFT = 0.3  # passeggiata casuale del livello a ogni meeting (σ)
RANKING_SYNTH_FIELD = 8  # partecipanti del campo virtuale con cui si simula il piazzamento di un sintetico
DNF_MARK = "Ritirato"


# Fasce d'età FIDAL (Q17): (età massima inclusa, nome). Si calcolano da `Athlete.age`, non si salvano: il gioco non ha
# l'anno di nascita e l'età cresce di 1 a ogni cambio stagione. Sotto i 14 anni vale la prima fascia.
AGE_CATEGORIES: List[Tuple[int, str]] = [
    (15, "Cadetti"),
    (17, "Allievi"),
    (19, "Juniores"),
    (22, "Promesse"),
]
AGE_CATEGORY_SENIOR = "Seniores"  # 23 anni e oltre
# Convocazioni (regolamento FIDAL art. 3.3 e 5.7): al massimo 2 gare individuali + 1 staffetta per atleta e meeting.
# La staffetta è già unica per atleta (vedi `GameState.relay_of`); qui il tetto delle gare individuali.
MAX_INDIVIDUAL_EVENTS = 2
# Q17: sotto questa età non si gareggia nel livello «Internazionale» (Finale Oro / Coppa Europa).
INTERNATIONAL_MIN_AGE = 20
# Contratti (Q22): durata di 1-3 stagioni, rinnovo automatico alla scadenza; per annullarlo si svincola l'atleta.
CONTRACT_MAX_SEASONS = 3
# Ritiro (C.3), valutato una volta al cambio stagione sulla Prima Squadra, dopo l'incremento dell'età. CIFRE PROVVISORIE
# (QUESTIONS Q28). Chance per età (a partire da RETIREMENT_MIN_AGE); da RETIREMENT_CERTAIN_AGE il ritiro è certo.
RETIREMENT_MIN_AGE = 33
RETIREMENT_CHANCE_BY_AGE: Dict[int, float] = {33: 0.25, 34: 0.50}
RETIREMENT_CERTAIN_AGE = 35
# Ritiro anticipato per «infortunato grave»: gli infortuni durano 1-4 settimane, quindi «grave» = stagione tormentata,
# cioè almeno RETIREMENT_INJURIES_PER_SEASON infortuni nella stessa stagione (`Athlete.season_injuries`, azzerato a ogni
# cambio stagione), da RETIREMENT_INJURY_MIN_AGE anni in su. La chance non scende mai sotto quella dell'età.
RETIREMENT_INJURY_MIN_AGE = 30
RETIREMENT_INJURIES_PER_SEASON = 3
RETIREMENT_INJURY_CHANCE = 0.35
# Post-carriera: probabilità che un ex atleta diventi allenatore (offerta al giocatore, non assunzione automatica).
RETIRED_COACH_CHANCE = 0.10
RETIRED_COACH_HIRE_COST = 750  # ingaggio ridotto (un allenatore di livello 1 costa 1.500): è un ex atleta della casa
RETIRED_COACH_SKILL_MIN = 55  # abilità principale e secondaria dall'attributo che aveva da atleta, limitate a [min, max]
RETIRED_COACH_SKILL_MAX = 85
RETIRED_COACH_SECONDARY_GAP = 10  # la secondaria vale meno della principale, come in `coach_hire_skills`
MAX_RETIRED_LIST = 100  # ex atleti ricordati (i più recenti)
# Agenti (D.1). CIFRE PROVVISORIE (QUESTIONS Q29). Un agente cura più atleti (relazione condivisa, 0-100, parte da 50).
# La richiesta sull'ingaggio al tesseramento è un +% secondo la personalità, spostato dalla relazione: a 50 nessuna
# modifica, a 100 −AGENT_RELATION_FEE_SPAN, a 0 +AGENT_RELATION_FEE_SPAN (punti percentuali, non relativi).
AGENT_RELATION_START = 50
AGENT_RELATION_MAX = 100
AGENT_RELATION_FEE_SPAN = 0.15
AGENT_NEW_SLOTS = 2  # un atleta nuovo va a un agente già noto o ne ha uno nuovo (probabilità slot / (agenti + slot))
AGENT_MAX_IDLE = 20  # agenti senza clienti ricordati al massimo (i più lontani dalla relazione neutra se ne vanno prima)
# Come cambia la relazione con l'agente di un atleta: il rinnovo e i podi la alzano, lo svincolo e il mancato rinnovo la abbassano.
AGENT_RELATION_RENEWED = 3
AGENT_RELATION_PODIUM = 1
AGENT_RELATION_RELEASED = -10
AGENT_RELATION_NOT_RENEWED = -5
AGENT_RELATION_IDLE = -2  # per ogni atleta della Prima Squadra che in una stagione non è mai stato convocato («resta fermo»)
SEASON_WEEKS = 36  # settimane di gara di una stagione di Carriera (3 fasi da 12): la settimana è continua, non riparte
PHASE_WEEKS = 12  # settimane di ogni fase con gare (Outdoor, Cross, Indoor)
# Avvio senza atleti (2026-11-20, QUESTIONS Q32): le partite di Carriera nuove hanno una Preparazione di questa durata a inizio
# di ogni stagione (nessuna gara, la società si costruisce). Deve essere multipla di 4 per tenere le gare ogni 4 settimane
# allineate. I salvataggi esistenti hanno `prep_weeks` = 0: il loro calendario non cambia.
SEASON_PREP_WEEKS = 8
FIRST_OUTDOOR_DATE = date(2026, 4, 6)  # data della prima settimana di Outdoor: una Carriera nuova parte `SEASON_PREP_WEEKS` prima
# A ogni cambio stagione la relazione si avvicina a quella neutra di questa frazione della distanza: senza, in autopilota
# (podi e rinnovi automatici) tutti gli agenti arrivavano a 100 entro la quarta stagione e la relazione non diceva più nulla.
AGENT_RELATION_DRIFT = 0.25
# Trattative (D.2). CIFRE PROVVISORIE (QUESTIONS Q30). L'agente apre con la sua richiesta (D.1) e accetta un'offerta fino a
# una soglia sotto di essa; la flessibilità dipende dalla personalità (`AGENT_FLEXIBILITY`) e dalla relazione. Un solo giro di
# controfferta, nessuna estrazione casuale.
AGENT_FLEXIBILITY_RELATION_SPAN = 0.10  # a relazione 100 la flessibilità sale di 10 punti percentuali, a 0 scende di 10
AGENT_FLEXIBILITY_MAX = 0.50
MIN_NEGOTIATED_FEE = 100  # ingaggio minimo trattabile (€), anche con un bonus alto
# Bonus per risultati: €X pagati a ogni record sociale individuale dell'atleta finché dura il contratto; l'agente abbassa la
# richiesta sull'ingaggio dello stesso importo (si paga dopo, e solo se il record arriva).
RECORD_BONUS_OPTIONS = (300, 600, 1000)
# Clausola rescissoria: per svincolare un atleta di Prima Squadra prima della scadenza si paga questo numero di settimane
# del suo rimborso spese (circa €1.000-10.400). «Non rinnovare» e la scadenza del contratto restano gratuiti; il vivaio non ne ha.
RELEASE_CLAUSE_WEEKS = 20
# Finanze (D.3). CIFRE PROVVISORIE (QUESTIONS Q31). Un mese = 4 settimane (la stagione di 36 ne ha 9).
MONTH_WEEKS = 4
MAX_MONTHLY_REPORTS = 36  # bilanci mensili ricordati (quattro stagioni)
# Merchandising settimanale: fan della Prima Squadra ÷ MERCH_FANS_DIVISOR + prestigio ÷ MERCH_PRESTIGE_DIVISOR (extra del 5-15%).
MERCH_FANS_DIVISOR = 40
MERCH_PRESTIGE_DIVISOR = 20
# Diritti TV: solo per i meeting IN CASA del livello Internazionale.
TV_RIGHTS_PER_HOME_MEET = 3000
# Sponsor con obiettivo: chiudere la stagione fuori dai primi SPONSOR_TOP_N della lega taglia lo sponsor società della stagione
# successiva del SPONSOR_MISS_PENALTY (si ripristina chiudendo nei primi N).
SPONSOR_TOP_N = 5
SPONSOR_MISS_PENALTY = 0.20


def age_category(age: int) -> str:
    """Fascia d'età FIDAL: Cadetti 14-15, Allievi 16-17, Juniores 18-19, Promesse 20-22, Seniores 23+."""
    for max_age, name in AGE_CATEGORIES:
        if age <= max_age:
            return name
    return AGE_CATEGORY_SENIOR


def gym_upgrade_cost(current_level: int) -> int:
    return (current_level + 1) * 2500


def stand_expansion_cost(current_seats: int) -> int:
    """Seats get pricier as the stand grows (like real stadium expansions)."""
    per_seat = 3 if current_seats < 5000 else (4 if current_seats < 10000 else 6)
    return STAND_EXPANSION_SEATS * per_seat + 500


# ---------------------------------------------------------------- coaches
COACH_STATS: List[str] = ["speed", "stamina", "strength", "technique"]
COACH_STAT_LABELS: Dict[str, str] = {
    "speed": "Velocità",
    "stamina": "Resistenza",
    "strength": "Forza",
    "technique": "Tecnica",
}
MAX_SPECIALIZED_COACHES = 6
MAX_YOUTH_COACHES = 2
COACH_COMFORT_LOAD = 6  # beyond this many athletes, each one gets less attention
COACH_BASE_SKILL = 25  # level of the skills the coach was not hired for
COACH_MAX_TIER = 5
COACH_NO_COACH_MULT = 0.6  # athletes without a (suitable) coach still train, but slowly


def coach_hire_skills(tier: int) -> Tuple[int, int]:
    """(primary, secondary) skill values for a recruitment tier 1-5."""
    primary = 60 + 7 * tier
    return primary, primary - 10


def coach_hire_cost(tier: int) -> int:
    return 1500 * tier


def coach_weekly_wage(skills: Dict[str, int]) -> int:
    return 40 + round(sum(max(0, v - 40) for v in skills.values()) * 2.2)


# ---------------------------------------------------------------- relays
@dataclass(frozen=True)
class RelayDefinition:
    name: str
    leg_weights: Dict[str, float]  # athlete attributes that matter for each leg
    base_seconds: float  # time for a very weak team
    span_seconds: float  # how much a strong team gains
    min_seconds: float
    indoor: bool  # also run during the indoor season
    requires_event: str  # only run when this individual event is in the programme
    base_seconds_f: float = 0.0
    span_seconds_f: float = 0.0
    min_seconds_f: float = 0.0


RELAYS: Dict[str, RelayDefinition] = {
    "4x100m": RelayDefinition(
        name="4x100m",
        leg_weights={"speed": 0.70, "technique": 0.20, "strength": 0.10},
        base_seconds=50.4,
        span_seconds=11.2,
        min_seconds=36.8,
        indoor=False,
        requires_event="100m",
        base_seconds_f=55.0,
        span_seconds_f=11.8,
        min_seconds_f=40.8,
    ),
    "4x400m": RelayDefinition(
        name="4x400m",
        leg_weights={"speed": 0.50, "stamina": 0.40, "technique": 0.10},
        base_seconds=229.0,
        span_seconds=50.0,
        min_seconds=174.0,
        indoor=True,
        requires_event="400m",
        base_seconds_f=250.0,
        span_seconds_f=53.0,
        min_seconds_f=195.0,
    ),
}
RELAY_LEG_WEIGHTS: List[float] = [0.24, 0.24, 0.24, 0.28]  # the anchor leg counts a bit more
RELAY_CHANGE_COOLDOWN_WEEKS = 4
# Moltiplicatore della probabilità di squalifica per staffetta (Q20). Nella 4x400 il cambio non è lanciato e
# i frazionisti sono più lenti: il cambio fuori zona è più raro. Valore confermato dall'utente (2026-11-19).
RELAY_DQ_MULT: Dict[str, float] = {"4x100m": 1.0, "4x400m": 0.5}
RELAY_DQ_MARK = "Squalificata"


# Cambio nelle staffette (B.3): scelta per staffetta prima della gara (M e F insieme, come l'atteggiamento), applicata dal
# modello. Cifre misurate e confermate dall'utente il 2026-11-20 (Q25, docs/BALANCE.md sezione D): punti di punteggio di
# squadra e variazione del rischio di squalifica in PUNTI PERCENTUALI, sommata al rischio finale (dopo il ×0,5 della 4x400m)
# e limitata tra 0 e 1. Nessuna estrazione RNG in più: cambia solo la soglia dell'estrazione che c'è già.
class RelayChange(str, Enum):
    CONSERVATIVO = "Conservativo"
    NORMALE = "Normale"
    AGGRESSIVO = "Aggressivo"


RELAY_STRATEGY_EVENTS: Tuple[str, ...] = ("4x100m", "4x400m")
# punti di punteggio di squadra, punti percentuali di rischio di squalifica
RELAY_CHANGE_EFFECTS: Dict[RelayChange, Tuple[float, float]] = {
    RelayChange.CONSERVATIVO: (-1.0, -0.10),
    RelayChange.NORMALE: (0.0, 0.0),
    RelayChange.AGGRESSIVO: (2.0, 0.10),
}


def harmony_grade(harmony: int) -> str:
    """Letter grade for relay harmony (E .. A++)."""
    grades = ["E", "D", "C-", "C", "C+", "B-", "B", "B+", "A", "A+", "A++"]
    return grades[max(0, min(10, harmony // 10))]


class StaffRole(str, Enum):
    """Specialized club staff roles."""

    COACH_SPRINTS = "Coach Velocità"
    COACH_JUMPS = "Coach Salti"
    COACH_DISTANCE = "Coach Mezzofondo"
    PHYSIO = "Fisioterapista"
    DOCTOR = "Medico Sportivo"
    MENTAL_COACH = "Preparatore Mentale"


# Staff con attributi (PIANOLAVORO E.1). Ogni specialista clinico ha due attributi 1-20 legati al suo ruolo. Al valore di
# riferimento `STAFF_ATTR_REF` gli effetti sono ESATTAMENTE quelli di prima di E.1 (staff «a stelle»): i tre candidati fissi
# e i vecchi salvataggi stanno lì, quindi il bilanciamento non si sposta. Sopra il riferimento l'effetto cresce, sotto cala.
# Cifre PROVVISORIE (QUESTIONS Q33).
STAFF_ATTR_MIN = 1
STAFF_ATTR_MAX = 20
STAFF_ATTR_REF = 14
# Attributi per ruolo: (chiave nel dizionario, etichetta in italiano). I coach non ne hanno (usano `Coach.skills`).
STAFF_ATTRIBUTES: Dict[StaffRole, Tuple[Tuple[str, str], ...]] = {
    StaffRole.PHYSIO: (("competenza", "Competenza infortuni"), ("recupero", "Velocità recupero")),
    StaffRole.DOCTOR: (("diagnosi", "Diagnosi"), ("prevenzione", "Prevenzione")),
    StaffRole.MENTAL_COACH: (("motivazione", "Motivazione"), ("pressione", "Gestione pressione")),
}
# Fisioterapista: `recupero` scala il sollievo di fatica a settimana e il recupero extra da infortunati; `competenza` scala
# la probabilità del doppio passo di guarigione e, da PHYSIO_WEEK_CUT_MIN in su, toglie una settimana a ogni infortunio.
PHYSIO_FATIGUE_RELIEF = 7
PHYSIO_INJURY_RECOVERY_BONUS = 8
PHYSIO_HEAL_STEP_CHANCE = 0.55
PHYSIO_HEAL_STEP_CHANCE_CAP = 0.95
PHYSIO_WEEK_CUT_MIN = 8
# Medico: `prevenzione` riduce il rischio d'infortunio da sovraccarico in allenamento, `diagnosi` quello di ritiro in gara.
# Moltiplicatore = 1 − DOCTOR_RISK_CUT × (attributo / riferimento), mai sotto DOCTOR_RISK_FLOOR.
DOCTOR_RISK_CUT = 0.45
DOCTOR_RISK_FLOOR = 0.20
# Preparatore mentale: `motivazione` scala il bonus al bersaglio di forma, `pressione` la deviazione dell'Impulsivo in gara
# (senza preparatore IMPULSIVE_SIGMA, col preparatore al riferimento CALM_SIGMA, più in basso fino a MENTAL_SIGMA_FLOOR).
MENTAL_FORM_BONUS = 4
# Liquidazione (scelta dell'utente 2026-11-20: sostituire uno specialista costa la liquidazione del precedente). CIFRA
# PROVVISORIA (QUESTIONS Q33): settimane di compenso pagate a ogni licenziamento di uno specialista assunto.
STAFF_SEVERANCE_WEEKS = 6
# Rinnovo del mercato dello staff a ogni fine stagione (scelta dell'utente 2026-11-20: «il mercato deve rinnovarsi nel tempo»).
# CIFRE PROVVISORIE (QUESTIONS Q33). Lo specialista assunto resta; i non assunti sono sostituiti da candidati nuovi, così che
# per ruolo ci siano sempre STAFF_POOL_PER_ROLE persone (assunto compreso). Il catalogo iniziale ha ids 4-12 (STAFF_ORIGINAL_IDS
# sono i tre candidati di prima del mercato); i nuovi partono da max(STAFF_CATALOGUE_LAST_ID, ids presenti) + 1.
STAFF_POOL_PER_ROLE = 3
STAFF_ORIGINAL_IDS = (4, 5, 6)
STAFF_CATALOGUE_LAST_ID = 12
# Profili dei candidati sorteggiati: (nome, fascia di ciascun attributo, stelle). Ogni attributo è estratto a parte nella fascia.
STAFF_TIERS = (
    ("junior", (8, 11), 2),
    ("esperto", (12, 15), 4),
    ("senior", (13, 19), 5),
)
# Costo settimanale = base del ruolo × (1 + pendenza × (media attributi − STAFF_ATTR_REF)), arrotondato a STAFF_COST_STEP.
# Sotto il riferimento la pendenza è dolce (media 10 → ×0,6), sopra è ripida (media 16 → ×1,5).
STAFF_COST_BASE: Dict[StaffRole, int] = {StaffRole.PHYSIO: 300, StaffRole.DOCTOR: 340, StaffRole.MENTAL_COACH: 220}
STAFF_COST_SLOPE_BELOW = 0.10
STAFF_COST_SLOPE_ABOVE = 0.27
STAFF_COST_STEP = 10
STAFF_COST_MIN = 100
IMPULSIVE_SIGMA = 5.6
CALM_SIGMA = 3.8
MENTAL_SIGMA_FLOOR = 3.0


@dataclass(frozen=True)
class EventDefinition:
    """Definition of an individual track & field event."""

    name: str
    specialty: Specialty
    unit: str
    lower_is_better: bool
    wind_affected: bool
    historic_mark: float
    historic_label: str
    weights: Dict[str, float]
    historic_mark_f: Optional[float] = None
    historic_label_f: str = ""


EVENTS: Dict[str, EventDefinition] = {
    "100m": EventDefinition(
        name="100m",
        specialty=Specialty.SPRINTS,
        unit="s",
        lower_is_better=True,
        wind_affected=True,
        historic_mark=11.00,
        historic_label="sub-11.00s nei 100m",
        weights={"speed": 0.55, "technique": 0.25, "strength": 0.15, "stamina": 0.05},
        historic_mark_f=11.80,
        historic_label_f="sub-11.80s nei 100m",
    ),
    "400m": EventDefinition(
        name="400m",
        specialty=Specialty.SPRINTS,
        unit="s",
        lower_is_better=True,
        wind_affected=False,
        historic_mark=48.00,
        historic_label="sub-48.00s nei 400m",
        weights={"speed": 0.45, "stamina": 0.30, "technique": 0.15, "strength": 0.10},
        historic_mark_f=52.00,
        historic_label_f="sub-52.00s nei 400m",
    ),
    "800m": EventDefinition(
        name="800m",
        specialty=Specialty.MIDDLE_DISTANCE,
        unit="min",
        lower_is_better=True,
        wind_affected=False,
        historic_mark=113.0,  # 1:53.00 (stima: stesso score storico del 1500m)
        historic_label="sub-1:53.00 negli 800m",
        weights={"stamina": 0.40, "speed": 0.38, "technique": 0.15, "strength": 0.07},
        historic_mark_f=128.0,  # 2:08.00
        historic_label_f="sub-2:08.00 negli 800m",
    ),
    "1500m": EventDefinition(
        name="1500m",
        specialty=Specialty.MIDDLE_DISTANCE,
        unit="min",
        lower_is_better=True,
        wind_affected=False,
        historic_mark=235.0,  # 3:55.00
        historic_label="sub-3:55.00 nei 1500m",
        weights={"stamina": 0.55, "speed": 0.25, "technique": 0.15, "strength": 0.05},
        historic_mark_f=260.0,  # 4:20.00
        historic_label_f="sub-4:20.00 nei 1500m",
    ),
    "Salto in Lungo": EventDefinition(
        name="Salto in Lungo",
        specialty=Specialty.JUMPS,
        unit="m",
        lower_is_better=False,
        wind_affected=True,
        historic_mark=7.50,
        historic_label="oltre 7.50m nel Lungo",
        weights={"speed": 0.40, "technique": 0.35, "strength": 0.20, "stamina": 0.05},
        historic_mark_f=6.60,
        historic_label_f="oltre 6.60m nel Lungo",
    ),
    "Getto del Peso": EventDefinition(
        name="Getto del Peso",
        specialty=Specialty.THROWS,
        unit="m",
        lower_is_better=False,
        wind_affected=False,
        historic_mark=18.00,
        historic_label="oltre 18.00m nel Peso",
        weights={"strength": 0.55, "technique": 0.35, "speed": 0.05, "stamina": 0.05},
        historic_mark_f=16.50,
        historic_label_f="oltre 16.50m nel Peso",
    ),
}

# Curva punteggio -> tempo dell'800m (Q16): secondi = a - norm * b, minimo = record del mondo (M Rudisha 2012,
# F Kratochvilova 1983). Le ancore (score 42/56/84: M 2:05 / 1:58,5 / 1:45,5, F 2:21 / 2:14,7 / 2:02) sono STIME.
MIDDLE_800M_CURVE: Dict[str, Tuple[float, float, float]] = {  # sesso -> (a, b, minimo)
    "M": (144.5, 46.4, 100.91),
    "F": (160.0, 45.2, 113.28),
}

# Record del mondo del gioco (PIANOLAVORO F.4): sono i tetti già usati da `_score_to_mark` (che li ha ancora scritti a mano, AUDIT R36):
# una misura che li raggiunge è un record del mondo. (evento, sesso) -> misura (secondi o metri).
WORLD_RECORDS: Dict[Tuple[str, str], float] = {
    ("100m", "M"): 9.58, ("100m", "F"): 10.49,
    ("400m", "M"): 43.10, ("400m", "F"): 47.60,
    ("800m", "M"): MIDDLE_800M_CURVE["M"][2], ("800m", "F"): MIDDLE_800M_CURVE["F"][2],
    ("1500m", "M"): 206.0, ("1500m", "F"): 229.0,
    ("Salto in Lungo", "M"): 8.95, ("Salto in Lungo", "F"): 7.52,
    ("Getto del Peso", "M"): 23.56, ("Getto del Peso", "F"): 22.63,
}
WORLD_RECORD_EPSILON = 1e-6  # tolleranza sul confronto con il tetto (le misure sono float)

VERTICAL_SLICE_EVENTS: List[str] = ["100m", "Salto in Lungo", "1500m"]


# Nationality name -> flag emoji. Most of the pool is Italian; the rest are foreign athletes.
NATIONALITIES: Dict[str, str] = {
    "Italia": "🇮🇹",
    "Francia": "🇫🇷",
    "Spagna": "🇪🇸",
    "Germania": "🇩🇪",
    "Regno Unito": "🇬🇧",
    "Stati Uniti": "🇺🇸",
    "Canada": "🇨🇦",
    "Giamaica": "🇯🇲",
    "Kenya": "🇰🇪",
    "Etiopia": "🇪🇹",
    "Nigeria": "🇳🇬",
    "Brasile": "🇧🇷",
    "Giappone": "🇯🇵",
    "Australia": "🇦🇺",
}


@dataclass
class Athlete:
    """Represents a single track & field athlete on the team."""

    id: Optional[int]
    name: str
    age: int
    specialty: Specialty
    speed: int
    stamina: int
    strength: int
    technique: int
    resilience: int
    form: int
    fatigue: int
    potential: int = 75
    personality: Personality = Personality.PERFEZIONISTA
    training_focus: TrainingFocus = TrainingFocus.ENDURANCE
    periodization: PeriodizationPhase = PeriodizationPhase.PREP_GENERALE
    sleep_quality: int = 75
    nutrition: int = 75
    weekly_wage: int = 200
    injured_weeks: int = 0
    is_youth_prospect: bool = False
    personal_best: Optional[float] = None
    personal_best_display: Optional[str] = None
    doping_boost_weeks: int = 0
    in_youth_squad: bool = False
    fans: int = 0
    coach_id: Optional[int] = None
    nationality: str = "Italia"
    contract_end_season: int = 0  # ultima stagione di contratto (inclusa); 0 = nessuno (vivaio) o ancora da assegnare
    height_cm: int = 0  # 0 = not yet generated (old saves)
    weight_kg: int = 0
    gender: str = "M"
    contract_no_renew: bool = False  # il giocatore non vuole rinnovarlo: alla scadenza lascia la società
    ranking_points: Dict[str, float] = field(default_factory=dict)  # punti ranking per evento (C.1)
    season_injuries: int = 0  # infortuni subiti nella stagione in corso (C.3: ritiro anticipato)
    agent_id: Optional[int] = None  # agente (D.1); None = ancora da assegnare (vecchi salvataggi, atleti creati a mano)
    # Relazioni con gli altri atleti (F.3): id dell'altro → −100..+100, simmetrico; vuoto = nessuna (atleta nuovo, vecchi salvataggi).
    relationships: Dict[int, int] = field(default_factory=dict)
    record_bonus: int = 0  # € pagati a ogni record sociale individuale finché dura il contratto (D.2); 0 = nessun bonus
    # Storico per i grafici (G.1/G.2): {"weekly": [[forma, fatica, infortunato], ...], "results": [{...}, ...]}, dal più vecchio al più recente.
    history: Dict[str, list] = field(default_factory=dict)

    @property
    def release_clause_cost(self) -> int:
        """Clausola rescissoria (D.2): quanto costa svincolarlo prima della scadenza. 0 per il vivaio (non ha contratto)."""
        return 0 if self.in_youth_squad else RELEASE_CLAUSE_WEEKS * self.weekly_wage

    @property
    def gender_label(self) -> str:
        return "Donna" if self.gender == "F" else "Uomo"

    @property
    def flag(self) -> str:
        return NATIONALITIES.get(self.nationality, "🏳")

    @property
    def height_display(self) -> str:
        return f"{self.height_cm / 100:.2f} m" if self.height_cm else "—"

    @property
    def weight_display(self) -> str:
        return f"{self.weight_kg} kg" if self.weight_kg else "—"

    @property
    def power(self) -> int:
        """Composite power attribute combining speed and strength."""
        return round(self.speed * 0.55 + self.strength * 0.45)

    @property
    def overall(self) -> int:
        """Weighted overall rating based on specialty."""
        if self.specialty == Specialty.SPRINTS:
            score = (
                self.speed * 0.42
                + self.technique * 0.23
                + self.strength * 0.15
                + self.stamina * 0.12
                + self.resilience * 0.08
            )
        elif self.specialty == Specialty.MIDDLE_DISTANCE:
            score = (
                self.stamina * 0.46
                + self.speed * 0.22
                + self.technique * 0.14
                + self.resilience * 0.12
                + self.strength * 0.06
            )
        elif self.specialty == Specialty.JUMPS:
            score = (
                self.speed * 0.33
                + self.technique * 0.33
                + self.strength * 0.18
                + self.resilience * 0.08
                + self.stamina * 0.08
            )
        else:  # Throws
            score = (
                self.strength * 0.46
                + self.technique * 0.30
                + self.resilience * 0.10
                + self.speed * 0.08
                + self.stamina * 0.06
            )
        return max(1, min(100, round(score)))

    @property
    def age_category(self) -> str:
        return age_category(self.age)

    def can_race_in(self, tier: "CompetitionTier") -> bool:
        """Gli under 20 non gareggiano nel livello Internazionale (Q17)."""
        return tier != CompetitionTier.INTERNAZIONALE or self.age >= INTERNATIONAL_MIN_AGE

    @property
    def is_injured(self) -> bool:
        return self.injured_weeks > 0

    @property
    def status_label(self) -> str:
        if self.injured_weeks > 0:
            return f"Infortunato ({self.injured_weeks}s)"
        if self.doping_boost_weeks > 0:
            return "Sospetto"
        if self.fatigue >= 80:
            return "Esausto"
        if self.fatigue >= 60:
            return "Affaticato"
        if self.form >= 78:
            return "Al Picco"
        return "In Forma"


@dataclass
class Coach:
    """A coach with their own skills. Specialized coaches train one specialty;
    youth coaches (specialty None) only train the youth academy, any discipline."""

    id: Optional[int]
    name: str
    specialty: Optional[Specialty]
    skills: Dict[str, int]  # speed / stamina / strength / technique, 1-100

    @property
    def is_youth_coach(self) -> bool:
        return self.specialty is None

    @property
    def weekly_wage(self) -> int:
        return coach_weekly_wage(self.skills)

    @property
    def kind_label(self) -> str:
        return "Vivaio" if self.specialty is None else self.specialty.value

    def skill_for(self, stat_name: str) -> int:
        if stat_name == "resilience":  # resilience is built through endurance work
            return self.skills.get("stamina", COACH_BASE_SKILL)
        return self.skills.get(stat_name, COACH_BASE_SKILL)

    def can_train(self, athlete: "Athlete") -> bool:
        if self.specialty is None:
            return athlete.in_youth_squad
        return self.specialty == athlete.specialty


@dataclass
class RetiredAthlete:
    """Un ex atleta della società (C.3): resta solo questo ricordo, l'`Athlete` esce da `GameState.athletes`.

    `coach_skills` è valorizzato solo se l'ex atleta si è offerto come allenatore (post-carriera): finché `coach_offer`
    è vero il giocatore può assumerlo (`GameController.hire_retired_coach`); l'offerta scade al cambio stagione dopo.
    """

    name: str
    gender: str
    specialty: Specialty
    age: int  # età al ritiro
    season: int  # stagione appena chiusa al momento del ritiro
    reason: str  # «Età» o «Infortuni»
    nationality: str = "Italia"
    overall: int = 0
    personal_best_display: Optional[str] = None
    coach_skills: Dict[str, int] = field(default_factory=dict)
    coach_offer: bool = False
    became_coach: bool = False

    @property
    def status_label(self) -> str:
        if self.became_coach:
            return "Allenatore della società"
        if self.coach_offer:
            return "Disponibile come allenatore"
        return "In pensione"


class AgentPersonality(Enum):
    """Come tratta un agente: l'Aggressivo chiede di più, il Leale di meno (D.1)."""

    AGGRESSIVE = "Aggressivo"
    REASONABLE = "Ragionevole"
    LOYAL = "Leale"


# Richiesta base sull'ingaggio al tesseramento per personalità (frazione dell'ingaggio standard).
AGENT_FEE_MARKUP: Dict[AgentPersonality, float] = {
    AgentPersonality.AGGRESSIVE: 0.20,
    AgentPersonality.REASONABLE: 0.0,
    AgentPersonality.LOYAL: -0.10,
}
# Quanto sotto la sua richiesta un agente accetta di scendere in trattativa (frazione), per personalità: il Leale cede di più.
AGENT_FLEXIBILITY: Dict[AgentPersonality, float] = {
    AgentPersonality.AGGRESSIVE: 0.05,
    AgentPersonality.REASONABLE: 0.15,
    AgentPersonality.LOYAL: 0.25,
}
# Peso nella scelta della personalità di un agente nuovo (somma 100).
AGENT_PERSONALITY_WEIGHTS: Dict[AgentPersonality, int] = {
    AgentPersonality.AGGRESSIVE: 30,
    AgentPersonality.REASONABLE: 50,
    AgentPersonality.LOYAL: 20,
}


@dataclass
class Agent:
    """Agente di uno o più atleti (D.1). La relazione (0-100) è del giocatore con l'agente, non con il singolo atleta."""

    id: int
    name: str
    personality: AgentPersonality = AgentPersonality.REASONABLE
    relation: int = AGENT_RELATION_START

    @property
    def fee_modifier(self) -> float:
        """Frazione da aggiungere all'ingaggio standard: personalità + relazione (a 100 −15 punti, a 0 +15)."""
        trust = (AGENT_RELATION_START - self.relation) / AGENT_RELATION_START
        return AGENT_FEE_MARKUP[self.personality] + AGENT_RELATION_FEE_SPAN * trust

    @property
    def relation_label(self) -> str:
        if self.relation >= 75:
            return "Ottima"
        if self.relation >= 55:
            return "Buona"
        if self.relation >= 45:
            return "Neutra"
        if self.relation >= 25:
            return "Tesa"
        return "Pessima"


@dataclass
class Relay:
    """A relay team: 4 ordered legs plus a reserve. Harmony grows by training together."""

    event: str
    member_ids: List[Optional[int]] = field(default_factory=lambda: [None, None, None, None])
    reserve_id: Optional[int] = None
    harmony: int = 30  # 0-100
    last_change_week: int = -100

    @property
    def is_complete(self) -> bool:
        return all(mid is not None for mid in self.member_ids)

    def all_ids(self) -> List[int]:
        ids = [mid for mid in self.member_ids if mid is not None]
        if self.reserve_id is not None:
            ids.append(self.reserve_id)
        return ids


# ---------------------------------------------------------------- rival clubs
RIVAL_RACE_SIGMA = 4.5  # day-to-day variance of a rival's performance
RIVAL_RETIREMENT_AGE = 33
RIVAL_SEASON_INFLATION = 0.8  # each season new rival recruits are a bit stronger
RIVAL_TREND_SNAPSHOTS = 13  # one every 4 weeks: about a year of history


@dataclass
class RivalAthlete:
    """A named athlete of a rival club. Their level uses the same scale as race scores."""

    name: str
    event: str
    age: int
    skill: float
    pb: Optional[float] = None
    pb_display: Optional[str] = None
    gender: str = "M"
    ranking_points: Dict[str, float] = field(default_factory=dict)  # punti ranking per evento (C.1); un solo evento


@dataclass
class SyntheticAthlete:
    """Atleta di fantasia del campo mondiale (C.1): ha un livello e punti ranking, non gareggia con il club."""

    name: str
    nationality: str
    event: str
    gender: str
    skill: float
    points: float = 0.0


@dataclass
class RivalClub:
    """A rival club that develops over time: young athletes grow, veterans decline and retire.

    Ambition (0.6-1.6) scales how much the club invests in progress; it rises when
    the club keeps finishing behind the player and drops when it is comfortably ahead.
    """

    name: str
    tier: CompetitionTier
    ambition: float
    offset: float = 0.0  # club quality vs the category average (drives its recruits)
    athletes: Dict[str, RivalAthlete] = field(default_factory=dict)
    female_athletes: Dict[str, RivalAthlete] = field(default_factory=dict)
    history: List[float] = field(default_factory=list)  # average level, one snapshot every 4 weeks

    def athletes_for(self, gender: str = "M") -> Dict[str, RivalAthlete]:
        return self.female_athletes if gender == "F" else self.athletes

    def athlete_for(self, event: str, gender: str = "M") -> Optional[RivalAthlete]:
        pool = self.female_athletes if gender == "F" else self.athletes
        return pool.get(event) or self.athletes.get(event)

    def level(self, events: Optional[List[str]] = None, gender: Optional[str] = None) -> float:
        pools: List[Dict[str, RivalAthlete]] = []
        if gender in (None, "M"):
            pools.append(self.athletes)
        if gender in (None, "F") and self.female_athletes:
            pools.append(self.female_athletes)
        vals = [a.skill for p in pools for e, a in p.items() if events is None or e in events]
        return sum(vals) / len(vals) if vals else 0.0

    @property
    def trend(self) -> float:
        """Change in average level over the stored history (about the last year)."""
        if len(self.history) < 2:
            return 0.0
        return self.history[-1] - self.history[0]

    @property
    def ambition_label(self) -> str:
        if self.ambition >= 1.2:
            return "Ambiziosa"
        if self.ambition <= 0.85:
            return "Appagata"
        return "Stabile"

    def star(self, events: Optional[List[str]] = None, gender: Optional[str] = None) -> Optional[RivalAthlete]:
        pools: List[Dict[str, RivalAthlete]] = []
        if gender in (None, "M"):
            pools.append(self.athletes)
        if gender in (None, "F") and self.female_athletes:
            pools.append(self.female_athletes)
        pool = [a for p in pools for e, a in p.items() if events is None or e in events]
        return max(pool, key=lambda a: a.skill) if pool else None


# ---------------------------------------------------------------- league promotion & relegation
PROMOTION_SPOTS = 2  # top 2 of the final league table move up
RELEGATION_SPOTS = 1  # last club moves down

# Obiettivi del Board (PIANOLAVORO C.2, 2026-11-20). CIFRE PROVVISORIE: vedi docs/BALANCE.md §L e QUESTIONS Q27.
# A inizio stagione (solo Carriera) il Board assegna tre obiettivi; la stagione è «fallita» se se ne centrano meno di
# `BOARD_OBJECTIVES_TO_PASS`, e `BOARD_MAX_FAILED_STREAK` stagioni fallite di fila portano all'esonero (game over).
BOARD_KEY_LEAGUE = "board_league"
BOARD_KEY_BUDGET = "board_budget"
BOARD_KEY_RECORDS = "board_records"
# Obiettivi di FONDAZIONE (stagione 1 di una Carriera nuova, che parte senza atleti; QUESTIONS Q32, cifre provvisorie).
# Misurano la costruzione della società, non i risultati; non danno mai una stagione «fallita» né l'esonero.
FOUND_KEY_ATHLETES = "found_athletes"
FOUND_KEY_YOUTH = "found_youth"
FOUND_KEY_MEETS = "found_meets"
FOUNDATION_KEYS: Tuple[str, ...] = (FOUND_KEY_ATHLETES, FOUND_KEY_YOUTH, FOUND_KEY_MEETS)
FOUNDATION_MIN_ATHLETES = 6  # atleti in società alla fine della stagione (Prima Squadra e vivaio)
FOUNDATION_MIN_YOUTH = 2  # ragazzi nel vivaio
FOUNDATION_MIN_MEETS = 3  # meeting in cui la società schiera almeno un atleta
# Stagione 2 (primo anno «normale»): stesse tre chiavi standard, ma il posto in lega richiesto si allarga di un posto ogni
# BOARD_RAMP_GAP_PER_PLACE punti di forza che la rosa (media dei migliori BOARD_RAMP_SQUAD_SIZE) ha sotto la media dei rivali
# del livello, al massimo di BOARD_RAMP_MAX_SLACK posti. Dalla stagione 3 è tutto standard.
BOARD_RAMP_GAP_PER_PLACE = 5.0
BOARD_RAMP_MAX_SLACK = 3
BOARD_RAMP_SQUAD_SIZE = 8
STANDARD_BOARD_KEYS: Tuple[str, ...] = (BOARD_KEY_LEAGUE, BOARD_KEY_BUDGET, BOARD_KEY_RECORDS)
BOARD_KEYS: Tuple[str, ...] = STANDARD_BOARD_KEYS + FOUNDATION_KEYS
# Posto massimo in lega richiesto, per livello (a pari merito di forza, più in alto gli avversari sono più forti).
BOARD_LEAGUE_TARGET: Dict[CompetitionTier, int] = {
    CompetitionTier.PROVINCIALE: 3,
    CompetitionTier.REGIONALE: 4,
    CompetitionTier.NAZIONALE: 5,
    CompetitionTier.INTERNAZIONALE: 5,
}
BOARD_MIN_RECORDS = 2  # record sociali da stabilire nella stagione (individuali e staffette)
BOARD_OBJECTIVES_TO_PASS = 2  # obiettivi centrati su tre perché la stagione non sia fallita
BOARD_MAX_FAILED_STREAK = 2  # stagioni fallite di fila che portano all'esonero


class SeasonOutcome(str, Enum):
    PROMOTED = "Promossa"
    STAYED = "Salvezza"
    RELEGATED = "Retrocessa"
    CHAMPION = "Campione"


@dataclass
class SeasonEndResult:
    """Final league table of a season and what it meant for the club."""

    season: int
    tier: CompetitionTier
    placement: int
    outcome: SeasonOutcome
    final_table: List[Tuple[str, int]] = field(default_factory=list)
    new_tier: Optional[CompetitionTier] = None
    # Verdetto del Board (C.2): (obiettivo, centrato?) per ciascuno; `board_failed` è None se la stagione non aveva
    # obiettivi del Board (partita iniziata prima di C.2), `board_streak` le stagioni fallite di fila dopo questa.
    board_results: List[Tuple[str, bool]] = field(default_factory=list)
    board_failed: Optional[bool] = None
    board_streak: int = 0
    fired: bool = False
    board_foundation: bool = False  # stagione di fondazione: il verdetto è solo informativo (Q32)


@dataclass
class Scout:
    """Osservatore capo (E.3): due attributi 1-20 (`SCOUT_ATTRIBUTES`) e un compenso settimanale."""

    scout_id: int
    name: str
    weekly_cost: int
    potenziale: int
    attuale: int


@dataclass
class StaffMember:
    """Club staff specialist providing bonuses at a weekly salary."""

    id: Optional[int]
    name: str
    role: StaffRole
    skill: int  # 1-5 stars
    weekly_cost: int
    hired: bool = False
    description: str = ""
    # Attributi 1-20 del ruolo (E.1, chiavi in `STAFF_ATTRIBUTES`); vuoto = tutti al riferimento (vecchi salvataggi).
    attributes: Dict[str, int] = field(default_factory=dict)


@dataclass
class SeasonObjective:
    """Trackable seasonal club milestone/objective."""

    key: str
    title: str
    completed: bool = False
    target: int = 0  # soglia dell'obiettivo del Board (posto massimo, bilancio da non peggiorare, n. record); 0 = nessuna
    value: int = 0  # avanzamento dove si conta (record sociali stabiliti nella stagione)


@dataclass
class EthicalDilemma:
    """Narrative moral choice with short-term vs long-term consequences."""

    id: str
    title: str
    description: str
    accept_label: str
    reject_label: str
    athlete_id: Optional[int] = None


@dataclass
class Transaction:
    """Financial ledger entry."""

    id: Optional[int]
    week: int
    description: str
    category: str
    amount: int


@dataclass
class MonthlyReport:
    """Bilancio di un mese (D.3): entrate e uscite per categoria, ricavate dal libro mastro delle sue 4 settimane."""

    season: int
    month: int  # 1-9 nella stagione
    first_week: int
    last_week: int
    income: Dict[str, int] = field(default_factory=dict)  # categoria -> importo positivo
    expenses: Dict[str, int] = field(default_factory=dict)  # categoria -> importo positivo (uscite)
    budget_end: int = 0

    @property
    def total_income(self) -> int:
        return sum(self.income.values())

    @property
    def total_expenses(self) -> int:
        return sum(self.expenses.values())

    @property
    def net(self) -> int:
        return self.total_income - self.total_expenses

    @property
    def label(self) -> str:
        return f"Stagione {self.season} · mese {self.month} (sett. {self.first_week}-{self.last_week})"


@dataclass
class EventStanding:
    """A single competitor's performance in an event."""

    athlete_name: str
    team_name: str
    is_player: bool
    mark_value: float
    mark_display: str
    placement: int = 0
    wind_ms: Optional[float] = None
    wind_illegal: bool = False


@dataclass
class EventResult:
    """Full results of a single simulated event."""

    event_name: str
    player_athlete_name: str
    placement: int
    total_competitors: int
    player_mark: str
    prize_money: int
    prestige_gained: int
    wind_ms: Optional[float] = None
    wind_illegal: bool = False
    is_pb: bool = False
    is_club_record: bool = False
    standings: List[EventStanding] = field(default_factory=list)
    attitude: str = RaceAttitude.NORMALE.value
    withdrew_injured: bool = False
    disqualified: bool = False
    gender: str = ""

    @property
    def display_event_name(self) -> str:
        if self.gender in ("M", "F"):
            return f"{self.event_name} ({self.gender})"
        return self.event_name


@dataclass
class CompetitionSummary:
    """Summary of an entire competition meet."""

    week: int
    tier: CompetitionTier
    season_phase: SeasonPhase
    meet_name: str
    weather: WeatherCondition
    track_surface: str
    event_results: List[EventResult]
    total_prize_money: int
    total_prestige_gained: int
    travel_cost: int = 0
    promoted_to: Optional[CompetitionTier] = None
    is_home: bool = False
    spectators: int = 0
    ticket_income: int = 0
    team_standings: List[Tuple[str, int]] = field(default_factory=list)
    player_team: str = ""
    # La società non aveva atleti e non si è iscritta (Q32). Transitorio, NON salvato: serve solo ai dialoghi del tick.
    club_absent: bool = False

    @property
    def team_placement(self) -> int:
        for idx, (team, _pts) in enumerate(self.team_standings, start=1):
            if team == self.player_team:
                return idx
        return 0


# Stessa lista (valore, etichetta), stesso ordine, per i due punti di ingresso di "nuova partita"
# (StartScreen e NewGameDialog): prima erano in ordine opposto con default diversi.
GAME_MODE_OPTIONS: List[Tuple[str, str]] = [
    ("career", "Carriera Completa (Outdoor, Cross, Indoor, Promozioni)"),
    ("vertical_slice", "Prototipo Outdoor (10 atleti, 3 discipline, 2 gare)"),
]


@dataclass
class GameState:
    """Root state object for the management simulation."""

    team_name: str = "Atletica Aurora"
    game_mode: str = "vertical_slice"  # "vertical_slice" or "career"
    budget: int = 12000
    week: int = 1
    season_number: int = 1
    season_phase: SeasonPhase = SeasonPhase.OUTDOOR
    start_date: date = field(default_factory=lambda: FIRST_OUTDOOR_DATE)
    prestige: int = 0
    reputation: int = 70  # 0-100 ethical standing affecting sponsors
    tier: CompetitionTier = CompetitionTier.PROVINCIALE
    track_condition: int = 82  # 1-100 tartan track condition
    member_fees_weekly: int = 450
    athletes: List[Athlete] = field(default_factory=list)
    staff: List[StaffMember] = field(default_factory=list)
    transactions: List[Transaction] = field(default_factory=list)
    competition_history: List[CompetitionSummary] = field(default_factory=list)
    event_lineup: Dict[str, Optional[int]] = field(default_factory=dict)
    club_records: Dict[str, Tuple[float, str, str]] = field(default_factory=dict)
    objectives: List[SeasonObjective] = field(default_factory=list)
    milestones: List[str] = field(default_factory=list)
    news_log: List[str] = field(default_factory=list)
    pending_dilemma: Optional[EthicalDilemma] = None
    event_attitude: Dict[str, str] = field(default_factory=dict)
    # Piano gara per evento (B.1): {"800m": {"pace": "Veloce", "kick": "Ultimo giro"}}; mancante = Medio + Nessuno.
    race_strategy: Dict[str, Dict[str, str]] = field(default_factory=dict)
    # Campo mondiale di atleti sintetici per il ranking (C.1); vuoto = salvataggio vecchio, si genera al caricamento.
    ranking_pool: List[SyntheticAthlete] = field(default_factory=list)
    gym_level: int = 0
    # Impianti avanzati posseduti (E.2): chiave di `FACILITY_ORDER` → livello (1 = posseduto). Vuoto = nessuno.
    facilities: Dict[str, int] = field(default_factory=dict)
    academy_level: int = 0  # stelle dell'Academy 0-5 (E.3); 0 = il vivaio di prima
    scout: Optional[Scout] = None  # osservatore capo assunto (E.3); None = nessuno
    stand_seats: int = 500
    fidelity: int = 100  # 0-100: drops with transfers, sponsors value stable squads
    scouting_points_used: int = 0
    bankrupt: bool = False
    board_failed_streak: int = 0  # stagioni fallite di fila secondo il Board (C.2)
    fired: bool = False  # esonerato dal Board: la partita è finita, come nel fallimento
    # Settimane di Preparazione (senza gare) a inizio di ogni stagione: SEASON_PREP_WEEKS nelle Carriere nuove, 0 nei
    # salvataggi esistenti e nel Prototipo (calendario invariato). Tutta l'aritmetica del ciclo passa da qui sotto.
    prep_weeks: int = 0
    league_table: Dict[str, int] = field(default_factory=dict)
    # Per club: quanti 1°, 2°, ... posti (indice 0 = 1°) ha ottenuto in stagione; serve allo spareggio (A.2).
    league_places: Dict[str, List[int]] = field(default_factory=dict)
    # Stato completo dell'RNG della partita (`random.Random.getstate()` come lista JSON); vuoto = salvataggio vecchio (A.3).
    rng_state: List = field(default_factory=list)
    coaches: List[Coach] = field(default_factory=list)
    retired: List[RetiredAthlete] = field(default_factory=list)  # ex atleti (C.3), i più recenti in testa
    agents: List[Agent] = field(default_factory=list)  # agenti degli atleti (D.1), anche senza clienti se la relazione non è neutra
    monthly_reports: List[MonthlyReport] = field(default_factory=list)  # bilanci mensili (D.3), il più recente in testa
    relays: Dict[str, Relay] = field(default_factory=dict)
    coach_hired_week: int = 0  # one new coach per week
    rival_clubs: List[RivalClub] = field(default_factory=list)
    season_history: List[SeasonEndResult] = field(default_factory=list)  # newest first
    event_lineup_f: Dict[str, Optional[int]] = field(default_factory=dict)
    club_records_f: Dict[str, Tuple[float, str, str]] = field(default_factory=dict)
    relays_f: Dict[str, Relay] = field(default_factory=dict)

    def lineup_for(self, gender: str = "M") -> Dict[str, Optional[int]]:
        return self.event_lineup_f if gender == "F" else self.event_lineup

    def records_for(self, gender: str = "M") -> Dict[str, Tuple[float, str, str]]:
        return self.club_records_f if gender == "F" else self.club_records

    def relays_for(self, gender: str = "M") -> Dict[str, Relay]:
        return self.relays_f if gender == "F" else self.relays

    def tiebreak_draw(self, team: str) -> int:
        """Sorteggio deterministico per l'ultimo spareggio: dipende da stagione e posizione del club, non dal nome.

        La posizione è nell'elenco [società del giocatore, rivali della categoria]; `hashlib` e non `hash()`
        (quello è salato per processo). Stesso salvataggio → stesso ordine, a ogni esecuzione.
        """
        order = [self.team_name] + [c.name for c in self.rivals_in()]
        index = order.index(team) if team in order else len(order)
        digest = hashlib.sha256(f"{TIEBREAK_DRAW_TAG}|{self.season_number}|{index}".encode()).digest()
        return int.from_bytes(digest[:8], "big")

    def rank_key(self, team: str, points: int, places: Optional[List[int]] = None):
        """Chiave di ordinamento (crescente = meglio): punti, poi più 1°, 2°, ..., poi sorteggio."""
        counts = list(places or [])[:LEAGUE_PLACE_SLOTS]
        counts += [0] * (LEAGUE_PLACE_SLOTS - len(counts))
        return (-points, tuple(-n for n in counts), self.tiebreak_draw(team))

    def league_standings(self) -> List[Tuple[str, int]]:
        """Current league table with every club of the category (0 points if not scored yet).

        Ties are broken by placements (more 1st places, then 2nd, ...), then by a deterministic draw (A.2).
        """
        table = {self.team_name: 0}
        table.update({c.name: 0 for c in self.rivals_in()})
        table.update({k: v for k, v in self.league_table.items() if k in table})
        return sorted(table.items(), key=lambda kv: self.rank_key(kv[0], kv[1], self.league_places.get(kv[0])))

    @property
    def league_position(self) -> int:
        for idx, (team, _pts) in enumerate(self.league_standings(), start=1):
            if team == self.team_name:
                return idx
        return 0

    @property
    def weeks_to_season_end(self) -> Optional[int]:
        """Weeks left before the final league table is drawn up (career mode only)."""
        if self.game_mode != "career":
            return None
        return self.season_length - ((self.week - 1) % self.season_length)

    # ---- calendario della stagione (Preparazione + Outdoor, Cross, Indoor)
    @property
    def season_length(self) -> int:
        """Settimane di una stagione di Carriera: la Preparazione (se c'è) più le tre fasi da `PHASE_WEEKS`."""
        return SEASON_WEEKS + self.prep_weeks

    @property
    def season_cycle(self) -> List[SeasonPhase]:
        """Le fasi di una stagione, nell'ordine in cui si susseguono."""
        cycle = [SeasonPhase.OUTDOOR, SeasonPhase.CROSS, SeasonPhase.INDOOR]
        return ([SeasonPhase.PREPARAZIONE] if self.prep_weeks > 0 else []) + cycle

    def is_phase_start(self, week: int) -> bool:
        """Vero se `week` è la prima settimana di una fase (o della stagione)."""
        pos = (week - 1) % self.season_length
        # Con `prep_weeks` = 0 il primo e il secondo inizio coincidono: restano 0, 12 e 24 come prima.
        return pos in (0, self.prep_weeks, self.prep_weeks + PHASE_WEEKS, self.prep_weeks + 2 * PHASE_WEEKS)

    def is_prep_week(self, week: int) -> bool:
        """Vero se `week` cade nella Preparazione di una stagione (mai nelle partite con `prep_weeks` = 0)."""
        return self.prep_weeks > 0 and (week - 1) % self.season_length < self.prep_weeks

    def is_race_week(self, week: int) -> bool:
        """Si gareggia ogni 4 settimane, tranne in Preparazione."""
        return week % 4 == 0 and not self.is_prep_week(week)

    @property
    def is_foundation_season(self) -> bool:
        """La stagione 1 di una Carriera nuova (senza atleti): il Board giudica la fondazione, non i risultati (Q32)."""
        return self.is_foundation(self.season_number)

    def is_foundation(self, season: int) -> bool:
        return self.prep_weeks > 0 and season == 1

    def rivals_in(self, tier: Optional[CompetitionTier] = None) -> List[RivalClub]:
        t = tier or self.tier
        return [c for c in self.rival_clubs if c.tier == t]

    def coach_of(self, athlete: Athlete) -> Optional[Coach]:
        """The athlete's coach, if assigned and allowed to train them."""
        if athlete.coach_id is None:
            return None
        coach = next((c for c in self.coaches if c.id == athlete.coach_id), None)
        return coach if coach is not None and coach.can_train(athlete) else None

    def coach_load(self, coach: Coach) -> int:
        return sum(1 for a in self.athletes if a.coach_id == coach.id and coach.can_train(a))

    @property
    def active_relays(self) -> List[str]:
        """Relays run this season: they need their sprint event in the programme; no 4x100 indoors."""
        out: List[str] = []
        if self.season_phase == SeasonPhase.CROSS:
            return out
        for name, rdef in RELAYS.items():
            if rdef.requires_event not in self.active_events:
                continue
            if self.season_phase == SeasonPhase.INDOOR and not rdef.indoor:
                continue
            out.append(name)
        return out

    def lineup_problem(self, athlete: Athlete, event_name: str, gender: str) -> Optional[str]:
        """Motivo (in italiano) per cui `athlete` non può essere convocato in `event_name`, o None se può.

        Regole: stessa divisione, Prima Squadra, età minima del livello (Q17) e al massimo
        `MAX_INDIVIDUAL_EVENTS` gare individuali tra quelle attive (le altre non si disputano).
        """
        if athlete.gender != gender:
            return f"{athlete.name} non può gareggiare nella divisione {gender}."
        if athlete.in_youth_squad:
            return f"{athlete.name} è nel vivaio e non gareggia."
        if not athlete.can_race_in(self.tier):
            return (
                f"{athlete.name} ha {athlete.age} anni: in {self.tier.display_name} "
                f"gareggiano solo atleti dai {INTERNATIONAL_MIN_AGE} anni."
            )
        lineup = self.lineup_for(gender)
        others = [e for e in self.active_events if e != event_name and lineup.get(e) == athlete.id]
        if len(others) >= MAX_INDIVIDUAL_EVENTS:
            return (
                f"{athlete.name} è già iscritto a {len(others)} gare individuali "
                f"({', '.join(others)}): il massimo è {MAX_INDIVIDUAL_EVENTS} più una staffetta."
            )
        return None

    def relay_of(self, athlete_id: Optional[int], gender: Optional[str] = None) -> Optional[str]:
        if athlete_id is None:
            return None
        pools = (
            [self.relays_for(gender)]
            if gender in ("M", "F")
            else [self.relays, self.relays_f]
        )
        for pool in pools:
            for name, relay in pool.items():
                if athlete_id in relay.all_ids():
                    return name
        return None

    @property
    def main_squad(self) -> List[Athlete]:
        return [a for a in self.athletes if not a.in_youth_squad]

    @property
    def youth_squad(self) -> List[Athlete]:
        return [a for a in self.athletes if a.in_youth_squad]

    @property
    def scouting_points_left(self) -> int:
        return max(0, WEEKLY_SCOUTING_POINTS - self.scouting_points_used)

    def attitude_for(self, event_name: str) -> RaceAttitude:
        raw = self.event_attitude.get(event_name, RaceAttitude.NORMALE.value)
        try:
            return RaceAttitude(raw)
        except ValueError:
            return RaceAttitude.NORMALE

    def strategy_for(self, event_name: str) -> Tuple[RacePace, RaceKick]:
        """Ritmo e scatto scelti per l'evento (solo 800m/1500m li usano); valori sconosciuti → i neutri."""
        raw = self.race_strategy.get(event_name, {})
        try:
            pace = RacePace(raw.get("pace", RacePace.MEDIO.value))
        except ValueError:
            pace = RacePace.MEDIO
        try:
            kick = RaceKick(raw.get("kick", RaceKick.NESSUNO.value))
        except ValueError:
            kick = RaceKick.NESSUNO
        return pace, kick

    def risk_for(self, event_name: str) -> FieldRisk:
        """Rischio scelto per un concorso (lungo/peso, B.2); assente o sconosciuto → Sicuro."""
        try:
            return FieldRisk(self.race_strategy.get(event_name, {}).get("risk", FieldRisk.SICURO.value))
        except ValueError:
            return FieldRisk.SICURO

    def change_for(self, relay_name: str) -> RelayChange:
        """Cambio scelto per una staffetta (B.3); assente o sconosciuto → Normale."""
        try:
            return RelayChange(self.race_strategy.get(relay_name, {}).get("change", RelayChange.NORMALE.value))
        except ValueError:
            return RelayChange.NORMALE

    @property
    def next_meet_is_home(self) -> bool:
        """Meets alternate home/away: odd-numbered meets are hosted in the club's own stadium."""
        next_meet_week = self.week if self.is_competition_week else self.week + self.weeks_until_competition
        return (next_meet_week // 4) % 2 == 1

    @property
    def active_events(self) -> List[str]:
        """Events active in the current mode."""
        if self.game_mode == "vertical_slice":
            return list(VERTICAL_SLICE_EVENTS)
        return list(EVENTS.keys())

    @property
    def current_date(self) -> date:
        return self.start_date + timedelta(days=(self.week - 1) * 7)

    @property
    def is_competition_week(self) -> bool:
        """Competitions occur every 4 in-game weeks (never during the Preparazione)."""
        return self.is_race_week(self.week)

    @property
    def weeks_until_competition(self) -> int:
        """Settimane alla prossima gara (0 se questa è di gara); la Preparazione non ne ha, si salta."""
        if self.is_competition_week:
            return 0
        return next(k for k in range(1, self.season_length + 5) if self.is_race_week(self.week + k))

    @property
    def is_vertical_slice_complete(self) -> bool:
        """In the 8-week outdoor prototype, two meets take place (Week 4 & Week 8)."""
        return self.game_mode == "vertical_slice" and self.week > 8
