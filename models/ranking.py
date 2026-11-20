"""Ranking individuale e di società (PIANOLAVORO C.1). Nessuna dipendenza da Qt.

Tre tipi di concorrenti condividono **una sola scala di punti**: gli atleti del club, gli atleti dei club rivali
della lega e gli atleti *sintetici* (di fantasia, `SyntheticAthlete`), che riempiono la classifica mondiale
(100 per evento e sesso) ma non gareggiano con il club. Un piazzamento vale `RANKING_PLACE_POINTS[posto-1]` ×
`RANKING_TIER_MULT[livello]`; a ogni meeting i punti già posseduti decadono di `RANKING_DECAY`, per tutti
nello stesso tick (altrimenti i confronti tra un meeting e l'altro si sfalsano).

- Atleti del club e rivali: i punti vengono dai piazzamenti reali del meeting (`award_event_points`,
  `award_rival_place`), senza chiamate all'RNG.
- Sintetici: ogni meeting si simula un piazzamento dal loro livello contro un campo virtuale del livello che
  gareggia più vicino a loro (`update_synthetic_field`). Usano **l'RNG della partita** (convenzione 3): il campo
  si crea con `rng` alla partita nuova e al caricamento di un salvataggio vecchio (`upgrade_legacy_state`), e a
  ogni meeting estraggono da `r` in un punto fisso del tick (vedi `docs/TICK.md`, passo C-13b). Poiché lo stato
  dell'RNG è salvato, ricaricare dà gli stessi risultati.
- Staffette: **non** danno punti ranking (non sono individuali).
- Un rivale che si ritira porta via i suoi punti: il sostituto parte da zero.
"""

from __future__ import annotations

import math
import random
from bisect import bisect_left
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from models.entities import (
    NATIONALITIES,
    RANKING_DECAY,
    RANKING_HOME_NATION,
    RANKING_NATIONAL_SIZE,
    RANKING_PLACE_POINTS,
    RANKING_SYNTH_DRIFT,
    RANKING_SYNTH_FIELD,
    RANKING_SYNTH_ITALIAN_SHARE,
    RANKING_SYNTH_SKILL_BOTTOM,
    RANKING_SYNTH_SKILL_JITTER,
    RANKING_SYNTH_SKILL_TOP,
    RANKING_TIER_MULT,
    RANKING_WORLD_SIZE,
    RIVAL_RACE_SIGMA,
    TIER_CONFIG,
    Athlete,
    CompetitionTier,
    EventStanding,
    GameState,
    RivalAthlete,
    SyntheticAthlete,
)
from models.generator import FEMALE_NAME_LIST, LAST_NAMES, MALE_FIRST_NAMES

# Alla creazione i punti dei sintetici partono dal valore a regime atteso per il loro livello
# (`_expected_meeting_points` / (1 - decadimento)); poi si simulano questi meeting a vuoto per sporcarlo di rumore.
SYNTH_WARMUP_MEETINGS = 3
POINTS_EPSILON = 0.05  # sotto questa soglia i punti di un evento si cancellano


# ---------------------------------------------------------------- punti
def place_points(tier: CompetitionTier, placement: int) -> float:
    """Punti ranking di un piazzamento (1-based) in una gara del livello `tier`."""
    if placement < 1 or placement > len(RANKING_PLACE_POINTS):
        return 0.0
    return RANKING_PLACE_POINTS[placement - 1] * RANKING_TIER_MULT[tier]


def _add(holder: "Athlete | RivalAthlete", event: str, points: float) -> None:
    if points <= 0:
        return
    holder.ranking_points[event] = round(holder.ranking_points.get(event, 0.0) + points, 2)


def award_place(holder: "Athlete | RivalAthlete", event: str, tier: CompetitionTier, placement: int) -> None:
    """Assegna i punti di un piazzamento a un atleta del club o a un rivale."""
    _add(holder, event, place_points(tier, placement))


