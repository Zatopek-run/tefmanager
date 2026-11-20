"""Agenti degli atleti (PIANOLAVORO D.1). Nessuna dipendenza da Qt e **nessuna estrazione dall'RNG della partita**:
tutto è deterministico (dal nome dell'atleta e dall'id dell'agente), quindi l'ordine del tick e le sequenze casuali
non cambiano (convenzione 3: un `random.Random(intero)` locale, come `_backfill_bodies`, non tocca l'RNG della partita).

- Ogni atleta ha un agente (`Athlete.agent_id`); un agente ne cura più d'uno e la **relazione** (0-100, parte da 50) è del
  giocatore con l'agente: svincolare un atleta peggiora i rapporti anche con gli altri suoi assistiti.
- **Personalità:** Aggressivo chiede +20% sull'ingaggio al tesseramento, Ragionevole 0, Leale −10%. La relazione sposta la
  richiesta di ±`AGENT_RELATION_FEE_SPAN` punti percentuali (a 50 nulla, a 100 −15, a 0 +15).
- **Relazione:** sale con i rinnovi (`AGENT_RELATION_RENEWED`) e i podi (`AGENT_RELATION_PODIUM`) dei suoi atleti, scende con lo
  svincolo (`AGENT_RELATION_RELEASED`), con il mancato rinnovo (`AGENT_RELATION_NOT_RENEWED`) e con ogni atleta della Prima
  Squadra «lasciato fermo» una stagione intera (`AGENT_RELATION_IDLE`, `penalize_idle_athletes`). A ogni cambio stagione si
  raffredda verso 50 (`drift_relations`), così non satura a 100 da sola.
- Oggi l'agente agisce solo sull'ingaggio una tantum (`negotiated_fee`); con D.2 la stessa percentuale sarà la richiesta iniziale
  della trattativa.
"""

from __future__ import annotations

import math
import random
import zlib
from typing import List, Optional

from models.entities import (
    AGENT_MAX_IDLE,
    AGENT_RELATION_DRIFT,
    AGENT_RELATION_IDLE,
    AGENT_NEW_SLOTS,
    AGENT_PERSONALITY_WEIGHTS,
    AGENT_RELATION_MAX,
    AGENT_RELATION_START,
    RELAYS,
    Agent,
    AgentPersonality,
    Athlete,
    GameState,
)
from models.generator import (
    FEMALE_NAME_LIST,
    LAST_NAMES,
    MALE_FIRST_NAMES,
    get_recruitment_fee,
)

_PICK_TAG = "agent-pick"
_NAME_TAG = "agent-name"


def _crc(*parts: object) -> int:
    """Numero stabile da testo (`zlib.crc32`, non `hash()`: quello è salato per processo)."""
    return zlib.crc32("|".join(str(p) for p in parts).encode("utf-8"))


def make_agent(agent_id: int, seed_text: str) -> Agent:
    """Agente nuovo: nome e personalità dipendono solo da `seed_text` (il nome del primo assistito) e dall'id."""
    r = random.Random(_crc(_NAME_TAG, agent_id, seed_text))
    first = r.choice(MALE_FIRST_NAMES + FEMALE_NAME_LIST)
    name = f"{first} {r.choice(LAST_NAMES)}"
    personalities = list(AGENT_PERSONALITY_WEIGHTS)
    weights = [AGENT_PERSONALITY_WEIGHTS[p] for p in personalities]
    personality: AgentPersonality = r.choices(personalities, weights=weights, k=1)[0]
    return Agent(id=agent_id, name=name, personality=personality, relation=AGENT_RELATION_START)


def agent_by_id(state: GameState, agent_id: Optional[int]) -> Optional[Agent]:
    if agent_id is None:
        return None
    return next((a for a in state.agents if a.id == agent_id), None)


def agent_of(state: GameState, athlete: Athlete) -> Optional[Agent]:
    return agent_by_id(state, athlete.agent_id)


def clients_of(state: GameState, agent: Agent) -> List[Athlete]:
    return [a for a in state.athletes if a.agent_id == agent.id]


def assign_agent(state: GameState, athlete: Athlete) -> Agent:
    """Dà un agente all'atleta (se non ne ha già uno valido): uno già noto o uno nuovo, in modo deterministico.

    Con `n` agenti noti, la scelta è `crc32(nome) % (n + AGENT_NEW_SLOTS)`: un indice sotto `n` è un agente esistente, gli
    altri creano un agente nuovo. Gli agenti nuovi finiscono in `state.agents` subito, anche se l'atleta è solo un
    candidato del mercato: quelli rimasti senza clienti e con relazione neutra si potano a fine settimana (`prune_idle_agents`).
    """
    existing = agent_by_id(state, athlete.agent_id)
    if existing is not None:
        return existing
    n = len(state.agents)
    index = _crc(_PICK_TAG, athlete.name) % (n + AGENT_NEW_SLOTS)
    if index < n:
        agent = state.agents[index]
    else:
        agent = make_agent(max((a.id for a in state.agents), default=0) + 1, athlete.name)
        state.agents.append(agent)
    athlete.agent_id = agent.id
    return agent


