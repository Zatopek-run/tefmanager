"""Trattativa per tesserare un atleta (PIANOLAVORO D.2). Nessuna dipendenza da Qt e **nessuna estrazione dall'RNG**:
l'esito dipende solo dall'agente (personalità e relazione, D.1) e dall'offerta, quindi la sequenza del tick non cambia.

Flusso (un solo giro di controfferta):

1. L'agente **apre** con la sua richiesta (`opening_terms`): l'ingaggio chiesto in D.1 (standard × personalità × relazione),
   ridotto dell'eventuale **bonus per risultati** scelto (`RECORD_BONUS_OPTIONS`: lo si paga a ogni record sociale
   individuale finché dura il contratto; lo sconto sull'ingaggio è uguale al bonus).
2. Il giocatore può **accettare** la richiesta, **rifiutare** o **offrire** una cifra più bassa.
3. Se l'offerta è sotto `AGENT_BREAK_FRACTION` della soglia l'agente **rompe la trattativa** (Q30b: stato «Rotta», relazione −3,
   nessuna controfferta). Se l'offerta arriva alla **soglia** dell'agente (`floor_fee`: la sua richiesta meno la flessibilità della personalità,
   più alta con buona relazione) è accettata. Altrimenti l'agente **controffre** una volta, a metà strada tra offerta e
   richiesta (ma non sotto la soglia); il giocatore accetta o rifiuta, non si rilancia.

La clausola rescissoria (`Athlete.release_clause_cost`) non si negozia: vale per tutti i contratti (Q30).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from models.agents import negotiated_fee
from models.entities import (
    AGENT_FLEXIBILITY,
    AGENT_FLEXIBILITY_MAX,
    AGENT_BREAK_FRACTION,
    AGENT_FLEXIBILITY_RELATION_SPAN,
    AGENT_RELATION_BROKEN,
    AGENT_RELATION_START,
    MIN_NEGOTIATED_FEE,
    RECORD_BONUS_OPTIONS,
    Agent,
    Athlete,
)


@dataclass(frozen=True)
class Terms:
    """Condizioni di un contratto: ingaggio una tantum e bonus per ogni record sociale individuale (0 = nessuno)."""

    fee: int
    bonus: int = 0


class NegotiationState(Enum):
    OPEN = "Aperta"  # l'agente ha fatto la richiesta, il giocatore non ha ancora risposto
    COUNTERED = "Controfferta"  # l'agente ha rilanciato: resta solo accettare o rifiutare
    ACCEPTED = "Accettata"
    REFUSED = "Rifiutata"
    BROKEN = "Rotta"  # offerta troppo bassa: l'agente chiude la trattativa e la relazione cala (Q30b)


def agent_flexibility(agent: Agent) -> float:
    """Frazione sotto la sua richiesta fino a cui l'agente accetta: personalità ± relazione, tra 0 e `AGENT_FLEXIBILITY_MAX`."""
    trust = (agent.relation - AGENT_RELATION_START) / AGENT_RELATION_START
    flex = AGENT_FLEXIBILITY[agent.personality] + AGENT_FLEXIBILITY_RELATION_SPAN * trust
    return max(0.0, min(AGENT_FLEXIBILITY_MAX, flex))


def _base_ask(athlete: Athlete, agent: Agent) -> int:
    return max(MIN_NEGOTIATED_FEE, negotiated_fee(athlete, agent))


def bonus_options(athlete: Athlete, agent: Agent) -> List[int]:
    """Bonus tra cui scegliere (0 = nessuno): solo quelli che lasciano un ingaggio di almeno `MIN_NEGOTIATED_FEE`."""
    ask = _base_ask(athlete, agent)
    return [0] + [b for b in RECORD_BONUS_OPTIONS if ask - b >= MIN_NEGOTIATED_FEE]


def opening_terms(athlete: Athlete, agent: Agent, bonus: int = 0) -> Terms:
    """Richiesta di apertura dell'agente, con il bonus scelto (lo sconto sull'ingaggio è uguale al bonus)."""
    return Terms(fee=max(MIN_NEGOTIATED_FEE, _base_ask(athlete, agent) - bonus), bonus=bonus)


def floor_fee(athlete: Athlete, agent: Agent, bonus: int = 0) -> int:
    """Ingaggio minimo che l'agente accetta (con quel bonus): la sua richiesta meno la flessibilità, mai sotto il minimo."""
    ask = opening_terms(athlete, agent, bonus).fee
    return max(MIN_NEGOTIATED_FEE, round(ask * (1 - agent_flexibility(agent))))