def award_event_points(
    tier: CompetitionTier,
    event: str,
    standings: Iterable[EventStanding],
    holders: Dict[Tuple[str, str], "Athlete | RivalAthlete"],
) -> None:
    """Punti per i piazzamenti di una gara. `holders` mappa (squadra, nome) all'atleta: chi non c'è non ne riceve
    (per esempio il ritirato del club, che non è stato classificato)."""
    for standing in standings:
        holder = holders.get((standing.team_name, standing.athlete_name))
        if holder is not None:
            award_place(holder, event, tier, standing.placement)


def _decay_dict(points: Dict[str, float]) -> None:
    for event in list(points):
        value = round(points[event] * RANKING_DECAY, 2)
        if value < POINTS_EPSILON:
            del points[event]
        else:
            points[event] = value


def _decay_pool(pool: Iterable[SyntheticAthlete]) -> None:
    for s in pool:
        s.points = round(s.points * RANKING_DECAY, 2)


def decay_ranking(state: GameState) -> None:
    """Decadimento di tutti i punti (club, rivali di ogni livello, sintetici): una volta per meeting, prima dei
    nuovi punti."""
    for athlete in state.athletes:
        _decay_dict(athlete.ranking_points)
    for club in state.rival_clubs:
        for pool in (club.athletes, club.female_athletes):
            for rival in pool.values():
                _decay_dict(rival.ranking_points)
    _decay_pool(state.ranking_pool)


# ---------------------------------------------------------------- campo sintetico
# Livelli ordinati per forza del campo, con i punti dei piazzamenti 1..RANKING_SYNTH_FIELD già moltiplicati
# (calcolati una volta: il campo sintetico è la parte più costosa del ranking).
_TIERS_BY_SKILL: List[CompetitionTier] = sorted(TIER_CONFIG, key=lambda t: TIER_CONFIG[t]["opponent_skill"])
_TIER_CUTS: List[float] = [
    (TIER_CONFIG[a]["opponent_skill"] + TIER_CONFIG[b]["opponent_skill"]) / 2
    for a, b in zip(_TIERS_BY_SKILL, _TIERS_BY_SKILL[1:])
]
_TIER_POINTS: Dict[CompetitionTier, Tuple[float, ...]] = {
    t: tuple(place_points(t, place) for place in range(1, RANKING_SYNTH_FIELD + 1)) for t in TIER_CONFIG
}


def _synth_tier(skill: float) -> CompetitionTier:
    """Il livello di gara con il campo più vicino al loro livello."""
    return _TIERS_BY_SKILL[bisect_left(_TIER_CUTS, skill)]


def _expected_meeting_points(skill: float) -> float:
    """Punti attesi in un meeting da un sintetico di livello `skill`, con la prestazione al suo livello medio
    (senza il rumore del giorno): distribuzione binomiale dei piazzamenti contro il campo virtuale."""
    tier = _synth_tier(skill)
    opponent_skill = TIER_CONFIG[tier]["opponent_skill"]
    p = 0.5 * math.erfc((skill - opponent_skill) / (RIVAL_RACE_SIGMA * math.sqrt(2.0)))
    n = RANKING_SYNTH_FIELD - 1
    points = _TIER_POINTS[tier]
    return sum(math.comb(n, k) * p**k * (1 - p) ** (n - k) * points[k] for k in range(n + 1))


