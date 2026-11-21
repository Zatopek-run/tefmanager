"""Finanze dettagliate (PIANOLAVORO D.3). Nessuna dipendenza da Qt e **nessuna estrazione dall'RNG**.

- **Bilancio mensile:** ogni `MONTH_WEEKS` (4) settimane il tick chiude un mese (`close_month_if_due`) e ne ricava il resoconto dal
  libro mastro (`state.transactions`): entrate e uscite per categoria. Il capitale iniziale non conta come entrata d'esercizio.
- **Quote tesserati:** piene da `MEMBER_FEES_FULL_ROSTER` atleti in su, proporzionali sotto (`member_fees_income`, Q32c).
- **Merchandising:** incasso settimanale in funzione dei fan della Prima Squadra e del prestigio (`merchandising_income`).
- **Sponsor con obiettivo:** chiudere la stagione fuori dai primi N della lega (`SPONSOR_TOP_N_BY_TIER`, per livello) taglia lo sponsor società della
  stagione dopo del `SPONSOR_MISS_PENALTY` (`sponsor_cut_active`, letto dal verdetto dell'ultima stagione: nessun dato in più da salvare).
- **Diritti TV:** solo per i meeting in casa del livello Internazionale (`tv_rights_income`).
"""

from __future__ import annotations

from typing import Dict, List

from models.entities import (
    MAX_MONTHLY_REPORTS,
    MEMBER_FEES_FULL_ROSTER,
    MERCH_FANS_DIVISOR,
    MERCH_PRESTIGE_DIVISOR,
    MONTH_WEEKS,
    SPONSOR_MISS_PENALTY,
    SPONSOR_TOP_N_BY_TIER,
    TV_RIGHTS_PER_HOME_MEET,
    CompetitionTier,
    GameState,
    MonthlyReport,
)

CATEGORY_NOT_OPERATING = "Capitale"  # il fondo iniziale non è un incasso d'esercizio


def month_bounds(week: int) -> tuple[int, int]:
    """Prima e ultima settimana del mese che contiene `week` (le settimane sono continue, i mesi da 4)."""
    first = ((week - 1) // MONTH_WEEKS) * MONTH_WEEKS + 1
    return first, first + MONTH_WEEKS - 1


def build_monthly_report(state: GameState, first_week: int, last_week: int) -> MonthlyReport:
    """Resoconto delle settimane `first_week`..`last_week` dal libro mastro, per categoria; `budget_end` = saldo di adesso."""
    income: Dict[str, int] = {}
    expenses: Dict[str, int] = {}
    for tx in state.transactions:
        if not (first_week <= tx.week <= last_week) or tx.category == CATEGORY_NOT_OPERATING:
            continue
        if tx.amount >= 0:
            income[tx.category] = income.get(tx.category, 0) + tx.amount
        else:
            expenses[tx.category] = expenses.get(tx.category, 0) - tx.amount
    return MonthlyReport(
        season=(first_week - 1) // state.season_length + 1,
        month=((first_week - 1) % state.season_length) // MONTH_WEEKS + 1,
        first_week=first_week,
        last_week=last_week,
        income=income,
        expenses=expenses,
        budget_end=state.budget,
    )


def close_month_if_due(state: GameState) -> bool:
    """Da chiamare a fine tick, con la settimana già incrementata: se è cominciato un nuovo mese chiude quello appena finito.

    Idempotente (non chiude due volte lo stesso mese). Tiene al più `MAX_MONTHLY_REPORTS` resoconti, il più recente in testa.
    """
    if state.week <= MONTH_WEEKS or (state.week - 1) % MONTH_WEEKS != 0:
        return False
    first, last = state.week - MONTH_WEEKS, state.week - 1
    if state.monthly_reports and state.monthly_reports[0].last_week >= last:
        return False
    state.monthly_reports.insert(0, build_monthly_report(state, first, last))
    del state.monthly_reports[MAX_MONTHLY_REPORTS:]
    return True


def merchandising_income(state: GameState) -> int:
    """Incasso settimanale dalle magliette: fan della Prima Squadra ÷ 40 + prestigio ÷ 20 (0 a inizio partita)."""
    fans = sum(a.fans for a in state.main_squad)
    return fans // MERCH_FANS_DIVISOR + max(0, state.prestige) // MERCH_PRESTIGE_DIVISOR


def member_fees_income(state: GameState) -> int:
    """Quote tesserati settimanali (Q32c): la quota piena da `MEMBER_FEES_FULL_ROSTER` atleti in su, proporzionale sotto, 0 a società vuota."""
    members = len(state.athletes)
    if members >= MEMBER_FEES_FULL_ROSTER:
        return state.member_fees_weekly
    return state.member_fees_weekly * members // MEMBER_FEES_FULL_ROSTER


def sponsor_top_n(tier: CompetitionTier) -> int:
    """Posto massimo in lega che tiene lo sponsor intero, per livello (`SPONSOR_TOP_N_BY_TIER`, Q31b)."""
    return SPONSOR_TOP_N_BY_TIER[tier]


def sponsor_cut_active(state: GameState) -> bool:
    """Lo sponsor società è tagliato se l'ultima stagione è finita fuori dai primi N della lega **del suo livello**.
    Non dopo la stagione di fondazione (Q32): una società nata senza atleti non è «sotto obiettivo»."""
    if not state.season_history:
        return False
    last = state.season_history[0]
    return last.placement > sponsor_top_n(last.tier) and not state.is_foundation(last.season)


def sponsor_target(state: GameState) -> int:
    """Il «primi N» da citare nei messaggi: quello del livello dell'ultima stagione chiusa (0 senza storia)."""
    return sponsor_top_n(state.season_history[0].tier) if state.season_history else 0


def sponsor_after_cut(state: GameState, sponsor: int) -> tuple[int, int]:
    """(sponsor dopo l'eventuale taglio, importo tagliato)."""
    if not sponsor_cut_active(state):
        return sponsor, 0
    cut = round(sponsor * SPONSOR_MISS_PENALTY)
    return sponsor - cut, cut


def tv_rights_income(state: GameState, is_home: bool) -> int:
    """Diritti TV di un meeting: solo in casa e solo nel livello Internazionale."""
    return TV_RIGHTS_PER_HOME_MEET if is_home and state.tier == CompetitionTier.INTERNAZIONALE else 0


def recent_reports(state: GameState, count: int) -> List[MonthlyReport]:
    """Gli ultimi `count` mesi in ordine cronologico (il più vecchio per primo), per i grafici."""
    return list(reversed(state.monthly_reports[:count]))