def break_fee(athlete: Athlete, agent: Agent, bonus: int = 0) -> int:
    """Ingaggio sotto il quale l'agente rompe la trattativa (Q30b): `AGENT_BREAK_FRACTION` della sua soglia."""
    return round(floor_fee(athlete, agent, bonus) * AGENT_BREAK_FRACTION)


def is_valid_terms(athlete: Athlete, agent: Agent, terms: Terms) -> bool:
    """Condizioni che una trattativa può davvero produrre: bonus ammesso e ingaggio tra la soglia e la richiesta."""
    if terms.bonus not in bonus_options(athlete, agent):
        return False
    return floor_fee(athlete, agent, terms.bonus) <= terms.fee <= opening_terms(athlete, agent, terms.bonus).fee


class Negotiation:
    """Una trattativa per tesserare `athlete` con l'agente `agent`. Macchina a stati senza RNG (vedi il modulo)."""

    def __init__(self, athlete: Athlete, agent: Agent) -> None:
        self.athlete = athlete
        self.agent = agent
        self.state = NegotiationState.OPEN
        self.bonus = 0
        self.offered: Optional[int] = None  # l'offerta del giocatore (una sola)
        self.counter: Optional[Terms] = None
        self.terms: Optional[Terms] = None  # le condizioni concordate, a trattativa accettata

    # ---------------------------------------------------------------- dati
    @property
    def ask(self) -> Terms:
        return opening_terms(self.athlete, self.agent, self.bonus)

    @property
    def floor(self) -> int:
        return floor_fee(self.athlete, self.agent, self.bonus)

    @property
    def break_below(self) -> int:
        return break_fee(self.athlete, self.agent, self.bonus)

    @property
    def bonus_choices(self) -> List[int]:
        return bonus_options(self.athlete, self.agent)

    @property
    def is_closed(self) -> bool:
        return self.state in (NegotiationState.ACCEPTED, NegotiationState.REFUSED, NegotiationState.BROKEN)

    # ---------------------------------------------------------------- mosse
    def set_bonus(self, bonus: int) -> None:
        """Sceglie il bonus per risultati: solo prima di rispondere alla richiesta (poi le condizioni sono fissate)."""
        if self.state is not NegotiationState.OPEN or self.offered is not None:
            raise ValueError("il bonus si sceglie prima di fare un'offerta")
        if bonus not in self.bonus_choices:
            raise ValueError(f"bonus non ammesso: {bonus}")
        self.bonus = bonus

    def accept_ask(self) -> Terms:
        """Accetta la richiesta dell'agente così com'è."""
        self._require(NegotiationState.OPEN)
        return self._close(self.ask)

    def offer(self, fee: int) -> NegotiationState:
        """Offre un ingaggio più basso. Sopra la soglia è accettato (non si paga più della richiesta); sotto, l'agente
        controffre una volta a metà strada, senza scendere sotto la soglia; sotto `break_below` rompe la trattativa
        (Q30b) e la relazione scende di `AGENT_RELATION_BROKEN`."""
        self._require(NegotiationState.OPEN)
        if fee < MIN_NEGOTIATED_FEE:
            raise ValueError(f"offerta sotto il minimo di €{MIN_NEGOTIATED_FEE}")
        self.offered = fee
        ask = self.ask
        if fee < self.break_below:  # Q30b: offesa, la trattativa si rompe e l'agente ricorda
            self.agent.relation = max(0, self.agent.relation + AGENT_RELATION_BROKEN)
            self.state = NegotiationState.BROKEN
        elif fee >= self.floor:
            self._close(Terms(fee=min(fee, ask.fee), bonus=self.bonus))
        else:
            midpoint = math.ceil((fee + ask.fee) / 2)
            self.counter = Terms(fee=min(ask.fee, max(self.floor, midpoint)), bonus=self.bonus)
            self.state = NegotiationState.COUNTERED
        return self.state

    def accept_counter(self) -> Terms:
        self._require(NegotiationState.COUNTERED)
        assert self.counter is not None
        return self._close(self.counter)

    def refuse(self) -> None:
        """Si ritira dalla trattativa (dalla richiesta o dalla controfferta): nessun costo."""
        if self.is_closed:
            raise ValueError("trattativa già conclusa")
        self.state = NegotiationState.REFUSED

    # ---------------------------------------------------------------- interni
    def _require(self, state: NegotiationState) -> None:
        if self.state is not state:
            raise ValueError(f"mossa non valida: la trattativa è «{self.state.value}»")

    def _close(self, terms: Terms) -> Terms:
        self.terms = terms
        self.state = NegotiationState.ACCEPTED
        return terms