def generate_synthetic_field(state: GameState, rng: random.Random) -> List[SyntheticAthlete]:
    """Crea il campo mondiale: `RANKING_WORLD_SIZE` atleti per evento attivo e sesso, con livello decrescente
    dal 1° al 100° e punti già a regime (stima analitica più `SYNTH_WARMUP_MEETINGS` meeting simulati).

    Riceve l'RNG della partita (`GameController.rng`, o quello passato a `upgrade_legacy_state`).
    """
    foreign = [n for n in NATIONALITIES if n != RANKING_HOME_NATION]
    pool: List[SyntheticAthlete] = []
    for gender in ("M", "F"):
        first_names = FEMALE_NAME_LIST if gender == "F" else MALE_FIRST_NAMES
        for event in state.active_events:
            for i in range(RANKING_WORLD_SIZE):
                q = i / (RANKING_WORLD_SIZE - 1)
                skill = RANKING_SYNTH_SKILL_TOP + (RANKING_SYNTH_SKILL_BOTTOM - RANKING_SYNTH_SKILL_TOP) * q
                skill = round(skill + rng.gauss(0.0, RANKING_SYNTH_SKILL_JITTER), 2)
                nationality = RANKING_HOME_NATION if rng.random() < RANKING_SYNTH_ITALIAN_SHARE else rng.choice(foreign)
                pool.append(
                    SyntheticAthlete(
                        name=f"{rng.choice(first_names)} {rng.choice(LAST_NAMES)}",
                        nationality=nationality,
                        event=event,
                        gender=gender,
                        skill=skill,
                    )
                )
    for s in pool:
        s.points = round(_expected_meeting_points(s.skill) / (1.0 - RANKING_DECAY), 2)
    for _ in range(SYNTH_WARMUP_MEETINGS):
        _decay_pool(pool)
        _play_meeting(pool, rng)
    return pool


def _play_meeting(pool: List[SyntheticAthlete], rng: random.Random) -> None:
    """Un meeting per ogni sintetico: il livello si muove un poco, poi si simula il piazzamento contro un campo
    virtuale e si sommano i punti. Ordine delle chiamate al flusso dedicato: per atleta, nell'ordine della lista,
    una `gauss` di deriva, una per la prestazione e `RANKING_SYNTH_FIELD - 1` `random()` per gli avversari."""
    for s in pool:
        s.skill = round(min(100.0, max(30.0, s.skill + rng.gauss(0.0, RANKING_SYNTH_DRIFT))), 2)
        tier = _synth_tier(s.skill)
        opponent_skill = TIER_CONFIG[tier]["opponent_skill"]
        mine = rng.gauss(s.skill, RIVAL_RACE_SIGMA)
        # Ciascun avversario virtuale batte `mine` con probabilità P(N(opponent_skill, σ) > mine), indipendente dagli
        # altri a parità di `mine`: una `random()` a testa invece di una `gauss` (più veloce, stessa distribuzione).
        p_ahead = 0.5 * math.erfc((mine - opponent_skill) / (RIVAL_RACE_SIGMA * math.sqrt(2.0)))
        ahead = 0
        for _ in range(RANKING_SYNTH_FIELD - 1):
            if rng.random() < p_ahead:
                ahead += 1
        s.points = round(s.points + _TIER_POINTS[tier][ahead], 2)


def update_synthetic_field(state: GameState, rng: random.Random) -> None:
    """Passo del tick: i sintetici gareggiano. Senza campo (stato costruito a mano, vecchi test) non fa nulla e
    non consuma l'RNG. Il decadimento è già stato applicato a tutti da `decay_ranking`."""
    if state.ranking_pool:
        _play_meeting(state.ranking_pool, rng)


def ensure_ranking_pool(state: GameState, rng: random.Random) -> bool:
    """Genera il campo sintetico se manca (partita nuova, salvataggio vecchio). Consuma `rng`: ritorna True se l'ha
    creato, False (RNG intatto) se c'era già."""
    if state.ranking_pool:
        return False
    state.ranking_pool = generate_synthetic_field(state, rng)
    return True


# ---------------------------------------------------------------- classifiche
@dataclass
class RankingEntry:
    rank: int
    name: str
    club: str
    nationality: str
    points: float
    kind: str  # "player" | "rival" | "synthetic"
    event: str = ""
    gender: str = "M"

    @property
    def is_player(self) -> bool:
        return self.kind == "player"


_KIND_ORDER = {"player": 0, "rival": 1, "synthetic": 2}