def ensure_agents(state: GameState) -> int:
    """Dà un agente a chi non ce l'ha (nuova partita, vecchi salvataggi). Restituisce quanti. Nessun RNG."""
    missing = [a for a in sorted(state.athletes, key=lambda x: x.id or 0) if agent_by_id(state, a.agent_id) is None]
    for athlete in missing:
        assign_agent(state, athlete)
    return len(missing)


def negotiated_fee(athlete: Athlete, agent: Optional[Agent]) -> int:
    """Ingaggio al tesseramento chiesto dall'agente: ingaggio standard × (1 + personalità + relazione), almeno 1 €."""
    base = get_recruitment_fee(athlete)
    if agent is None:
        return base
    return max(1, round(base * (1 + agent.fee_modifier)))


def adjust_relation(state: GameState, agent_id: Optional[int], delta: int) -> Optional[Agent]:
    """Sposta la relazione con un agente, tra 0 e 100. Non fa nulla se l'agente non esiste."""
    agent = agent_by_id(state, agent_id)
    if agent is None:
        return None
    agent.relation = max(0, min(AGENT_RELATION_MAX, agent.relation + delta))
    return agent


def drift_relations(state: GameState) -> None:
    """Al cambio stagione ogni relazione si avvicina a quella neutra di `AGENT_RELATION_DRIFT` della distanza (nessun RNG).

    Il passo è arrotondato per eccesso: chi non è a 50 si muove sempre di almeno un punto, così arriva davvero al neutro
    (con `round()` i valori 48-52 non si sarebbero mai mossi e gli agenti inattivi non sarebbero mai stati potati).
    """
    for agent in state.agents:
        gap = AGENT_RELATION_START - agent.relation
        if gap:
            agent.relation += int(math.copysign(math.ceil(abs(gap) * AGENT_RELATION_DRIFT), gap))


def raced_names(state: GameState, season: int) -> set:
    """Nomi degli atleti del club convocati in una gara individuale (anche ritirati prima del via) nella stagione `season`."""
    first, last = (season - 1) * state.season_length + 1, season * state.season_length
    return {
        er.player_athlete_name
        for summary in state.competition_history
        if first <= summary.week <= last
        for er in summary.event_results
        if er.event_name not in RELAYS
    }


def penalize_idle_athletes(state: GameState, season: int) -> int:
    """«Resta fermo»: ogni atleta della Prima Squadra mai convocato nella stagione `season` (né in una gara individuale
    né in una staffetta, quella in formazione al cambio stagione) abbassa di `AGENT_RELATION_IDLE` la relazione con il suo
    agente. Restituisce quanti atleti. Nessun RNG. Chi è arrivato a stagione quasi finita è penalizzato come gli altri."""
    if state.is_foundation(season):  # Q32: nella stagione di fondazione nessuna penalità («resta fermo» non si applica)
        return 0
    raced = raced_names(state, season)
    in_relay = {
        mid
        for relay in list(state.relays.values()) + list(state.relays_f.values())
        for mid in relay.all_ids()
    }
    idle = [a for a in state.main_squad if a.name not in raced and a.id not in in_relay]
    for athlete in idle:
        adjust_relation(state, athlete.agent_id, AGENT_RELATION_IDLE)
    return len(idle)


def prune_idle_agents(state: GameState) -> int:
    """Toglie gli agenti senza clienti e con relazione neutra (i candidati del mercato non presi); ne ricorda al più
    `AGENT_MAX_IDLE` senza clienti, tenendo quelli con la relazione più lontana da quella neutra. Restituisce quanti ne toglie."""
    with_clients = {a.agent_id for a in state.athletes}
    idle = [ag for ag in state.agents if ag.id not in with_clients]
    drop = {ag.id for ag in idle if ag.relation == AGENT_RELATION_START}
    remembered = sorted(
        (ag for ag in idle if ag.id not in drop), key=lambda ag: (-abs(ag.relation - AGENT_RELATION_START), ag.id)
    )
    drop |= {ag.id for ag in remembered[AGENT_MAX_IDLE:]}
    if drop:
        state.agents = [ag for ag in state.agents if ag.id not in drop]
    return len(drop)