def _entries(state: GameState, event: str, gender: str) -> List[RankingEntry]:
    out: List[RankingEntry] = []
    for s in state.ranking_pool:
        if s.event == event and s.gender == gender:
            out.append(RankingEntry(0, s.name, "—", s.nationality, s.points, "synthetic", event, gender))
    for club in state.rival_clubs:
        rival = club.athletes_for(gender).get(event)
        if rival is not None and rival.gender == gender:
            points = rival.ranking_points.get(event, 0.0)
            if points > 0:
                out.append(RankingEntry(0, rival.name, club.name, RANKING_HOME_NATION, points, "rival", event, gender))
    for athlete in state.athletes:
        points = athlete.ranking_points.get(event, 0.0)
        if points > 0 and athlete.gender == gender:
            out.append(
                RankingEntry(0, athlete.name, state.team_name, athlete.nationality, points, "player", event, gender)
            )
    # Stessi punti: prima il club, poi i rivali, poi i sintetici, poi il nome (ordine stabile e deterministico).
    out.sort(key=lambda e: (-e.points, _KIND_ORDER[e.kind], e.name))
    for i, entry in enumerate(out, start=1):
        entry.rank = i
    return out


def world_ranking(state: GameState, event: str, gender: str = "M") -> List[RankingEntry]:
    """Classifica completa di un evento e sesso (`rank` 1-based); la «Top 100» è la fetta `[:RANKING_WORLD_SIZE]`."""
    return _entries(state, event, gender)


def national_ranking(state: GameState, event: str, gender: str = "M") -> List[RankingEntry]:
    """Classifica degli atleti di nazionalità `RANKING_HOME_NATION`, numerata da 1."""
    out = [e for e in _entries(state, event, gender) if e.nationality == RANKING_HOME_NATION]
    for i, entry in enumerate(out, start=1):
        entry.rank = i
    return out


def athlete_rankings(state: GameState, athlete: Athlete, event: str) -> Tuple[Optional[int], Optional[int], float]:
    """(posto mondiale, posto nazionale, punti) di un atleta del club in un evento. I posti sono `None` se non ha
    ancora punti: oltre il 100° (o 50°) il posto c'è comunque, sta al chiamante mostrare «oltre»."""
    points = athlete.ranking_points.get(event, 0.0)
    if points <= 0:
        return None, None, 0.0
    world = next((e.rank for e in world_ranking(state, event, athlete.gender) if e.is_player and e.name == athlete.name), None)
    national = next(
        (e.rank for e in national_ranking(state, event, athlete.gender) if e.is_player and e.name == athlete.name), None
    )
    return world, national, points


def _total(pool: Iterable["Athlete | RivalAthlete"]) -> float:
    return round(sum(sum(a.ranking_points.values()) for a in pool), 2)


def club_ranking(state: GameState) -> List[Tuple[str, float, bool]]:
    """Società della lega attuale (club compreso) per somma dei punti dei loro atleti: (nome, punti, è il club)."""
    rows: List[Tuple[str, float, bool]] = [(state.team_name, _total(state.main_squad), True)]
    for club in state.rivals_in():
        rows.append((club.name, _total([*club.athletes.values(), *club.female_athletes.values()]), False))
    rows.sort(key=lambda r: (-r[1], not r[2], r[0]))
    return rows


def club_points(state: GameState) -> float:
    """Punti ranking del club (somma dei suoi atleti in rosa)."""
    return _total(state.main_squad)


__all__ = [
    "RANKING_NATIONAL_SIZE",
    "RANKING_WORLD_SIZE",
    "RankingEntry",
    "athlete_rankings",
    "award_event_points",
    "award_place",
    "club_points",
    "club_ranking",
    "decay_ranking",
    "ensure_ranking_pool",
    "generate_synthetic_field",
    "national_ranking",
    "place_points",
    "update_synthetic_field",
    "world_ranking",
]
